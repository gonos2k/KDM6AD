#!/usr/bin/env python3
"""Bounded production-reader verification and full-audit summary importer.

The default run samples the exact pixels returned by the current production
``read_ko_slot(stride=16)`` and ``read_fd_slot(stride=8)`` calls.  Its second
decode is independent word arithmetic: the old ``&8191``/``>>13`` equations
are a counterfactual, while ``valid_bits``/``>>14`` plus the finite-positive
radiance QC is the current contract under test. ``--full-raster-input`` only
summarizes an already completed full-raster audit; it never reruns that
artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

_ORACLE = Path(__file__).resolve().parents[1]
if str(_ORACLE) not in sys.path:
    sys.path.insert(0, str(_ORACLE))

import netCDF4  # noqa: E402
from kdm6.obs import gk2a_l1b as ko_reader  # noqa: E402
from kdm6.obs import gk2a_l1b_fd as fd_reader  # noqa: E402
from kdm6.obs.gk2a_l1b import (  # noqa: E402
    AMI_CHANNELS, IR_CHANNELS, ko_grid_latlon, load_cal_table,
    read_ko_slot, slot_files,
)
from kdm6.obs.gk2a_l1b_fd import (  # noqa: E402
    _CAL_ATTRS, _GEO_ATTRS, fd_slot_files, find_domain_window,
    geos_latlon, read_fd_slot,
)

KO_TS = "202507190000"
FD_TS = "202507190100"
BBOX = (31.0, 45.0, 118.0, 134.6)
CAL_KEYS = tuple(_CAL_ATTRS)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def scalar(x: Any) -> float:
    return float(x)


def cal_equal(ds: netCDF4.Dataset, cal: dict[str, Any]) -> bool:
    if not all(k in ds.ncattrs() for k in CAL_KEYS):
        return False
    try:
        return all(scalar(ds.getncattr(k)) == scalar(cal[k]) for k in CAL_KEYS)
    except (TypeError, ValueError, KeyError):
        return False


def file_info(path: Path, source: str, channel: str, timestamp: str,
              cal: dict[str, Any]) -> dict[str, Any]:
    with netCDF4.Dataset(str(path), "r") as ds:
        var = ds.variables["image_pixel_values"]
        vb = int(var.getncattr("number_of_valid_bits_per_pixel"))
        va, ga = set(var.ncattrs()), set(ds.ncattrs())
        dqf = (int(var.getncattr("number_of_data_quality_flag_bits_per_pixel"))
               if "number_of_data_quality_flag_bits_per_pixel" in va else None)
        embedded = cal_equal(ds, cal) if source == "FD" else None
        dtype, shape = str(np.dtype(var.dtype)), [int(n) for n in var.shape]
    digest = sha256(path)
    return {
        "source": source, "channel": channel, "timestamp": timestamp,
        "basename": path.name, "size_bytes": path.stat().st_size,
        "sha256": digest, "sha256_32": digest[:32], "dtype": dtype,
        "shape": shape, "valid_bits": vb,
        "valid_bits_location": "image_pixel_values variable attribute",
        "global_valid_bits_present": "number_of_valid_bits_per_pixel" in ga,
        "variable_dqf_bits": dqf,
        "embedded_calibration_matches_external": embedded,
    }


def sampled_raw(path: Path, rows: np.ndarray, cols: np.ndarray,
                chunk_rows: int) -> tuple[np.ndarray, np.ndarray, int]:
    raw_parts, mask_parts = [], []
    with netCDF4.Dataset(str(path), "r") as ds:
        var = ds.variables["image_pixel_values"]
        if np.dtype(var.dtype) != np.dtype(np.uint16):
            raise ValueError(f"{path.name}: image_pixel_values must be uint16")
        vb = int(var.getncattr("number_of_valid_bits_per_pixel"))
        for start in range(0, rows.size, chunk_rows):
            stop = min(rows.size, start + chunk_rows)
            selected_rows = rows[start:stop]
            first, last = int(selected_rows[0]), int(selected_rows[-1]) + 1
            block_ma = np.ma.asarray(var[first:last, :])
            block_mask = np.ma.getmaskarray(block_ma)
            block = np.asarray(np.ma.filled(block_ma, 0), dtype=np.uint16)
            local = selected_rows - first
            raw_parts.append(block[local][:, cols].reshape(-1))
            mask_parts.append(block_mask[local][:, cols].reshape(-1))
    empty_raw, empty_mask = np.empty(0, dtype=np.uint16), np.empty(0, dtype=bool)
    return (np.concatenate(raw_parts) if raw_parts else empty_raw,
            np.concatenate(mask_parts) if mask_parts else empty_mask, vb)


def independent_words(raw: np.ndarray, vb: int, missing: np.ndarray
                      ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    old_dn = (raw & np.uint16(8191)).astype(np.float64)
    old_q = ((raw >> np.uint16(13)) & np.uint16(3)).astype(np.float64)
    new_dn = (raw & np.uint16((1 << vb) - 1)).astype(np.float64)
    new_q = ((raw >> np.uint16(14)) & np.uint16(3)).astype(np.float64)
    return old_dn, np.where(missing, 1.0, old_q), new_dn, np.where(missing, 1.0, new_q)


def independent_radiance_ok(dn: np.ndarray, cal: dict[str, Any]) -> np.ndarray:
    """Independent finite-positive radiance predicate for current-QC checks."""
    gain, offset = scalar(cal["DN_to_Radiance_Gain"]), scalar(cal["DN_to_Radiance_Offset"])
    with np.errstate(over="ignore", invalid="ignore"):
        radiance = offset + gain * dn
    return np.isfinite(radiance) & (radiance > 0.0)


def independent_bt(dn: np.ndarray, cal: dict[str, Any], *, historical: bool = False
                   ) -> np.ndarray:
    """Independent BT arithmetic; ``historical`` retains the old clip behavior."""
    gain, offset = scalar(cal["DN_to_Radiance_Gain"]), scalar(cal["DN_to_Radiance_Offset"])
    wave = scalar(cal["channel_center_wavelength"])
    h, c, k = (scalar(cal[x]) for x in ("Plank_constant_h", "light_speed", "Boltzmann_constant_k"))
    with np.errstate(over="ignore", invalid="ignore"):
        rad = offset + gain * dn
    sigma = (10000.0 / wave) * 100.0
    if historical:
        # Preserve the bit-only historical counterfactual: its old decoder
        # clipped nonpositive radiance and left DQF unchanged.
        radiance_ok = np.ones(rad.shape, dtype=bool)
        ls = np.clip(rad * 1.0e-3 / 100.0, 1.0e-30, None)
    else:
        radiance_ok = np.isfinite(rad) & (rad > 0.0)
        safe_rad = np.where(radiance_ok, rad, 1.0)
        ls = np.clip(safe_rad * 1.0e-3 / 100.0, 1.0e-30, None)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        teff = h * c * sigma / k / np.log((2.0 * h * c * c * sigma ** 3) / ls + 1.0)
        tbb = (scalar(cal["Teff_to_Tbb_c0"])
               + scalar(cal["Teff_to_Tbb_c1"]) * teff
               + scalar(cal["Teff_to_Tbb_c2"]) * teff * teff)
    if historical:
        return tbb
    if not np.isfinite(tbb[radiance_ok]).all():
        raise ValueError("independent AMI calibration yields non-finite brightness temperature")
    if not (tbb[radiance_ok] > 0.0).all():
        raise ValueError("independent AMI calibration yields non-positive brightness temperature")
    return np.where(radiance_ok, tbb, 0.0)


def stats(delta: np.ndarray) -> list[Any]:
    """Return [count, mean_signed, mean_abs, RMSE, max_abs] in kelvin."""
    if delta.size == 0:
        return [0, None, None, None, None]
    d = np.asarray(delta, dtype=np.float64)
    return [int(d.size), float(d.mean()), float(np.abs(d).mean()),
            float(np.sqrt(np.mean(d * d))), float(np.abs(d).max())]


def counts(q: np.ndarray) -> list[int]:
    return [int(np.count_nonzero(q == i)) for i in range(4)]


def selection(source: str, files: list[Path], stride: int) -> dict[str, Any]:
    with netCDF4.Dataset(str(files[0]), "r") as ds:
        if source == "KO":
            attrs = {a: ds.getncattr(a) for a in ds.ncattrs()}
            ny, nx = (int(n) for n in ds.variables["image_pixel_values"].shape)
            rows, cols = (np.arange(stride // 2, n, stride, dtype=np.int64)
                          for n in (ny, nx))
            lat, lon = ko_grid_latlon(attrs)
            lat_s, lon_s = lat[rows[:, None], cols[None, :]], lon[rows[:, None], cols[None, :]]
            domain = {"kind": "full KO raster", "raster_shape": [ny, nx],
                      "window_line_column_exclusive": None}
        else:
            g = {a: float(ds.getncattr(a)) for a in _GEO_ATTRS}
            n = int(ds.dimensions["dim_image_y"].size)
            win = find_domain_window(g, bbox=BBOX, n=n)
            l0, l1, c0, c1 = win
            rows = np.arange(l0 + stride // 2, l1, stride, dtype=np.int64)
            cols = np.arange(c0 + stride // 2, c1, stride, dtype=np.int64)
            lines, columns = np.meshgrid(rows.astype(float), cols.astype(float), indexing="ij")
            lat_s, lon_s = geos_latlon(lines, columns, g)
            domain = {"kind": "default read_fd_slot ROI within FD raster",
                      "raster_shape": [n, n], "bbox_lat_lon": list(BBOX),
                      "window_line_column_exclusive": list(win)}
    flat_lat, flat_lon = lat_s.reshape(-1), lon_s.reshape(-1)
    keep = np.isfinite(flat_lat) & np.isfinite(flat_lon)
    domain.update({"stride_pixels": stride, "row_start_in_selection": stride // 2,
                   "column_start_in_selection": stride // 2, "order": "row-major",
                   "selected_count_before_finite_coordinate_filter": int(keep.size),
                   "finite_coordinate_selected_count": int(keep.sum()),
                   "nonfinite_coordinate_selected_count": int((~keep).sum()),
                   "selected_shape": [int(rows.size), int(cols.size)]})
    return {"rows": rows, "cols": cols, "keep": keep,
            "coordinates": (flat_lat, flat_lon), "domain": domain}


def sample_source(source: str, files: list[Path], timestamp: str, cal_table: dict[str, Any],
                  payload: Any, sel: dict[str, Any], chunk_rows: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records, rows = [], {}
    keep = sel["keep"]
    exp_lat, exp_lon = (a[keep] for a in sel["coordinates"])
    prod_lat = payload.lat.detach().cpu().numpy()
    prod_lon = payload.lon.detach().cpu().numpy()
    coordinate_match = (np.array_equal(prod_lat, exp_lat) and np.array_equal(prod_lon, exp_lon))
    for path in files:
        channel = path.name.split("_ami_le1b_", 1)[1].split("_", 1)[0]
        cal = cal_table["channels"][channel]
        info = file_info(path, source, channel, timestamp, cal)
        raw, missing, vb = sampled_raw(path, sel["rows"], sel["cols"], chunk_rows)
        old_dn, old_q, new_dn, new_q = independent_words(raw, vb, missing)
        new_radiance_ok = independent_radiance_ok(new_dn, cal)
        new_q = np.where((~new_radiance_ok) & (new_q == 0.0), 3.0, new_q)
        finite_old_q, finite_new_q = old_q[keep], new_q[keep]
        old_valid, new_valid = finite_old_q == 0, finite_new_q == 0
        old_bt = independent_bt(old_dn[keep], cal, historical=True)
        new_bt = independent_bt(new_dn[keep], cal)
        j = AMI_CHANNELS.index(channel)
        prod_bt = payload.bt[:, j].detach().cpu().numpy()
        prod_q = payload.obs_quality[:, j].detach().cpu().numpy()
        confusion = np.zeros((4, 4), dtype=np.int64)
        for oq, nq in zip(finite_old_q.astype(int), finite_new_q.astype(int)):
            confusion[oq, nq] += 1
        delta = new_bt - old_bt
        rows[channel] = {
            "valid_bits": vb, "raw_selected": int(raw.size),
            "finite_coordinate_selected": int(keep.sum()),
            "netcdf_masked_selected": int(missing.sum()),
            "old_dqf_counts_finite": counts(finite_old_q),
            "correct_dqf_counts_finite": counts(finite_new_q),
            "old_usable_finite": int(old_valid.sum()), "correct_usable_finite": int(new_valid.sum()),
            "newly_accepted": int((~old_valid & new_valid).sum()),
            "newly_rejected": int((old_valid & ~new_valid).sum()),
            "dqf_confusion_old_rows_correct_columns": confusion.tolist(),
            "bt_correct_minus_old_K": {
                "metric_order": ["n", "mean_signed", "mean_abs", "rmse", "max_abs"],
                "all": stats(delta), "common_usable": stats(delta[old_valid & new_valid]),
                "newly_usable": stats(delta[~old_valid & new_valid]),
            },
            "production_vs_independent_correct": {
                "q_exact": bool(np.array_equal(prod_q, finite_new_q)),
                "bt_exact_count": int(np.count_nonzero(prod_bt == new_bt)),
                "bt_max_abs_error_K": float(np.max(np.abs(prod_bt - new_bt))) if new_bt.size else 0.0,
                "bt_max_ulp": int(np.max(np.abs(prod_bt.view(np.int64) - new_bt.view(np.int64)))) if new_bt.size else 0,
            },
        }
        records.append(info)
    return ({"timestamp": timestamp,
             "reader_call": ("read_ko_slot(files, cal_table, stride=16)" if source == "KO"
                              else "read_fd_slot(files, stride=8) [default bbox/ROI]"),
             "payload_n_obs": int(payload.n_obs), "domain": sel["domain"],
             "coordinate_match": coordinate_match, "channels": rows}, records)


def full_raster_summary(path: Path) -> dict[str, Any]:
    """Redact and compact the immutable full-raster result; do not recalculate it."""
    original = json.loads(path.read_text())
    out: dict[str, Any] = {
        "artifact_role": "full_raster_audit_summary",
        "computation": {"mode": "redacted import of immutable completed audit",
                         "full_raster_recomputed": False},
        "derived_from_immutable_artifact": {"basename": path.name, "sha256": sha256(path)},
        "original_full_raster_script": {"basename": Path(original["script"]).name,
                                         "sha256": sha256(Path(original["script"]))},
        "contract": original["contract"],
        "scope": {"domain": "full raster; NetCDF-unmasked pixels intersect finite geolocation",
                   "timestamps": {s: original["representative_slots"][s]["timestamp"] for s in ("KO", "FD")},
                   "channels": list(AMI_CHANNELS), "source_paths_redacted": True},
        "sources": {"format": original["sources"]}, "files": {"KO": [], "FD": []},
        "coordinate_method": {s: original["channel_comparison"][s][AMI_CHANNELS[0]]["coordinate_method"]
                              for s in ("KO", "FD")},
        "channel_columns": [
            "channel", "valid_bits", "dtype", "shape_y", "shape_x", "total_pixels",
            "netcdf_unmasked", "netcdf_masked", "finite_coordinates", "nonfinite_coordinates",
            "old_valid_finite", "correct_valid_finite", "newly_accepted_finite", "newly_rejected_finite",
            "old_valid_unmasked", "correct_valid_unmasked", "newly_accepted_unmasked", "newly_rejected_unmasked",
            "old_dqf_finite", "correct_dqf_finite", "dqf_confusion_finite", "dqf_confusion_unmasked",
            "bt_common_usable", "bt_newly_usable",
        ],
        "bt_metric_order": ["n", "old_mean_K", "new_mean_K", "mean_signed_K", "mean_abs_K", "rmse_K", "max_abs_K"],
        "channels": {"KO": [], "FD": []},
    }
    for source in ("KO", "FD"):
        for channel, entry in sorted(original[source.lower() + "_files"].items()):
            p = Path(entry["path"])
            out["files"][source].append({"channel": channel, "basename": p.name,
                "size_bytes": entry["size_bytes"], "sha256": entry["sha256"],
                "sha256_32": entry["sha256"][:32]})
            c = original["channel_comparison"][source][channel]
            common = c["bt_change_common_usable_new_minus_old"]
            newly = c["bt_change_newly_accepted_new_minus_old"]
            pick = lambda x: [x.get(k) for k in ("n", "old_mean_K", "new_mean_K",
                                                  "mean_signed_K", "mean_abs_K", "rmse_K", "max_abs_K")]
            y, x = c["shape"]
            out["channels"][source].append([
                channel, c["valid_bits"], c["dtype"], y, x, c["total_pixels"],
                c["netcdf_unmasked_pixels"], c["netcdf_masked_pixels"], c["finite_coordinate_pixels"],
                c["nonfinite_coordinate_pixels"], c["old_valid_pixels"], c["correct_valid_pixels"],
                c["newly_accepted_correct_only"], c["newly_rejected_old_only"],
                c["old_valid_all_netcdf_unmasked_pixels"], c["correct_valid_all_netcdf_unmasked_pixels"],
                c["newly_accepted_all_netcdf_unmasked_correct_only"], c["newly_rejected_all_netcdf_unmasked_old_only"],
                c["old_dqf_counts_0_1_2_3"], c["correct_dqf_counts_0_1_2_3"],
                c["dqf_confusion_rows_old_0_1_2_3_cols_correct_0_1_2_3"],
                c["dqf_confusion_all_netcdf_unmasked_rows_old_0_1_2_3_cols_correct_0_1_2_3"],
                pick(common), pick(newly),
            ])
    return out


def compact_sample(source: dict[str, Any]) -> dict[str, Any]:
    """Use one compact row per channel while retaining every sample metric."""
    columns = ["channel", "valid_bits", "raw_selected", "finite_coordinate_selected",
               "netcdf_masked_selected", "old_dqf_counts_finite", "correct_dqf_counts_finite",
               "old_usable_finite", "correct_usable_finite", "newly_accepted", "newly_rejected",
               "dqf_confusion_old_rows_correct_columns", "production_q_exact", "production_bt_exact_count",
               "production_bt_max_abs_error_K", "production_bt_max_ulp", "bt_all", "bt_common_usable",
               "bt_newly_usable"]
    rows = []
    for channel in IR_CHANNELS:
        r = source["channels"][channel]
        rows.append([channel, r["valid_bits"], r["raw_selected"], r["finite_coordinate_selected"],
                     r["netcdf_masked_selected"], r["old_dqf_counts_finite"], r["correct_dqf_counts_finite"],
                     r["old_usable_finite"], r["correct_usable_finite"], r["newly_accepted"],
                     r["newly_rejected"], r["dqf_confusion_old_rows_correct_columns"],
                     r["production_vs_independent_correct"]["q_exact"],
                     r["production_vs_independent_correct"]["bt_exact_count"],
                     r["production_vs_independent_correct"]["bt_max_abs_error_K"],
                     r["production_vs_independent_correct"]["bt_max_ulp"],
                     r["bt_correct_minus_old_K"]["all"],
                     r["bt_correct_minus_old_K"]["common_usable"],
                     r["bt_correct_minus_old_K"]["newly_usable"]])
    return {"timestamp": source["timestamp"], "reader_call": source["reader_call"],
            "payload_n_obs": source["payload_n_obs"], "domain": source["domain"],
            "coordinate_match": source["coordinate_match"], "channel_columns": columns,
            "bt_metric_order": ["n", "mean_signed", "mean_abs", "rmse", "max_abs"],
            "channels": rows}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ko-root", type=Path)
    ap.add_argument("--fd-root", type=Path)
    ap.add_argument("--calibration", type=Path)
    ap.add_argument("--ko-timestamp", default=KO_TS)
    ap.add_argument("--fd-timestamp", default=FD_TS)
    ap.add_argument("--chunk-rows", type=int, default=32)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--full-raster-input", type=Path,
                    help="existing full-raster JSON to compact; no rerun")
    ap.add_argument("--full-raster-output", type=Path)
    args = ap.parse_args()
    if args.full_raster_input:
        if not args.full_raster_output:
            ap.error("--full-raster-output is required with --full-raster-input")
        args.full_raster_output.parent.mkdir(parents=True, exist_ok=True)
        args.full_raster_output.write_text(json.dumps(full_raster_summary(args.full_raster_input),
                                                       sort_keys=True, separators=(",", ":")) + "\n")
    if not (args.ko_root and args.fd_root and args.calibration and args.output):
        if args.full_raster_input:
            return 0
        ap.error("sample mode requires --ko-root, --fd-root, --calibration and --output")
    if args.chunk_rows < 1:
        ap.error("--chunk-rows must be positive")
    cal = load_cal_table(args.calibration)
    ko_files = slot_files(args.ko_root, args.ko_timestamp, channels=IR_CHANNELS)
    fd_files = fd_slot_files(args.fd_root, args.fd_timestamp, IR_CHANNELS)
    ko_payload = read_ko_slot(ko_files, cal, stride=16)
    fd_payload = read_fd_slot(fd_files, stride=8)
    ko, ko_records = sample_source("KO", ko_files, args.ko_timestamp, cal, ko_payload,
                                    selection("KO", ko_files, 16), args.chunk_rows)
    fd, fd_records = sample_source("FD", fd_files, args.fd_timestamp, cal, fd_payload,
                                    selection("FD", fd_files, 8), args.chunk_rows)
    records = ko_records + fd_records
    result = {"artifact_role": "production_sample_verification",
              "comparison_role": "current_production_reader_vs_independent_contract_decode",
              "old_equations_are_counterfactual": True,
              "current_quality_contract": "embedded DQF + NetCDF mask + finite-positive radiance",
              "current_bt_contract": "positive finite Kelvin for valid radiance; zero unusable placeholder otherwise",
              "historical_bt_contract": "old radiance clipping retained without radiance QC",
              "scope": {"channels": list(IR_CHANNELS), "ko_timestamp": args.ko_timestamp,
                         "fd_timestamp": args.fd_timestamp, "read_only": True,
                         "independent_read_chunk_rows": args.chunk_rows,
                         "no_full_raster_independent_read": True},
              "valid_bits": {"attribute": "number_of_valid_bits_per_pixel",
                  "location": "image_pixel_values variable attribute",
                  "by_source": {s: {r["channel"]: r["valid_bits"] for r in records if r["source"] == s}
                                for s in ("KO", "FD")},
                  "global_attribute_present": {s: sorted({r["global_valid_bits_present"] for r in records if r["source"] == s})
                                                for s in ("KO", "FD")},
                  "global_helper_fallback_used": False},
              "calibration": {"KO": "external table basename: gk2a_ami_cal_202507190000.json",
                  "FD": "embedded per-file attributes", "FD_embedded_matches_external": all(
                      r["embedded_calibration_matches_external"] for r in records if r["source"] == "FD")},
              "code_provenance": {
                  "gk2a_l1b.py": {"source_path": "oracle/kdm6/obs/gk2a_l1b.py",
                                  "sha256": sha256(Path(ko_reader.__file__).resolve())},
                  "gk2a_l1b_fd.py": {"source_path": "oracle/kdm6/obs/gk2a_l1b_fd.py",
                                     "sha256": sha256(Path(fd_reader.__file__).resolve())},
                  "calibration_json": {"basename": args.calibration.name,
                                        "sha256": sha256(args.calibration.resolve())},
              },
              "files": {"KO": ko_records, "FD": fd_records},
              "sources": {"KO": compact_sample(ko), "FD": compact_sample(fd)},
              "format_sources": {"satpy_ami_l1b": "https://satpy.readthedocs.io/en/v0.57.0/_modules/satpy/readers/ami_l1b.html#AMIFileHandler.get_dataset",
                                 "kim_2021_table2": "https://doi.org/10.3390/rs13071303"}}
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"))
    result["sample_result_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    result["source_sha256"] = sha256(Path(__file__).resolve())
    result["source_path"] = "oracle/scripts/measure_ami_bits.py"
    result["invocation"] = "python oracle/scripts/measure_ami_bits.py --ko-root REDACTED --fd-root REDACTED --calibration REDACTED --output REDACTED"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps({"output": str(args.output), "sample_result_sha256": result["sample_result_sha256"],
                      "source_sha256": result["source_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
