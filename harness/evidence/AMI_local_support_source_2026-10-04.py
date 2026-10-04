#!/usr/bin/env python3
"""Measure local GK2A AMI BT heterogeneity around the frozen C5 pixel.

This is an observation-support diagnostic on retained KO L1B files. It does
not estimate a 5 km footprint or radiance variance. Every reported window
statistic requires all nine pixels in the centered 3x3 window to pass
the existing decoder QC and NetCDF missingness checks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "oracle"))

from kdm6.obs.gk2a_l1b import (  # noqa: E402
    AMI_CHANNELS,
    load_cal_table,
    read_ko_slot,
    slot_files,
    unpack_ami_word,
)


CHANNELS = ("wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133")
SLOTS = ("202507190000", "202507190002")
PIXEL = (411, 338)  # zero-based row, column from the frozen C5 diagnostic
WINDOW_RADIUS = 1
MIN_GOOD_PIXELS = 9
CAL_SHA256 = "f519149e3ea3538866bad9f3e28cc0ddef741b6b4cdbf8febb7988aff6c08d40"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def bt_from_radiance(radiance: float, cal: dict) -> float:
    """Apply dn_to_bt's Planck and Teff-to-Tbb map to unquantized radiance."""
    lam_um = float(cal["channel_center_wavelength"])
    h = float(cal["Plank_constant_h"])
    c = float(cal["light_speed"])
    k = float(cal["Boltzmann_constant_k"])
    sigma_m = (10000.0 / lam_um) * 100.0
    planck_t = h * c * sigma_m / k
    planck_r = 2.0 * h * c * c * sigma_m ** 3
    l_sigma = max(radiance * 1.0e-3 / 100.0, 1.0e-30)
    teff = planck_t / math.log(planck_r / l_sigma + 1.0)
    return (float(cal["Teff_to_Tbb_c0"])
            + float(cal["Teff_to_Tbb_c1"]) * teff
            + float(cal["Teff_to_Tbb_c2"]) * teff * teff)


def expected_centers(diagnostic_path: Path) -> dict[str, float]:
    doc = json.loads(diagnostic_path.read_text())
    if tuple(doc.get("pixel_zero_based", ())) != PIXEL:
        raise ValueError("diagnostic pixel does not match frozen C5 pixel (411,338)")
    expected = {
        item["channel"]: float(item["bt_K"])
        for item in doc.get("channels", [])
        if item.get("channel") in CHANNELS
    }
    if set(expected) != set(CHANNELS):
        raise ValueError("C5 diagnostic does not contain exactly the required channel set")
    return expected


def inspect_slot(root: Path, stamp: str, cal_table: dict,
                 expected: dict[str, float]) -> dict:
    files = slot_files(root, stamp, channels=CHANNELS)
    # Use the production slot decoder for full-grid BT and embedded DQF.
    payload = read_ko_slot(files, cal_table, stride=1)
    ny, nx = 900, 900
    if payload.valid_time_utc != stamp:
        raise ValueError(f"{stamp}: decoder returned unexpected slot timestamp {payload.valid_time_utc}")
    if payload.bt.shape[0] != ny * nx:
        raise ValueError(f"{stamp}: expected the retained 900x900 KO grid")
    result = {"timestamp": stamp, "channels": {}, "files": []}

    for path in files:
        result["files"].append({"path": str(path), "sha256": sha256(path),
                                "size_bytes": path.stat().st_size})

    row, col = PIXEL
    ys = slice(row - WINDOW_RADIUS, row + WINDOW_RADIUS + 1)
    xs = slice(col - WINDOW_RADIUS, col + WINDOW_RADIUS + 1)
    import netCDF4

    for ch, path in zip(CHANNELS, files):
        j = AMI_CHANNELS.index(ch)
        bt_grid = payload.bt[:, j].cpu().numpy().reshape(ny, nx)
        q_grid = payload.obs_quality[:, j].cpu().numpy().reshape(ny, nx)
        bt_window = bt_grid[ys, xs]
        q_window = q_grid[ys, xs]
        with netCDF4.Dataset(str(path)) as ds:
            var = ds.variables["image_pixel_values"]
            raw_masked = var[ys, xs]
            missing = np.ma.getmaskarray(raw_masked)
            raw = np.ma.filled(raw_masked, 0)
            dn, word_q = unpack_ami_word(raw, var.getncattr("number_of_valid_bits_per_pixel"))
            cal = cal_table["channels"][ch]
            # Same linear calibration as dn_to_bt; mean-radiance inversion does
            # not requantize to an integer DN.
            rad = float(cal["DN_to_Radiance_Offset"]) + float(cal["DN_to_Radiance_Gain"]) * dn
        usable = (~missing) & (word_q == 0.0) & (q_window == 0.0) & np.isfinite(rad) & (rad > 0.0)
        count = int(np.count_nonzero(usable))
        center_bt = float(bt_grid[row, col])
        center_q = float(q_grid[row, col])
        if center_q != 0.0 or not np.isfinite(center_bt) or center_bt <= 0.0:
            raise ValueError(f"{stamp} {ch}: C5 center is not usable under decoder QC")
        if stamp == SLOTS[0] and center_bt != expected[ch]:
            raise ValueError(f"{ch}: decoded center BT differs from frozen C5 diagnostic")

        entry = {
            "center_bt_K": center_bt,
            "center_obs_quality": center_q,
            "window_good_pixel_count": count,
            "window_pixel_count": 9,
            "minimum_good_pixel_count": MIN_GOOD_PIXELS,
            "decoder_quality_counts": {
                str(int(flag)): int(np.count_nonzero(word_q == flag))
                for flag in np.unique(word_q)
            },
            "netcdf_missing_pixel_count": int(np.count_nonzero(missing)),
            "nonfinite_or_nonpositive_radiance_pixel_count": int(np.count_nonzero(~(np.isfinite(rad) & (rad > 0.0)))),
            "statistics_status": "REPORTED" if count >= MIN_GOOD_PIXELS else "INSUFFICIENT_SUPPORT",
        }
        if count >= MIN_GOOD_PIXELS:
            bt_good = bt_window[usable]
            rad_good = rad[usable]
            mean_rad = float(np.mean(rad_good, dtype=np.float64))
            entry.update({
                "window_bt_K": bt_window.tolist(),
                "window_radiance": rad.tolist(),
                "min_bt_K": float(np.min(bt_good)),
                "max_bt_K": float(np.max(bt_good)),
                "spatial_bt_std_K_ddof0": float(np.std(bt_good, ddof=0, dtype=np.float64)),
                "mean_bt_K": float(np.mean(bt_good, dtype=np.float64)),
                "mean_radiance": mean_rad,
                "bt_from_mean_radiance_K": bt_from_radiance(mean_rad, cal),
                "radiance_unit": "mW m-2 sr-1 (cm-1)-1 (AMI calibration convention)",
            })
        result["channels"][ch] = entry
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-root", type=Path, required=True,
                   help="root containing the retained GK2A/00 KO files")
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--diagnostic", type=Path, required=True,
                   help="frozen C5 matched-observation diagnostic JSON")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    root = a.input_root.resolve()
    cal_path = a.calibration.resolve()
    diagnostic_path = a.diagnostic.resolve()
    source_path = Path(__file__).resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    if sha256(cal_path) != CAL_SHA256:
        raise ValueError("calibration hash differs from the frozen C5 calibration")
    expected = expected_centers(diagnostic_path)
    cal_table = load_cal_table(cal_path)
    slots = [inspect_slot(root, stamp, cal_table, expected) for stamp in SLOTS]

    deltas = {}
    for ch in CHANNELS:
        deltas[ch] = {
            "from_timestamp": SLOTS[0],
            "to_timestamp": SLOTS[1],
            "center_bt_change_K": (slots[1]["channels"][ch]["center_bt_K"]
                                   - slots[0]["channels"][ch]["center_bt_K"]),
            "quality_both_slots": (
                slots[0]["channels"][ch]["center_obs_quality"] == 0.0
                and slots[1]["channels"][ch]["center_obs_quality"] == 0.0),
        }
    report = {
        "status": "COMPLETE" if all(
            s["channels"][ch]["statistics_status"] == "REPORTED"
            for s in slots for ch in CHANNELS) else "INCOMPLETE_SUPPORT",
        "diagnostic": {
            "pixel_zero_based_row_column": list(PIXEL),
            "channels": list(CHANNELS),
            "timestamps": list(SLOTS),
            "window": "centered 3x3 pixels",
            "support_rule": "all 9 pixels must have decoder obs_quality=0, unmasked NetCDF input, and finite positive calibrated radiance",
            "no_qc_relaxation": True,
            "scope_note": "local retained-observation support only; not a 5 km footprint or a radiance-variance estimate",
        },
        "provenance": {
            "decoder": "oracle/kdm6/obs/gk2a_l1b.py:read_ko_slot, _read_ami_bt, unpack_ami_word, dn_to_bt",
            "decoder_sha256": sha256(REPO / "oracle/kdm6/obs/gk2a_l1b.py"),
            "source_path": str(source_path),
            "source_sha256": sha256(source_path),
            "cli_argv": sys.argv,
            "calibration_path": str(cal_path),
            "calibration_sha256": sha256(cal_path),
            "diagnostic_path": str(diagnostic_path),
            "diagnostic_sha256": sha256(diagnostic_path),
            "input_root": str(root),
        },
        "slots": slots,
        "center_bt_00_to_02": deltas,
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "output": str(a.output),
                      "sha256": sha256(a.output)}, sort_keys=True))
    if report["status"] != "COMPLETE":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
