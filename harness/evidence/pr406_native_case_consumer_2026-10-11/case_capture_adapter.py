"""Explicit case-input boundary for the unchanged single-column capture body.

Only value/provenance validation is adapted on a fresh module instance.
The M/H, objective, optimizer, final audit and checkpoint writer are unchanged.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
PACKET = Path(__file__).resolve().parent
CAPTURE = ROOT / "harness/evidence/pr395_tq_state_capture_2026-10-10/capture_tq_state.py"
INTAKE = PACKET / "intake_native_case_v2.py"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    spec.loader.exec_module(module)
    return module


def prepare_capture_module():
    """Return isolated legacy capture with a strict case-specific I/O validator."""
    capture = load_module(CAPTURE, "native_case_capture_isolated")
    intake = load_module(INTAKE, "native_case_binding_intake")
    pinned = {str(p): sha(p) for p in (CAPTURE, INTAKE, Path(__file__), PACKET / "run_case_analysis.py")}
    original_snapshot = capture._source_snapshot

    def source_snapshot():
        current = {path: sha(Path(path)) for path in pinned}
        if current != pinned:
            raise ValueError("case adapter/capture source changed after preflight")
        return {**original_snapshot(), **current}

    def validate_binding(xb, forcings, context_path, context_sha, npz_path, npz_sha):
        if sha(context_path) != context_sha or sha(npz_path) != npz_sha:
            raise ValueError("case intake manifest/NPZ differs from caller-pinned input")
        manifest, arrays = intake.load_bound_intake(context_path, npz_path)
        native = manifest["native_run"]
        case_path = Path(manifest["case_json"]["path"])
        case = intake.validate_case(json.loads(case_path.read_text()))
        if (native["run_id"] != case["native"]["run_id"]
                or native["background_valid_time"] != case["native"]["background_valid_time"]
                or native["nominal_obs_model_time"] != case["observation"]["nominal_obs_model_time"]
                or native["exit_code"] != 0 or native["experiment_valid"] is not True
                or native["model_completed"] is not True):
            raise ValueError("case/native run and time identity differ")
        capture._require_finite_state(xb, label="case_native_background")
        state_hash = capture.state_sha256(xb)
        if state_hash != {f: capture.array_sha256(arrays[f"background_initial_state__{f}"]) for f in capture.STATE_FIELDS}:
            raise ValueError("State differs from case-bound native background")
        if len(forcings) != 1:
            raise ValueError("case study requires one declared frozen 20-second forcing")
        capture._require_finite_forcing(forcings[0], label="case_native_forcing")
        forcing_hash = capture.forcing_sha256(forcings[0])
        if forcing_hash != {f: capture.array_sha256(arrays[f"forcing_window_0__{f}"]) for f in capture.FORCING_FIELDS}:
            raise ValueError("Forcing differs from case-bound native background")
        if not torch.equal(torch.as_tensor(arrays["p_centers_native_bottomup_Pa"], dtype=torch.float64), forcings[0].p.reshape(-1)):
            raise ValueError("native centers differ from case Forcing.p")
        mass = arrays["host_dry_mass_background_kg_m2"]
        if mass.shape != (39,) or mass.dtype != np.float32 or not np.isfinite(mass).all() or np.any(mass <= 0):
            raise ValueError("background host eta dry mass must be positive f32[39]")
        coordinates = {}
        definitions = {
            "native_p_centers_bottomup": ("p_centers_native_bottomup_Pa", "Pa", "bottom-up", "native float64-first P+PB"),
            "native_p_half_calc_p8w_bottomup_real4": ("p_half_native_bottomup_Pa", "Pa", "bottom-up", "REAL(4)-transcribed calc_p8w"),
            "PH_raw_native_bottomup": ("PH_raw_native_bottomup", "m2 s-2", "bottom-up", "raw geopotential PH"),
            "PHB_raw_native_bottomup": ("PHB_raw_native_bottomup", "m2 s-2", "bottom-up", "raw base geopotential PHB"),
            "p_lay_rttov_topdown": ("p_lay_rttov_topdown_hPa", "hPa", "top-down", "RTTOV native-preserving grid"),
            "p_half_rttov_topdown": ("p_half_rttov_topdown_hPa", "hPa", "top-down", "RTTOV native-preserving interfaces"),
        }
        for name, (key, units, orientation, method) in definitions.items():
            a = np.ascontiguousarray(arrays[key])
            coordinates[name] = {"units": units, "orientation": orientation, "source": method,
                                 "shape": list(a.shape), "dtype": str(a.dtype),
                                 "sha256": hashlib.sha256(a.tobytes()).hexdigest(), "values": a}
        selected_times = native["selected_times"]
        mass_summary = {"source_key": "host_dry_mass_background_kg_m2", "shape": [39], "dtype": "float32",
                        "units": "kg dry air m-2 per native eta layer", "orientation": "bottom-up native levels",
                        "sha256_raw_dtype_bytes": hashlib.sha256(np.ascontiguousarray(mass).tobytes()).hexdigest(),
                        "window_source_key": "native_window_host_dry_mass_kg_m2",
                        "window_shape": list(arrays["native_window_host_dry_mass_kg_m2"].shape),
                        "background_matches_window_frame_0": True,
                        "formula": "-(C1H*(MU+MUB)+C2H)*DNW/9.81 with retained REAL(4) operations"}
        binding = {"path": str(Path(context_path).resolve()), "sha256": context_sha,
                   "npz_path": str(Path(npz_path).resolve()), "npz_sha256": npz_sha,
                   "manifest_schema": manifest["schema"], "manifest_status": manifest["status"],
                   "case_id": manifest["case_id"], "case_json_sha256": manifest["case_json"]["sha256"],
                   "background_time": native["background_valid_time"],
                   "expected_saved_times": selected_times, "actual_saved_times": selected_times,
                   "selected_column": native["selected_column"],
                   "clock": {"obs_time": 1, "dt_s": 20, "pixel_time_verified": False,
                             "nominal_slot_utc": native["nominal_obs_model_time"],
                             "forcing_hypothesis": "one native-background forcing held for one local KDM20s step"},
                   "state_time_mapping": {
                       "0": {"time": native["background_valid_time"], "source": "SAVED_NATIVE_BACKGROUND"},
                       "1": {"time": native["nominal_obs_model_time"], "source": "DERIVED_LOCAL_M_SLOT_NOT_SAVED_HOST"}},
                   "host_dry_mass_background": mass_summary, "initial_state_sha256": state_hash,
                   "forcing_window_0_sha256": forcing_hash,
                   "science_approved": False, "analysis_executed_at_intake": False}
        return binding, coordinates, arrays, manifest

    capture._validate_intake_binding = validate_binding
    capture._source_snapshot = source_snapshot
    capture.case_adapter_source_binding = pinned
    return capture
