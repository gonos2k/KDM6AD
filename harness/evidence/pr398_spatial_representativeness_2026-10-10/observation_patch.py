#!/usr/bin/env python3
"""Read the predeclared AMI 5x5 patch and VIIRS samples in the native 3x3 center bounds.

The default mode writes a source-bound preflight without reading image samples.
One extraction requires an existing preflight and ``--extract-after-preflight``.
It does not download data or call the native model, M, H, RTTOV, or the optimizer.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "oracle"))

from kdm6.obs.gk2a_l1b import (  # noqa: E402
    AMI_CHANNELS, dn_to_bt, load_cal_table, unpack_ami_word,
)
from kdm6.obs.gk2a_l1b_la import read_la_slot  # noqa: E402

EVIDENCE = ROOT / "harness/evidence/pr398_spatial_representativeness_2026-10-10"
COMMON_PREDECLARED = EVIDENCE / "PREDECLARED.json"
NATIVE_GEOGRAPHY = EVIDENCE / "NATIVE_PATCH_GEOGRAPHY.json"
NATIVE_PATCH_PLAN = EVIDENCE / "NATIVE_PATCH_v2.json"
PATCH_PREFLIGHT = EVIDENCE / "PATCH_PREFLIGHT_v3.json"
OBSERVATION_PATCH = EVIDENCE / "OBSERVATION_PATCH.json"
AMI_SLOT_DIR = Path("/private/tmp/KDM6AD-case-readiness-20261007/AMI_LA_202507190556")
AMI_SLOT_RECEIPT = AMI_SLOT_DIR / "slot_receipt.json"
OBSERVATION_RECEIPT = ROOT / "harness/evidence/pr395_observation_matchup_2026-10-10/RECEIPT.json"
AMI_CANDIDATE = ROOT / "harness/evidence/VIIRS_AMI_candidate_result_2026-10-07.json"
CALIBRATION = ROOT / "oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json"
PATCH_CHANNELS_1BASED = tuple(range(10, 17))
PATCH_CHANNELS = tuple(AMI_CHANNELS[ch - 1] for ch in PATCH_CHANNELS_1BASED)
VIIRS_PHASE = Path("/private/tmp/KDM6AD-time-contract-20261007/raw/JRR-CloudPhase_v3r2_j01_s202507190555475_e202507190557102_c202507190621171.nc")
VIIRS_GMTCO = Path("/private/tmp/KDM6AD-viirs-context-20261007/raw/GMTCO_j01_d20250719_t0555475_e0557102_b39724_c20250719061432885000_oeac_ops.h5")
VIIRS_GEOMETRY_RESULT = ROOT / "harness/evidence/VIIRS_geometry_result_2026-10-07.json"
VIIRS_ANGLE_NAMES = ("SatelliteZenithAngle", "SatelliteAzimuthAngle",
                     "SolarZenithAngle", "SolarAzimuthAngle")
PRIVATE_DIR = ROOT / "graphify-out/pr398-spatial-representativeness-2026-10-10/private"
CANONICAL_PRIVATE_DIR = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/pr398_sensitivity_20261010")
PRIVATE_NPZ = CANONICAL_PRIVATE_DIR / "observation_patch_ami5x5_viirs_nativebbox.npz"
AMI_TABLE = EVIDENCE / "AMI_PATCH_5x5.csv"
AMI_CHANNEL_SUMMARY = EVIDENCE / "AMI_PATCH_CHANNEL_SUMMARY.csv"
VIIRS_COUNTS = EVIDENCE / "VIIRS_PATCH_CATEGORY_COUNTS.csv"
RUN_LOCK = PRIVATE_DIR / "PATCH_STARTED_ONCE.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def source_hashes() -> dict[str, str]:
    paths = {
        "observation_patch": Path(__file__).resolve(),
        "gk2a_l1b_la": ROOT / "oracle/kdm6/obs/gk2a_l1b_la.py",
        "gk2a_l1b": ROOT / "oracle/kdm6/obs/gk2a_l1b.py",
        "gk2a_l1b_fd": ROOT / "oracle/kdm6/obs/gk2a_l1b_fd.py",
        "obs_ingest": ROOT / "oracle/kdm6/obs/obs_ingest.py",
        "ami_candidate_reader": ROOT / "harness/evidence/VIIRS_AMI_candidate_source_2026-10-07.py",
        "viirs_geometry_reader": ROOT / "harness/evidence/VIIRS_geometry_source_2026-10-07.py",
    }
    return {name: sha256(path) for name, path in paths.items()}


def write_exclusive_json(path: Path, value: dict, *, mode: int = 0o600) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("x") as f:
        f.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    path.chmod(mode)


def _predeclared_context() -> tuple[dict, dict, dict, dict, list[Path]]:
    pre = json.loads(COMMON_PREDECLARED.read_text())
    native = json.loads(NATIVE_GEOGRAPHY.read_text())
    observation = json.loads(OBSERVATION_RECEIPT.read_text())
    slot = json.loads(AMI_SLOT_RECEIPT.read_text())
    candidate = json.loads(AMI_CANDIDATE.read_text())
    geometry_result = json.loads(VIIRS_GEOMETRY_RESULT.read_text())
    if (pre.get("schema") != "pr398.fixed_candidate_spatial_diagnostic.v1"
            or pre.get("native", {}).get("center_j_i_zero_based") != [86, 48]
            or pre.get("native", {}).get("saved_frame_indices") != [1, 4, 6]
            or pre.get("ami", {}).get("fixed_center_row_col_zero_based") != [320, 48]
            or pre.get("ami", {}).get("rows") != [318, 319, 320, 321, 322]
            or pre.get("ami", {}).get("cols") != [46, 47, 48, 49, 50]
            or pre.get("ami", {}).get("channels_1based") != list(PATCH_CHANNELS_1BASED)
            or pre.get("no_M_H_or_optimization") is not True
            or pre.get("no_new_observation_or_model_acquisition") is not True
            or pre.get("no_candidate_replacement") is not True
            or pre.get("no_BT_averaging_as_radiance") is not True
            or pre.get("no_spatial_scatter_as_calibrated_R_or_sigma") is not True):
        raise ValueError("common PR398 spatial PREDECLARED contract is missing or changed")
    pre_sha = sha256(COMMON_PREDECLARED)
    if (native.get("schema") != "pr398_native_patch_geography_v1"
            or native.get("status") != "GEOMETRY_ONLY_SELECTED_COORDINATES"
            or native.get("common_predeclared_sha256") != pre_sha
            or native.get("no_M_H_or_optimization") is not True):
        raise ValueError("native georegion file is not the hash-bound geometry-only package")
    if (observation.get("physical_matchup_approved") is not False
            or observation.get("external_model_or_reanalysis_acquired") is not False
            or observation.get("fixed_candidate", {}).get("ami_row_col_zero_based") != [320, 48]
            or observation.get("fixed_candidate", {}).get("viirs_row_col_zero_based") != [205, 27]):
        raise ValueError("PR395 observation receipt no longer binds the fixed sample pair")
    if (slot.get("schema") != "gk2a_la_candidate_slot_v1"
            or slot.get("all_nine_requested_channels_present") is not True):
        raise ValueError("existing AMI slot receipt does not bind the nine-channel source slot")
    if candidate.get("ami_row_col_0based") != [320, 48]:
        raise ValueError("existing AMI candidate result moved from fixed row/column 320/48")
    receipt_source_hashes = observation.get("local_source_result_sha256", {})
    if (receipt_source_hashes.get("VIIRS_AMI_candidate_result_2026-10-07.json")
            != sha256(AMI_CANDIDATE)
            or receipt_source_hashes.get("VIIRS_geometry_result_2026-10-07.json")
            != sha256(VIIRS_GEOMETRY_RESULT)
            or geometry_result.get("geo_sha256")
            != observation.get("original_payloads", {}).get("viirs_gmtco_original", {}).get("sha256")
            or geometry_result.get("phase_sha256")
            != observation.get("original_payloads", {}).get("viirs_cloudphase_original", {}).get("sha256")):
        raise ValueError("retained VIIRS candidate/geolocation results differ from the source-bound receipt")
    files = [AMI_SLOT_DIR / entry["local_file"] for entry in slot.get("file_records", [])]
    if len(files) != 9:
        raise ValueError("existing AMI source inventory must list all nine LA files")
    return pre, native, observation, slot, files


def build_preflight() -> dict:
    if (PATCH_PREFLIGHT.exists() or OBSERVATION_PATCH.exists() or RUN_LOCK.exists()
            or PRIVATE_NPZ.exists()):
        raise FileExistsError("spatial patch preflight/output/lock already exists; no replacement or retry")
    pre, native, observation, slot, files = _predeclared_context()
    native_plan = json.loads(NATIVE_PATCH_PLAN.read_text())
    if (native_plan.get("schema") != "pr398_native_patch_plan_v2"
            or native_plan.get("status") != "PREDECLARED_NO_STATE_DIAGNOSTICS"
            or native_plan.get("common_predeclaration_sha256") != sha256(COMMON_PREDECLARED)
            or native_plan.get("geography_only_source", {}).get("sha256")
            != sha256(NATIVE_GEOGRAPHY)
            or native_plan.get("execution", {}).get("actual_arrays_read_at_predeclaration") is not False
            or native_plan.get("execution", {}).get("M_calls") != 0
            or native_plan.get("execution", {}).get("H_calls") != 0):
        raise ValueError("native patch plan is not a no-sample, geometry-bound PR398 plan")
    cal = json.loads(CALIBRATION.read_text())
    candidate = json.loads(AMI_CANDIDATE.read_text())
    geometry_result = json.loads(VIIRS_GEOMETRY_RESULT.read_text())
    expected_ami = {entry["local_file"]: entry["sha256"] for entry in slot["file_records"]}
    actual_ami = {p.name: sha256(p) for p in files}
    if expected_ami != actual_ami:
        raise ValueError("local AMI files differ from the existing retained slot receipt")
    observation_payloads = observation.get("original_payloads", {})
    phase_expected = observation_payloads.get("viirs_cloudphase_original", {}).get("sha256")
    geo_expected = observation_payloads.get("viirs_gmtco_original", {}).get("sha256")
    if sha256(VIIRS_PHASE) != phase_expected or sha256(VIIRS_GMTCO) != geo_expected:
        raise ValueError("local VIIRS products differ from their existing observation receipt hashes")
    if candidate.get("calibration_sha256") != sha256(CALIBRATION):
        raise ValueError("bundled AMI calibration table differs from the existing candidate result")
    if (observation.get("local_source_result_sha256", {}).get(
            "VIIRS_geometry_result_2026-10-07.json") != sha256(VIIRS_GEOMETRY_RESULT)
            or geometry_result.get("geo_sha256") != geo_expected
            or geometry_result.get("phase_sha256") != phase_expected):
        raise ValueError("existing VIIRS angle/geolocation receipt does not match retained raw products")

    # Header-only inspection records raw scaling/fill contracts without reading
    # any surrounding image samples.
    header_summary = {}
    for p in files:
        with netCDF4.Dataset(str(p)) as ds:
            var = ds.variables["image_pixel_values"]
            scale = float(var.getncattr("scale_factor")) if "scale_factor" in var.ncattrs() else 1.0
            offset = float(var.getncattr("add_offset")) if "add_offset" in var.ncattrs() else 0.0
            if scale != 1.0 or offset != 0.0:
                raise ValueError(f"{p.name}: nonidentity NetCDF auto-scale is unsupported by the pinned reader")
            header_summary[p.name] = {
                "shape": list(var.shape),
                "dtype": str(var.dtype),
                "channel_name": var.getncattr("channel_name"),
                "valid_bits": int(var.getncattr("number_of_valid_bits_per_pixel")),
                "dqf_bits": int(var.getncattr("number_of_data_quality_flag_bits_per_pixel")),
                "dqf_meaning": var.getncattr("data_quality_flag_meaning"),
                "fill_value": (int(var.getncattr("_FillValue"))
                               if "_FillValue" in var.ncattrs() else None),
                "missing_value": (int(var.getncattr("missing_value"))
                                  if "missing_value" in var.ncattrs() else None),
                "scale_factor": (float(var.getncattr("scale_factor"))
                                 if "scale_factor" in var.ncattrs() else None),
                "add_offset": (float(var.getncattr("add_offset"))
                               if "add_offset" in var.ncattrs() else None),
                "file_calibration_table_version": ds.getncattr("calibration_table_version"),
            }
    native_bounds = native["union_bounds_of_native_3x3_centers_only"]
    record = {
        "schema": "pr398_observation_patch_preflight_v1",
        "status": "READY_NO_SURROUNDING_PIXEL_VALUES_READ",
        "common_predeclared_sha256": sha256(COMMON_PREDECLARED),
        "native_geometry_sha256": sha256(NATIVE_GEOGRAPHY),
        "native_patch_plan_sha256": sha256(NATIVE_PATCH_PLAN),
        "native_bounds_from_3x3_centers_only": native_bounds,
        "selection_contract": pre["viirs"]["selection"],
        "AMI_patch": {
            "fixed_row_col_center_zero_based": [320, 48],
            "rows": pre["ami"]["rows"], "cols": pre["ami"]["cols"],
            "channels_1based": list(PATCH_CHANNELS_1BASED),
            "channels_names": list(PATCH_CHANNELS),
            "files_sha256": actual_ami,
            "header_contract": header_summary,
        },
        "VIIRS_sources": {
            "cloudphase_path": str(VIIRS_PHASE), "cloudphase_sha256": phase_expected,
            "gmtco_path": str(VIIRS_GMTCO), "gmtco_sha256": geo_expected,
            "geometry_result_sha256": sha256(VIIRS_GEOMETRY_RESULT),
            "cloudheight_patch": "unavailable; full source object was not downloaded/hash-verified; center value will not be extended",
        },
        "calibration": {
            "table_path": str(CALIBRATION), "table_sha256": sha256(CALIBRATION),
            "meta": cal.get("meta", {}),
            "2025_FD_SRF_version_verified": cal.get("meta", {}).get(
                "audited_pairing_reference", {}).get("2025_fd_srf_version_verified"),
            "radiance_semantics": "derived per sample from DN_to_Radiance_Offset + Gain*DN; not a spatially averaged BT converted to radiance",
        },
        "existing_receipts": {
            "observation_receipt_sha256": sha256(OBSERVATION_RECEIPT),
            "ami_slot_receipt_sha256": sha256(AMI_SLOT_RECEIPT),
            "candidate_result_sha256": sha256(AMI_CANDIDATE),
            "viirs_geometry_result_sha256": sha256(VIIRS_GEOMETRY_RESULT),
        },
        "canonical_private_npz_path": str(PRIVATE_NPZ),
        "reader_source_sha256": source_hashes(),
        "no_sample_values_inspected": True,
        "no_new_download_or_model_M_H": True,
    }
    write_exclusive_json(PATCH_PREFLIGHT, record)
    return record


def _counter(values) -> dict:
    counts = Counter(int(v) for v in np.asarray(values).reshape(-1))
    return {str(k): counts[k] for k in sorted(counts)}


def _write_csv_exclusive(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    if path.exists():
        raise FileExistsError(path)
    with path.open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o644)


def _atomic_npz(path: Path, arrays: dict[str, np.ndarray]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    if path.exists():
        raise FileExistsError(path)
    with tempfile.NamedTemporaryFile(prefix=".patch-", suffix=".npz", dir=path.parent,
                                     delete=False) as f:
        temp = Path(f.name)
    temp.chmod(0o600)
    try:
        with temp.open("wb") as f:
            np.savez_compressed(f, **arrays)
            f.flush()
            os.fsync(f.fileno())
        digest = sha256(temp)
        os.link(temp, path)
        path.chmod(0o600)
        temp.unlink()
        return digest
    except BaseException:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise


def extract_once(preflight: dict) -> dict:
    if (RUN_LOCK.exists() or OBSERVATION_PATCH.exists() or PRIVATE_NPZ.exists()
            or AMI_TABLE.exists() or AMI_CHANNEL_SUMMARY.exists() or VIIRS_COUNTS.exists()):
        raise FileExistsError("spatial patch extraction is one-shot and refuses replacement/retry")
    if (preflight.get("status") != "READY_NO_SURROUNDING_PIXEL_VALUES_READ"
            or sha256(PATCH_PREFLIGHT) != preflight.get("preflight_sha256")):
        raise ValueError("extraction requires the hash-bound preflight that predates sample reading")
    pre, native, observation, slot, ami_files = _predeclared_context()
    if (sha256(COMMON_PREDECLARED) != preflight["common_predeclared_sha256"]
            or sha256(NATIVE_GEOGRAPHY) != preflight["native_geometry_sha256"]):
        raise ValueError("common predeclaration/geographic bounds changed after preflight")
    if sha256(NATIVE_PATCH_PLAN) != preflight["native_patch_plan_sha256"]:
        raise ValueError("native patch plan changed after preflight")
    if {p.name: sha256(p) for p in ami_files} != preflight["AMI_patch"]["files_sha256"]:
        raise ValueError("AMI source files changed after header preflight")
    if sha256(VIIRS_PHASE) != preflight["VIIRS_sources"]["cloudphase_sha256"] or sha256(
            VIIRS_GMTCO) != preflight["VIIRS_sources"]["gmtco_sha256"]:
        raise ValueError("VIIRS source files changed after header preflight")
    if sha256(VIIRS_GEOMETRY_RESULT) != preflight["VIIRS_sources"]["geometry_result_sha256"]:
        raise ValueError("VIIRS geometry result changed after header preflight")
    if sha256(CALIBRATION) != preflight["calibration"]["table_sha256"]:
        raise ValueError("calibration table changed after preflight")
    if source_hashes() != preflight["reader_source_sha256"]:
        raise ValueError("observation reader or patch source changed after header preflight")

    PRIVATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    PRIVATE_DIR.chmod(0o700)
    fd = os.open(RUN_LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps({"status": "PATCH_EXTRACTION_STARTED_ONCE",
                            "preflight_sha256": sha256(PATCH_PREFLIGHT)}, sort_keys=True)+"\n")

    table = load_cal_table(CALIBRATION)
    la = read_la_slot(ami_files, table, stride=1)
    row_values = np.arange(318, 323, dtype=np.int64)
    col_values = np.arange(46, 51, dtype=np.int64)
    wanted = [(int(r), int(c)) for r in row_values for c in col_values]
    position = {(int(r), int(c)): i for i, (r, c) in enumerate(
        zip(la.pixel_rows.tolist(), la.pixel_cols.tolist()))}
    if any(rc not in position for rc in wanted):
        raise ValueError("authoritative LA reader omitted a fixed 5x5 pixel; aborting patch")
    select_indices = np.asarray([position[rc] for rc in wanted], dtype=np.int64)
    channel_names = list(la.metadata["channels"])
    chan_idx = [channel_names.index(ch) for ch in PATCH_CHANNELS]
    bt = la.payload.bt.numpy()[select_indices][:, chan_idx].reshape(5, 5, 7)
    dqf_reader = la.payload.obs_quality.numpy()[select_indices][:, chan_idx].reshape(5, 5, 7)
    coords = np.column_stack((la.payload.lat.numpy()[select_indices],
                              la.payload.lon.numpy()[select_indices])).reshape(5, 5, 2)

    raw_word = np.empty((5, 5, 7), dtype=np.uint16)
    raw_dn = np.empty((5, 5, 7), dtype=np.float64)
    raw_dqf = np.empty((5, 5, 7), dtype=np.float64)
    decoder_dqf = np.empty((5, 5, 7), dtype=np.float64)
    fill_mask = np.zeros((5, 5, 7), dtype=bool)
    invalid_radiance_mask = np.zeros((5, 5, 7), dtype=bool)
    radiance = np.full((5, 5, 7), np.nan, dtype=np.float64)
    bt_replay = np.full((5, 5, 7), np.nan, dtype=np.float64)
    files_by_name = {p.name.split("_le1b_", 1)[1].split("_la020ge_", 1)[0]: p
                     for p in ami_files}
    for j, ch in enumerate(PATCH_CHANNELS):
        file = files_by_name[ch]
        if sha256(file) != preflight["AMI_patch"]["files_sha256"][file.name]:
            raise ValueError(f"{file.name} changed before spatial sampling")
        with netCDF4.Dataset(str(file)) as ds:
            var = ds.variables["image_pixel_values"]
            var.set_auto_mask(True)
            var.set_auto_scale(False)
            raw_ma = var[318:323, 46:51]
            values = np.asarray(np.ma.getdata(raw_ma), dtype=np.uint16)
            fill = np.ma.getmaskarray(raw_ma)
            decode_words = np.where(fill, 0, values).astype(np.uint16)
            valid_bits = int(var.getncattr("number_of_valid_bits_per_pixel"))
            dn, q_raw = unpack_ami_word(decode_words, valid_bits)
            bt_decoded, q_decoded = dn_to_bt(decode_words, table["channels"][ch],
                                             valid_bits=valid_bits)
            effective_dqf = np.where(fill, 1.0, q_decoded)
            if (not np.array_equal(effective_dqf, dqf_reader[:, :, j])
                    or not np.allclose(bt_decoded, bt[:, :, j], rtol=0.0, atol=0.0)):
                raise ValueError(f"{ch}: direct packed-word decode differs from the authoritative LA reader")
            cal = table["channels"][ch]
            rad = float(cal["DN_to_Radiance_Offset"]) + float(
                cal["DN_to_Radiance_Gain"]) * dn
            rad = np.where(fill, np.nan, rad)
            invalid_rad = (~fill) & (~np.isfinite(rad) | (rad <= 0.0))
            raw_word[:, :, j] = values
            raw_dn[:, :, j] = dn
            raw_dqf[:, :, j] = np.where(fill, -1.0, q_raw)
            decoder_dqf[:, :, j] = q_decoded
            fill_mask[:, :, j] = fill
            invalid_radiance_mask[:, :, j] = invalid_rad
            radiance[:, :, j] = rad
            bt_replay[:, :, j] = bt_decoded
        if sha256(file) != preflight["AMI_patch"]["files_sha256"][file.name]:
            raise ValueError(f"{file.name} changed during spatial sampling")

    candidate = json.loads(AMI_CANDIDATE.read_text())
    center_candidate_row, center_candidate_col = candidate["ami_row_col_0based"]
    if [center_candidate_row, center_candidate_col] != [320, 48]:
        raise ValueError("candidate result no longer identifies the fixed AMI center")
    candidate_channels = candidate["channels"]
    center_pos = (2, 2)
    candidate_idx = [candidate_channels.index(ch) for ch in PATCH_CHANNELS]
    center_bt_delta = bt[center_pos[0], center_pos[1], :] - np.asarray(
        candidate["bt_K"], dtype=np.float64)[candidate_idx]
    center_dqf_same = np.array_equal(dqf_reader[center_pos[0], center_pos[1], :],
                                     np.asarray(candidate["dqf"])[candidate_idx])
    if not center_dqf_same or float(np.max(np.abs(center_bt_delta))) > 3e-6:
        raise ValueError("5x5 center no longer replays the existing fixed AMI candidate")

    # Geometry-only native union bounds select descriptive VIIRS center samples.
    bounds = native["union_bounds_of_native_3x3_centers_only"]
    r0, c0 = (int(candidate["selected_viirs_sample"]["obs_row_col_0based"][i])
              for i in (0, 1))
    # Read center geolocation from the existing CloudPhase EDR first; no
    # categorical fields are read until the native-bound candidate set exists.
    with netCDF4.Dataset(str(VIIRS_PHASE)) as phase_ds:
        if int(phase_ds.variables["StartRow"][:]) != 1 or int(
                phase_ds.variables["StartColumn"][:]) != 1:
            raise ValueError("VIIRS CloudPhase subset origin changed from 1-based row/column")
        for key in ("Latitude", "Longitude"):
            phase_ds.variables[key].set_auto_maskandscale(False)
        phase_lat = np.asarray(phase_ds.variables["Latitude"][:], dtype=np.float32)
        phase_lon = np.asarray(phase_ds.variables["Longitude"][:], dtype=np.float32)
        geo_valid = (np.isfinite(phase_lat) & np.isfinite(phase_lon)
                     & (phase_lat >= -90) & (phase_lat <= 90)
                     & (phase_lon >= -180) & (phase_lon <= 180))
        in_box = (geo_valid
                  & (phase_lat >= bounds["latitude_min"])
                  & (phase_lat <= bounds["latitude_max"])
                  & (phase_lon >= bounds["longitude_min"])
                  & (phase_lon <= bounds["longitude_max"]))
        viirs_rows_sel, viirs_cols_sel = np.where(in_box)
        if not (0 <= r0 < phase_lat.shape[0] and 0 <= c0 < phase_lat.shape[1]
                and in_box[r0, c0]):
            raise ValueError("fixed VIIRS candidate is no longer inside the declared native-center bounds")
        if viirs_rows_sel.size == 0:
            raise ValueError("predeclared geographic box contains no VIIRS geolocation centers")
        rmin, rmax = int(viirs_rows_sel.min()), int(viirs_rows_sel.max())
        cmin, cmax = int(viirs_cols_sel.min()), int(viirs_cols_sel.max())
        rr, cc = viirs_rows_sel - rmin, viirs_cols_sel - cmin
        tile_slice = (slice(rmin, rmax+1), slice(cmin, cmax+1))
        phase_vars = {}
        for name in ("CloudPhase", "CloudType", "CloudPhaseFlag"):
            var = phase_ds.variables[name]
            var.set_auto_maskandscale(False)
            phase_vars[name] = (np.asarray(var[tile_slice]),
                                {a: np.asarray(var.getncattr(a)).tolist()
                                 for a in var.ncattrs() if a in ("_FillValue", "valid_range", "units")})
        phase_raw = phase_vars["CloudPhase"][0][rr, cc]
        type_raw = phase_vars["CloudType"][0][rr, cc]
        flag_tile = phase_vars["CloudPhaseFlag"][0]
        if flag_tile.ndim == 3 and flag_tile.shape[-1] == 1:
            flag_tile = flag_tile[..., 0]
        flag_raw = flag_tile[rr, cc]
        cloud_geolocation = np.column_stack((phase_lat[viirs_rows_sel, viirs_cols_sel],
                                             phase_lon[viirs_rows_sel, viirs_cols_sel]))

    with netCDF4.Dataset(str(VIIRS_GMTCO)) as geo_ds:
        geo_group = geo_ds.groups["All_Data"].groups["VIIRS-MOD-GEO-TC_All"]
        for name in ("Latitude", "Longitude", *VIIRS_ANGLE_NAMES):
            geo_group.variables[name].set_auto_maskandscale(False)
        geo_lat_tile = np.asarray(geo_group.variables["Latitude"][tile_slice], dtype=np.float32)
        geo_lon_tile = np.asarray(geo_group.variables["Longitude"][tile_slice], dtype=np.float32)
        gmtco_coords = np.column_stack((geo_lat_tile[rr, cc], geo_lon_tile[rr, cc]))
        if not np.array_equal(gmtco_coords, cloud_geolocation):
            raise ValueError("selected EDR geolocations differ from same-granule GMTCO coordinates")
        angle_arrays = {name: np.asarray(geo_group.variables[name][tile_slice],
                                         dtype=np.float32)[rr, cc]
                        for name in VIIRS_ANGLE_NAMES}

    phase_valid = (phase_raw != -128) & (phase_raw >= 0) & (phase_raw <= 5)
    type_valid = (type_raw != -128) & (type_raw >= 0) & (type_raw <= 8)
    flag_fill = flag_raw == -128
    phase_counts = _counter(phase_raw)
    type_counts = _counter(type_raw)
    flag_counts = _counter(flag_raw)

    geometry_result = json.loads(VIIRS_GEOMETRY_RESULT.read_text())
    center_viirs_index = int(np.flatnonzero((viirs_rows_sel == r0)
                                            & (viirs_cols_sel == c0))[0])
    center_angles = {name: float(angle_arrays[name][center_viirs_index])
                     for name in VIIRS_ANGLE_NAMES}
    expected_angles = geometry_result["viirs_angles_degrees"]
    center_angle_deltas = {name: center_angles[name] - float(expected_angles[name])
                           for name in VIIRS_ANGLE_NAMES}
    if max(abs(x) for x in center_angle_deltas.values()) > 1e-5:
        raise ValueError("VIIRS center angle sample differs from the hash-bound existing geometry result")
    if (int(phase_raw[center_viirs_index]) != observation["fixed_candidate"]["viirs_phase"]
            or int(type_raw[center_viirs_index]) != observation["fixed_candidate"]["viirs_cloud_type"]
            or int(flag_raw[center_viirs_index])
            != observation["fixed_candidate"]["viirs_cloud_phase_flag_stored_byte"]):
        raise ValueError("VIIRS center categorical sample differs from the existing fixed-candidate receipt")

    arrays = {
        "ami_patch_row_col_0based": np.asarray(wanted, dtype=np.int32).reshape(5, 5, 2),
        "ami_patch_lat_lon_deg": coords.astype(np.float64),
        "ami_patch_channels_1based": np.asarray(PATCH_CHANNELS_1BASED, dtype=np.int8),
        "ami_patch_channel_names": np.asarray(PATCH_CHANNELS),
        "ami_patch_raw_word_uint16": raw_word,
        "ami_patch_dn_float64": raw_dn,
        "ami_patch_raw_dqf_int": raw_dqf.astype(np.int8),
        "ami_patch_decoder_effective_dqf": decoder_dqf.astype(np.int8),
        "ami_patch_reader_dqf": dqf_reader.astype(np.int8),
        "ami_patch_fill_mask": fill_mask,
        "ami_patch_invalid_radiance_mask": invalid_radiance_mask,
        "ami_patch_radiance_from_dn": radiance,
        "ami_patch_bt_authoritative_K": bt.astype(np.float64),
        "ami_patch_bt_raw_decoder_check_K": bt_replay,
        "native_geo_frames": np.asarray([1, 4, 6], dtype=np.int8),
        "native_geo_latitude_3x3_deg": np.asarray(
            [fr["latitude_deg_centers"] for fr in native["frames"]], dtype=np.float32),
        "native_geo_longitude_3x3_deg": np.asarray(
            [fr["longitude_deg_centers"] for fr in native["frames"]], dtype=np.float32),
        "viirs_selected_row_col_0based": np.column_stack((viirs_rows_sel, viirs_cols_sel)).astype(np.int32),
        "viirs_selected_lat_lon_deg": cloud_geolocation.astype(np.float32),
        "viirs_cloud_phase_raw": phase_raw.astype(np.int16),
        "viirs_cloud_type_raw": type_raw.astype(np.int16),
        "viirs_cloud_phase_flag_raw": flag_raw.astype(np.int16),
        "viirs_satellite_zenith_deg": angle_arrays["SatelliteZenithAngle"],
        "viirs_satellite_azimuth_deg": angle_arrays["SatelliteAzimuthAngle"],
        "viirs_solar_zenith_deg": angle_arrays["SolarZenithAngle"],
        "viirs_solar_azimuth_deg": angle_arrays["SolarAzimuthAngle"],
    }
    private_sha = _atomic_npz(PRIVATE_NPZ, arrays)

    ami_rows = []
    for ix, (row, col) in enumerate(wanted):
        iy, ixcol = divmod(ix, 5)
        for j, ch in enumerate(PATCH_CHANNELS):
            ami_rows.append({
                "row_0based": row, "col_0based": col,
                "latitude_deg": float(coords[iy, ixcol, 0]),
                "longitude_deg": float(coords[iy, ixcol, 1]),
                "ami_channel_id_1based": PATCH_CHANNELS_1BASED[j],
                "ami_channel": ch,
                "raw_word_hex": f"0x{int(raw_word[iy, ixcol, j]):04x}",
                "dn": float(raw_dn[iy, ixcol, j]),
                "radiance_estimate_mW_m-2_sr-1_per_cm-1": (
                    "" if fill_mask[iy, ixcol, j] else float(radiance[iy, ixcol, j])),
                "BT_K": float(bt[iy, ixcol, j]),
                "DQF_raw": int(raw_dqf[iy, ixcol, j]),
                "DQF_after_radiance_validation": int(decoder_dqf[iy, ixcol, j]),
                "DQF_reader": int(dqf_reader[iy, ixcol, j]),
                "fill_mask": bool(fill_mask[iy, ixcol, j]),
                "invalid_calibrated_radiance": bool(invalid_radiance_mask[iy, ixcol, j]),
            })
    _write_csv_exclusive(AMI_TABLE,
        ["row_0based", "col_0based", "latitude_deg", "longitude_deg",
         "ami_channel_id_1based", "ami_channel", "raw_word_hex", "dn",
         "radiance_estimate_mW_m-2_sr-1_per_cm-1", "BT_K", "DQF_raw",
         "DQF_after_radiance_validation", "DQF_reader", "fill_mask",
         "invalid_calibrated_radiance"], ami_rows)

    channel_summary = []
    for j, ch in enumerate(PATCH_CHANNELS):
        valid = (~fill_mask[:, :, j]) & (dqf_reader[:, :, j] == 0)
        channel_summary.append({
            "ami_channel_id_1based": PATCH_CHANNELS_1BASED[j], "ami_channel": ch,
            "pixel_count": 25, "fill_count": int(fill_mask[:, :, j].sum()),
            "invalid_calibrated_radiance_count": int(invalid_radiance_mask[:, :, j].sum()),
            "dqf_counts_raw": json.dumps(_counter(raw_dqf[:, :, j]), sort_keys=True),
            "reader_dqf_usable_count": int(valid.sum()),
            "bt_valid_min_K": float(np.min(bt[:, :, j][valid])) if valid.any() else "",
            "bt_valid_median_K": float(np.median(bt[:, :, j][valid])) if valid.any() else "",
            "bt_valid_max_K": float(np.max(bt[:, :, j][valid])) if valid.any() else "",
            "radiance_valid_min": float(np.nanmin(radiance[:, :, j][valid])) if valid.any() else "",
            "radiance_valid_median": float(np.nanmedian(radiance[:, :, j][valid])) if valid.any() else "",
            "radiance_valid_max": float(np.nanmax(radiance[:, :, j][valid])) if valid.any() else "",
            "radiance_units": "mW m-2 sr-1 per cm-1; estimate from gain/offset applied to DN",
            "scatter_as_sigmaR": False,
        })
    _write_csv_exclusive(AMI_CHANNEL_SUMMARY, list(channel_summary[0]), channel_summary)

    viirs_table = []
    for i, (row, col) in enumerate(zip(viirs_rows_sel, viirs_cols_sel)):
        viirs_table.append({
            "row_0based": int(row), "col_0based": int(col),
            "latitude_deg": float(cloud_geolocation[i, 0]),
            "longitude_deg": float(cloud_geolocation[i, 1]),
            "cloud_phase_raw_category": int(phase_raw[i]),
            "cloud_type_raw_category": int(type_raw[i]),
            "cloud_phase_flag_raw_byte_not_bit_decoded": int(flag_raw[i]),
            "satellite_zenith_deg": float(angle_arrays["SatelliteZenithAngle"][i]),
            "satellite_azimuth_deg": float(angle_arrays["SatelliteAzimuthAngle"][i]),
            "solar_zenith_deg": float(angle_arrays["SolarZenithAngle"][i]),
            "solar_azimuth_deg": float(angle_arrays["SolarAzimuthAngle"][i]),
        })
    if len(viirs_table) != int(viirs_rows_sel.size) or int(viirs_rows_sel.size) != int(in_box.sum()):
        raise RuntimeError("VIIRS descriptive sample table count differs from the fixed center-in-bounds mask")
    _write_csv_exclusive(VIIRS_COUNTS,
        ["field", "raw_value_or_category", "count", "interpretation"],
        ([{"field": name, "raw_value_or_category": code, "count": count,
           "interpretation": "categorical count only; code values are never averaged"}
          for name, counts in (("CloudPhase", phase_counts), ("CloudType", type_counts),
                               ("CloudPhaseFlag_raw", flag_counts))
          for code, count in counts.items()] +
         [{"field": "CloudPhase", "raw_value_or_category": "valid_range_0_5_count",
           "count": int(phase_valid.sum()), "interpretation": "raw values in declared range"},
          {"field": "CloudPhase", "raw_value_or_category": "fill_or_out_of_range_count",
           "count": int((~phase_valid).sum()), "interpretation": "fill/out-of-range raw categories"},
          {"field": "CloudType", "raw_value_or_category": "valid_range_0_8_count",
           "count": int(type_valid.sum()), "interpretation": "raw values in declared range"},
          {"field": "CloudType", "raw_value_or_category": "fill_or_out_of_range_count",
           "count": int((~type_valid).sum()), "interpretation": "fill/out-of-range raw categories"},
          {"field": "CloudPhaseFlag_raw", "raw_value_or_category": "fill_byte_count",
           "count": int(flag_fill.sum()), "interpretation": "raw fill bytes only; nonzero bytes not bit-decoded"}]))

    angle_summary = {}
    for name, value in angle_arrays.items():
        finite = np.isfinite(value)
        angle_summary[name] = {
            "finite_count": int(finite.sum()),
            "nonfinite_count": int((~finite).sum()),
            "min_deg": float(np.min(value[finite])) if finite.any() else None,
            "median_deg": float(np.median(value[finite])) if finite.any() else None,
            "max_deg": float(np.max(value[finite])) if finite.any() else None,
        }

    post_sources = {"AMI": {p.name: sha256(p) for p in ami_files},
                    "CloudPhase": sha256(VIIRS_PHASE), "GMTCO": sha256(VIIRS_GMTCO),
                    "calibration": sha256(CALIBRATION),
                    "geometry_result": sha256(VIIRS_GEOMETRY_RESULT),
                    "native_geometry": sha256(NATIVE_GEOGRAPHY),
                    "native_patch_plan": sha256(NATIVE_PATCH_PLAN),
                    "common_predeclared": sha256(COMMON_PREDECLARED),
                    "observation_receipt": sha256(OBSERVATION_RECEIPT),
                    "ami_slot_receipt": sha256(AMI_SLOT_RECEIPT),
                    "ami_candidate_result": sha256(AMI_CANDIDATE),
                    "reader_sources": source_hashes()}
    if (post_sources["AMI"] != preflight["AMI_patch"]["files_sha256"]
            or post_sources["CloudPhase"] != preflight["VIIRS_sources"]["cloudphase_sha256"]
            or post_sources["GMTCO"] != preflight["VIIRS_sources"]["gmtco_sha256"]
            or post_sources["calibration"] != preflight["calibration"]["table_sha256"]
            or post_sources["geometry_result"] != preflight["VIIRS_sources"]["geometry_result_sha256"]
            or post_sources["native_geometry"] != preflight["native_geometry_sha256"]
            or post_sources["native_patch_plan"] != preflight["native_patch_plan_sha256"]
            or post_sources["common_predeclared"] != preflight["common_predeclared_sha256"]
            or post_sources["observation_receipt"] != preflight["existing_receipts"][
                "observation_receipt_sha256"]
            or post_sources["ami_slot_receipt"] != preflight["existing_receipts"][
                "ami_slot_receipt_sha256"]
            or post_sources["ami_candidate_result"] != preflight["existing_receipts"][
                "candidate_result_sha256"]
            or post_sources["reader_sources"] != preflight["reader_source_sha256"]):
        raise ValueError("an observation source changed during patch extraction")

    npz_sha = private_sha
    ami_channel_summaries = channel_summary
    result = {
        "schema": "pr398_observation_patch_result_v1",
        "status": "AUDITED_DESCRIPTIVE_PATCH_NO_MATCHUP_CLAIM",
        "common_predeclared_sha256": sha256(COMMON_PREDECLARED),
        "native_geography_sha256": sha256(NATIVE_GEOGRAPHY),
        "native_patch_plan_sha256": sha256(NATIVE_PATCH_PLAN),
        "native_bounds_contract": pre["viirs"]["region_boundary_contract"],
        "native_bounds_center_union": bounds,
        "native_frames_and_times": [{"frame_index": fr["frame_index"],
                                      "time": fr["time_label"]} for fr in native["frames"]],
        "AMI_patch": {
            "selection": "fixed 5x5 LA pixel-center grid rows318:323 cols46:51, zero based, including fixed center (320,48)",
            "channels_1based": list(PATCH_CHANNELS_1BASED),
            "channel_names": list(PATCH_CHANNELS),
            "center_lat_lon_deg": coords[2, 2].tolist(),
            "center_BT_delta_from_existing_candidate_K": center_bt_delta.tolist(),
            "center_DQF_equals_existing_candidate": center_dqf_same,
            "channel_summary": ami_channel_summaries,
            "radiance_semantics": "derived per pixel from packed DN and the hash-bound gain/offset; no BT-to-radiance conversion and no patch averaging",
            "radiance_units": "mW m-2 sr-1 per cm-1 according to existing reader equation",
            "BT_and_DQF_semantics": "authoritative existing GK2A LA reader output; DQF preserved per sample, fill mask separately retained",
            "source_srf_status": "the bundled calibration-table note states the 2025 FD SRF version is unverified",
            "spatial_variation_sigmaR": "not estimated; patch scatter is not a calibrated R or observation-error sigma",
        },
        "VIIRS_patch": {
            "selection": "existing CloudPhase and GMTCO center samples inside native 3x3-center union lat/lon bounds",
            "sample_count": int(viirs_rows_sel.size),
            "fixed_candidate_row_col_0based": [r0, c0],
            "fixed_candidate_in_selection": True,
            "center_angles_deg": center_angles,
            "center_angle_delta_from_existing_geometry_result_deg": center_angle_deltas,
            "angle_summary_deg": angle_summary,
            "CloudPhase_raw_category_counts": phase_counts,
            "CloudType_raw_category_counts": type_counts,
            "CloudPhaseFlag_raw_byte_counts_not_bit_decoded": flag_counts,
            "CloudPhase_raw_fill_or_out_of_range_count": int((~phase_valid).sum()),
            "CloudType_raw_fill_or_out_of_range_count": int((~type_valid).sum()),
            "CloudPhaseFlag_nonzero_bytes_bit_decoded": False,
            "categorical_code_averaging": False,
            "cloud_height_patch_status": "NOT_AVAILABLE_FULL_SOURCE_UNVERIFIED",
            "center_CTH_extended_to_patch": False,
            "footprint_overlap_verified": False,
        },
        "comparison_limits": {
            "AMI_5x5_is_descriptive_patch_not_sensor_footprint": True,
            "VIIRS_bounds_are_center_only_not_cell_edges_or_areas": True,
            "parallax_applied": False,
            "per_pixel_UTC_verified": False,
            "height_datum_verified": False,
            "physical_matchup_approved": False,
            "science_admission": "NOT_ASSESSED",
        },
        "source_sha256_after_read": post_sources,
        "private_npz": {"path": str(PRIVATE_NPZ), "sha256": npz_sha,
                         "mode_octal": "0600", "directory_mode_octal": "0700",
                         "arrays": sorted(arrays)},
        "public_tables": {
            "ami_5x5_path": str(AMI_TABLE.relative_to(ROOT)),
            "ami_5x5_sha256": sha256(AMI_TABLE),
            "ami_channel_summary_path": str(AMI_CHANNEL_SUMMARY.relative_to(ROOT)),
            "ami_channel_summary_sha256": sha256(AMI_CHANNEL_SUMMARY),
            "viirs_category_counts_path": str(VIIRS_COUNTS.relative_to(ROOT)),
            "viirs_category_counts_sha256": sha256(VIIRS_COUNTS),
        },
        "execution_limits": {"new_observation_acquisition": False,
                              "new_native_run": False,
                              "M_H_RTTOV_or_optimizer_calls": 0,
                              "candidate_replacement": False},
    }
    write_exclusive_json(OBSERVATION_PATCH, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract-after-preflight", action="store_true",
                        help="read the predeclared existing AMI/VIIRS sample patch once")
    args = parser.parse_args()
    if not PATCH_PREFLIGHT.exists():
        preflight = build_preflight()
        print(json.dumps({"status": preflight["status"],
                          "preflight": str(PATCH_PREFLIGHT),
                          "sample_values_read": False}, indent=2))
        return 0
    preflight = json.loads(PATCH_PREFLIGHT.read_text())
    preflight["preflight_sha256"] = sha256(PATCH_PREFLIGHT)
    if not args.extract_after_preflight:
        print(json.dumps({"status": preflight["status"],
                          "preflight_sha256": preflight["preflight_sha256"],
                          "sample_values_read": False}, indent=2))
        return 0
    result = extract_once(preflight)
    print(json.dumps({"status": result["status"],
                      "observation_patch": str(OBSERVATION_PATCH),
                      "private_npz": result["private_npz"]["path"],
                      "viirs_sample_count": result["VIIRS_patch"]["sample_count"],
                      "M_H_calls": 0}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
