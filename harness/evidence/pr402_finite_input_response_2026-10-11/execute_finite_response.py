#!/usr/bin/env python3
"""Execute one frozen four-trial plan; default validates it without radiation.

No native integration, KDM, optimization, retry or extra baseline evaluation.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import json
import os
import re
import sys
from pathlib import Path

import numpy as np

import finite_input_response as prep

sys.path.insert(0, str(prep.ROOT / "oracle"))
from kdm6.obs._rttov_reference.rttov_ascii import parse_rttov_ascii_blocks  # noqa: E402
from kdm6.obs.ami_bt_coordinate import (  # noqa: E402
    read_ami_filters,
    read_kma_calibration,
    transform_rttov_to_kma,
)
from kdm6.obs.rttov_runner import parse_rttov_radiance, run_rttov_k  # noqa: E402

RELATIVE_CUTOFF_K = 1e-6


def loss(bt: np.ndarray, obs: np.ndarray, sigma: np.ndarray) -> float:
    residual = (bt - obs) / sigma
    absolute = np.abs(residual)
    return float(np.sum(np.where(absolute <= 1, 0.5 * residual**2, absolute - 0.5)))


def compare_pair(minus, plus, baseline, kd, h, linear_minus, linear_plus) -> dict:
    """K0d is per declared unit direction; h is .5 for skin and 1 for O3."""
    if not np.isfinite(h) or h <= 0:
        raise ValueError("finite-difference h must be positive and finite")
    minus, plus, baseline, kd, linear_minus, linear_plus = (
        np.asarray(x, dtype=np.float64)
        for x in (minus, plus, baseline, kd, linear_minus, linear_plus)
    )
    if any(
        x.shape != (7,) or not np.isfinite(x).all()
        for x in (minus, plus, baseline, kd, linear_minus, linear_plus)
    ):
        raise ValueError("pair comparisons require seven finite channels")
    fd = (plus - minus) / (2 * h)
    error = fd - kd
    scale = np.maximum(np.abs(fd), np.abs(kd))
    relative = [
        float(error[j] / scale[j]) if scale[j] >= RELATIVE_CUTOFF_K else None
        for j in range(7)
    ]
    return {
        "h": h,
        "K0d_K_per_unit_direction": kd.tolist(),
        "D_FD_K_per_unit_direction": fd.tolist(),
        "K_effective_serialized_K_per_unit_direction": (
            (linear_plus - linear_minus) / (2 * h)
        ).tolist(),
        "derivative_error_serialized_K_per_unit_direction": (
            fd - (linear_plus - linear_minus) / (2 * h)
        ).tolist(),
        "derivative_error_K_per_unit_direction": error.tolist(),
        "relative_error": relative,
        "relative_denominator": "max(abs(D_FD),abs(K0d)); null below 1e-6 K per unit direction",
        "E_minus_ideal_K": (minus - baseline + h * kd).tolist(),
        "E_plus_ideal_K": (plus - baseline - h * kd).tolist(),
        "E_minus_serialized_K": (minus - baseline - linear_minus).tolist(),
        "E_plus_serialized_K": (plus - baseline - linear_plus).tolist(),
        "baseline_midpoint_difference_K": ((minus + plus) / 2 - baseline).tolist(),
    }


def assert_assets(plan):
    actual = prep.resolve_trial_assets(plan["runtime_assets"])
    for key in ("rttov_executable_sha256", "coefficient_sha256", "hydrotable_sha256"):
        prep.require(
            actual[key] == plan["runtime_assets"][key], f"runtime changed: {key}"
        )
    prep.require(
        actual["library_manifest"]["libraries"]
        == plan["runtime_assets"]["library_manifest"]["libraries"],
        "library manifest changed",
    )


def validate(plan_path: Path, expected_sha: str) -> dict:
    prep.require(prep.sha256(plan_path) == expected_sha, "frozen plan hash mismatch")
    plan = json.loads(plan_path.read_text())
    prep.require(
        plan["status"] == "PREFLIGHT_READY_NOT_EXECUTED", "plan is not preflight-ready"
    )
    prep.require(
        [t["trial_name"] for t in plan["trials"]] == list(prep.TRIALS),
        "four-trial order changed",
    )
    prep.require(plan["scope"]["max_wrapper_calls"] == 4, "wrapper budget changed")
    binding = plan["execution_source"]
    prep.require(
        Path(binding["path"]).resolve() == Path(__file__).resolve(),
        "executor path changed",
    )
    prep.require(
        binding["sha256"] == prep.sha256(Path(__file__)), "executor source changed"
    )
    pre = plan["preflight_provenance"]
    prep.require(
        pre["helper_sha256"] == prep.sha256(Path(prep.__file__)),
        "preflight source changed",
    )
    source = plan["production_runner_source"]
    prep.require(
        prep.sha256(Path(source["path"])) == source["sha256"],
        "production runner changed",
    )
    center = Path(plan["baseline"]["center_case_path_read_only"])
    prep.require(
        prep.file_inventory(center / "in") == plan["baseline"]["input_sha256"],
        "baseline input changed",
    )
    for trial in plan["trials"]:
        case = Path(trial["trial_case_path"])
        prep.require(
            case.resolve() != center.resolve()
            and center.resolve() not in case.resolve().parents,
            "trial aliases original center",
        )
        prep.require(
            prep.file_inventory(case / "in") == trial["input_sha256"],
            "trial input changed",
        )
        for name, digest in trial["out_static_files"].items():
            prep.require(
                prep.sha256(case / "out" / name) == digest,
                f"launch file changed: {name}",
            )
        prep.require(
            not list((case / "out/k").iterdir())
            and not list((case / "out/direct").iterdir()),
            "trial already contains outputs",
        )
    assert_assets(plan)
    return plan


def execute(plan_path: Path, expected_sha: str, execution_id: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,40}", execution_id):
        raise ValueError("execution ID must have 8–40 safe characters")
    plan = validate(plan_path, expected_sha)
    out = plan_path.parent
    prep.require(not (out / "FINITE_RESULT.json").exists(), "result already exists")
    guard = Path(plan["execution_guard"]["guard_path"])
    fd = os.open(guard, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(
            {
                "execution_id": execution_id,
                "plan_sha256": expected_sha,
                "executor_sha256": prep.sha256(Path(__file__)),
            },
            stream,
        )
    with Path(plan["execution_guard"]["lock_path"]).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return run_trials(plan, plan_path, execution_id)


def run_trials(plan: dict, plan_path: Path, execution_id: str) -> dict:
    out = plan_path.parent
    baseline = plan["baseline"]
    center = Path(baseline["center_case_path_read_only"])
    npz = Path(baseline["pr401_private_npz_path"])
    prep.require(
        prep.sha256(npz) == baseline["pr401_private_npz_sha256"], "baseline NPZ changed"
    )
    with np.load(npz, allow_pickle=False) as saved:
        a = {key: saved[key].copy() for key in saved.files}
    bt0 = a["kma_bt_k"].reshape(7)
    obs = a["observation_bt_kma_k"].reshape(7)
    sigma = np.broadcast_to(a["observation_sigma_k"], (1, 7)).reshape(7)
    prep.require(
        np.all(sigma == 1)
        and np.all(a["observation_bias_k"] == 0)
        and np.all(a["frozen_support"] == 1),
        "fixed objective changed",
    )
    base_jo = loss(bt0, obs, sigma)
    slope = np.clip((bt0 - obs) / sigma, -1, 1) / sigma
    names = a["direction_names"].tolist()
    kd_skin = a["direction_delta_bt_kma_k"][names.index("skin_T_plus_1K")]
    kd_o3 = a["direction_delta_bt_kma_k"][names.index("reference_o3_plus_1pct")]
    filters = read_ami_filters(plan["runtime_assets"]["coefficient_resolved_path"])
    calibration = read_kma_calibration()
    arrays = {
        "baseline_bt_K": bt0,
        "observation_bt_K": obs,
        "baseline_Kd_skin": kd_skin,
        "baseline_Kd_o3": kd_o3,
        "P": a["log_pressure_interpolation_matrix"],
        "source_o3_ppmv": a["reference_o3_ppmv_moist"],
    }
    rows, launched, stage = [], 0, "before_trial"
    try:
        for trial in plan["trials"]:
            case, name = Path(trial["trial_case_path"]), trial["trial_name"]
            stage = f"prelaunch:{name}"
            prep.require(
                prep.file_inventory(case / "in") == trial["input_sha256"],
                "trial input changed",
            )
            assert_assets(plan)
            if name.startswith("skin"):
                delta = (
                    prep.read_skin_temperature(
                        (case / "in/profiles/001/sfc/01/skin.txt").read_text()
                    )
                    - baseline["baseline_skin_t_k"]
                )
                predicted = a["k_kma__SKIN_1_T"].reshape(7) * delta
                arrays[f"{name}__actual_input_delta"] = np.asarray([delta])
            else:
                values = np.loadtxt(
                    case / "in/profiles/001/atm/o3.txt", dtype=np.float64
                )
                delta = values - a["active_o3_ppmv_moist"]
                predicted = a["k_kma__O3"].reshape(7, 66) @ delta
                arrays[f"{name}__o3_input_ppmv"] = values
                arrays[f"{name}__actual_input_delta"] = delta
            stage = f"wrapper:{name}"
            launched += 1
            prep.require(launched <= 4, "wrapper budget exceeded")
            returned = run_rttov_k(
                case / "out", nchannels=7, expected_nprofiles=1, timeout=300
            )
            stage = f"quality:{name}"
            quality = np.asarray(returned.rad_quality)
            prep.require(
                quality.shape == (1, 7) and np.all(quality == 0),
                f"fixed-channel quality lost: {quality.tolist()}",
            )
            direct = parse_rttov_radiance(case / "out/direct/radiance.txt", nchannels=7)
            prep.require(
                direct["nprofiles"] == 1
                and np.all(np.asarray(direct["rad_quality"]) == 0),
                "direct output quality/profile count failed",
            )
            direct_difference = float(
                np.max(np.abs(np.asarray(direct["bt"]) - np.asarray(returned.bt)))
            )
            prep.require(
                direct_difference <= 3e-6, "same-run direct and K native BT differ"
            )
            total = np.asarray(
                parse_rttov_ascii_blocks(case / "out/k/radiance.txt")["RADIANCE%TOTAL"]
            ).reshape(1, 7)
            bt, converted, ratio = transform_rttov_to_kma(
                returned.bt, total, returned.k, prep.CHANNEL_IDS, filters, calibration
            )
            bt = bt.reshape(7)
            jo = loss(bt, obs, sigma)
            row = {
                "trial": name,
                "BT_K": bt.tolist(),
                "quality": quality.reshape(7).tolist(),
                "delta_BT_K": (bt - bt0).tolist(),
                "linear_BT_serialized_K": predicted.tolist(),
                "E_serialized_K": (bt - bt0 - predicted).tolist(),
                "Jo_dimensionless": jo,
                "delta_Jo_actual": jo - base_jo,
                "delta_Jo_linear_serialized": float(slope @ predicted),
                "wrapper_returned": True,
                "direct_vs_K_native_BT_max_abs_K": direct_difference,
                "k_output_sha256": prep.sha256(case / "out/k/profiles_k.txt"),
                "radiance_output_sha256": prep.sha256(case / "out/k/radiance.txt"),
                "direct_radiance_sha256": prep.sha256(case / "out/direct/radiance.txt"),
            }
            rows.append(row)
            arrays[f"{name}__BT_K"] = bt
            arrays[f"{name}__quality"] = quality
            arrays[f"{name}__native_BT_K"] = np.asarray(returned.bt)
            arrays[f"{name}__total_radiance"] = total
            arrays[f"{name}__coordinate_ratio"] = ratio
            for field, matrix in converted.items():
                key = re.sub(r"[^A-Za-z0-9]+", "_", field)
                arrays[f"{name}__K_KMA__{key}"] = np.asarray(matrix)
                arrays[f"{name}__K_native__{key}"] = np.asarray(returned.k[field])
            prep.require(
                prep.file_inventory(case / "in") == trial["input_sha256"],
                "RTTOV changed input",
            )
        stage = "postcheck"
        assert_assets(plan)
        prep.require(
            prep.file_inventory(center / "in") == baseline["input_sha256"],
            "original input changed",
        )
        for rel, digest in plan["original_case_unchanged_during_preflight"][
            "before"
        ].items():
            path = center / rel if rel.startswith("out/") else center / "out" / rel
            prep.require(prep.sha256(path) == digest, "original center output changed")
        by = {r["trial"]: r for r in rows}
        comparisons = {}
        for direction, minus, plus, kd, h in (
            ("skin", prep.TRIALS[0], prep.TRIALS[1], kd_skin, 0.5),
            ("o3", prep.TRIALS[2], prep.TRIALS[3], kd_o3, 1.0),
        ):
            comparisons[direction] = compare_pair(
                by[minus]["BT_K"],
                by[plus]["BT_K"],
                bt0,
                kd,
                h,
                by[minus]["linear_BT_serialized_K"],
                by[plus]["linear_BT_serialized_K"],
            )
        private = (
            Path(plan["execution_guard"]["guard_path"]).parent / "FINITE_PAYLOAD.npz"
        )
        with private.open("xb") as stream:
            os.chmod(private, 0o600)
            np.savez_compressed(stream, **arrays)
        result = {
            "status": "ALL_FOUR_TRIALS_RETURNED",
            "execution_id": execution_id,
            "plan_sha256": prep.sha256(plan_path),
            "executor_sha256": prep.sha256(Path(__file__)),
            "baseline_Jo_dimensionless": base_jo,
            "trials": rows,
            "comparisons": comparisons,
            "calls": {
                "wrapper_launches": launched,
                "returned_direct_outputs": 4,
                "returned_K_outputs": 4,
                "internal_RTTOV_H_calls": None,
                "M": 0,
                "native": 0,
                "optimizer": 0,
            },
            "private_npz": {"path": str(private), "sha256": prep.sha256(private)},
            "limits": [
                "Unit perturbations, not measured errors or corrections",
                "Historical baseline library hashes unavailable; E uses preserved baseline",
                "No fresh baseline, fifth trial, retry or channel removal",
            ],
        }
        with (out / "FINITE_RESULT.json").open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        with (out / "FINITE_CHANNELS.csv").open("x", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "trial",
                    "channel",
                    "BT_K",
                    "delta_BT_K",
                    "linear_BT_K",
                    "E_serialized_K",
                ],
            )
            writer.writeheader()
            for row in rows:
                for j, channel in enumerate(prep.CHANNEL_IDS):
                    writer.writerow(
                        {
                            "trial": row["trial"],
                            "channel": channel,
                            "BT_K": row["BT_K"][j],
                            "delta_BT_K": row["delta_BT_K"][j],
                            "linear_BT_K": row["linear_BT_serialized_K"][j],
                            "E_serialized_K": row["E_serialized_K"][j],
                        }
                    )
        return result
    except BaseException as exc:
        failure = {
            "status": "FAILED_NO_ACCEPTED_RESULT",
            "stage": stage,
            "wrapper_launches": launched,
            "returned_trials": rows,
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "automatic_retry": False,
        }
        with Path(plan["execution_guard"]["failure_record_path"]).open("x") as stream:
            json.dump(failure, stream, indent=2)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha", required=True)
    parser.add_argument("--execution-id")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.execute:
        result = execute(args.plan, args.plan_sha, args.execution_id or "")
        print(json.dumps({"status": result["status"], "calls": result["calls"]}))
    else:
        validate(args.plan, args.plan_sha)
        print(json.dumps({"status": "VALIDATED_NO_WRAPPER_CALL", "wrapper_calls": 0}))


if __name__ == "__main__":
    main()
