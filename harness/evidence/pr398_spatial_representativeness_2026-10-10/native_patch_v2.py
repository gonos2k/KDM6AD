#!/usr/bin/env python3
"""Predeclare and extract a bounded 3x3 native KDM6 column patch.

Default invocation writes NATIVE_PATCH.json only. --extract-once reads only
selected NetCDF hyperslabs at saved frames 1/4/6. It never calls M or H.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import time

import netCDF4
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "oracle"))
PACKET = ROOT / "harness/evidence/pr398_spatial_representativeness_2026-10-10"
OUT = ROOT / "graphify-out/pr398-spatial-representativeness-v2-2026-10-10"
PRIVATE = OUT / "private"
PLAN_PATH = PACKET / "NATIVE_PATCH_v2.json"
GEOGRAPHY_PATH = PACKET / "NATIVE_PATCH_GEOGRAPHY.json"
STARTED = PRIVATE / "STARTED_ONCE_v2.json"
NPZ_PATH = PRIVATE / "native_patch_3x3_frames_1_4_6_v2.npz"
RESULT_PATH = PACKET / "NATIVE_PATCH_RESULT_v2.json"
SUMMARY_PATH = PACKET / "NATIVE_PATCH_SUMMARY_v2.md"
FAILURE_PATH = PRIVATE / "FAILED_v2.json"
COMMON_PLAN = PACKET / "PREDECLARED.json"
INTAKE_MANIFEST = ROOT / "harness/evidence/pr395_native_tq_intake_2026-10-10/INTAKE.json"
INTAKE_NPZ = ROOT / "graphify-out/pr395-native-tq-intake-2026-10-10/private/native_column_8frame.npz"
OBS_RECEIPT = ROOT / "harness/evidence/pr395_observation_matchup_2026-10-10/RECEIPT.json"
VIIRS_GEOMETRY = ROOT / "harness/evidence/VIIRS_geometry_result_2026-10-07.json"
INTAKE_SOURCE = ROOT / "harness/evidence/pr395_native_tq_intake_2026-10-10/intake_native_tq.py"
READER_SOURCE = ROOT / "harness/evidence/native358_artifact_diag_2026-10-08/recipe/run_native_kma_bt_frames.py"
THERMO_SOURCE = ROOT / "oracle/kdm6/thermo.py"
CONSTANTS_SOURCE = ROOT / "oracle/kdm6/constants.py"
REGISTRY_SOURCE = Path("/private/tmp/KDM6AD-viirs-native-run-20261007/isolated_project/host/KIM-meso_v1.0/Registry/Registry.EM_COMMON")
CANONICAL_DIR = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/pr398_sensitivity_20261010")
CANONICAL_NPZ = CANONICAL_DIR / "native_patch_3x3_frames_1_4_6_v2.npz"
FRAME_INDICES = (1, 4, 6)
EXPECTED_TIMES = ("2025-07-19_05:56:00", "2025-07-19_05:57:00", "2025-07-19_05:57:40")
J_INDICES = (85, 86, 87)
I_INDICES = (47, 48, 49)
STATE_FIELDS = ("th", "qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg")
HYDROMETEOR_RAW = ("QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP")
NUMBER_RAW = ("QNCCN", "QNCLOUD", "QNICE", "QNRAIN", "QIB")
SURFACE_RAW = ("XLAND", "TSK", "T2", "Q2", "U10", "V10", "HGT", "MU", "MUB", "XLAT", "XLONG")
SURFACE_KEYS = {
    "XLAND": "xland", "TSK": "TSK", "T2": "T2", "Q2": "Q2",
    "U10": "U10", "V10": "V10", "HGT": "HGT", "MU": "MU", "MUB": "MUB",
    "XLAT": "latitude_deg", "XLONG": "longitude_deg", "SEAICE": "seaice",
}
F64 = {"dtype": torch.float64}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def array_sha256(value) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import source module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_common_plan() -> tuple[dict, dict, dict, Path]:
    common = json.loads(COMMON_PLAN.read_text())
    intake = json.loads(INTAKE_MANIFEST.read_text())
    geometry = json.loads(GEOGRAPHY_PATH.read_text())
    observation = json.loads(OBS_RECEIPT.read_text())
    if (common.get("schema") != "pr398.fixed_candidate_spatial_diagnostic.v1"
            or common.get("no_new_native_run") is not True
            or common.get("no_M_H_or_optimization") is not True
            or common.get("no_new_observation_or_model_acquisition") is not True
            or common.get("native", {}).get("saved_frame_indices") != [1, 4, 6]
            or common.get("native", {}).get("j_indices") != [85, 86, 87]
            or common.get("native", {}).get("i_indices") != [47, 48, 49]):
        raise ValueError("common parent spatial predeclaration differs from fixed native patch")
    if (intake.get("schema") != "pr395_native_tq_intake_v1"
            or intake.get("status") != "READY_VALID_NATIVE_INTAKE"
            or intake.get("science_approved") is not False
            or intake.get("selected_column") != {"j": 86, "i": 48, "levels": 39}
            or intake.get("native_run", {}).get("actual_saved_times") != list(
                json.loads(INTAKE_MANIFEST.read_text())["native_run"]["expected_saved_times"])):
        raise ValueError("accepted native intake identity or time contract differs")
    run_dir = Path(intake["native_run"]["run_directory"])
    if run_dir.name != intake["native_run"]["run_id"]:
        raise ValueError("intake archive path/run ID mismatch")
    geo_plan_hash = hashlib.sha256(COMMON_PLAN.read_bytes()).hexdigest()
    if geometry.get("common_predeclared_sha256") != geo_plan_hash:
        raise ValueError("geometry-only selected-coordinate packet is bound to another common plan")
    if observation.get("schema") != "pr395_observation_matchup_receipt_v1":
        raise ValueError("fixed observation receipt schema changed")
    return common, intake, geometry, run_dir


def _source_bindings() -> dict:
    paths = {
        "native_patch_driver": Path(__file__).resolve(),
        "intake_consumer": INTAKE_SOURCE,
        "selected_frame_reader": READER_SOURCE,
        "kdm6_thermo": THERMO_SOURCE,
        "kdm6_constants": CONSTANTS_SOURCE,
        "wrf_registry": REGISTRY_SOURCE,
        "observation_receipt": OBS_RECEIPT,
        "viirs_geometry_result": VIIRS_GEOMETRY,
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"pinned source/provenance files are missing: {missing}")
    return {name: {"path": str(path), "sha256": sha256(path)} for name, path in paths.items()}


def _plan_payload() -> dict:
    common, intake, geometry, run_dir = _check_common_plan()
    sources = _source_bindings()
    archive_run = intake["native_run"]
    return {
        "schema": "pr398_native_patch_plan_v2",
        "status": "PREDECLARED_NO_STATE_DIAGNOSTICS",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scope": "bounded 3x3 native selected-column patch from an already accepted forecast; no M/H, optimization, new run, reanalysis, or acquisition",
        "common_predeclaration_path": str(COMMON_PLAN.relative_to(ROOT)),
        "common_predeclaration_sha256": sha256(COMMON_PLAN),
        "native_intake": {
            "manifest_path": str(INTAKE_MANIFEST.relative_to(ROOT)),
            "manifest_sha256": sha256(INTAKE_MANIFEST),
            "npz_path": str(INTAKE_NPZ), "npz_sha256": sha256(INTAKE_NPZ),
            "run_id": archive_run["run_id"], "run_directory": str(run_dir),
            "forecast_path": archive_run["forecast_path"],
            "forecast_sha256": None,
            "forecast_stat_at_intake": archive_run["forecast_stat_after"],
            "forecast_integrity_contract": "reuse existing runner validity/identity and intake receipt; selected hyperslabs only; no multi-gigabyte whole-file hash",
        },
        "reconstruction_provenance": {
            "selected_reader": {"path": intake["model_data_provenance"]["reader_path"],
                                "sha256": intake["model_data_provenance"]["reader_sha256"],
                                "function": "selected_frame; formulas replicated for neighbor cells without its center-ocean-only reject"},
            "temperature": intake["model_data_provenance"]["temperature"],
            "water_vapor": intake["model_data_provenance"]["water_vapor"],
            "cloud_fields": intake["model_data_provenance"]["cloud_fields"],
            "center_pressure": intake["model_data_provenance"]["center_pressure"],
            "interface_pressure": intake["model_data_provenance"]["native_interface_pressure"],
            "host_dry_mass": intake["model_data_provenance"]["host_dry_mass"],
            "registry_source": {"path": str(REGISTRY_SOURCE), "sha256": sha256(REGISTRY_SOURCE),
                                "water_species_units": "Registry labels kg kg-1; dry/moist denominator basis not specified in this receipt",
                                "number_species_units": "Registry labels # kg-1; dry/moist denominator basis not specified",
                                "qib_units": "m3 kg-1"},
            "physical_temperature_formula": "T_K = th*pii; th from (THM+300)/(1+(Rv/Rd)*QVAPOR), selected_frame convention",
            "rho_d_formula": "p_pa/(Rd*(THM+300)*pii), selected_frame convention",
            "p_center_formula": "float64-first P+PB",
            "p8w_formula": "reader.p8w_for_column REAL(4) transcription of pinned calc_p8w; not executed host output",
            "delz_formula": "((PH+PHB)/g)[k+1]-((PH+PHB)/g)[k], selected_frame convention",
        },
        "selection": {
            "center_j_i_zero_based": [86, 48],
            "j_indices": list(J_INDICES), "i_indices": list(I_INDICES),
            "saved_frame_indices": list(FRAME_INDICES), "saved_times": list(EXPECTED_TIMES),
            "vertical_levels": 39, "interface_levels": 40,
            "orientation": "WRF j/i, bottom-up vertical; arrays do not remap or select a replacement column",
            "sampling": "all nine fixed cells at each of the same three predeclared saved frames",
        },
        "read_contract": {
            "mask_fill_finite_checks_before_ndarray_conversion": True,
            "state_variables": list(load_module(INTAKE_SOURCE, "pr398_patch_intake_fields").RAW_STATE_FIELDS),
            "selected_3d_slices": "only ds[name][time_index,:,j,i] for each of nine fixed cells",
            "interface_slices": "only PH/PHB [time_index,:,j,i] for 40 interfaces at each cell",
            "surface_slices": "only selected XLAND/SEAICE/TSK/T2/Q2/U10/V10/HGT/MU/MUB/XLAT/XLONG scalars",
            "vertical_coefficients": "FNM/FNP/C1H/C2H/DNW vectors of 39 values once per frame",
            "p8w": "authoritative archived reader p8w_for_column per cell; Python REAL(4) transcription, not an executed host output",
            "duplicate_small_reads": "P/PB/PH/PHB hyperslabs are re-read inside p8w_for_column; no single-read claim",
            "center_crosscheck": "j86/i48 arrays must equal existing PR395 intake arrays at frames 1/4/6 before publication",
        },
        "planned_arrays": {
            "native_patch__wrf_raw__<THM,QVAPOR,QCLOUD,QRAIN,QICE,QSNOW,QGRAUP,QNCCN,QNCLOUD,QNICE,QNRAIN,QIB>": "[3,3,3,39] float64",
            "native_patch__wrf_raw__P/PB": "[3,3,3,39] source float32",
            "native_patch__wrf_raw__PH/PHB": "[3,3,3,40] source float32",
            "native_patch__state__<12 KDM6 fields>": "[3,3,3,39] float64; th follows selected_frame THM/QVAPOR conversion",
            "native_patch__temperature_K": "[3,3,3,39] float64, th*pii",
            "native_patch__p_centers_native_bottomup_Pa": "[3,3,3,39] float64-first P+PB; same values as Forcing.p",
            "native_patch__p_half_calc_p8w_bottomup_Pa": "[3,3,3,40] float32 REAL(4) transcription",
            "native_patch__delz/rho_d/rho_m/pii": "[3,3,3,39] float64; selected_frame formulas",
            "native_patch__host_dry_mass_kg_m2": "[3,3,3,39] float32; host eta measure -(C1H*(MU+MUB)+C2H)*DNW/9.81",
            "native_patch__surface__<fields>": "[3,3,3] selected scalar surface and XLAND/SEAICE/geolocation values",
            "native_patch__vertical_coeff__<FNM,FNP,C1H,C2H,DNW>": "[3,39] source float32",
        },
        "diagnostic_table_contract": {
            "per_cell_metrics": ["KDM6 phase-aware max qv/qs ratio and layer", "liquid-only qv/qs_water max and layer", "qv maximum", "temperature min/max", "nonzero QC/QC max/unweighted-level QC sum", "NC raw max/nonzero-count/unweighted-level sum", "all hydrometeor raw maxima and nonzero counts", "surface and class fields"],
            "maxsat_semantics": "KDM6 thermo.compute_qs_ice phase-aware qv/qs diagnostic; also report qv/qs_water; neither is claimed as observed vapor-pressure RH",
            "qc_sum_semantics": "unweighted native-level QC sum is not LWP, not a path integral, and not a water budget",
            "number_units": "Registry raw QN fields retained; # kg-1 basis not specified dry-vs-moist; QIB m3 kg-1; no calibration/conversion claim",
            "mass_weighting": "host eta dry mass retained; no mass-weighted water path is reported",
        },
        "geography_only_source": {
            "path": str(GEOGRAPHY_PATH.relative_to(ROOT)),
            "sha256": sha256(GEOGRAPHY_PATH),
            "viirs_region_filter": "center-in-axis-aligned-bounds-of-native-3x3-centers; descriptive only, not nine-cell union or physical footprint",
        },
        "source_sha256": sources,
        "outputs": {
            "private_npz": str(NPZ_PATH),
            "canonical_private_npz": str(CANONICAL_NPZ),
            "public_result": str(RESULT_PATH.relative_to(ROOT)),
            "public_summary": str(SUMMARY_PATH.relative_to(ROOT)),
            "no_overwrite_or_retry": True,
        },
        "execution": {"M_calls": 0, "H_calls": 0, "optimizer_calls": 0,
                      "forecast_relaunch": False, "external_acquisition": False,
                      "actual_arrays_read_at_predeclaration": False},
    }


def write_plan() -> None:
    if PLAN_PATH.exists():
        raise FileExistsError(f"refusing to overwrite {PLAN_PATH}")
    payload = _plan_payload()
    OUT.mkdir(mode=0o700, parents=True, exist_ok=False)
    OUT.chmod(0o700)
    PRIVATE.mkdir(mode=0o700)
    PRIVATE.chmod(0o700)
    payload["native_patch_driver_sha256"] = sha256(Path(__file__))
    with PLAN_PATH.open("x") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    PLAN_PATH.chmod(0o644)
    print(json.dumps({"status": payload["status"], "plan": str(PLAN_PATH),
                      "plan_sha256": sha256(PLAN_PATH), "NPZ_written": False,
                      "native_forecast_opened": False}, indent=2))


def _load_plan() -> tuple[dict, dict, dict, Path, dict]:
    if not PLAN_PATH.is_file():
        raise FileNotFoundError(f"run the no-read plan phase first: {PLAN_PATH}")
    plan = json.loads(PLAN_PATH.read_text())
    current = _plan_payload()
    if plan.get("status") != "PREDECLARED_NO_STATE_DIAGNOSTICS":
        raise ValueError("native patch plan is not in predeclared state")
    if plan.get("native_patch_driver_sha256") != sha256(Path(__file__)):
        raise ValueError("native patch driver changed after predeclaration")
    comparable = set(current) - {"created_utc"}
    if any(plan.get(key) != current.get(key) for key in comparable):
        raise ValueError("source/input/predeclared native patch contract changed")
    common, intake, geography, run_dir = _check_common_plan()
    return plan, common, intake, run_dir, geography


def _mask_checked(intake, ds, name, raw, shape, ti, j=None, i=None):
    return intake._check_selected_hyperslab(
        ds[name], raw, expected_shape=shape, time_index=ti, j=j, i=i)


def _read_cell(ds, intake, reader, ti: int, j: int, i: int,
               vertical: dict[str, np.ndarray]) -> dict:
    location = f"Time={ti}, j={j}, i={i}"
    raw = {}
    for name in reader.STATE_VARS:
        values = _mask_checked(intake, ds, name, ds[name][ti, :, j, i], (39,), ti, j, i)
        raw[name] = np.asarray(values, dtype=np.float64)
    p_raw = _mask_checked(intake, ds, "P", ds["P"][ti, :, j, i], (39,), ti, j, i)
    pb_raw = _mask_checked(intake, ds, "PB", ds["PB"][ti, :, j, i], (39,), ti, j, i)
    ph_raw = _mask_checked(intake, ds, "PH", ds["PH"][ti, :, j, i], (40,), ti, j, i)
    phb_raw = _mask_checked(intake, ds, "PHB", ds["PHB"][ti, :, j, i], (40,), ti, j, i)
    surface_raw = {}
    for name in SURFACE_RAW:
        surface_raw[name] = _mask_checked(
            intake, ds, name, ds[name][ti, j, i], (), ti, j, i)
    if "SEAICE" in ds.variables:
        surface_raw["SEAICE"] = _mask_checked(
            intake, ds, "SEAICE", ds["SEAICE"][ti, j, i], (), ti, j, i)
    p_pa = np.asarray(p_raw, dtype=np.float64) + np.asarray(pb_raw, dtype=np.float64)
    qv = raw["QVAPOR"]
    thm = raw["THM"] + reader.T0
    pii = np.power(p_pa / reader.P0, reader.RCP)
    th = thm / (1.0 + (reader.R_V / reader.R_D) * qv)
    temperature = th * pii
    rho_d = p_pa / (reader.R_D * thm * pii)
    rho_m = rho_d * (1.0 + qv)
    ph64, phb64 = np.asarray(ph_raw, dtype=np.float64), np.asarray(phb_raw, dtype=np.float64)
    z_w = (ph64 + phb64) / float(reader.G)
    delz = z_w[1:] - z_w[:-1]
    mu, mub = np.float32(surface_raw["MU"]), np.float32(surface_raw["MUB"])
    c1h, c2h, dnw = (np.asarray(vertical[name], dtype=np.float32)
                     for name in ("C1H", "C2H", "DNW"))
    host_mass = (-(c1h * (mu + mub) + c2h) * dnw / np.float32(9.81)).astype(np.float32)
    p8w = reader.p8w_for_column(ds, ti, j, i)
    if (not np.isfinite(p_pa).all() or not np.isfinite(p8w).all()
            or not np.isfinite(delz).all() or not np.isfinite(host_mass).all()
            or np.any(host_mass <= 0.0) or not np.isfinite(rho_d).all()
            or not np.isfinite(temperature).all()):
        raise FloatingPointError(f"non-finite/invalid derived selected data at {location}")
    surface = {SURFACE_KEYS[name]: float(np.asarray(value))
               for name, value in surface_raw.items() if name in SURFACE_KEYS}
    return {
        "raw_state": raw,
        "P_raw": np.asarray(p_raw).copy(), "PB_raw": np.asarray(pb_raw).copy(),
        "PH_raw": np.asarray(ph_raw).copy(), "PHB_raw": np.asarray(phb_raw).copy(),
        "p_pa": p_pa, "p8w_pa": np.asarray(p8w, dtype=np.float32),
        "thm_moist_potential_K": thm, "th": th, "pii": pii,
        "temperature_K": temperature, "rho_d": rho_d, "rho_m": rho_m,
        "delz": delz, "host_dry_mass_kg_m2": host_mass,
        "surface": surface,
    }


def _read_patch_frame(ds, intake, reader, ti: int, expected_time: str) -> tuple[dict, dict]:
    time_values = ds["Times"][ti]
    if np.ma.is_masked(time_values):
        raise ValueError(f"Times mask at frame {ti}")
    actual_time = time_values.tobytes().decode("ascii").strip()
    if actual_time != expected_time:
        raise ValueError(f"Time {ti}={actual_time} differs from predeclared {expected_time}")
    if int(getattr(ds, "USE_THETA_M", 0)) != 1:
        raise ValueError("native patch reconstruction requires USE_THETA_M=1")
    vertical = {}
    for name in ("FNM", "FNP", "C1H", "C2H", "DNW"):
        vertical[name] = np.asarray(_mask_checked(
            intake, ds, name, ds[name][ti, :], (39,), ti), dtype=np.float32).copy()
    cells = []
    for j in J_INDICES:
        row = []
        for i in I_INDICES:
            row.append(_read_cell(ds, intake, reader, ti, j, i, vertical))
        cells.append(row)
    frame = {"frame_index": ti, "time": actual_time, "cells": cells, "vertical": vertical}
    return frame, vertical


def _stack_cells(frames: list[dict], getter) -> np.ndarray:
    return np.stack([
        np.stack([
            np.stack([getter(cell) for cell in row], axis=0)
            for row in frame["cells"]
        ], axis=0)
        for frame in frames
    ], axis=0)


def _pack_arrays(frames: list[dict], intake_arrays: dict[str, np.ndarray]) -> tuple[dict, dict]:
    arrays = {
        "frame_indices": np.asarray(FRAME_INDICES, dtype=np.int32),
        "time_labels_ascii": np.asarray([f["time"].encode("ascii") for f in frames], dtype="S19"),
        "j_indices": np.asarray(J_INDICES, dtype=np.int32),
        "i_indices": np.asarray(I_INDICES, dtype=np.int32),
    }
    for raw_name in (*reader_state_vars(), "P", "PB", "PH", "PHB"):
        key = "P_raw" if raw_name == "P" else "PB_raw" if raw_name == "PB" else \
              "PH_raw" if raw_name == "PH" else "PHB_raw" if raw_name == "PHB" else None
        arrays[f"native_patch__wrf_raw__{raw_name}"] = _stack_cells(
            frames, lambda c, name=raw_name, rawkey=key:
                c[rawkey] if rawkey is not None else c["raw_state"][name])
    for state_name in STATE_FIELDS:
        if state_name == "th":
            arrays[f"native_patch__state__{state_name}"] = _stack_cells(
                frames, lambda c: c["th"])
        else:
            raw_name = intake_state_to_raw()[state_name]
            arrays[f"native_patch__state__{state_name}"] = _stack_cells(
                frames, lambda c, name=raw_name: c["raw_state"][name])
    for field in ("p_pa", "temperature_K", "thm_moist_potential_K", "pii",
                  "rho_d", "rho_m", "delz"):
        arrays[f"native_patch__{field}"] = _stack_cells(frames, lambda c, name=field: c[name])
    arrays["native_patch__p_centers_native_bottomup_Pa"] = arrays["native_patch__p_pa"].copy()
    arrays["native_patch__rho"] = arrays["native_patch__rho_m"].copy()
    arrays["native_patch__p_half_calc_p8w_bottomup_Pa"] = _stack_cells(
        frames, lambda c: c["p8w_pa"])
    arrays["native_patch__host_dry_mass_kg_m2"] = _stack_cells(
        frames, lambda c: c["host_dry_mass_kg_m2"])
    surface_fields = sorted(set(key for frame in frames for row in frame["cells"]
                                for cell in row for key in cell["surface"]))
    for key in surface_fields:
        arrays[f"native_patch__surface__{key}"] = _stack_cells(
            frames, lambda c, name=key: np.asarray(c["surface"][name], dtype=np.float64))
    for name in ("FNM", "FNP", "C1H", "C2H", "DNW"):
        arrays[f"native_patch__vertical_coeff__{name}"] = np.stack(
            [frame["vertical"][name] for frame in frames], axis=0)
    for key, value in arrays.items():
        if isinstance(value, np.ndarray) and value.dtype.kind in "f" and not np.isfinite(value).all():
            raise FloatingPointError(f"packed native patch array is non-finite: {key}")
    _check_center_equals_intake(arrays, intake_arrays)
    return arrays, _array_specs(arrays)


def reader_state_vars() -> tuple[str, ...]:
    reader = load_module(READER_SOURCE, "pr398_patch_reader_state_fields")
    return tuple(reader.STATE_VARS)


def intake_state_to_raw() -> dict[str, str]:
    module = load_module(INTAKE_SOURCE, "pr398_patch_intake_state_map")
    return dict(module.STATE_TO_RAW)


def _check_center_equals_intake(arrays: dict, intake_arrays: dict[str, np.ndarray]) -> None:
    for frame_pos, ti in enumerate(FRAME_INDICES):
        for name in STATE_FIELDS:
            if not np.array_equal(arrays[f"native_patch__state__{name}"][frame_pos, 1, 1],
                                  intake_arrays[f"native_window_state__{name}"][ti]):
                raise ValueError(f"native patch center State.{name} differs from bound intake at frame {ti}")
        for field in ("rho", "pii", "p", "delz"):
            key = {"rho": "rho", "pii": "pii", "p": "p_pa", "delz": "delz"}[field]
            packed = arrays[f"native_patch__{key}"][frame_pos, 1, 1]
            if not np.array_equal(packed, intake_arrays[f"native_window_forcing__{field}"][ti]):
                raise ValueError(f"native patch center Forcing.{field} differs from bound intake at frame {ti}")
        if not np.array_equal(arrays["native_patch__p_half_calc_p8w_bottomup_Pa"][frame_pos, 1, 1],
                              intake_arrays["native_window_p_half_calc_p8w_bottomup_Pa"][ti]):
            raise ValueError(f"native patch center P8W differs from bound intake at frame {ti}")
        if not np.array_equal(arrays["native_patch__host_dry_mass_kg_m2"][frame_pos, 1, 1],
                              intake_arrays["native_window_host_dry_mass_kg_m2"][ti]):
            raise ValueError(f"native patch center host eta mass differs from bound intake at frame {ti}")
        for raw in reader_state_vars():
            if not np.array_equal(arrays[f"native_patch__wrf_raw__{raw}"][frame_pos, 1, 1],
                                  intake_arrays[f"wrf_raw__{raw}"][ti]):
                raise ValueError(f"native patch center raw {raw} differs from bound intake at frame {ti}")
        for raw,name in (("PH","native_window_PH_raw_bottomup"),("PHB","native_window_PHB_raw_bottomup")):
            if not np.array_equal(arrays[f"native_patch__wrf_raw__{raw}"][frame_pos,1,1],intake_arrays[name][ti]):
                raise ValueError(f"native patch center raw {raw} differs from bound intake at frame {ti}")
        for field in ("TSK", "T2", "Q2", "U10", "V10", "HGT", "xland",
                      "latitude_deg", "longitude_deg", "seaice"):
            intake_key=f"native_surface__{field}"
            patch_key=f"native_patch__surface__{field}"
            if intake_key in intake_arrays and not np.array_equal(
                    arrays[patch_key][frame_pos,1,1],intake_arrays[intake_key][ti]):
                raise ValueError(f"native patch center surface {field} differs from bound intake at frame {ti}")


def _array_specs(arrays: dict[str, np.ndarray]) -> dict:
    return {key: {"shape": list(value.shape), "dtype": str(value.dtype),
                  "sha256": array_sha256(value)}
            for key, value in sorted(arrays.items())}


def _cell_diagnostics(cell: dict) -> dict:
    state = cell["raw_state"]
    p = torch.as_tensor(cell["p_pa"], **F64)
    t = torch.as_tensor(cell["temperature_K"], **F64)
    from kdm6.thermo import compute_qs_ice, compute_qs_water, default_thermo_params
    thermo = default_thermo_params()
    qsi = compute_qs_ice(t, p, params=thermo).detach().cpu().numpy()
    qsw = compute_qs_water(t, p, params=thermo).detach().cpu().numpy()
    phase_ratio = state["QVAPOR"] / np.maximum(qsi, thermo.qmin)
    water_ratio = state["QVAPOR"] / np.maximum(qsw, thermo.qmin)
    hydro = {}
    for name in HYDROMETEOR_RAW:
        values = state[name]
        hydro[name] = {"maximum_raw_kgkg": float(np.max(values)),
                       "positive_level_count": int(np.count_nonzero(values > 0.0)),
                       "unweighted_native_level_sum_raw": float(np.sum(values, dtype=np.float64))}
    numbers = {}
    for name in NUMBER_RAW:
        values = state[name]
        numbers[name] = {"maximum_raw": float(np.max(values)),
                         "positive_level_count": int(np.count_nonzero(values > 0.0)),
                         "unweighted_native_level_sum_raw": float(np.sum(values, dtype=np.float64))}
    surface = dict(cell["surface"])
    return {
        "latitude_deg": surface["latitude_deg"], "longitude_deg": surface["longitude_deg"],
        "surface": surface,
        "temperature_min_K": float(np.min(cell["temperature_K"])),
        "temperature_max_K": float(np.max(cell["temperature_K"])),
        "qv_max_kgkg_dry": float(np.max(state["QVAPOR"])),
        "maxsat_phase_aware_qv_over_qs_percent": float(np.max(phase_ratio) * 100.0),
        "maxsat_phase_aware_layer_bottomup_0based": int(np.argmax(phase_ratio)),
        "maxsat_liquid_qv_over_qs_water_percent": float(np.max(water_ratio) * 100.0),
        "maxsat_liquid_layer_bottomup_0based": int(np.argmax(water_ratio)),
        "phase_metric_interpretation": "KDM6 thermo qv/qs ratio; not observed vapor-pressure/e_es relative humidity",
        "hydrometeors": hydro,
        "nc_raw": numbers["QNCLOUD"],
        "number_fields_raw": numbers,
        "qc_unweighted_sum_is_lwp": False,
        "host_eta_dry_mass_sum_kg_m2": float(np.sum(cell["host_dry_mass_kg_m2"], dtype=np.float64)),
        "host_eta_mass_weighted_water_path_reported": False,
    }


def _array_sha256_file(path: Path) -> str:
    return sha256(path)


def geometry_only() -> None:
    plan=json.loads(PLAN_PATH.read_text())
    current=_plan_payload()
    if (plan.get("native_patch_driver_sha256")!=sha256(Path(__file__))
            or plan.get("common_predeclaration_sha256")!=current["common_predeclaration_sha256"]):
        raise ValueError("native patch predeclaration/source changed")
    if GEOGRAPHY_PATH.exists():
        raise FileExistsError(GEOGRAPHY_PATH)
    print(f"Geometry-only coordinates already recorded in {PACKET/'NATIVE_PATCH_GEOGRAPHY.json'}; do not overwrite.")


def extract_once() -> int:
    plan, common, manifest, run_dir, geometry = _load_plan()
    if STARTED.exists() or NPZ_PATH.exists() or RESULT_PATH.exists() or FAILURE_PATH.exists():
        raise FileExistsError("native patch one-shot extraction was already claimed or published")
    intake = load_module(INTAKE_SOURCE, "pr398_patch_intake")
    reader = load_module(READER_SOURCE, "pr398_patch_reader")
    valid, forecast, identity, run_settings = intake._read_completion_gate(run_dir)
    if str(forecast) != manifest["native_run"]["forecast_path"]:
        raise ValueError("completion gate resolved a different forecast path than the accepted intake")
    expected_all_times = manifest["native_run"]["expected_saved_times"]
    actual_all_times = manifest["native_run"]["actual_saved_times"]
    if (manifest["native_run"]["exit_code"] != 0
            or manifest["native_run"]["experiment_valid"] is not True
            or manifest["native_run"]["model_completed_flag"] is not True
            or actual_all_times != expected_all_times):
        raise ValueError("native intake completion gate or exact full eight-time receipt failed")
    selected_actual_times = [actual_all_times[index] for index in FRAME_INDICES]
    if selected_actual_times != list(common["native"]["times"]):
        raise ValueError("actual saved_times[1,4,6] differ from common predeclared three frame times")
    reader.validate_p8w_source()
    with np.load(INTAKE_NPZ, allow_pickle=False) as archive:
        intake_arrays = {key: archive[key].copy() for key in archive.files}
    npz_sha = sha256(INTAKE_NPZ)
    if npz_sha != manifest["npz"]["sha256"] or npz_sha != plan["native_intake"]["npz_sha256"]:
        raise ValueError("existing intake NPZ changed after native patch predeclaration")
    start_payload = {"status":"STARTED_ONCE","plan_sha256":sha256(PLAN_PATH),
                     "driver_sha256":sha256(Path(__file__)),"intake_npz_sha256":npz_sha,
                     "frames":list(FRAME_INDICES),"cells":9,"M_calls":0,"H_calls":0}
    with STARTED.open("x") as stream:
        json.dump(start_payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    STARTED.chmod(0o600)
    before=forecast.stat()
    frames=[]
    try:
        with netCDF4.Dataset(forecast,"r") as ds:
            dims={name:len(ds.dimensions[name]) for name in ("Time","bottom_top","bottom_top_stag","south_north","west_east")}
            if dims["bottom_top"]!=39 or dims["bottom_top_stag"]!=40 or dims["south_north"]<88 or dims["west_east"]<50:
                raise ValueError(f"native forecast dimensions are incompatible with predeclared 3x3: {dims}")
            if int(getattr(ds,"USE_THETA_M",0))!=1:
                raise ValueError("native patch requires USE_THETA_M=1")
            for ti,expected_time in zip(FRAME_INDICES,EXPECTED_TIMES):
                frame,vertical=_read_patch_frame(ds,intake,reader,ti,expected_time)
                frames.append(frame)
        arrays,array_specs=_pack_arrays(frames,intake_arrays)
        after=forecast.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
            raise RuntimeError("forecast size or mtime changed during bounded patch hyperslab extraction")
        geometry_hash=sha256(GEOGRAPHY_PATH)
        if geometry_hash!=plan["geography_only_source"]["sha256"]:
            raise ValueError("geometry-only source changed during patch extraction")
        # Publish the compact private NPZ exactly once.
        fd=os.open(NPZ_PATH,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as stream:
            np.savez_compressed(stream,**arrays)
        NPZ_PATH.chmod(0o600)
        npz_sha=sha256(NPZ_PATH)
        if CANONICAL_NPZ.exists():
            raise FileExistsError(f"canonical spatial patch already exists: {CANONICAL_NPZ}")
        if not CANONICAL_DIR.is_dir() or stat.S_IMODE(CANONICAL_DIR.stat().st_mode)!=0o700:
            raise PermissionError(f"canonical private directory must exist with mode 0700: {CANONICAL_DIR}")
        fd=os.open(CANONICAL_NPZ,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as dst, NPZ_PATH.open("rb") as src:
            while True:
                block = src.read(1 << 20)
                if not block:
                    break
                dst.write(block)
        CANONICAL_NPZ.chmod(0o600)
        canonical_sha=sha256(CANONICAL_NPZ)
        if canonical_sha!=npz_sha:
            raise IOError("canonical native patch copy SHA differs from private workspace NPZ")
        diagnostics=[]
        for fpos,frame in enumerate(frames):
            for rj,j in enumerate(J_INDICES):
                for ri,i in enumerate(I_INDICES):
                    row={"frame_index":frame["frame_index"],"time":frame["time"],"j":j,"i":i,
                         **_cell_diagnostics(frame["cells"][rj][ri])}
                    diagnostics.append(row)
        serialized_stats={"forecast_stat_before":{"size_bytes":before.st_size,"mtime_ns":before.st_mtime_ns},
                          "forecast_stat_after":{"size_bytes":after.st_size,"mtime_ns":after.st_mtime_ns},
                          "forecast_stat_stable":True,"forecast_sha256":None}
        result={
            "schema":"pr398_native_patch_result_v2","status":"READY_NATIVE_PATCH_DIAGNOSTIC_ONLY",
            "plan_path":str(PLAN_PATH.relative_to(ROOT)),"plan_sha256":sha256(PLAN_PATH),
            "native_patch_driver_sha256":sha256(Path(__file__)),
            "common_predeclaration_sha256":plan["common_predeclaration_sha256"],
            "native_run_id":manifest["native_run"]["run_id"],
            "intake_manifest_sha256":sha256(INTAKE_MANIFEST),"intake_npz_sha256":sha256(INTAKE_NPZ),
            "runner_valid_receipt":valid,"run_identity_sha256":sha256(run_dir/"run_identity.json"),
            "forecast_path":str(forecast),"forecast_sha256":None,"forecast_stats":serialized_stats,
            "selection":{"j_indices":list(J_INDICES),"i_indices":list(I_INDICES),
                         "frame_indices":list(FRAME_INDICES),"times":list(EXPECTED_TIMES),
                         "native_column_center_j_i":[86,48]},
            "private_npz":{"path":str(NPZ_PATH),"sha256":npz_sha,"size_bytes":NPZ_PATH.stat().st_size,
                           "mode":oct(stat.S_IMODE(NPZ_PATH.stat().st_mode)),
                           "array_count":len(arrays),"arrays":array_specs},
            "canonical_npz":{"path":str(CANONICAL_NPZ),"sha256":canonical_sha,
                             "mode":oct(stat.S_IMODE(CANONICAL_NPZ.stat().st_mode)),
                             "directory_mode":oct(stat.S_IMODE(CANONICAL_DIR.stat().st_mode)),
                             "hash_matches_private":canonical_sha==npz_sha},
            "geography_only_source_sha256":geometry_hash,
            "center_matches_intake_at_all_frames":True,
            "diagnostic_table":diagnostics,
            "interpretation_limits":{
                "native_cell_centers_only_bounds_not_physical_footprint":True,
                "viirs_filter":"fixed VIIRS candidate center is described relative to native3x3 center-bounds box; no candidate replacement or footprint overlap claim",
                "qc_unweighted_sum_not_lwp_or_budget":True,
                "number_units_unresolved_basis":True,
                "maxsat_is_kdm6_phase_aware_qv_over_qs_diagnostic_not_observed_RH":True,
                "no_area_weighted_or_spatially_calibrated_R_or_sigma":True,
                "science_admission":"NOT_ASSESSED",
            },
            "M_calls":0,"H_calls":0,"optimizer_calls":0,"retry":False,
        }
        with RESULT_PATH.open("x") as stream:
            json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        RESULT_PATH.chmod(0o644)
        _write_summary(result,geometry)
        print(json.dumps({"status":result["status"],"private_npz":str(NPZ_PATH),
                          "canonical_npz":str(CANONICAL_NPZ),"array_count":len(arrays),
                          "diagnostic_rows":len(diagnostics),"M_H_calls":0},indent=2))
        return 0
    except BaseException as exc:
        failure={"schema":"pr398_native_patch_failure_v2","status":"FAILED_NO_RETRY",
                 "error_type":type(exc).__name__,"error":str(exc),"M_calls":0,"H_calls":0,
                 "retry":False}
        with FAILURE_PATH.open("x") as stream:
            json.dump(failure, stream, indent=2, sort_keys=True)
            stream.write("\n")
        FAILURE_PATH.chmod(0o600)
        raise


def _write_summary(result: dict, geometry: dict) -> None:
    lines=[
        "# PR398 native 3x3 saved-frame spatial diagnostics",
        "",
        "Diagnostic only. The arrays use the fixed native cells j=85..87, i=47..49 at saved frames 1/4/6. No M/H, optimizer, new native run, or external data was used.",
        "",
        f"Private NPZ SHA256: `{result['private_npz']['sha256']}`; canonical copy SHA256: `{result['canonical_npz']['sha256']}`.",
        "",
        "VIIRS region filter is the axis-aligned bounding box of native 3x3 cell centers. The corners below are descriptive bounds of center coordinates only, not cell-edge or sensor footprint corners.",
        "",
        "| Frame/time | Native center-bounds corners (NW, NE, SE, SW; lat/lon deg) | VIIRS candidate center inside |",
        "|---|---|---|",
    ]
    viirs=geometry["viirs_source"]
    corners=geometry["union_bounds_axis_aligned_corners_lat_lon_deg"]
    corner_text="; ".join(f"{k}={v[0]:.6f},{v[1]:.6f}" for k,v in corners.items())
    for ti,t in zip(FRAME_INDICES,EXPECTED_TIMES):
        lines.append(f"| {ti} / {t} | {corner_text} | {viirs['center_in_native_3x3_center_bounds']} |")
    lines.extend([
        "",
        "`maxsat` is the KDM6 phase-aware qv/qs diagnostic, not observed vapor-pressure RH. QC and NC sums are unweighted native-level summaries; unweighted QC sum is not LWP. QN number basis is not calibrated; no mass-weighted LWP or area-weighted matchup score is claimed.",
        "",
        "Per-cell arrays and diagnostics are in the private NPZ/result. These nine cells are not independent 5 km scenes, and the seven-band VIIRS/AMI comparison remains NOT_ASSESSED.",
        "",
    ])
    with SUMMARY_PATH.open("x") as stream:
        stream.write("\n".join(lines))
    SUMMARY_PATH.chmod(0o644)


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument("--plan-only",action="store_true",help="write NATIVE_PATCH.json without opening forecast")
    mode.add_argument("--extract-once",action="store_true",help="read only predeclared selected 3x3 hyperslabs")
    args=parser.parse_args()
    if args.extract_once:
        return extract_once()
    write_plan()
    return 0


if __name__=="__main__":
    raise SystemExit(main())
