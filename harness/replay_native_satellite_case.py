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


def _arrays(path):
    with np.load(path, allow_pickle=False) as archive:
        return {name: archive[name].copy() for name in archive.files}


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    result = replay(args.evidence)
    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output_json:
        with args.output_json.open("x") as stream:
            stream.write(text)
    print(text, end="")


if __name__ == "__main__":
    main()
