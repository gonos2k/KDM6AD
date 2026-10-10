"""Compare saved H outputs and observed patch ranges; no model/H calls."""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
PACKET = Path(__file__).resolve().parent


def main():
    result = json.loads((PACKET / "NEIGHBOR_RESULT_attempt2.json").read_text())
    observed = json.loads((ROOT / "harness/evidence/pr398_spatial_representativeness_2026-10-10/OBSERVATION_PATCH.json").read_text())
    rows = result["results"]
    if len(rows) != 9 or {(r["j"], r["i"]) for r in rows} != {(j, i) for j in range(85, 88) for i in range(47, 50)}:
        raise ValueError("Nine fixed native cells must all be present")
    bt = np.array([r["BT_K"][0] for r in rows])
    quality = np.array([r["rad_quality"][0] for r in rows])
    if bt.shape != (9, 7) or not np.isfinite(bt).all() or np.any(quality != 0):
        raise ValueError("Full seven-channel support required for range comparison")
    target = np.asarray(result["fixed_observation"]["BT_K"])
    residual = np.abs(bt - target)
    costs = np.where(residual <= 1, .5 * residual**2, residual - .5).sum(axis=1)
    np.testing.assert_allclose(costs, [r["Jo_huber_K_units"] for r in rows], rtol=0, atol=1e-12)
    comparison = []
    for k, row in enumerate(observed["AMI_patch"]["channel_summary"]):
        low, high = float(bt[:, k].min()), float(bt[:, k].max())
        obs_low, obs_high = row["bt_valid_min_K"], row["bt_valid_max_K"]
        comparison.append({"channel": row["ami_channel"], "model_min_K": low,
                           "model_max_K": high, "observation_min_K": obs_low,
                           "observation_max_K": obs_high,
                           "interval_distance_K": max(0, low - obs_high, obs_low - high),
                           "model_side": "warmer" if low > obs_high else "colder" if high < obs_low else "overlapping"})
    output = {"schema": "pr399.saved_range_comparison.v1", "source_result": "NEIGHBOR_RESULT_attempt2.json",
              "new_H_calls": 0, "comparisons": comparison,
              "limits": "Fixed common geometry, existing gas/surface/reference assumptions and paired BT coordinate. Range separation is not physical matchup or unique process attribution; signed SINC weights and outside-patch inputs excluded."}
    with (PACKET / "NEIGHBOR_RANGE_COMPARISON.json").open("x") as f:
        json.dump(output, f, indent=2, allow_nan=False)
        f.write("\n")


if __name__ == "__main__":
    main()
