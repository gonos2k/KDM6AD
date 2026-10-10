#!/usr/bin/env python3
"""One-case arithmetic/thermodynamic interpretation of saved actual arrays.

No model, observation operator, minimizer, native reader or RTTOV is evaluated.
Full derived profiles remain local. Public output contains scalar summaries.
"""
from pathlib import Path
import hashlib
import json
import os
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "oracle"))
from kdm6.thermo import compute_qs_water, default_thermo_params  # noqa: E402

PACKET = Path(__file__).resolve().parent
RECEIPT = ROOT / "harness/evidence/pr395_tq_state_capture_2026-10-10/RESULT_3d2e97f159.json"
DRIVER = RECEIPT.with_name("DRIVER_3d2e97f159.json")
WATER = ("qv", "qc", "qr", "qi", "qs", "qg")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def huber(bt, y):
    a = np.abs(np.asarray(bt) - np.asarray(y))  # sigma=1 K, bias=0, delta=1
    return float(np.sum(np.where(a <= 1, 0.5 * a * a, a - 0.5)))


def main():
    r, driver = json.loads(RECEIPT.read_text()), json.loads(DRIVER.read_text())
    assert r["status"] == "RETURNED_DIAGNOSTIC_ONLY"
    cp, binding = r["private_checkpoint"], r["native_intake_context"]
    assert sha(cp["path"]) == cp["sha256"]
    assert sha(binding["npz_path"]) == binding["npz_sha256"]
    assert sha(binding["path"]) == binding["sha256"]
    assert driver["capture_receipt_sha256"] == sha(RECEIPT)
    with np.load(cp["path"], allow_pickle=False) as archive:
        data = {k: archive[k].copy() for k in archive.files}
    with np.load(binding["npz_path"], allow_pickle=False) as archive:
        native = {k: archive[k].copy() for k in archive.files}
    state = lambda prefix, f: np.asarray(data[f"{prefix}__{f}"], dtype=np.float64).reshape(-1)
    prefixes = {"xb": "background_initial_state", "xa": "returned_analysis_initial_state",
                "mb": "background_slot_state", "ma": "final_slot_state"}
    q = {name: sum(state(prefix, f) for f in WATER) for name, prefix in prefixes.items()}
    pi0, pi1 = native["native_window_forcing__pii"][:2]
    p0 = native["native_window_forcing__p"][0]
    weights = native["native_window_host_dry_mass_kg_m2"].astype(np.float64)
    profiles = {"native_pressure_hPa": p0 / 100}
    saturation = {}
    for name, prefix in prefixes.items():
        temp = state(prefix, "th") * pi0
        qs = compute_qs_water(torch.as_tensor(temp), torch.as_tensor(p0),
                              params=default_thermo_params()).numpy()
        ratio = 100 * state(prefix, "qv") / qs
        profiles[f"{name}_liquid_qv_over_qs_percent"] = ratio
        saturation[name] = {"max_percent": float(ratio.max()),
                            "max_layer_bottomup_0based": int(ratio.argmax())}
    dt = (state(prefixes["xa"], "th") - state(prefixes["xb"], "th")) * pi0
    dq = state(prefixes["xa"], "qv") - state(prefixes["xb"], "qv")
    qb = state(prefixes["xb"], "qv")
    relative = np.full(39, np.nan)
    relative[qb > 0] = 100 * dq[qb > 0] / qb[qb > 0]
    profiles.update(initial_delta_temperature_K=dt, initial_delta_qv_kg_kg=dq,
                    initial_delta_qv_percent=relative)
    qt_native = sum(native[f"native_window_state__{f}"] for f in WATER)
    fixed = float(np.sum(weights[0] * (qt_native[1] - qt_native[0])))
    measure = float(np.sum((weights[1] - weights[0]) * qt_native[1]))
    actual = float(np.sum(weights[1] * qt_native[1]) - np.sum(weights[0] * qt_native[0]))
    th_h, th_l = native["native_window_state__th"][1], state(prefixes["mb"], "th")
    cross = (pi1 - pi0) * (th_h - th_l)
    y = data["observation_y_bt_K"]
    baseline_bt = driver["objective_audit"]["background_quality_probe"]["probe_BT_K"]
    final_event = r["logical_h_calls"][-1]
    assert final_event["grad"] and final_event["returned"]
    assert final_event["state_sha256"] == r["state_array_sha256"]["final_slot"]
    final_bt = np.asarray(final_event["BT_K"], dtype=np.float64)
    final_mask = np.asarray(final_event["fixed_mask"], dtype=np.float64)
    assert np.array_equal(final_mask, final_event["frozen_mask"])
    assert hashlib.sha256(final_mask.tobytes()).hexdigest() == r["objective"][
        "final_audit_signature"]["final_frozen_mask"]["sha256_f64"]
    assert np.array_equal(final_event["rad_quality"], data["final_slot_rad_quality"])
    jo0, jo1 = huber(baseline_bt, y), huber(final_bt, y)
    objective = r["objective"]
    np.testing.assert_allclose(jo0, objective["initial_zero_control_closure"]["Jo"], rtol=0, atol=1e-12)
    np.testing.assert_allclose(jo1, objective["Jo"], rtol=0, atol=1e-12)
    sigma_counts = {f: int(np.count_nonzero(data[f"control__b_sigma__{f}"]))
                    for f in r["final_control_gradient"]["v_state_order"]}
    grad = data["control__optimizer_final_gradient_v_state"]
    np.testing.assert_allclose(np.max(np.abs(grad)),
                               r["final_control_gradient"]["combined_linf_norm"], rtol=0, atol=1e-15)
    report = {
        "schema": "pr397_actual_saved_array_interpretation_v1",
        "receipt_sha256": sha(RECEIPT), "driver_sha256": sha(DRIVER),
        "capture_npz_sha256": cp["sha256"], "intake_npz_sha256": binding["npz_sha256"],
        "source_sha256": sha(__file__), "additional_model_or_rttov_calls": 0,
        "objective": {"Jo0": jo0, "Jo_final": jo1, "Jb_final": objective["Jb_state"],
                      "Jtotal_final": objective["Jtotal"],
                      "total_decrease_percent": 100 * (jo0 - objective["Jtotal"]) / jo0,
                      "observational_decrease_percent": 100 * (jo0 - jo1) / jo0},
        "active_initial_sigma_counts": sigma_counts,
        "conditional_rank_bound": {"rows": 7, "active_columns": sum(sigma_counts.values()),
                                   "max_rank": 7, "rank_measured": False},
        "initial_increment": {
            "coolest_delta_T_K": float(dt.min()), "coolest_layer_0based": int(dt.argmin()),
            "warmest_delta_T_K": float(dt.max()), "warmest_layer_0based": int(dt.argmax()),
            "max_delta_qv_kg_kg": float(dq.max()), "max_absolute_qv_layer_0based": int(dq.argmax()),
            "max_relative_qv_percent": float(np.nanmax(relative)),
            "max_relative_qv_layer_0based": int(np.nanargmax(relative))},
        "liquid_saturation_ratio": saturation,
        "four_state_condensate_positive_counts": {
            name: {f: int(np.count_nonzero(state(prefix, f) > 0)) for f in WATER[1:]}
            for name, prefix in prefixes.items()},
        "fixed_host_mass_water_kg_m2": {
            "analysis": float(np.sum(weights[0] * (q["xa"] - q["xb"]))),
            "model_analysis": float(np.sum(weights[0] * (q["ma"] - q["xa"]))),
            "model_background": float(np.sum(weights[0] * (q["mb"] - q["xb"])))},
        "native_host_20s_water_change_kg_m2": {
            "fixed_w0_mixing_ratio_term": fixed, "changing_mass_term": measure,
            "actual_w1_q1_minus_w0_q0": actual,
            "identity_residual": actual - fixed - measure,
            "closed_budget": False, "boundary_external_fluxes": "NOT_MEASURED"},
        "alternate_temperature_split_cross_term_max_abs_K": float(np.max(np.abs(cross))),
        "named_process_attribution": "NOT_MEASURED", "science_accepted": False,
    }
    private = ROOT / "graphify-out/pr397-actual-interpretation/private"
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(private, 0o700)
    path = private / "derived_profiles.npz"
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        np.savez_compressed(stream, **profiles)
    report["local_derived_profiles"] = {"path": str(path), "sha256": sha(path)}
    sidecar = private / "receipt_derived_observation_support.npz"
    with sidecar.open("xb") as stream:
        os.chmod(sidecar, 0o600)
        np.savez_compressed(stream, final_slot_bt_K=final_bt,
                            final_slot_frozen_mask=final_mask,
                            final_slot_rad_quality=data["final_slot_rad_quality"])
    report["local_observation_sidecar"] = {
        "path": str(sidecar), "sha256": sha(sidecar),
        "source": "final accepted grad=True callback in the hash-bound original public capture receipt",
        "original_checkpoint_has_bt": "final_slot_bt_K" in data,
        "original_checkpoint_has_mask": "final_slot_frozen_mask" in data,
        "original_checkpoint_rewritten": False,
        "sidecar_is_new_rttov_execution": False,
    }
    with (PACKET / "ACTUAL_ARRAY_CALCULATIONS.json").open("x") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
