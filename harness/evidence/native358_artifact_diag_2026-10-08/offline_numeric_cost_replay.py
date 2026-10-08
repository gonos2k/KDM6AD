#!/usr/bin/env python3
"""Offline replay of the stored eight-frame, common-mask Huber cost only.

This reads the enriched JSON in this evidence packet. It does not read model
NetCDF, source profiles, RTTOV assets, or private output directories.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "results/native8frame_failed_run_artifact_diagnostic_enriched.json"
OUTPUT = ROOT / "results/offline_numeric_cost_replay.json"


def close(a: float, b: float, tolerance: float = 1.0e-12) -> bool:
    return abs(a - b) <= tolerance * max(1.0, abs(a), abs(b))


def main() -> None:
    data = json.loads(INPUT.read_text())
    if not (data.get("status") == "DIAGNOSTIC_ONLY_FAILED_NATIVE_RUN"
            and data.get("native_run_valid") is False
            and data.get("experiment_valid") is False
            and data.get("diagnostic_only") is True
            and data.get("eligible_for_artifact_gates") is False):
        raise ValueError("input result does not retain the failed-run diagnostic-only flags")
    times = data["forecast_times"]
    frames = data["per_frame"]
    if len(times) != 8 or len(frames) != 8:
        raise ValueError("expected eight saved frames")
    observation = data["observation_bt_K"]
    dqf = data["observation_dqf"]
    quality = data["model_rad_quality"]
    if len(observation) != 9 or any(x != 0 for x in dqf):
        raise ValueError("expected the retained 9-channel observation with DQF zero")
    if len(quality) != 8 or any(len(row) != 9 for row in quality):
        raise ValueError("RTTOV quality array is not 8×9")
    support = [j for j in range(9) if dqf[j] == 0 and all(quality[i][j] == 0 for i in range(8))]
    if support != data["fixed_common_support_channel_indices_0based"]:
        raise ValueError("recomputed fixed common mask differs from stored mask")
    if [data["rttov_channel_ids"][j] for j in support] != data["fixed_common_support_rttov_channels"]:
        raise ValueError("common RTTOV channel IDs differ from stored mask")

    sigma = float(data["sigma_K"])
    delta = float(data["huber_delta"])
    if sigma != 1.0 or float(data["bias_K"]) != 0.0 or delta != 1.0:
        raise ValueError("this replay is scoped to sigma=1 K, zero bias, delta=1")
    replay_costs = []
    frame_records = []
    for index, frame in enumerate(frames):
        if frame["valid_time"] != times[index] or frame["common_support"] != [j in support for j in range(9)]:
            raise ValueError(f"frame {index} time or common mask differs")
        contribution = []
        for j in range(9):
            r = (float(frame["bt_K"][j]) - float(observation[j])) / sigma
            h = 0.5 * r * r if abs(r) <= delta else delta * (abs(r) - 0.5 * delta)
            contribution.append(h if j in support else 0.0)
        cost = math.fsum(contribution)
        recorded = float(data["cost_sum_huber_all_eight_same_support"][index])
        if not close(cost, recorded):
            raise ValueError(f"frame {index} replayed cost {cost} differs from stored {recorded}")
        saved_contribution = frame["common_support_huber_contribution_dimensionless"]
        if any(not close(contribution[j], float(saved_contribution[j])) for j in range(9)):
            raise ValueError(f"frame {index} per-channel dimensionless contributions differ")
        replay_costs.append(cost)
        frame_records.append(dict(index=index, valid_time=times[index],
                                  dimensionless_huber_cost=cost,
                                  max_abs_BT_residual_K=max(abs(float(frame["bt_K"][j])
                                                               - float(observation[j])) for j in support)))

    result = dict(
        schema="offline_numeric_cost_replay_v1",
        replayed_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        input_path=str(INPUT.name),
        input_scope="Enriched stored result only; no NetCDF or RTTOV invocation",
        output_scope="Replay of stored Huber arithmetic and common mask only; no H, K, state, or model computation",
        native_run_valid=False, experiment_valid=False, diagnostic_only=True,
        eligible_for_artifact_gates=False,
        sigma_K=sigma, bias_K=float(data["bias_K"]), huber_delta=delta,
        observation_DQF_all_zero=all(x == 0 for x in dqf),
        common_support_channel_indices_0based=support,
        common_support_rttov_channels=[data["rttov_channel_ids"][j] for j in support],
        replay_matches_stored_costs=True,
        replayed_costs=replay_costs,
        stored_costs=data["cost_sum_huber_all_eight_same_support"],
        max_abs_cost_difference=max(abs(a-b) for a, b in zip(replay_costs,
                                                             data["cost_sum_huber_all_eight_same_support"])),
        per_frame=frame_records,
        K_product_computed_by_RTTOV_but_not_consumed_by_adjoint=True,
        native_invalid_reason=data["native_run_lifecycle"],
    )
    OUTPUT.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(OUTPUT.name),
                      "replay_matches_stored_costs": result["replay_matches_stored_costs"],
                      "max_abs_cost_difference": result["max_abs_cost_difference"],
                      "common_support_rttov_channels": result["common_support_rttov_channels"],
                      "native_run_valid": False}, indent=2))


if __name__ == "__main__":
    main()
