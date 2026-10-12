#!/usr/bin/env python3
"""Value-only comparison of the completed PR420 DOM7 and DOM9 analyses.

This reader validates the pinned analysis receipts, retained RTTOV call inputs,
channel support, and selected objective/state summaries. It never calls H, M,
RTTOV, an optimizer, or a native model.
"""
from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np


PACKET = Path(__file__).resolve().parent
ROOT = PACKET.parents[2]
ORACLE = ROOT / "oracle"
sys.path.insert(0, str(ORACLE))
from kdm6.thermo import (  # noqa: E402
    compute_qs_ice,
    compute_qs_water,
    compute_rh,
    default_thermo_params,
)
import torch  # noqa: E402


PRIVATE = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/pr420_nine_channel_20261013")
PAIR_ROOT = PRIVATE / "DOM_ANALYSIS_PAIR_ONCE_01"
CHANNEL_NAMES = {
    8: "wv063",
    9: "wv069",
    10: "wv073",
    11: "ir087",
    12: "ir096",
    13: "ir105",
    14: "ir112",
    15: "ir123",
    16: "ir133",
}
CHANNELS_7 = list(range(10, 17))
CHANNELS_9 = list(range(8, 17))
WATER_FIELDS = ("qv", "qc", "qr", "qi", "qs", "qg")
THERMO_PARAMS = default_thermo_params()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def finite_stats(values: np.ndarray) -> dict:
    x = np.asarray(values, dtype=np.float64).reshape(-1)
    if not np.isfinite(x).all():
        raise ValueError("non-finite values in saved checkpoint")
    return {
        "n": int(x.size),
        "mean": float(x.mean()),
        "min": float(x.min()),
        "max": float(x.max()),
        "l2_norm": float(np.linalg.norm(x)),
    }


def state_array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    return hashlib.sha256(array.tobytes()).hexdigest()


def qsat_rh(qv: np.ndarray, temperature: np.ndarray, pressure: np.ndarray) -> np.ndarray:
    """Recompute the capture's phase-aware KDM6 q/qs RH diagnostic."""
    q = torch.as_tensor(qv, dtype=torch.float64)
    t = torch.as_tensor(temperature, dtype=torch.float64)
    p = torch.as_tensor(pressure, dtype=torch.float64)
    qsat_w = compute_qs_water(t, p, params=THERMO_PARAMS)
    qsat_i = compute_qs_ice(t, p, params=THERMO_PARAMS)
    qsat = torch.where(t < THERMO_PARAMS.ttp, qsat_i, qsat_w)
    return (100.0 * compute_rh(q, qsat, params=THERMO_PARAMS)).cpu().numpy()


def load_checkpoint(label: str, capture: dict) -> tuple[dict[str, np.ndarray], Path]:
    path = Path(capture["private_checkpoint"]["path"])
    expected_sha = capture["private_checkpoint"]["sha256"]
    actual_sha = sha256(path)
    if actual_sha != expected_sha:
        raise ValueError(f"{label} private checkpoint SHA mismatch: {actual_sha} != {expected_sha}")
    with np.load(path, allow_pickle=False) as archive:
        arrays = {key: archive[key].copy() for key in archive.files}
    expected_keys = set(capture["private_checkpoint"]["array_keys"])
    if not expected_keys.issubset(arrays):
        raise ValueError(f"{label} private checkpoint misses bound keys")
    return arrays, path


def state_from(archive: dict[str, np.ndarray], prefix: str) -> dict[str, np.ndarray]:
    names = ("th", "qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg")
    return {name: archive[f"{prefix}__{name}"][0].astype(np.float64, copy=False) for name in names}


def huber_cost(residual: np.ndarray, sigma: float = 1.0, delta: float = 1.0) -> np.ndarray:
    normalized = np.asarray(residual, dtype=np.float64) / sigma
    absolute = np.abs(normalized)
    return np.where(absolute <= delta, 0.5 * normalized**2, delta * (absolute - 0.5 * delta))


def h_case_check(label: str, expected_channels: list[int]) -> list[dict]:
    cases = sorted((PAIR_ROOT / label / "h_cases").glob("*/*/case"))
    if len(cases) != 6:
        raise ValueError(f"{label} expected six retained H call cases, got {len(cases)}")
    result = []
    for case in cases:
        channel_path = case / "in/channels.txt"
        actual_channels = [int(x) for x in channel_path.read_text().split()]
        nml = case / "out/rttov_test.txt"
        nml_text = nml.read_text()
        solvers = re.findall(
            r"(?im)^\s*defn%opts%scatt%thermal_solver\s*=\s*([^!\n]+)", nml_text)
        solar = re.findall(
            r"(?im)^\s*defn%opts%rt_all%solar\s*=\s*([^!\n]+)", nml_text)
        if actual_channels != expected_channels:
            raise ValueError(f"{label} emitted channel mismatch in {case}: {actual_channels}")
        if [s.strip().rstrip(",") for s in solvers] != ["1"]:
            raise ValueError(f"{label} retained call did not use DOM1: {case}")
        if [s.strip().rstrip(",").upper() for s in solar] != [".FALSE."]:
            raise ValueError(f"{label} retained call did not keep solar disabled: {case}")
        result.append({
            "case_path": str(case),
            "channels": actual_channels,
            "thermal_solver": 1,
            "solar": False,
            "channels_file_sha256": sha256(channel_path),
            "rttov_test_sha256": sha256(nml),
        })
    return result


def state_metrics(capture: dict, archive: dict[str, np.ndarray]) -> dict:
    initial_bg = state_from(archive, "background_initial_state")
    initial_da = state_from(archive, "returned_analysis_initial_state")
    slot_bg = state_from(archive, "background_slot_state")
    slot_da = state_from(archive, "final_slot_state")
    pii0 = archive["forcing_window_0__pii"][0]
    p0 = archive["forcing_window_0__p"][0]
    pii1 = archive["final_slot_forcing__pii"][0]
    p1 = archive["final_slot_forcing__p"][0]

    def thermo_pair(before: dict, after: dict, pii: np.ndarray, p: np.ndarray) -> dict:
        t_before = before["th"] * pii
        t_after = after["th"] * pii
        rh_before = qsat_rh(before["qv"], t_before, p)
        rh_after = qsat_rh(after["qv"], t_after, p)
        return {
            "temperature_K": {
                "before": finite_stats(t_before),
                "after": finite_stats(t_after),
                "delta": finite_stats(t_after - t_before),
            },
            "qv_kg_kg_dry": {
                "before": finite_stats(before["qv"]),
                "after": finite_stats(after["qv"]),
                "delta": finite_stats(after["qv"] - before["qv"]),
            },
            "phase_aware_q_over_qs_RH_percent": {
                "before": finite_stats(rh_before),
                "after": finite_stats(rh_after),
                "delta": finite_stats(rh_after - rh_before),
                "meaning": "model q/qs diagnostic; not an observed RH or a ratio of column sums",
            },
        }

    initial = thermo_pair(initial_bg, initial_da, pii0, p0)
    slot = thermo_pair(slot_bg, slot_da, pii1, p1)

    def field_change(before: dict, after: dict, name: str, units: str) -> dict:
        b, a = before[name], after[name]
        return {
            "units": units,
            "background": finite_stats(b),
            "analysis": finite_stats(a),
            "analysis_minus_background": finite_stats(a - b),
            "identical": bool(np.array_equal(b, a)),
        }

    cloud = {
        "initial_time": {
            "qc": field_change(initial_bg, initial_da, "qc", "kg kg-1 dry air"),
            "nc": field_change(initial_bg, initial_da, "nc", "number per kg dry air"),
        },
        "after_M20": {
            "qc": field_change(slot_bg, slot_da, "qc", "kg kg-1 dry air"),
            "nc": field_change(slot_bg, slot_da, "nc", "number per kg dry air"),
        },
    }

    mass_raw = archive["host_dry_mass_background_kg_m2"]
    if mass_raw.dtype != np.float32 or mass_raw.shape != (39,):
        raise ValueError("checkpoint host dry-mass vector did not preserve native f32 [39]")
    mass = mass_raw.astype(np.float64)

    def mass_water(state: dict) -> float:
        total = np.sum(np.stack([state[name] for name in WATER_FIELDS]), axis=0)
        return float(np.sum(total * mass, dtype=np.float64))

    def mass_increment(before: dict, after: dict) -> dict:
        species = {
            name: float(np.sum((after[name] - before[name]) * mass, dtype=np.float64))
            for name in WATER_FIELDS
        }
        return {
            "before_kg_m2": mass_water(before),
            "after_kg_m2": mass_water(after),
            "increment_kg_m2": mass_water(after) - mass_water(before),
            "by_species_kg_m2": species,
        }

    water = {
        "measure": "sum_k [(qv+qc+qr+qi+qs+qg)_k * host_dry_mass_background_kg_m2[k]]",
        "dry_mass_source": capture["host_dry_mass_background"],
        "background_M20": mass_increment(initial_bg, slot_bg),
        "analysis_M20": mass_increment(initial_da, slot_da),
        "same_increment_within_1e-12_kg_m2": bool(abs(
            mass_increment(initial_bg, slot_bg)["increment_kg_m2"]
            - mass_increment(initial_da, slot_da)["increment_kg_m2"]) <= 1e-12),
        "interpretation": "finite-water mass increment under the fixed host dry-air layer measure; this is not a full conservation proof",
    }

    # Validate independent checkpoint reductions against the capture summaries.
    metric = capture["metrics"]
    checks = {
        "initial_T_mean_delta_matches_receipt": math.isclose(
            initial["temperature_K"]["delta"]["mean"],
            metric["initial_time_state"]["physical_temperature_K"]["delta"]["mean"], abs_tol=1e-10),
        "initial_qv_mean_delta_matches_receipt": math.isclose(
            initial["qv_kg_kg_dry"]["delta"]["mean"],
            metric["initial_time_state"]["qv_dry_mixing_ratio_kg_kg"]["absolute_delta"]["mean"], abs_tol=1e-12),
        "initial_RH_mean_delta_matches_receipt": math.isclose(
            initial["phase_aware_q_over_qs_RH_percent"]["delta"]["mean"],
            metric["initial_time_state"]["relative_humidity_percent"]["delta"]["mean"], abs_tol=1e-8),
        "slot_T_mean_delta_matches_receipt": math.isclose(
            slot["temperature_K"]["delta"]["mean"],
            metric["observation_slot_state"]["physical_temperature_K"]["delta"]["mean"], abs_tol=1e-10),
        "slot_qv_mean_delta_matches_receipt": math.isclose(
            slot["qv_kg_kg_dry"]["delta"]["mean"],
            metric["observation_slot_state"]["qv_dry_mixing_ratio_kg_kg"]["absolute_delta"]["mean"], abs_tol=1e-12),
        "slot_RH_mean_delta_matches_receipt": math.isclose(
            slot["phase_aware_q_over_qs_RH_percent"]["delta"]["mean"],
            metric["observation_slot_state"]["relative_humidity_percent"]["delta"]["mean"], abs_tol=1e-8),
    }
    if not all(checks.values()):
        raise ValueError(f"checkpoint/receipt state metrics disagree: {checks}")
    return {"initial_time_background_to_analysis": initial,
            "observation_slot_background_to_analysis": slot,
            "qc_nc": cloud,
            "host_dry_mass_finite_water": water,
            "checkpoint_vs_receipt_checks": checks}


def plot_profiles(checkpoints: dict[str, dict[str, np.ndarray]]) -> Path:
    """Write one profile figure from retained states; no model calls."""
    import matplotlib.pyplot as plt

    a7, a9 = checkpoints["DOM7"], checkpoints["DOM9"]
    level = np.arange(1, 40)
    mass_bg = state_from(a7, "background_slot_state")
    mass_7 = state_from(a7, "final_slot_state")
    mass_9 = state_from(a9, "final_slot_state")
    exner = a7["final_slot_forcing__pii"][0].astype(np.float64)
    if not np.array_equal(a7["host_dry_mass_background_kg_m2"], a9["host_dry_mass_background_kg_m2"]):
        raise ValueError("profile plot host dry mass differs between paired runs")

    fig, axes = plt.subplots(1, 4, figsize=(14, 7), sharey=True, constrained_layout=True)
    fig.suptitle("PR420 paired DOM1 profiles after one saved local 20 s KDM6 window\n"
                 "39 native levels, bottom-up; background vs returned 7/9-channel states")

    def panel(ax, field: str, title: str, xlabel: str, scale: float = 1.0):
        bg_values = mass_bg[field] * scale
        v7 = mass_7[field] * scale
        v9 = mass_9[field] * scale
        ax.plot(bg_values, level, color="0.25", linewidth=1.8, label="background after M20")
        ax.plot(v7, level, color="#2563eb", linewidth=1.8, label="DOM1 7-channel")
        ax.plot(v9, level, color="#dc2626", linestyle="--", linewidth=1.8, label="DOM1 9-channel")
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.grid(True, alpha=0.25)

    t_bg = mass_bg["th"] * exner
    t7 = mass_7["th"] * exner
    t9 = mass_9["th"] * exner
    axes[0].plot(t_bg, level, color="0.25", linewidth=1.8, label="background after M20")
    axes[0].plot(t7, level, color="#2563eb", linewidth=1.8, label="DOM1 7-channel")
    axes[0].plot(t9, level, color="#dc2626", linestyle="--", linewidth=1.8, label="DOM1 9-channel")
    axes[0].set_title("Physical temperature")
    axes[0].set_xlabel("T (K)")
    axes[0].set_ylabel("native level index (1=bottom, 39=top)")
    axes[0].grid(True, alpha=0.25)
    panel(axes[1], "qv", "Water vapor", "qv (g kg⁻¹ dry)", 1000.0)
    panel(axes[2], "qc", "Cloud liquid", "qc (kg kg⁻¹ dry)")
    panel(axes[3], "nc", "Cloud number", "nc (10⁶ kg⁻¹ dry)", 1.0e-6)
    axes[3].legend(loc="best", fontsize=8)
    path = PACKET / "PROFILE.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def run_summary(label: str, channels: list[int], capture: dict,
                audit: dict, checkpoint: dict[str, np.ndarray]) -> tuple[dict, dict[int, dict]]:
    if capture["status"] != "RETURNED_DIAGNOSTIC_ONLY":
        raise ValueError(f"{label} did not return diagnostic-only capture")
    if audit["status"] != "CROSSCHECKED" or audit["expected_channel_count"] != len(channels):
        raise ValueError(f"{label} selected-channel audit did not cross-check")
    obs = np.asarray(capture["observations"]["y_bt_K"], dtype=np.float64)[0]
    dqf = np.asarray(capture["observations"]["observation_dqf"], dtype=np.float64)[0]
    if capture["observations"]["channels_ami_physical_ids"] != channels:
        raise ValueError(f"{label} observation order differs from fixed channels")
    if obs.shape != (len(channels),) or dqf.shape != (len(channels),) or not np.all(dqf == 0):
        raise ValueError(f"{label} source DQF/observation shape is invalid")

    calls = capture["logical_h_calls"]
    if len(calls) != 6:
        raise ValueError(f"{label} expected six logical H callback records; got {len(calls)}")
    per_channel = {channel: {"channel_id": channel,
                             "channel_name": CHANNEL_NAMES[channel],
                             "source_dqf": float(dqf[i]),
                             "callback_count": len(calls),
                             "model_rad_quality_each_callback": []}
                   for i, channel in enumerate(channels)}
    for event in calls:
        if event["channels"] != channels:
            raise ValueError(f"{label} callback {event['call_index']} changed channel order")
        bt = np.asarray(event["BT_K"], dtype=np.float64)[0]
        quality = np.asarray(event["rad_quality"], dtype=np.float64)[0]
        if bt.shape != (len(channels),) or quality.shape != (len(channels),):
            raise ValueError(f"{label} callback {event['call_index']} has invalid channel shape")
        for i, channel in enumerate(channels):
            per_channel[channel]["model_rad_quality_each_callback"].append(float(quality[i]))
    for channel, row in per_channel.items():
        if not all(value == 0.0 for value in row["model_rad_quality_each_callback"]):
            raise ValueError(f"{label} rad_quality nonzero for channel {channel}")
        row["model_rad_quality_zero_all_callbacks"] = True

    probe_bt = np.asarray(capture["background_quality_probe"]["BT_K"], dtype=np.float64)[0]
    final_bt = np.asarray(calls[-1]["BT_K"], dtype=np.float64)[0]
    ob = obs - probe_bt
    oa = obs - final_bt
    init_cost = huber_cost(ob)
    final_cost = huber_cost(oa)
    initial_closure = capture["objective"]["initial_zero_control_closure"]
    final_objective = capture["objective"]
    if not math.isclose(float(init_cost.sum()), float(initial_closure["Jo"]), abs_tol=1e-9):
        raise ValueError(f"{label} recomputed initial Huber cost does not match captured closure")
    if not math.isclose(float(final_cost.sum()), float(final_objective["Jo"]), abs_tol=1e-9):
        raise ValueError(f"{label} recomputed final Huber cost does not match final objective")
    if not np.array_equal(final_bt, checkpoint["final_slot_bt_K"][0]):
        raise ValueError(f"{label} final callback BT differs from retained final-slot BT")
    event_probe_state = calls[0]["state_sha256"]
    event_final_state = calls[-1]["state_sha256"]
    archive_probe_state = {
        field: state_array_sha256(checkpoint[f"background_slot_state__{field}"])
        for field in event_probe_state
    }
    archive_final_state = {
        field: state_array_sha256(checkpoint[f"final_slot_state__{field}"])
        for field in event_final_state
    }
    if event_probe_state != archive_probe_state:
        raise ValueError(f"{label} quality probe state differs from retained background_slot_state")
    if event_final_state != archive_final_state:
        raise ValueError(f"{label} final audit state differs from retained final_slot_state")

    for i, channel in enumerate(channels):
        per_channel[channel].update({
            "observation_bt_K": float(obs[i]),
            "background_bt_K": float(probe_bt[i]),
            "O_minus_B_K": float(ob[i]),
            "initial_huber_cost": float(init_cost[i]),
            "analysis_bt_K": float(final_bt[i]),
            "O_minus_A_K": float(oa[i]),
            "final_huber_cost": float(final_cost[i]),
        "o_b_forward_state": "H(M(x_b)); first grad=False quality-probe state",
        "o_a_forward_state": "H(M(x_a)); last successful grad=True final audit state",
        })

    opt = capture["optimization"]
    grad = capture["final_control_gradient"]
    metric = capture["metrics"]
    summary = {
        "status": capture["status"],
        "selected_audit": audit["status"],
        "channels": channels,
        "n_valid": int(final_objective["n_valid"]),
        "source_dqf_all_zero": True,
        "rad_quality_all_zero_at_every_callback": True,
        "logical_H_callbacks": len(calls),
        "probe_callbacks": sum(not bool(c["grad"]) for c in calls),
        "optimizer_closure_callbacks": int(capture["adapter_metadata"]["n_window_evals"]),
        "final_audit_callbacks": int(capture["adapter_metadata"]["n_audit_evals"]),
        "probe_state_hash_matches_retained_background_slot": True,
        "final_callback_state_hash_matches_retained_final_slot": True,
        "initial_zero_control_Jo": float(initial_closure["Jo"]),
        "final_Jb_state": float(final_objective["Jb_state"]),
        "final_Jtheta": float(final_objective["Jtheta"]),
        "final_Jo": float(final_objective["Jo"]),
        "final_Jtotal": float(final_objective["Jtotal"]),
        "observation_cost_reduction": float(initial_closure["Jo"] - final_objective["Jo"]),
        "optimizer": {
            "constructor_calls": int(opt["constructor_calls"]),
            "step_calls": int(opt["step_calls"]),
            "step_returned": bool(opt["step_returned"]),
            "actual_n_iter": int(opt["actual_n_iter"]),
            "max_iter": int(opt["max_iter"]),
            "actual_func_evals": int(opt["actual_func_evals"]),
            "max_eval": int(opt["max_eval"]),
            "termination_status": opt["termination_status"],
            "termination_reason": opt["termination_reason"],
            "final_gradient_within_tolerance": bool(opt["final_audit_gradient_within_tolerance_grad"]),
            "final_gradient_absmax": float(opt["final_audit_gradient_absmax"]),
            "state_gradient_l2": float(grad["state_l2_norm"]),
            "state_gradient_linf": float(grad["state_linf_norm"]),
            "combined_gradient_l2": float(grad["combined_l2_norm"]),
            "combined_gradient_linf": float(grad["combined_linf_norm"]),
            "gradient_contract": grad["contract"],
        },
        "physical_matchup_science_acceptance": capture["physical_matchup_and_science_acceptance"],
        "physical_temperature_initial": metric["initial_time_state"]["physical_temperature_K"],
        "qv_initial": metric["initial_time_state"]["qv_dry_mixing_ratio_kg_kg"],
        "rh_initial": metric["initial_time_state"]["relative_humidity_percent"],
        "physical_temperature_M20_slot": metric["observation_slot_state"]["physical_temperature_K"],
        "qv_M20_slot": metric["observation_slot_state"]["qv_dry_mixing_ratio_kg_kg"],
        "rh_M20_slot": metric["observation_slot_state"]["relative_humidity_percent"],
        "qc_nc_M20_slot": {
            "background_qc": metric["background_slot_qc"],
            "analysis_qc": metric["final_slot_qc"],
            "background_nc": metric["background_slot_nc"],
            "analysis_nc": metric["final_slot_nc"],
        },
    }
    return summary, per_channel


def main() -> None:
    plan_path = PACKET / "ANALYSIS_PLAN.json"
    plan = load_json(plan_path)
    result = load_json(PACKET / "ANALYSIS_RESULT.json")
    if result["plan_sha256"] != sha256(plan_path):
        raise ValueError("ANALYSIS_RESULT plan hash does not match ANALYSIS_PLAN")
    pin_checks = {}
    for path_text, expected in plan["bindings"].items():
        path = Path(path_text)
        if not path.is_file():
            pin_checks[path_text] = {"exists": False}
            continue
        actual = sha256(path)
        pin_checks[path_text] = {"exists": True, "sha256": actual, "matches": actual == expected}
    binding_mismatches = [p for p, v in pin_checks.items() if v.get("matches") is not True]
    if binding_mismatches:
        raise ValueError(f"ANALYSIS_PLAN pinned inputs changed: {binding_mismatches}")

    captures = {label: load_json(PACKET / f"{label}_CAPTURE.json") for label in ("DOM7", "DOM9")}
    audits = {label: load_json(PACKET / f"{label}_AUDIT.json") for label in ("DOM7", "DOM9")}
    channels_by_label = {"DOM7": CHANNELS_7, "DOM9": CHANNELS_9}
    checkpoints = {}
    checkpoint_paths = {}
    h_inputs = {}
    summaries = {}
    rows_by_channel = {}
    for label, channels in channels_by_label.items():
        capture = captures[label]
        if result["runs"][label]["status"] != capture["status"]:
            raise ValueError(f"{label} result/capture status mismatch")
        if result["runs"][label]["objective_audit"] != "CROSSCHECKED":
            raise ValueError(f"{label} selected-channel objective audit missing")
        if int(result["runs"][label]["n_valid"]) != len(channels):
            raise ValueError(f"{label} result support count mismatch")
        if capture["actual_h_configuration"]["channels"] != channels:
            raise ValueError(f"{label} H config channel order mismatch")
        if capture["effective_h_configuration"]["channels"] != channels:
            raise ValueError(f"{label} effective H channel order mismatch")
        if capture["actual_h_configuration"]["fixture_case_dir"] != capture["effective_h_configuration"]["fixture_case_dir"]:
            raise ValueError(f"{label} actual/effective H fixture directory mismatch")
        checkpoint, checkpoint_path = load_checkpoint(label, capture)
        checkpoints[label] = checkpoint
        checkpoint_paths[label] = checkpoint_path
        h_inputs[label] = h_case_check(label, channels)
        summaries[label], rows = run_summary(label, channels, capture, audits[label], checkpoint)
        for channel, row in rows.items():
            rows_by_channel.setdefault(channel, {})[label] = row

    # The run manifests are identical except for the supplemental 9-channel
    # source binding, which is absent from the original seven-channel contract.
    manifest7 = dict(plan["runs"]["DOM7"]["run_manifest"])
    manifest9 = dict(plan["runs"]["DOM9"]["run_manifest"])
    manifest9.pop("observation_channel_binding", None)
    same_run_manifest_except_channel_selection = manifest7 == manifest9
    if not same_run_manifest_except_channel_selection:
        raise ValueError("run manifest changed outside channel selection/binding")

    # Confirm the two DOM runs share the same native background, forcing, host
    # dry-mass measure and pressure grids. Their only intended difference is H
    # channel support; they each retain distinct controls/accepted endpoints.
    common_keys = (
        "background_initial_state__th", "background_initial_state__qv",
        "background_initial_state__qc", "background_initial_state__nc",
        "forcing_window_0__rho", "forcing_window_0__pii", "forcing_window_0__p",
        "forcing_window_0__delz", "host_dry_mass_background_kg_m2",
        "native_coordinate__p_lay_rttov_topdown", "native_coordinate__p_half_rttov_topdown",
        "rttov_config__p_lay", "rttov_config__p_half", "rttov_config__t_ref", "rttov_config__q_ref",
    )
    common_input_arrays_equal = {
        key: bool(np.array_equal(checkpoints["DOM7"][key], checkpoints["DOM9"][key]))
        for key in common_keys
    }
    if not all(common_input_arrays_equal.values()):
        raise ValueError(f"DOM7/DOM9 common native inputs differ: {common_input_arrays_equal}")
    observed_common_equal = bool(np.array_equal(
        checkpoints["DOM7"]["observation_y_bt_K"], checkpoints["DOM9"]["observation_y_bt_K"][:, 2:]))
    if not observed_common_equal:
        raise ValueError("common seven observation values differ between DOM7 and DOM9")

    # Compare the earlier operational Eddington seven-channel background H only
    # as a per-channel operator diagnostic, not as an objective-score baseline.
    old = load_json(ROOT / "harness/evidence/pr412_native_process_case_2026-10-12/CAPTURE.json")
    old_channels = old["actual_h_configuration"]["channels"]
    if old_channels != CHANNELS_7:
        raise ValueError("historical Eddington reference is not the fixed 10..16 support")
    old_nml = Path(old["actual_h_configuration"]["fixture_case_dir"]) / "out/rttov_test.txt"
    old_solvers = re.findall(r"(?im)^\s*defn%opts%scatt%thermal_solver\s*=\s*([^!\n]+)", old_nml.read_text())
    if [s.strip().rstrip(",") for s in old_solvers] != ["3"]:
        raise ValueError("historical operational comparison is not the pinned solver-3 fixture")
    old_obs = np.asarray(old["observations"]["y_bt_K"], dtype=np.float64)[0]
    old_bg = np.asarray(old["background_quality_probe"]["BT_K"], dtype=np.float64)[0]
    if not np.array_equal(old_obs, np.asarray(captures["DOM7"]["observations"]["y_bt_K"])[0]):
        raise ValueError("historical seven-channel observation vector differs")
    for index, channel in enumerate(CHANNELS_7):
        rows_by_channel.setdefault(channel, {})["EDD3_BASELINE"] = {
            "background_bt_K": float(old_bg[index]),
            "O_minus_B_K": float(old_obs[index] - old_bg[index]),
            "solver": 3,
        }

    process_plan_path = PACKET / "PROCESS_PLAN.json"
    process_result_path = PACKET / "PROCESS_RESPONSE.json"
    process_plan = load_json(process_plan_path)
    process_response = load_json(process_result_path)
    if process_response["plan_sha256"] != sha256(process_plan_path):
        raise ValueError("saved M-response receipt does not match its plan")
    if not process_response["quality_all_zero"] or process_response["M_optimizer_native_calls"] != 0:
        raise ValueError("saved M-response checks did not preserve all-zero quality/no-M execution")
    process_bindings = {}
    for path_text, expected in process_plan["bindings"].items():
        path = Path(path_text)
        actual = sha256(path) if path.is_file() else None
        process_bindings[path_text] = {
            "expected_sha256": expected, "actual_sha256": actual, "matches": actual == expected,
        }
    if not all(item["matches"] for item in process_bindings.values()):
        raise ValueError("saved M-response plan inputs changed")
    for label, channels in channels_by_label.items():
        process_run = process_response["runs"][label]
        if process_run["channels"] != channels:
            raise ValueError(f"{label} M-response channel selection mismatch")
        for key in ("R_M_background_K", "R_M_returned_K", "I_M_K"):
            vec = np.asarray(process_run[key], dtype=np.float64)[0]
            if vec.shape != (len(channels),) or not np.isfinite(vec).all():
                raise ValueError(f"{label} M-response vector invalid: {key}")
        if label == "DOM9":
            for name in ("background_initial_DOM9", "returned_initial_DOM9"):
                quality = np.asarray(process_response["calls"][name]["quality"], dtype=np.float64)
                if not np.all(quality == 0.0):
                    raise ValueError(f"nonzero quality in saved value-only call {name}")
        else:
            quality = np.asarray(process_response["calls"]["returned_initial_DOM7"]["quality"], dtype=np.float64)
            if not np.all(quality == 0.0):
                raise ValueError("nonzero quality in saved value-only DOM7 call")
        for i, channel in enumerate(channels):
            rows_by_channel[channel][label].update({
                "R_M_background_K": float(process_run["R_M_background_K"][0][i]),
                "R_M_returned_K": float(process_run["R_M_returned_K"][0][i]),
                "I_M_K": float(process_run["I_M_K"][0][i]),
            })

    # Record the separate DOM9 first-order check already executed by the root.
    # It is value-only directional evidence, distinct from optimizer convergence.
    direction_plan_path = PACKET / "DIRECTION_PLAN.json"
    direction_result_path = PACKET / "DIRECTION_RESULT.json"
    direction_plan = load_json(direction_plan_path)
    direction_result = load_json(direction_result_path)
    if direction_result["plan_sha256"] != sha256(direction_plan_path):
        raise ValueError("DOM9 direction result does not match its immutable plan")
    direction_binding_checks = {}
    for path_text, expected in direction_plan["bindings"].items():
        path = Path(path_text)
        actual = sha256(path) if path.is_file() else None
        direction_binding_checks[path_text] = {
            "expected_sha256": expected,
            "actual_sha256": actual,
            "matches": actual == expected,
        }
    if not all(item["matches"] for item in direction_binding_checks.values()):
        raise ValueError("DOM9 direction-plan bindings changed")

    # Add a readable all-nine row table. Seven-channel values are blank for
    # IDs 8 and 9 by design; do not synthesize/drop them in that run.
    channel_csv = PACKET / "CHANNELS.csv"
    columns = [
        "ami_channel_id_1based", "channel_name", "source_dqf",
        "edd3_baseline_bg_bt_K", "edd3_baseline_O_minus_B_K",
        "dom1_7_bg_bt_K", "dom1_7_O_minus_B_K", "dom1_7_initial_huber_cost",
        "dom1_7_analysis_bt_K", "dom1_7_O_minus_A_K", "dom1_7_final_huber_cost",
        "dom1_7_all_six_callback_rad_quality_zero",
        "dom1_7_R_M_background_K", "dom1_7_R_M_returned_K", "dom1_7_I_M_K",
        "dom1_9_bg_bt_K", "dom1_9_O_minus_B_K", "dom1_9_initial_huber_cost",
        "dom1_9_analysis_bt_K", "dom1_9_O_minus_A_K", "dom1_9_final_huber_cost",
        "dom1_9_all_six_callback_rad_quality_zero",
        "dom1_9_R_M_background_K", "dom1_9_R_M_returned_K", "dom1_9_I_M_K",
    ]
    with channel_csv.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for channel in CHANNELS_9:
            data = rows_by_channel[channel]
            edd = data.get("EDD3_BASELINE", {})
            r7 = data.get("DOM7", {})
            r9 = data.get("DOM9", {})
            writer.writerow({
                "ami_channel_id_1based": channel,
                "channel_name": CHANNEL_NAMES[channel],
                "source_dqf": r9["source_dqf"],
                "edd3_baseline_bg_bt_K": edd.get("background_bt_K", ""),
                "edd3_baseline_O_minus_B_K": edd.get("O_minus_B_K", ""),
                "dom1_7_bg_bt_K": r7.get("background_bt_K", ""),
                "dom1_7_O_minus_B_K": r7.get("O_minus_B_K", ""),
                "dom1_7_initial_huber_cost": r7.get("initial_huber_cost", ""),
                "dom1_7_analysis_bt_K": r7.get("analysis_bt_K", ""),
                "dom1_7_O_minus_A_K": r7.get("O_minus_A_K", ""),
                "dom1_7_final_huber_cost": r7.get("final_huber_cost", ""),
                "dom1_7_all_six_callback_rad_quality_zero": r7.get("model_rad_quality_zero_all_callbacks", ""),
                "dom1_7_R_M_background_K": r7.get("R_M_background_K", ""),
                "dom1_7_R_M_returned_K": r7.get("R_M_returned_K", ""),
                "dom1_7_I_M_K": r7.get("I_M_K", ""),
                "dom1_9_bg_bt_K": r9.get("background_bt_K", ""),
                "dom1_9_O_minus_B_K": r9.get("O_minus_B_K", ""),
                "dom1_9_initial_huber_cost": r9.get("initial_huber_cost", ""),
                "dom1_9_analysis_bt_K": r9.get("analysis_bt_K", ""),
                "dom1_9_O_minus_A_K": r9.get("O_minus_A_K", ""),
                "dom1_9_final_huber_cost": r9.get("final_huber_cost", ""),
                "dom1_9_all_six_callback_rad_quality_zero": r9.get("model_rad_quality_zero_all_callbacks", ""),
                "dom1_9_R_M_background_K": r9.get("R_M_background_K", ""),
                "dom1_9_R_M_returned_K": r9.get("R_M_returned_K", ""),
                "dom1_9_I_M_K": r9.get("I_M_K", ""),
            })

    common_final_7 = sum(rows_by_channel[c]["DOM7"]["final_huber_cost"] for c in CHANNELS_7)
    common_final_9 = sum(rows_by_channel[c]["DOM9"]["final_huber_cost"] for c in CHANNELS_7)
    common_initial_7 = sum(rows_by_channel[c]["DOM7"]["initial_huber_cost"] for c in CHANNELS_7)
    common_initial_9 = sum(rows_by_channel[c]["DOM9"]["initial_huber_cost"] for c in CHANNELS_7)
    extra_initial = sum(rows_by_channel[c]["DOM9"]["initial_huber_cost"] for c in (8, 9))
    extra_final = sum(rows_by_channel[c]["DOM9"]["final_huber_cost"] for c in (8, 9))
    profile_path = plot_profiles(checkpoints)
    summary = {
        "schema": "pr420_dom1_7v9_value_comparison_v1",
        "authored_at_kst": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        "display_timezone": "KST",
        "inputs": {
            "analysis_plan_path": str(plan_path),
            "analysis_plan_sha256": sha256(plan_path),
            "analysis_result_path": str(PACKET / "ANALYSIS_RESULT.json"),
            "analysis_result_sha256": sha256(PACKET / "ANALYSIS_RESULT.json"),
            "paired_dom7_capture_sha256": sha256(PACKET / "DOM7_CAPTURE.json"),
            "paired_dom9_capture_sha256": sha256(PACKET / "DOM9_CAPTURE.json"),
            "private_checkpoints": {
                label: {"path": str(checkpoint_paths[label]), "sha256": sha256(checkpoint_paths[label])}
                for label in channels_by_label
            },
        },
        "run_result": result,
        "plan_binding_validation": {
            "all_bound_inputs_match": True,
            "binding_count": len(pin_checks),
            "binding_checks": pin_checks,
        },
        "experiment_identity": {
            "same_v4_background_forcing_geometry_pressure_and_priors": True,
            "run_manifest_identical_except_nine_channel_binding": same_run_manifest_except_channel_selection,
            "common_checkpoint_input_arrays_equal": common_input_arrays_equal,
            "common_seven_observation_values_equal": observed_common_equal,
            "solver": "RTTOV built-in DOM thermal solver 1; solar false",
            "native_background_time": "2025-07-19_05:55:40",
            "nominal_observation_slot": "2025-07-19_05:56:00",
            "selected_native_column_j_i_1based": [103, 48],
            "native_levels": 39,
            "native_interface_identity_independently_verified": False,
            "actual_pixel_utc_verified": False,
            "new_native_model_runs_or_new_observation_acquisition": 0,
        },
        "runs": summaries,
        "channel_cost_split": {
            "definition": "Huber residual cost per channel, sigma=1 K and delta=1 K; residuals are O minus simulated BT; priors reported separately",
            "initial_common_7_cost_dom7": common_initial_7,
            "initial_common_7_cost_dom9": common_initial_9,
            "initial_added_channels_8_9_cost_dom9": extra_initial,
            "final_common_7_cost_dom7": common_final_7,
            "final_common_7_cost_dom9": common_final_9,
            "final_added_channels_8_9_cost_dom9": extra_final,
            "dom9_common7_final_minus_dom7_common7": common_final_9 - common_final_7,
            "interpretation": "whole-vector Jo/Jtotal differs by channel count; compare shared-channel costs and per-channel O-B/O-A, not the unnormalized totals across N",
        },
        "historical_eddington_baseline": {
            "solver": 3,
            "channel_support": CHANNELS_7,
            "used_only_for_per_channel_background_H_diagnostics": True,
            "aggregate_objective_comparison": False,
            "per_channel_rows_in_csv": True,
        },
        "dom9_directional_validation": {
            "status": direction_result["status"],
            "direction_plan_sha256": sha256(direction_plan_path),
            "directional_FD": float(direction_result["directional_FD"]),
            "directional_AD": float(direction_result["directional_AD"]),
            "absolute_error": float(direction_result["absolute_error"]),
            "relative_error": float(direction_result["relative_error"]),
            "quality_all_zero": bool(direction_result["quality_all_zero"]),
            "two_logical_H_calls": int(direction_plan["logical_H_calls"]),
            "two_KDM_value_steps": int(direction_plan["KDM_value_steps"]),
            "optimizer_calls": int(direction_plan["optimizer_calls"]),
            "calibration_bound_for_direction_check": bool(direction_plan["calibration_json_bound_for_this_check"]),
            "calibration_bound_before_original_pair": bool(direction_plan["calibration_json_bound_before_original_pair"]),
            "binding_validation": direction_binding_checks,
            "scope": direction_plan["scope"],
        },
        "saved_M_response": {
            "status": process_response["status"],
            "process_plan_path": str(process_plan_path),
            "process_plan_sha256": sha256(process_plan_path),
            "process_response_path": str(process_result_path),
            "process_response_sha256": sha256(process_result_path),
            "bindings_all_match": True,
            "three_value_only_H_calls": int(process_response["logical_H_calls"]),
            "M_optimizer_native_calls": int(process_response["M_optimizer_native_calls"]),
            "quality_all_zero": bool(process_response["quality_all_zero"]),
            "calibration_bound_for_process_check": bool(process_plan["calibration_prepost_bound_here_but_not_original_pair"]),
            "calibration_bound_before_original_pair": False,
            "operator_response": {
                label: {
                    "Jo_background_initial": process_response["runs"][label]["Jo_background_initial"],
                    "Jo_background_slot": process_response["runs"][label]["Jo_background_slot"],
                    "Jo_returned_initial": process_response["runs"][label]["Jo_returned_initial"],
                    "Jo_returned_slot": process_response["runs"][label]["Jo_returned_slot"],
                    "G_M": process_response["runs"][label]["G_M"],
                    "G_0_bypassed_M": process_response["runs"][label]["G_0_bypassed_M"],
                    "G_M_minus_G_0": process_response["runs"][label]["G_M_minus_G_0"],
                    "R_M_background_K": process_response["runs"][label]["R_M_background_K"],
                    "R_M_returned_K": process_response["runs"][label]["R_M_returned_K"],
                    "I_M_K": process_response["runs"][label]["I_M_K"],
                }
                for label in channels_by_label
            },
            "interpretation_limit": process_response["interpretation"],
            "sampled_WV063_WV069_returned_R_M_zero_is_case_specific": True,
        },
        "per_channel": {
            str(channel): rows_by_channel[channel] for channel in CHANNELS_9
        },
        "retained_h_case_input_checks": h_inputs,
        "profile_plot": {
            "path": str(profile_path),
            "sha256": sha256(profile_path),
            "source": "retained accepted_state.npz checkpoints only",
            "no_H_M_optimizer_native_calls": True,
        },
        "state_and_process_diagnostics": {
            label: state_metrics(captures[label], checkpoints[label])
            for label in channels_by_label
        },
        "science_status_and_limits": {
            "both_captures_returned_diagnostic_only": True,
            "both_accepted_state_objective_audits_crosschecked": True,
            "all_selected_source_dqf_zero": True,
            "all_model_rad_quality_zero_on_all_six_callbacks": True,
            "optimizer_converged": False,
            "final_control_gradient_within_tolerance": False,
            "background_probe_semantics": "O-B uses H(M(x_b)) at the saved observation slot; O-A uses H(M(x_a)). PROCESS_RESPONSE separately records H(x_b) and H(x_a) to compute R_M=H(M(x))-H(x).",
            "pixel_time_matchup_science_acceptance": "NOT_ASSESSED; pixel UTC not independently verified",
            "analysis_product_status": "diagnostic retained checkpoint; not a published valid native analysis",
            "p_half_interface_identity": "not independently verified; do not infer from numerical equivalence or retained p8w provenance",
            "natural_cloud_regime": "one saved cloudy native background; the single local 20 s KDM6 window ends with qc/nc at zero; this is a case-specific process result, not a generalized cloud-regime claim",
            "finite_water_scope": "one local M20 step weighted by the fixed WRF host dry-mass background vector; not full column conservation certification",
            "calibration_provenance_limit": "the original pair plan did not pre-bind the calibration JSON before execution; the separate direction check did bind it. Preserve this distinction and rely on the root-authored additive provenance-limits record for the post-hoc source-history statement.",
        },
    }
    summary_path = PACKET / "SUMMARY.json"
    summary_path.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(json.dumps({
        "status": "OK",
        "summary": str(summary_path),
        "channels_csv": str(channel_csv),
        "DOM7_final_Jo": summaries["DOM7"]["final_Jo"],
        "DOM9_final_Jo": summaries["DOM9"]["final_Jo"],
        "DOM9_common7_final_cost": common_final_9,
        "DOM9_added2_final_cost": extra_final,
        "analysis_executed": False,
    }, indent=2))


if __name__ == "__main__":
    main()
