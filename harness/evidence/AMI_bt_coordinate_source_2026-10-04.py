#!/usr/bin/env python3
"""Compare retained AMI and RTTOV IR-channel radiance/BT coordinates.

This bounded evidence script reuses retained AMI windows, saved DOM32 base/±
BT/JVP arrays, and already-produced 17-digit RTTOV radiance text. It does not
run an engine, alter radiances, or make a calibration/physical approval claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import numpy as np


CHANNELS = ("wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133")
RTTOV_CHANNEL = {"wv073": 10, "ir087": 11, "ir096": 12,
                 "ir105": 13, "ir112": 14, "ir123": 15, "ir133": 16}
RTTOV_CONSTANTS = (1.191042972e-5, 1.438776878)  # pinned rttov_test BT conversion
MINIMUM_WINDOW_PIXELS = 9


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path) as archive:
        return {k: archive[k].copy() for k in archive.files}


def ami_phi(radiance, coeff: dict, wavenumber_cm1: float) -> np.ndarray:
    """Source-order AMI Planck + retained Teff-to-Tbb polynomial."""
    rad = np.asarray(radiance, dtype=np.float64)
    l_sigma = np.clip(rad * 1.0e-3 / 100.0, 1e-30, None)
    sigma_m = float(wavenumber_cm1) * 100.0
    h = float(coeff["Plank_constant_h"])
    c = float(coeff["light_speed"])
    k = float(coeff["Boltzmann_constant_k"])
    planck_t = h * c * sigma_m / k
    planck_r = 2.0 * h * c * c * sigma_m ** 3
    teff = planck_t / np.log(planck_r / l_sigma + 1.0)
    return (float(coeff["Teff_to_Tbb_c0"])
            + float(coeff["Teff_to_Tbb_c1"]) * teff
            + float(coeff["Teff_to_Tbb_c2"]) * teff * teff)


def ami_phi_prime(radiance, coeff: dict, wavenumber_cm1: float) -> np.ndarray:
    rad = np.asarray(radiance, dtype=np.float64)
    x = np.clip(rad * 1.0e-3 / 100.0, 1e-30, None)
    sigma_m = float(wavenumber_cm1) * 100.0
    h = float(coeff["Plank_constant_h"])
    c = float(coeff["light_speed"])
    k = float(coeff["Boltzmann_constant_k"])
    a = h * c * sigma_m / k
    b = 2.0 * h * c * c * sigma_m ** 3
    log_term = np.log(b / x + 1.0)
    teff = a / log_term
    dteff_dl = a * b / (x * (x + b) * log_term ** 2) * 1.0e-5
    poly_prime = float(coeff["Teff_to_Tbb_c1"]) + 2.0 * float(coeff["Teff_to_Tbb_c2"]) * teff
    return poly_prime * dteff_dl


def rttov_psi(radiance, channel_coeff: dict) -> np.ndarray:
    rad = np.asarray(radiance, dtype=np.float64)
    nu = float(channel_coeff["wavenumber_cm1"])
    offset = float(channel_coeff["offset_K"])
    slope = float(channel_coeff["slope"])
    c1, c2 = RTTOV_CONSTANTS
    return (c2 * nu / np.log(c1 * nu ** 3 / rad + 1.0) - offset) / slope


def rttov_psi_prime(radiance, channel_coeff: dict) -> np.ndarray:
    rad = np.asarray(radiance, dtype=np.float64)
    nu = float(channel_coeff["wavenumber_cm1"])
    slope = float(channel_coeff["slope"])
    c1, c2 = RTTOV_CONSTANTS
    a = c2 * nu
    b = c1 * nu ** 3
    log_term = np.log(b / rad + 1.0)
    return a * b / (rad * (rad + b) * log_term ** 2) / slope


def parse_filter_functions(path: Path) -> dict[int, dict]:
    text = path.read_text(errors="replace")
    try:
        body = text.split("FILTER_FUNCTIONS", 1)[1]
    except IndexError as exc:
        raise ValueError(f"{path}: no FILTER_FUNCTIONS section") from exc
    rows = {}
    for line in body.splitlines():
        fields = line.split()
        if len(fields) != 6:
            if rows:
                break
            continue
        try:
            chan = int(fields[0])
            status = int(fields[1])
            nu, offset, slope, gamma = map(float, fields[2:])
        except ValueError:
            if rows:
                break
            continue
        rows[chan] = {"status": status, "wavenumber_cm1": nu,
                      "offset_K": offset, "slope": slope,
                      "gamma": gamma}
    if not set(RTTOV_CHANNEL.values()).issubset(rows):
        raise ValueError("pinned coefficient table lacks one or more required channels")
    return rows


def parse_direct_radiance(path: Path) -> tuple[np.ndarray, np.ndarray]:
    text = path.read_text()
    parsed = []
    for field in ("TOTAL", "BT"):
        match = re.search(rf"RADIANCE%{field} = \((.*?)\)", text, re.S)
        if not match:
            raise ValueError(f"{path}: missing RADIANCE%{field}")
        parsed.append(np.asarray([float(v) for v in match.group(1).split()], dtype=np.float64))
    if parsed[0].shape != (9,) or parsed[1].shape != (9,):
        raise ValueError(f"{path}: expected the nine retained RTTOV channels 8..16")
    return parsed[0], parsed[1]


def stats(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    return {"min": float(np.min(x)), "max": float(np.max(x)),
            "std_ddof0": float(np.std(x, ddof=0)),
            "mean": float(np.mean(x, dtype=np.float64))}


def validate_cal_pair(legacy: dict, shipped: dict, pairing: dict) -> None:
    if pairing.get("calibration_source", {}).get("authority") != "Korea Meteorological Administration, GK-2A AMI Calibration Table v3.0 (20190415)":
        raise ValueError("pairing receipt does not identify the audited KMA v3.0 table")
    for ch in CHANNELS:
        a, b = legacy["channels"][ch], shipped["channels"][ch]
        for key in ("DN_to_Radiance_Gain", "DN_to_Radiance_Offset",
                    "channel_center_wavelength", "Teff_to_Tbb_c0",
                    "Teff_to_Tbb_c1", "Teff_to_Tbb_c2",
                    "Plank_constant_h", "light_speed", "Boltzmann_constant_k"):
            if a[key] != b[key]:
                raise ValueError(f"{ch}: updated table changed preserved legacy {key}")
        if "bt_wavenumber_cm1" not in b:
            raise ValueError(f"{ch}: updated table is missing bt_wavenumber_cm1")
        recorded = pairing.get("pairing_check", {}).get("channels", {}).get(ch, {})
        if float(recorded.get("bt_wavenumber_cm1", math.nan)) != float(b["bt_wavenumber_cm1"]):
            raise ValueError(f"{ch}: updated wavenumber disagrees with pairing receipt")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--observation-result", type=Path, required=True)
    p.add_argument("--legacy-calibration", type=Path, required=True)
    p.add_argument("--updated-calibration", type=Path, required=True)
    p.add_argument("--pairing-receipt", type=Path, required=True)
    p.add_argument("--rttov-coefficient", type=Path, required=True)
    p.add_argument("--base-npz", type=Path, required=True)
    p.add_argument("--plus-npz", type=Path, required=True)
    p.add_argument("--minus-npz", type=Path, required=True)
    p.add_argument("--derivatives-npz", type=Path, required=True)
    p.add_argument("--dom32-result", type=Path, required=True)
    p.add_argument("--rttov-channels", type=Path, required=True)
    p.add_argument("--base-radiance", type=Path, required=True)
    p.add_argument("--plus-radiance", type=Path, required=True)
    p.add_argument("--minus-radiance", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    in_paths = {k: Path(v).resolve() for k, v in vars(args).items() if isinstance(v, Path)}
    obs_doc = json.loads(args.observation_result.read_text())
    old_doc = json.loads(args.legacy_calibration.read_text())
    new_doc = json.loads(args.updated_calibration.read_text())
    pairing_doc = json.loads(args.pairing_receipt.read_text())
    dom32_doc = json.loads(args.dom32_result.read_text())
    validate_cal_pair(old_doc, new_doc, pairing_doc)
    expected_stamps = ["202507190000", "202507190002"]
    if obs_doc.get("diagnostic", {}).get("pixel_zero_based_row_column") != [411, 338]:
        raise ValueError("observation result does not describe frozen C5 pixel (411,338)")
    if [s.get("timestamp") for s in obs_doc.get("slots", [])] != expected_stamps:
        raise ValueError("observation result must contain the exact 00:00 and first-following 00:02 slots")
    if any(set(s.get("channels", {})) != set(CHANNELS) for s in obs_doc["slots"]):
        raise ValueError("each observation slot must contain exactly the common seven channels")
    rttov_all = parse_filter_functions(args.rttov_coefficient)
    channels_rt = {ch: rttov_all[RTTOV_CHANNEL[ch]] for ch in CHANNELS}
    for ch, v in channels_rt.items():
        if v["status"] != 1:
            raise ValueError(f"RTTOV channel {RTTOV_CHANNEL[ch]} is not active")
    if not math.isclose(channels_rt["ir105"]["wavenumber_cm1"], 966.1533839, abs_tol=5e-7):
        raise ValueError("IR105 pinned coefficient wavenumber does not match audited RTTOV source")
    if not math.isclose(channels_rt["ir105"]["offset_K"], 0.1026489494, abs_tol=5e-11):
        raise ValueError("IR105 pinned coefficient offset does not match audited RTTOV source")
    if not math.isclose(channels_rt["ir105"]["slope"], 0.9996594440, abs_tol=5e-11):
        raise ValueError("IR105 pinned coefficient slope does not match audited RTTOV source")

    npzs = {name: load_npz(getattr(args, f"{name}_npz")) for name in ("base", "plus", "minus")}
    deriv = load_npz(args.derivatives_npz)
    h = float(dom32_doc["h"])
    if not math.isfinite(h) or h <= 0.0 or dom32_doc.get("nc_direction") != "0.01*NC; all other state/forcing held fixed":
        raise ValueError("unexpected saved DOM32 FD direction/step")
    channel_list = [int(v) for v in args.rttov_channels.read_text().split()]
    if channel_list != list(range(8, 17)):
        raise ValueError("retained RTTOV channel list is not the expected 8..16 ordering")
    if "FD" not in deriv or "BT" not in npzs["base"]:
        raise ValueError("saved DOM32 BT/JVP/FD inputs are incomplete")
    direct_paths = {"base": args.base_radiance, "plus": args.plus_radiance,
                    "minus": args.minus_radiance}
    direct = {name: parse_direct_radiance(path) for name, path in direct_paths.items()}
    direct_bt_equal_npz = {}
    for name in ("base", "plus", "minus"):
        bt_npz = np.asarray(npzs[name]["BT"], dtype=np.float64).reshape(-1)
        if bt_npz.shape != (9,):
            raise ValueError(f"{name}: NPZ BT array is not nine channels")
        direct_bt_equal_npz[name] = bool(np.array_equal(bt_npz, direct[name][1]))
        if not direct_bt_equal_npz[name]:
            raise ValueError(f"{name}: public DOM32 BT array differs from retained direct radiance text")
    if deriv["JVP"].shape != (9,) or deriv["FD"].shape != (9,):
        raise ValueError("DOM32 derivative arrays must be length nine")
    if not np.array_equal(np.asarray(dom32_doc["jvp_bt_K"], dtype=np.float64), deriv["JVP"]):
        raise ValueError("saved DOM32 result JSON and derivative NPZ disagree on JVP")
    if not np.array_equal(np.asarray(dom32_doc["fd_bt_K"], dtype=np.float64), deriv["FD"]):
        raise ValueError("saved DOM32 result JSON and derivative NPZ disagree on FD")
    qualities = {name: np.asarray(npzs[name]["QUALITY"], dtype=np.float64).reshape(-1)
                 for name in ("base", "plus", "minus")}
    if any(q.shape != (9,) for q in qualities.values()) or not (
            np.array_equal(qualities["base"], qualities["plus"])
            and np.array_equal(qualities["base"], qualities["minus"])):
        raise ValueError("saved DOM32 endpoint quality arrays differ")
    if not np.array_equal(qualities["base"], np.zeros(9, dtype=np.float64)):
        raise ValueError("saved DOM32 base quality is not all-zero for this frozen case")

    channel_rows = {}
    observed_records = {}
    model_records = {}
    tangent_records = {}
    for ch in CHANNELS:
        oldc, newc = old_doc["channels"][ch], new_doc["channels"][ch]
        old_wn = 10000.0 / float(oldc["channel_center_wavelength"])
        new_wn = float(newc["bt_wavenumber_cm1"])
        rt = channels_rt[ch]
        slot_records = {}
        obs_center_l = None
        obs_center_old = None
        for slot in obs_doc["slots"]:
            stamp = slot["timestamp"]
            entry = slot["channels"][ch]
            if entry["statistics_status"] != "REPORTED" or entry["window_good_pixel_count"] != MINIMUM_WINDOW_PIXELS:
                raise ValueError(f"{ch}@{stamp}: incomplete/nonpassing observation support")
            if entry.get("window_pixel_count") != MINIMUM_WINDOW_PIXELS:
                raise ValueError(f"{ch}@{stamp}: recorded window size is not nine pixels")
            if entry.get("decoder_quality_counts") != {"0": MINIMUM_WINDOW_PIXELS}:
                raise ValueError(f"{ch}@{stamp}: decoder DQF counts are not nine usable pixels")
            if entry.get("netcdf_missing_pixel_count") != 0:
                raise ValueError(f"{ch}@{stamp}: NetCDF-masked samples are present")
            if entry.get("nonfinite_or_nonpositive_radiance_pixel_count") != 0:
                raise ValueError(f"{ch}@{stamp}: invalid calibrated radiance samples are present")
            rad = np.asarray(entry["window_radiance"], dtype=np.float64)
            old_bt_saved = np.asarray(entry["window_bt_K"], dtype=np.float64)
            if rad.shape != (3, 3) or old_bt_saved.shape != (3, 3):
                raise ValueError(f"{ch}@{stamp}: expected preserved 3x3 raw radiance/BT")
            old_bt = ami_phi(rad, oldc, old_wn)
            new_bt = ami_phi(rad, newc, new_wn)
            rt_bt = rttov_psi(rad, rt)
            if not np.allclose(old_bt, old_bt_saved, rtol=0.0, atol=2e-11):
                raise ValueError(f"{ch}@{stamp}: replay of old AMI phi differs from retained decoder BT")
            center_l = float(rad[1, 1])
            if stamp == "202507190000":
                obs_center_l = center_l
                obs_center_old = float(old_bt[1, 1])
            slot_records[stamp] = {
                "window_good_pixel_count": entry["window_good_pixel_count"],
                "decoder_quality_counts": entry["decoder_quality_counts"],
                "netcdf_missing_pixel_count": entry["netcdf_missing_pixel_count"],
                "raw_radiance_window": rad.tolist(),
                "legacy_ami_bt_window_K": old_bt.tolist(),
                "kma_v3_0_source_paired_bt_window_K": new_bt.tolist(),
                "pinned_rttov_bt_window_K": rt_bt.tolist(),
                "window_radiance_stats": stats(rad),
                "legacy_ami_bt_stats_K": stats(old_bt),
                "kma_v3_0_source_paired_bt_stats_K": stats(new_bt),
                "pinned_rttov_bt_stats_K": stats(rt_bt),
                "bt_from_mean_radiance_K": {
                    "legacy_ami": float(ami_phi(np.mean(rad), oldc, old_wn)),
                    "kma_v3_0_source_paired": float(ami_phi(np.mean(rad), newc, new_wn)),
                    "pinned_rttov": float(rttov_psi(np.mean(rad), rt)),
                },
                "rttov_minus_kma_v3_0_bt_range_K": stats(rt_bt - new_bt),
                "kma_v3_0_minus_legacy_bt_range_K": stats(new_bt - old_bt),
            }
        if obs_center_l is None:
            raise ValueError(f"{ch}: no first-slot center")

        k = channel_list.index(RTTOV_CHANNEL[ch])
        m = {}
        for name in ("base", "plus", "minus"):
            l = float(direct[name][0][k])
            npz_bt = float(npzs[name]["BT"].reshape(-1)[k])
            m[name] = {
                "radiance": l,
                "stored_rttov_bt_K": npz_bt,
                "legacy_ami_bt_K": float(ami_phi(l, oldc, old_wn)),
                "kma_v3_0_source_paired_bt_K": float(ami_phi(l, newc, new_wn)),
                "pinned_rttov_bt_K": float(rttov_psi(l, rt)),
            }
            if not math.isclose(m[name]["pinned_rttov_bt_K"], npz_bt, rel_tol=0.0, abs_tol=3e-6):
                raise ValueError(f"{ch}/{name}: coefficient-source RTTOV BT replay mismatch")
        model_l = m["base"]["radiance"]
        rt_prime = float(rttov_psi_prime(model_l, rt))
        old_prime = float(ami_phi_prime(model_l, oldc, old_wn))
        new_prime = float(ami_phi_prime(model_l, newc, new_wn))
        jvp_psi = float(deriv["JVP"][k])
        fd_psi_saved = float(deriv["FD"][k])
        model_fd = {}
        for key, fn in (("legacy_ami", lambda x: ami_phi(x, oldc, old_wn)),
                        ("kma_v3_0_source_paired", lambda x: ami_phi(x, newc, new_wn)),
                        ("pinned_rttov", lambda x: rttov_psi(x, rt))):
            model_fd[key] = float((fn(m["plus"]["radiance"]) - fn(m["minus"]["radiance"])) / (2.0 * h))
        tangent_records[ch] = {
            "input_jvp_rttov_bt_K_per_control": jvp_psi,
            "saved_rttov_fd_K_per_control": fd_psi_saved,
            "rttov_radiance_derivative_from_endpoints_per_control": float(
                (m["plus"]["radiance"] - m["minus"]["radiance"]) / (2.0 * h)),
            "phi_prime_legacy_at_model_radiance_K_per_radiance": old_prime,
            "phi_prime_kma_v3_0_at_model_radiance_K_per_radiance": new_prime,
            "psi_prime_rttov_at_model_radiance_K_per_radiance": rt_prime,
            "legacy_phi_prime_over_psi_prime": old_prime / rt_prime,
            "kma_v3_0_phi_prime_over_psi_prime": new_prime / rt_prime,
            "jvp_legacy_phi_K_per_control": jvp_psi * old_prime / rt_prime,
            "jvp_kma_v3_0_phi_K_per_control": jvp_psi * new_prime / rt_prime,
            "endpoint_fd_K_per_control": model_fd,
            "window_local_kma_phi_prime_over_psi_prime_range": {
                stamp: [
                    float(np.min(ami_phi_prime(np.asarray(o["raw_radiance_window"]), newc, new_wn)
                                 / rttov_psi_prime(np.asarray(o["raw_radiance_window"]), rt))),
                    float(np.max(ami_phi_prime(np.asarray(o["raw_radiance_window"]), newc, new_wn)
                                 / rttov_psi_prime(np.asarray(o["raw_radiance_window"]), rt))),
                ] for stamp, o in slot_records.items()
            },
            "bound_scope": "deterministic derivative-ratio range over retained 3x3 radiances; not uncertainty or a confidence interval",
        }
        model_records[ch] = {
            **m,
            "model_minus_202507190000_observation_residual_K": {
                "legacy_ami_coordinate": m["base"]["legacy_ami_bt_K"] - obs_center_old,
                "kma_v3_0_source_paired_coordinate": m["base"]["kma_v3_0_source_paired_bt_K"] - float(ami_phi(obs_center_l, newc, new_wn)),
                "pinned_rttov_coordinate": m["base"]["pinned_rttov_bt_K"] - float(rttov_psi(obs_center_l, rt)),
            },
            "center_same_radiance_map_offsets_K": {
                "kma_v3_0_minus_legacy_ami": float(ami_phi(obs_center_l, newc, new_wn) - ami_phi(obs_center_l, oldc, old_wn)),
                "pinned_rttov_minus_legacy_ami": float(rttov_psi(obs_center_l, rt) - ami_phi(obs_center_l, oldc, old_wn)),
                "pinned_rttov_minus_kma_v3_0": float(rttov_psi(obs_center_l, rt) - ami_phi(obs_center_l, newc, new_wn)),
            },
        }
        observed_records[ch] = {
            "legacy_nominal_wavelength_um": float(oldc["channel_center_wavelength"]),
            "kma_v3_0_source_paired_wavenumber_cm1": new_wn,
            "pinned_rttov_channel": RTTOV_CHANNEL[ch],
            "pinned_rttov_wavenumber_cm1": rt["wavenumber_cm1"],
            "pinned_rttov_band_offset_K": rt["offset_K"],
            "pinned_rttov_band_slope": rt["slope"],
            "slots": slot_records,
        }

    # Preserve the requested IR133 distinction: v3.0 source pair is used for
    # the KMA map; RTTOV here remains the installed v3.1-shifted coefficient.
    ir133_ship_wn = float(new_doc["channels"]["ir133"]["bt_wavenumber_cm1"])
    ir133_rt_wn = channels_rt["ir133"]["wavenumber_cm1"]
    result = {
        "status": "COMPLETE_CONDITIONAL_COORDINATE_COMPARISON",
        "scope": {
            "channels": list(CHANNELS),
            "observation_pixel_zero_based_row_column": [411, 338],
            "observation_slots": [s["timestamp"] for s in obs_doc["slots"]],
            "window": "retained 3x3 source pixels; preserve existing decoder DQ/missingness; no QC relaxation",
            "radiance_unit": "retained AMI/RTTOV spectral-radiance numeric convention, mW m-2 sr-1 (cm-1)-1",
            "ir133_kma_source_pairing": "KMA v3.0 center wavenumber paired with retained legacy polynomial; RTTOV comparison uses installed v3.1-shifted coefficient",
            "ir133_srf_version_certified_physical": False,
            "global_physical_calibration_approval": False,
            "conditional_residuals_are_not": ["calibrated observation-error covariance", "5 km footprint validation", "physical/SRF approval"],
        },
        "model_configuration": {
            "nc_direction": "0.01*NC; all other state/forcing held fixed",
            "h": h,
            "rttov_channel_list": channel_list,
            "quality_unchanged": bool(dom32_doc.get("quality_unchanged", False)),
            "all_saved_endpoint_quality_zero": True,
            "public_dom32_bt_arrays_equal_direct_text_bt": direct_bt_equal_npz,
            "ir133_kma_v3_0_wavenumber_cm1": ir133_ship_wn,
            "ir133_pinned_rttov_v3_1_wavenumber_cm1": ir133_rt_wn,
            "source_calibration_version_physical_certification": False,
        },
        "provenance": {
            "source_path": str(Path(__file__).resolve()),
            "source_sha256": file_sha(Path(__file__).resolve()),
            "cli_argv": sys.argv,
            "input_hashes": {k: file_sha(v) for k, v in in_paths.items() if k != "output"},
            "source_paths": {k: str(v) for k, v in in_paths.items()},
        },
        "observed_channel_transform_and_window_statistics": observed_records,
        "model_base_plus_minus_radiance_bt_and_residuals": model_records,
        "nc_jvp_coordinate_transforms": tangent_records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "output": str(args.output),
                      "sha256": file_sha(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
