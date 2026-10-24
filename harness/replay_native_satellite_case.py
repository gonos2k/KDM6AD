"""Replay published KO7 case arithmetic with NumPy; never execute KDM/RTTOV.

This checks a publication bundle, not the authenticity of private inputs or a
new executable. The fixed 2025-07-19 case retains 129 original native blocks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


def _sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _sum(values):
    return math.fsum(float(x) for x in np.asarray(values).ravel())


def _sha_array(value):
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def _arrays(path):
    with np.load(path, allow_pickle=False) as archive:
        return {name: archive[name].copy() for name in archive.files}


def _restricted_initial_qc(arrays, n, levels):
    qc = arrays.get("initial_qc_kgkg")
    _require(
        isinstance(qc, np.ndarray)
        and qc.dtype == np.float64
        and qc.shape == (n, levels)
        and np.isfinite(qc).all(),
        "restricted initial_qc artifact requires finite float64 initial_qc_kgkg",
    )
    return qc


def replay(evidence):
    root = Path(evidence).resolve(strict=True)
    manifest_path = root / "publication_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    _require(manifest.get("schema") in ("kdm6.native_satellite_publication_pack.v1",
                                        "kdm6.native_satellite_publication_pack.v2"),
             "unsupported publication schema")
    required = {"scope.json", "summary.json", "channel_bt.npz", "observation_support.npz",
                "native_state_controls.npz", "baseline_native_gradient_cost.npz",
                "baseline_native_tangent.npz", "native_control_delta.npz", "trials/trials.json"}
    _require(required <= set(manifest["artifacts"]), "replayed input lacks a manifest hash")
    for name, record in manifest["artifacts"].items():
        path = (root / name).resolve(strict=True)
        _require(root in path.parents, "artifact escapes the evidence directory")
        _require(path.stat().st_size == record["bytes"] and _sha(path) == record["sha256"],
                 f"artifact hash/size differs: {name}")
    read = lambda name: json.loads((root / name).read_text())
    scope, summary = read("scope.json"), read("summary.json")
    _require(scope["grid"] == [282, 234, 39] and scope["trial_alphas"] == [1.0, 0.5, 0.25],
             "this replay requires the declared native grid and three-step budget")
    _require(scope["huber_delta"] == scope["observation_sigma_K"] == 1.0
             and scope["bias_K"] == 0.0 and scope["regularization_lambda"] == 1.0,
             "objective differs from the fixed case")
    bt, support = _arrays(root / "channel_bt.npz"), _arrays(root / "observation_support.npz")
    mask, weights = support["mask"], support["weights"]
    expected = np.arange(65988)
    _require(np.array_equal(bt["flat_index"], expected)
             and np.array_equal(support["flat_index"], expected), "missing or reordered native columns")
    _require(mask.shape == (65988, 7) and mask.dtype == np.bool_, "invalid support shape/type")
    _require(np.array_equal(support["source_eligible"],
                           support["raw_source_valid"] & support["profile_valid"][:, None]),
             "pre-RT eligibility differs from source/profile admission")
    _require(np.array_equal(mask, support["source_eligible"] & (bt["baseline_quality"] == 0)),
             "baseline model quality differs from support")
    _require(weights.dtype == np.float64 and np.array_equal(weights, mask.astype(np.float64)),
             "the unique-owner case requires weight one on support, zero elsewhere")
    z_total = _sum(weights)
    _require(z_total > 0.0 and z_total == summary["globalZ"], "empty or different global normalizer")
    observed, baseline = bt["observed_bt"], bt["baseline_bt"]
    _require(observed.dtype == baseline.dtype == np.float64
             and np.isfinite(observed).all() and np.isfinite(baseline[mask]).all(),
             "BT must be binary64 and finite on fixed support")

    # Match the declared binary64 reduction: rounded products, level/channel
    # fsum in each original block, then fsum of block numerators, one global Z.
    numerators = []
    for start in range(0, 65988, 512):
        stop = min(start + 512, 65988)
        selected = mask[start:stop]
        residual = (baseline[start:stop] - observed[start:stop])[selected]
        huber = np.where(np.abs(residual) <= 1.0,
                         0.5 * residual * residual, np.abs(residual) - 0.5)
        numerators.append(_sum(weights[start:stop][selected] * huber))
    numerator = math.fsum(numerators)
    objective = numerator / z_total
    _require(objective == summary["baseline_objective"]["J_total"], "baseline cost replay differs")

    state = _arrays(root / "native_state_controls.npz")
    gradient = _arrays(root / "baseline_native_gradient_cost.npz")
    tangent = _arrays(root / "baseline_native_tangent.npz")
    active = support["active"]
    g = np.stack((gradient["grad_theta_cost"], gradient["grad_qv_cost"]))
    scales = np.stack((np.full_like(state["theta_m"], 0.2), 0.02 * state["qv"]))
    _require(active.shape == g.shape == (2, 65988, 39)
             and active.dtype == np.bool_ and g.dtype == np.float64 and np.isfinite(g).all()
             and state["theta_m"].dtype == state["qv"].dtype == np.float64,
             "invalid binary64 native gradient/control layout")
    admitted = mask.any(axis=1)[:, None]
    expected_active = np.stack((np.broadcast_to(admitted, state["qv"].shape),
                                admitted & (state["qv"] > 0.0)))
    _require(np.array_equal(active, expected_active),
             "active controls differ from frozen support and positive baseline QV")
    scaled = np.where(active, scales * g, 0.0)
    maximum = float(np.max(np.abs(scaled)))
    direction = np.zeros_like(scaled)
    if maximum > 0.0:
        direction[active] = -scaled[active] / maximum
    seed = np.zeros_like(baseline)
    seed[mask] = np.clip(baseline[mask] - observed[mask], -1.0, 1.0)
    lhs = _sum(seed * tangent["bt_jvp"]) / z_total
    rhs = math.fsum((_sum(g[0] * tangent["direction_theta"]),
                     _sum(g[1] * tangent["direction_qv"])))
    dot_error = abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1e-12)
    _require(dot_error <= 1e-10, "published JVP/VJP dot criterion failed")

    trials, records = [], read("trials/trials.json")
    _require(len(records) == 3, "trial list differs from the fixed budget")
    for alpha, record in zip(scope["trial_alphas"], records):
        _require(record["alpha"] == alpha and record["globalZ"] == z_total,
                 "trial ordering or global normalizer differs")
        controls = np.ascontiguousarray(alpha * direction)
        _require(hashlib.sha256(controls.tobytes()).hexdigest() == record["controls_sha256"],
                 "trial is not the declared baseline-scaled descent vector")
        _require(not np.any(controls[~active]) and np.max(np.abs(controls)) <= 1.0,
                 "frozen controls changed or bounds exceeded")
        trial_name = "trials/" + record["arrays"]["file"]
        _require(trial_name in manifest["artifacts"], "trial array lacks a manifest hash")
        candidate = _arrays(root / trial_name)
        _require(np.array_equal(candidate["flat_index"], expected), "trial native coverage differs")
        lost = mask & ((candidate["quality"] != 0) | ~np.isfinite(candidate["bt"])
                       | ~candidate["profile_valid"][:, None])
        valid = not bool(lost.any())
        _require(record["objective_valid"] == valid and record["support_preserved"] == valid,
                 "trial validity differs from its exported support")
        _require(not valid and record["objective"] is None and not record["acceptance"]["accepted"],
                 "this completed case must retain all three invalid/rejected trials")
        trials.append({"alpha": alpha, "lost_profiles": int(lost.any(axis=1).sum()),
                       "lost_channel_cells": int(lost.sum()), "accepted": False})
    _require(len(trials) == 3 and manifest["status"] == summary["status"]
             == "COMPLETED_NO_ACCEPTABLE_UPDATE", "final classification differs")
    delta = _arrays(root / "native_control_delta.npz")
    _require(not np.any(delta["delta_theta"]) and not np.any(delta["delta_qv"]),
             "a rejected candidate was applied to the final input controls")
    _require(bt["final_bt"].tobytes() == baseline.tobytes()
             and summary["final_objective"] == summary["baseline_objective"],
             "no-accepted-update final values differ from baseline")
    return {"schema": "kdm6.native_satellite_public_arithmetic_replay.v1",
            "status": "REPLAY_PASSED", "run_id": manifest["run_id"],
            "native_columns": 65988, "blocks": 129, "globalZ": z_total,
            "observation_numerator": numerator, "baseline_J": objective,
            "published_dot_relative_error": dot_error, "trials": trials,
            "publication_manifest_sha256": _sha(manifest_path), "replayer_sha256": _sha(Path(__file__)),
            "new_KDM_RTTOV_host_calls": 0,
            "limits": "Published arithmetic/identity only; private model inputs, kernel execution, RTTOV K, navigation authenticity and physical budgets are not independently re-executed here."}


def _restricted_bundle(root):
    """Load every artifact in a restricted publication after path/hash checks."""
    root_arg = Path(root)
    _require(
        not root_arg.is_symlink(), "restricted evidence root must not be a symlink"
    )
    root = root_arg.resolve(strict=True)
    manifest_path = root / "publication_manifest.json"
    _require(
        not manifest_path.is_symlink()
        and root in manifest_path.resolve(strict=True).parents,
        "restricted publication manifest escapes the evidence directory",
    )
    manifest = json.loads(manifest_path.read_text())
    _require(
        manifest.get("schema") == "kdm6.native_satellite_restricted_publication.v1",
        "unsupported restricted publication schema",
    )
    artifacts = manifest.get("artifacts")
    _require(
        isinstance(artifacts, dict) and artifacts,
        "restricted manifest has no artifacts",
    )
    paths = {}
    for name, record in artifacts.items():
        rel = Path(name)
        _require(
            not rel.is_absolute() and ".." not in rel.parts,
            f"restricted artifact path is not relative: {name}",
        )
        raw = root / rel
        _require(
            not raw.is_symlink(), f"restricted artifact must not be a symlink: {name}"
        )
        path = raw.resolve(strict=True)
        _require(
            root in path.parents, "restricted artifact escapes the evidence directory"
        )
        _require(
            isinstance(record, dict), f"restricted artifact record is malformed: {name}"
        )
        _require(
            path.stat().st_size == record.get("bytes")
            and _sha(path) == record.get("sha256"),
            f"restricted artifact hash/size differs: {name}",
        )
        paths[name] = path
    required = {
        "summary.json",
        "restricted_controls.npz",
        "channel_comparison.npz",
        "candidate_input_state.npz",
        "candidate_input_delta.npz",
        "baseline_applied_tq.npz",
        "candidate_applied_tq.npz",
        "baseline_applied_qc.npz",
        "candidate_applied_qc.npz",
        "tendencies/finish_theta_coordinates.npz",
        "tendencies/initial_qc.npz",
        "tendencies/tendency_crosswalk.json",
    }
    _require(
        required <= set(paths), "restricted publication lacks a required hashed input"
    )
    return root, manifest, paths


def _restricted_objective(
    bt, obs, mask, weights, z, active, *, delta=1.0, sigma=1.0, bias=0.0
):
    """Recompute one 129-block Huber numerator and scaled-control prior."""
    numerators = []
    for start in range(0, bt.shape[0], 512):
        stop = min(start + 512, bt.shape[0])
        selected = mask[start:stop]
        residual = (bt[start:stop][selected] - obs[start:stop][selected] - bias) / sigma
        absolute = np.abs(residual)
        huber = np.where(
            absolute <= delta,
            0.5 * residual * residual,
            delta * (absolute - 0.5 * delta),
        )
        numerators.append(_sum(weights[start:stop][selected] * huber))
    observation_numerator = math.fsum(numerators)
    regularization_numerator = 0.5 * math.fsum(float(x * x) for x in z[active])
    numerator = math.fsum((observation_numerator, regularization_numerator))
    normalizer = _sum(weights)
    _require(normalizer > 0.0, "restricted objective has empty baseline support")
    return {
        "observation_numerator": observation_numerator,
        "regularization_numerator": regularization_numerator,
        "numerator": numerator,
        "Z": normalizer,
        "cost": numerator / normalizer,
    }


def _candidate_finish_numpy(
    before_theta, clean_theta, qv_before, qv_after, qc_before, qc_after, cfg
):
    """Replay the native finish map in its documented binary64 operation order."""
    dt = float(cfg["dt_seconds"])
    alpha = float(cfg["alpha"])
    t0 = float(cfg["t0_K"])
    limit_rate = float(cfg["mp_tend_lim_K_s"])
    _require(
        all(math.isfinite(x) for x in (dt, alpha, t0, limit_rate))
        and dt > 0.0
        and alpha >= 0.0
        and limit_rate >= 0.0,
        "restricted finish crosswalk scalars are invalid",
    )
    raw = clean_theta - before_theta
    bound = limit_rate * dt
    m = np.where(
        raw >= bound,
        np.full_like(raw, bound),
        np.where(raw <= -bound, np.full_like(raw, -bound), raw),
    )
    delta_qv = qv_after - qv_before
    a = 1.0 + alpha * qv_before
    b = 1.0 + alpha * qv_after
    n = m * b + alpha * delta_qv * clean_theta
    full = before_theta * a + n
    return {
        "H_RATE": n / dt,
        "QV_RATE": delta_qv / dt,
        "QC_RATE": (qc_after - qc_before) / dt,
        "T_NEW_AFTER": full - t0,
    }


def replay_restricted_case(parent_evidence, restricted_evidence):
    """Replay the published projected-control confirmation with NumPy only."""
    root, manifest, paths = _restricted_bundle(restricted_evidence)
    parent_result = replay(parent_evidence)
    parent_root = Path(parent_evidence).resolve(strict=True)
    _require(
        manifest.get("parent_run_id") == parent_result["run_id"],
        "restricted publication parent run ID differs",
    )
    _require(
        manifest.get("parent_publication_manifest_sha256")
        == parent_result["publication_manifest_sha256"],
        "restricted publication does not bind the parent publication manifest",
    )
    _require(
        manifest.get("status")
        in (
            "RESTRICTED_UPDATE_ACCEPTED",
            "RESTRICTED_UPDATE_NOT_ACCEPTED",
            "REPRODUCTION_MISMATCH",
        ),
        "restricted publication status is not a completed decision",
    )

    summary = json.loads(paths["summary.json"].read_text())
    crosswalk = json.loads(paths["tendencies/tendency_crosswalk.json"].read_text())
    _require(
        summary.get("run_id") == manifest.get("run_id")
        and summary.get("parent_run_id") == manifest.get("parent_run_id")
        and summary.get("status") == manifest.get("status"),
        "restricted summary identity/status differs from manifest",
    )
    _require(
        summary.get("native_columns") == 65988
        and summary.get("original_blocks") == 129,
        "restricted summary is not the complete original native partition",
    )

    parent_bt = _arrays(parent_root / "channel_bt.npz")
    parent_support = _arrays(parent_root / "observation_support.npz")
    parent_state = _arrays(parent_root / "native_state_controls.npz")
    parent_gradient = _arrays(parent_root / "baseline_native_gradient_cost.npz")
    comparison = _arrays(paths["channel_comparison.npz"])
    controls = _arrays(paths["restricted_controls.npz"])
    input_state = _arrays(paths["candidate_input_state.npz"])
    input_delta = _arrays(paths["candidate_input_delta.npz"])
    baseline_applied_tq = _arrays(paths["baseline_applied_tq.npz"])
    candidate_applied_tq = _arrays(paths["candidate_applied_tq.npz"])
    baseline_applied_qc = _arrays(paths["baseline_applied_qc.npz"])
    candidate_applied_qc = _arrays(paths["candidate_applied_qc.npz"])
    finish_coordinates = _arrays(paths["tendencies/finish_theta_coordinates.npz"])
    initial_qc = _arrays(paths["tendencies/initial_qc.npz"])
    n, levels = 65988, 39
    flat = np.arange(n, dtype=np.int32)
    _require(
        np.array_equal(comparison["flat_index"], flat)
        and np.array_equal(input_state["flat_index"], flat)
        and np.array_equal(input_delta["flat_index"], flat),
        "restricted arrays do not cover native indices exactly once",
    )
    for name, arr in (
        ("baseline_applied_tq", baseline_applied_tq),
        ("candidate_applied_tq", candidate_applied_tq),
        ("baseline_applied_qc", baseline_applied_qc),
        ("candidate_applied_qc", candidate_applied_qc),
        ("finish_theta_coordinates", finish_coordinates),
        ("initial_qc", initial_qc),
    ):
        _require(
            np.array_equal(arr["flat_index"], flat),
            f"restricted {name} index coverage differs",
        )
    mask, weights = comparison["mask"], comparison["weights"]
    _require(
        all(
            comparison[name].dtype == np.float64 and comparison[name].shape == (n, 7)
            for name in ("observed_bt", "baseline_bt", "candidate_bt", "final_bt")
        )
        and comparison["baseline_quality"].shape
        == comparison["candidate_quality"].shape
        == (n, 7)
        and comparison["baseline_quality"].dtype.kind in "iu"
        and comparison["candidate_quality"].dtype.kind in "iu"
        and comparison["baseline_profile_valid"].dtype
        == comparison["candidate_profile_valid"].dtype
        == np.bool_
        and comparison["baseline_profile_valid"].shape
        == comparison["candidate_profile_valid"].shape
        == (n,),
        "restricted comparison arrays have invalid shapes or dtypes",
    )
    _require(
        mask.shape == (n, 7)
        and mask.dtype == np.bool_
        and weights.dtype == np.float64
        and np.array_equal(mask, parent_support["mask"])
        and weights.tobytes() == parent_support["weights"].tobytes()
        and np.array_equal(comparison["observed_bt"], parent_bt["observed_bt"]),
        "restricted candidate changed observations or fixed baseline support/weights",
    )
    Z = _sum(weights)
    _require(
        Z == parent_result["globalZ"] == summary["globalZ"],
        "restricted candidate changed the one global normalizer",
    )
    _require(
        np.array_equal(
            comparison["baseline_bt"], parent_bt["baseline_bt"], equal_nan=True
        )
        and np.array_equal(
            comparison["baseline_quality"], parent_bt["baseline_quality"]
        )
        and np.array_equal(
            comparison["baseline_profile_valid"], parent_support["profile_valid"]
        ),
        "restricted bundle baseline BT/quality/profile differs from parent",
    )
    _require(
        np.array_equal(
            comparison["baseline_bt"], comparison["final_bt"], equal_nan=True
        )
        if not summary["accepted"]
        else np.array_equal(
            comparison["candidate_bt"], comparison["final_bt"], equal_nan=True
        ),
        "restricted final BT does not match accepted/rejected status",
    )

    theta0 = parent_state["theta_m"]
    qv0 = parent_state["qv"]
    active = parent_support["active"]
    g = np.stack((parent_gradient["grad_theta_cost"], parent_gradient["grad_qv_cost"]))
    scales = np.stack((np.full_like(theta0, 0.2), 0.02 * qv0))
    scaled = np.where(active, scales * g, 0.0)
    maximum = float(np.max(np.abs(scaled)))
    _require(
        math.isfinite(maximum) and maximum > 0.0,
        "parent baseline has no finite active control direction",
    )
    direction = -scaled / maximum
    freeze_blocks = summary.get("freeze_blocks_0based")
    expected_blocks = [
        1,
        35,
        51,
        52,
        53,
        54,
        60,
        62,
        64,
        66,
        67,
        69,
        70,
        73,
        82,
        89,
        91,
        93,
        100,
        102,
        108,
        109,
        113,
        118,
        124,
    ]
    _require(freeze_blocks == expected_blocks, "restricted frozen-block list differs")
    frozen_rows = np.isin(flat // 512, freeze_blocks)
    expected_frozen_rows = np.broadcast_to(frozen_rows, (n,))
    _require(
        input_delta["frozen_control_rows"].dtype == np.bool_
        and np.array_equal(input_delta["frozen_control_rows"], expected_frozen_rows),
        "restricted frozen-control row bitmap differs from original blocks",
    )
    direction[:, frozen_rows, :] = 0.0
    z = controls["z"]
    _require(
        z.dtype == np.float64
        and z.shape == (2, n, levels)
        and z.flags.c_contiguous
        and np.isfinite(z).all()
        and hashlib.sha256(z.tobytes()).hexdigest() == summary["controls_sha256"]
        and z.tobytes() == direction.tobytes(),
        "restricted controls differ from the exact unrenormalized baseline projection",
    )
    _require(
        not np.any(z[:, frozen_rows, :]) and not np.any(z[~active]),
        "restricted controls changed frozen degrees of freedom",
    )
    expected_delta_theta = 0.2 * z[0]
    expected_delta_qv = 0.02 * qv0 * z[1]
    _require(
        input_delta["delta_theta"].dtype == input_delta["delta_qv"].dtype == np.float64
        and input_delta["delta_theta"].shape
        == input_delta["delta_qv"].shape
        == (n, levels)
        and input_delta["delta_theta"].tobytes() == expected_delta_theta.tobytes()
        and input_delta["delta_qv"].tobytes() == expected_delta_qv.tobytes(),
        "restricted input increments differ from S*z",
    )
    _require(
        input_state["theta_m"].tobytes() == (theta0 + expected_delta_theta).tobytes()
        and input_state["qv"].tobytes() == (qv0 + expected_delta_qv).tobytes(),
        "restricted T/Q inputs are not one baseline-relative update",
    )

    candidate_quality = comparison["candidate_quality"]
    candidate_profile_valid = comparison["candidate_profile_valid"]
    candidate_bt = comparison["candidate_bt"]
    candidate_support_preserved = bool(
        np.all(candidate_quality[mask] == 0)
        and np.isfinite(candidate_bt[mask]).all()
        and candidate_profile_valid[mask.any(axis=1)].all()
    )
    _require(
        np.all(candidate_quality[mask] == 0)
        and np.isfinite(candidate_bt[mask]).all()
        and candidate_profile_valid[mask.any(axis=1)].all(),
        "restricted candidate loses baseline observation support",
    )
    _require(
        np.array_equal(comparison["final_bt"], candidate_bt, equal_nan=True)
        if summary["accepted"]
        else True,
        "accepted final BT does not use the candidate output",
    )

    parent_scope = json.loads((parent_root / "scope.json").read_text())
    delta_huber = float(parent_scope["huber_delta"])
    sigma = float(parent_scope["observation_sigma_K"])
    bias = float(parent_scope["bias_K"])
    regularization = float(parent_scope["regularization_lambda"])
    expected_cost = _restricted_objective(
        candidate_bt,
        comparison["observed_bt"],
        mask,
        weights,
        z,
        active,
        delta=delta_huber,
        sigma=sigma,
        bias=bias,
    )
    expected_cost["regularization_numerator"] *= regularization
    expected_cost["numerator"] = math.fsum(
        (
            expected_cost["observation_numerator"],
            expected_cost["regularization_numerator"],
        )
    )
    expected_cost["cost"] = expected_cost["numerator"] / expected_cost["Z"]
    actual_recorded = summary.get("actual_objective")
    _require(
        actual_recorded == expected_cost,
        "restricted actual global objective differs from NumPy replay",
    )
    baseline_recorded = summary.get("baseline_objective")
    _require(
        baseline_recorded is not None
        and baseline_recorded.get("cost") == parent_result["baseline_J"],
        "restricted baseline objective differs from parent replay",
    )
    cost_threshold = 1e-10 + 1e-12 * abs(parent_result["baseline_J"])
    decreased = parent_result["baseline_J"] - expected_cost["cost"] > cost_threshold
    expected_accepted = manifest["status"] == "RESTRICTED_UPDATE_ACCEPTED"
    _require(
        type(summary.get("accepted")) is bool
        and summary["accepted"] is expected_accepted
        and manifest["status"] == summary["status"],
        "restricted summary and publication status differ",
    )
    _require(
        summary.get("accepted_input_delta_artifact")
        == ("candidate_input_delta.npz" if expected_accepted else None),
        "restricted accepted-input artifact differs from the decision",
    )
    _require(
        not expected_accepted or (candidate_support_preserved and decreased),
        "accepted restricted update fails fixed-support or cost threshold",
    )
    screen_matches_actual = summary.get("screen_J_total") == expected_cost["cost"]
    _require(
        np.array_equal(
            comparison["final_bt"],
            candidate_bt if decreased else comparison["baseline_bt"],
            equal_nan=True,
        ),
        "restricted final BT differs from acceptance decision",
    )

    cross = crosswalk.get("finish_crosswalk", {})
    _require(
        cross.get("TH_coordinate") == "absolute dry potential temperature, K"
        and cross.get("T_NEW_AFTER_coordinate")
        == "moist potential-temperature perturbation relative to t0, K"
        and cross.get("dt_seconds") == 20.0,
        "restricted tendency coordinate/dt contract differs",
    )
    for name, unit, receiver in (
        ("H_RATE", "K/s", "native_after_thm_pert/T_NEW_AFTER; rate is not reapplied"),
        ("QV_RATE", "kg/kg dry air/s", "native_after_qv"),
        ("QC_RATE", "kg/kg dry air/s", "cloud_qc"),
    ):
        definition = cross.get(name, {})
        _require(
            definition.get("unit") == unit
            and definition.get("receiver_state") == receiver,
            f"restricted {name} crosswalk units/receiver differ",
        )
    finish_cfg = {
        "dt_seconds": cross.get("dt_seconds"),
        "alpha": cross.get("alpha"),
        "t0_K": cross.get("t0_K"),
        "mp_tend_lim_K_s": cross.get("mp_tend_lim_K_s"),
    }
    initial_qc_values = _restricted_initial_qc(initial_qc, n, levels)
    candidate_qv0 = input_state["qv"]
    candidate_qv1 = candidate_applied_tq["qv_after"]
    baseline_qv1 = baseline_applied_tq["qv_after"]
    baseline_qc1 = baseline_applied_qc["qc_after"]
    candidate_qc1 = candidate_applied_qc["qc_after"]
    before_theta = finish_coordinates["before_theta"]
    clean_theta = finish_coordinates["clean_theta"]
    _require(
        all(
            a.dtype == np.float64 and a.shape == (n, levels) and np.isfinite(a).all()
            for a in (
                initial_qc_values,
                candidate_qv0,
                candidate_qv1,
                baseline_qv1,
                baseline_qc1,
                candidate_qc1,
                before_theta,
                clean_theta,
            )
        ),
        "restricted tendency input arrays have wrong shape/dtype or nonfinite values",
    )
    candidate_formula = _candidate_finish_numpy(
        before_theta,
        clean_theta,
        candidate_qv0,
        candidate_qv1,
        initial_qc_values,
        candidate_qc1,
        finish_cfg,
    )
    _require(
        candidate_applied_tq["t_new_after"].tobytes()
        == candidate_formula["T_NEW_AFTER"].tobytes(),
        "candidate T_NEW_AFTER receiver differs from NumPy finish replay",
    )
    baseline_audit = json.loads(
        (parent_root / "applied_physics_audit.json").read_text()
    )
    audit_report = baseline_audit.get("report", {})
    audit_phases = audit_report.get("phases", [])
    _require(
        audit_report.get("run_id") == parent_result["run_id"]
        and len(audit_phases) == 1
        and audit_phases[0].get("all_replay_bit_gates_passed") is True
        and audit_phases[0].get("blocks") == 129,
        "parent applied-physics audit is not the pinned complete baseline audit",
    )
    audit_chunks = audit_phases[0].get("chunks", [])
    _require(
        len(audit_chunks) == 129
        and [c.get("chunk_index") for c in audit_chunks] == list(range(129))
        and all(
            c.get("rate_relations", {}).get("max_abs_residual", [None])[0] == 0.0
            for c in audit_chunks
        ),
        "parent baseline H_RATE qualification is not the recorded zero-residual audit",
    )
    rate_relations = crosswalk.get("rate_relation_audit", {})
    baseline_h_audit = rate_relations.get("baseline", {})
    _require(
        baseline_h_audit.get("H_RATE_relation_max_abs_residual") == 0.0
        and "APPLIED_PHYSICS_AUDIT"
        in baseline_h_audit.get("H_RATE_relation_source", ""),
        "public crosswalk does not qualify baseline H_RATE from its pinned audit",
    )
    confirmation_rate_audit = (
        summary.get("applied_tendencies", {})
        .get("rate_relation_audit", {})
        .get("confirmation", {})
    )
    _require(
        confirmation_rate_audit.get("H_RATE_QV_RATE_QC_RATE_formula_bitwise_match")
        == [True, True, True],
        "restricted public summary does not record all three candidate rate formula bit gates",
    )

    exports = crosswalk.get("exports", {})
    expected_rate_units = {
        "H_RATE": "K/s",
        "QV_RATE": "kg/kg dry air/s",
        "QC_RATE": "kg/kg dry air/s",
    }
    rate_replay = {}
    for name, unit in expected_rate_units.items():
        record = exports.get(name)
        _require(
            isinstance(record, dict) and record.get("unit") == unit,
            f"restricted crosswalk lacks {name} with its declared unit",
        )
        rel = Path(record.get("path", ""))
        _require(
            not rel.is_absolute() and ".." not in rel.parts,
            f"restricted {name} path escapes the public bundle",
        )
        rate_path = (root / rel).resolve(strict=True)
        _require(
            root in rate_path.parents and str(rel) in manifest["artifacts"],
            f"restricted {name} artifact is not manifest-owned",
        )
        rate = _arrays(rate_path)
        _require(
            set(rate) == {"flat_index", "baseline", "candidate", "delta"}
            and np.array_equal(rate["flat_index"], flat)
            and all(
                rate[field].dtype == np.float64
                and rate[field].shape == (n, levels)
                and np.isfinite(rate[field]).all()
                for field in ("baseline", "candidate", "delta")
            ),
            f"restricted {name} arrays have invalid schema",
        )
        _require(
            rate["delta"].tobytes() == (rate["candidate"] - rate["baseline"]).tobytes(),
            f"restricted {name} delta does not equal candidate minus baseline",
        )
        _require(
            all(
                _sha_array(rate[field]) == record.get("field_sha256", {}).get(field)
                for field in ("baseline", "candidate", "delta")
            ),
            f"restricted {name} field digest differs from crosswalk",
        )
        rate_replay[name] = rate

    _require(
        finish_cfg["dt_seconds"] == 20.0,
        "restricted finish rate replay requires the fixed 20-second map",
    )
    baseline_qv_formula = (baseline_qv1 - qv0) / 20.0
    baseline_qc_formula = (baseline_qc1 - initial_qc_values) / 20.0
    candidate_qv_formula = (candidate_qv1 - candidate_qv0) / 20.0
    candidate_qc_formula = (candidate_qc1 - initial_qc_values) / 20.0
    for name, baseline_formula, candidate_formula_values in (
        ("QV_RATE", baseline_qv_formula, candidate_qv_formula),
        ("QC_RATE", baseline_qc_formula, candidate_qc_formula),
    ):
        _require(
            rate_replay[name]["baseline"].tobytes() == baseline_formula.tobytes()
            and rate_replay[name]["candidate"].tobytes()
            == candidate_formula_values.tobytes(),
            f"restricted {name} does not match its independent state-difference formula",
        )
    _require(
        rate_replay["H_RATE"]["candidate"].tobytes()
        == candidate_formula["H_RATE"].tobytes(),
        "restricted candidate H_RATE does not match the independent finish formula",
    )
    tendency_limits = (
        "Candidate H/QV/QC rates are independently replayed from published finish inputs.",
        "Baseline QV/QC rates are independently replayed; baseline H_RATE is qualified only by the pinned parent applied-physics audit.",
        "Published control arrays do not expose every held non-T/Q model input; those are bound by execution/source receipts, not independently bit-compared here.",
        "No KDM, RTTOV, host, or Torch calls are made by this replayer.",
    )
    return {
        "schema": "kdm6.native_satellite_restricted_public_arithmetic_replay.v1",
        "status": "REPLAY_PASSED",
        "decision_status": manifest["status"],
        "run_id": manifest["run_id"],
        "parent_run_id": parent_result["run_id"],
        "parent_baseline_J": parent_result["baseline_J"],
        "restricted_J": expected_cost["cost"],
        "globalZ": Z,
        "control_z_sha256": hashlib.sha256(z.tobytes()).hexdigest(),
        "frozen_blocks_0based": freeze_blocks,
        "accepted": expected_accepted,
        "cost_decreased_past_threshold": decreased,
        "screen_cost_matches_actual": screen_matches_actual,
        "candidate_support_preserved": candidate_support_preserved,
        "candidate_finish_rates_replayed": True,
        "baseline_qv_qc_rates_replayed": True,
        "baseline_h_rate_scope": "pinned parent applied-physics audit, zero recorded relation residual; not independently reconstructed",
        "new_KDM_RTTOV_host_calls": 0,
        "parent_replay_manifest_sha256": parent_result["publication_manifest_sha256"],
        "restricted_manifest_sha256": _sha(root / "publication_manifest.json"),
        "replayer_sha256": _sha(Path(__file__)),
        "limits": list(tendency_limits),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument(
        "--restricted-evidence",
        type=Path,
        help="Optional restricted-confirmation publication to replay against parent evidence",
    )
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    result = (
        replay_restricted_case(args.evidence, args.restricted_evidence)
        if args.restricted_evidence is not None
        else replay(args.evidence)
    )
    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output_json:
        with args.output_json.open("x") as stream:
            stream.write(text)
    print(text, end="")


if __name__ == "__main__":
    main()
