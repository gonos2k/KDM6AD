#!/usr/bin/env python3
"""Diagnose saved native/capture arrays without another model or RTTOV call.

The host-minus-local difference includes processes and forcing updates absent
from the local KDM operator. It is neither a microphysics error nor R. Water
increments use the original first-frame host eta dry-mass measure; unknown
boundary and external terms are not filled with zero.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
STATE_FIELDS = ("qv", "qc", "qr", "qi", "qs", "qg", "nc", "ni", "nr", "nccn", "th", "bg")
WATER_FIELDS = ("qv", "qc", "qr", "qi", "qs", "qg")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def diagnose(native, capture):
    """Return derived profiles and scalar summaries on one fixed mass measure."""
    arrays = {}
    for field in STATE_FIELDS:
        host = np.asarray(native[f"native_window_state__{field}"], dtype=np.float64)[1]
        local = np.asarray(capture[f"background_slot_state__{field}"], dtype=np.float64).reshape(-1)
        if host.shape != (39,) or local.shape != host.shape:
            raise ValueError(f"invalid host/local shape for {field}")
        arrays[f"host_minus_local__{field}"] = host - local
    pi0 = np.asarray(native["native_window_forcing__pii"], dtype=np.float64)[0]
    pi1 = np.asarray(native["native_window_forcing__pii"], dtype=np.float64)[1]
    th_local = np.asarray(capture["background_slot_state__th"], dtype=np.float64).reshape(-1)
    th_host = np.asarray(native["native_window_state__th"], dtype=np.float64)[1]
    arrays["temperature_difference_K"] = pi1 * th_host - pi0 * th_local
    arrays["temperature_theta_term_K"] = pi1 * (th_host - th_local)
    arrays["temperature_exner_term_K"] = th_local * (pi1 - pi0)
    arrays["temperature_identity_residual_K"] = (
        arrays["temperature_difference_K"] - arrays["temperature_theta_term_K"]
        - arrays["temperature_exner_term_K"])
    raw_weights = np.asarray(native["native_window_host_dry_mass_kg_m2"])
    if raw_weights.shape != (8, 39) or raw_weights.dtype != np.dtype("float32"):
        raise ValueError("expected original float32 host eta dry-mass array [8,39]")
    weights = raw_weights[0].astype(np.float64)
    if not np.all(np.isfinite(weights)) or not np.all(weights > 0):
        raise ValueError("invalid fixed host dry-mass weights")
    arrays["fixed_host_dry_mass_kg_m2"] = raw_weights[0].copy()
    water = {}
    for label, prefix in (("xb", "background_initial_state"),
                          ("xa", "returned_analysis_initial_state"),
                          ("mb", "background_slot_state"), ("ma", "final_slot_state")):
        water[label] = sum(np.asarray(capture[f"{prefix}__{f}"], dtype=np.float64).reshape(-1)
                           for f in WATER_FIELDS)
    increments = {
        "analysis": water["xa"] - water["xb"],
        "model_analysis": water["ma"] - water["xa"],
        "model_background": water["mb"] - water["xb"],
        "slot_analysis_minus_background": water["ma"] - water["mb"],
    }
    totals = {}
    for label, values in increments.items():
        arrays[f"water_increment__{label}_kg_m2_per_layer"] = weights * values
        totals[label] = float(np.sum(weights * values))
    totals["decomposition_identity_residual"] = (
        totals["slot_analysis_minus_background"] - totals["analysis"]
        - totals["model_analysis"] + totals["model_background"])
    if not all(np.isfinite(a).all() for a in arrays.values()):
        raise FloatingPointError("non-finite derived diagnostic")
    return arrays, {
        "water_increments_kg_m2": totals,
        "temperature_identity_max_abs_residual_K": float(np.max(np.abs(
            arrays["temperature_identity_residual_K"]))),
        "host_minus_local_max_abs_by_field": {
            f: float(np.max(np.abs(arrays[f"host_minus_local__{f}"]))) for f in STATE_FIELDS},
        "temperature_difference_max_abs_K": float(np.max(np.abs(arrays["temperature_difference_K"]))),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = json.loads(args.capture_receipt.read_text())
    if receipt.get("status") != "RETURNED_DIAGNOSTIC_ONLY":
        raise ValueError("a completed capture receipt is required")
    binding = receipt["native_intake_context"]
    checkpoint = receipt["private_checkpoint"]
    native_path, capture_path = Path(binding["npz_path"]), Path(checkpoint["path"])
    if sha256(native_path) != binding["npz_sha256"] or sha256(capture_path) != checkpoint["sha256"]:
        raise ValueError("saved array digest mismatch")
    if sha256(Path(binding["path"])) != binding["sha256"]:
        raise ValueError("intake manifest digest mismatch")
    times = binding["actual_saved_times"]
    if times[:2] != ["2025-07-19_05:55:40", "2025-07-19_05:56:00"]:
        raise ValueError("host/local time pair differs from the declared nominal pair")
    with np.load(native_path, allow_pickle=False) as native, np.load(capture_path, allow_pickle=False) as capture:
        arrays, summary = diagnose(native, capture)
    # Reuse the existing no-clobber private writer; its module imports physics
    # helpers, but this reader does not evaluate a model or observation operator.
    import importlib.util
    helper = ROOT / "harness/evidence/pr395_tq_state_capture_2026-10-10/capture_tq_state.py"
    spec = importlib.util.spec_from_file_location("saved_state_capture_io", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    private_path = args.output.with_suffix(".npz")
    if args.output.exists() or private_path.exists():
        raise FileExistsError("refusing to overwrite a diagnostic")
    private_sha = module.write_private_npz_atomic(private_path, arrays)
    report = {
        "schema": "pr396_saved_state_diagnostic_v1", "status": "DERIVED_FROM_SAVED_ARRAYS",
        "capture_receipt_sha256": sha256(args.capture_receipt),
        "native_npz_sha256": binding["npz_sha256"], "capture_npz_sha256": checkpoint["sha256"],
        "diagnostic_source_sha256": sha256(__file__),
        "private_profile_path": str(private_path), "private_profile_sha256": private_sha,
        "times": times[:2], "mass_measure": "fixed first-frame native host eta dry mass",
        "boundary_and_external_fluxes": "NOT_MEASURED", "closed_water_budget": False,
        "host_local_difference_attribution": "included processes, splitting and forcing updates differ; not microphysics error or R",
        "additional_model_or_rttov_calls": 0, "science_accepted": False, **summary,
    }
    try:
        module._write_receipt_exclusive(args.output, report)
    except BaseException:
        private_path.unlink()
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
