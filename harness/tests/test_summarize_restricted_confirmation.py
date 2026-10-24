"""Full-grid output assembly remains separate from physical execution."""
import hashlib

import numpy as np

from harness import summarize_native_satellite_case as summary


def test_restricted_summary_joins_parent_once_and_keeps_rejected_final_baseline(tmp_path, monkeypatch):
    parent, run, out = (tmp_path / name for name in ("parent", "run", "summary"))
    parent.mkdir()
    run.mkdir()
    n, levels = 65988, 39
    zero = np.zeros((n, levels))
    z = np.zeros((2, n, levels))
    mask = np.ones((n, 7), dtype=bool)
    baseline = {"flat_index": np.arange(n), "mask": mask, "weights": mask.astype(float),
                "obs_bt": np.full((n, 7), 200.0), "bt": np.full((n, 7), 201.0),
                "source_eligible": mask, "active": np.ones_like(z, dtype=bool),
                "theta_m": zero, "qv": zero, "finish": np.zeros((5, n, levels)),
                "profile_valid": np.ones(n, dtype=bool), "quality": np.zeros((n, 7), dtype=np.int32),
                "reasons": np.full(n, "OK")}
    candidate = dict(baseline, z=z, delta_theta=zero, delta_qv=zero)
    chunks = [{"chunk_index": i, "start": s, "stop": min(s + 512, n)}
              for i, s in enumerate(range(0, n, 512))]
    cost = {"observation_numerator": n * 7 / 2, "regularization_numerator": 0.0,
            "numerator": n * 7 / 2, "Z": float(n * 7), "cost": 0.5}
    manifest = {"chunks": chunks, "globalZ": n * 7, "objective": {"J_total": 0.5}}
    confirmation = {"chunks": chunks, "globalZ": n * 7, "actual_objective": cost,
                    "controls_sha256": hashlib.sha256(z.tobytes()).hexdigest(),
                    "stage": "RESTRICTED_alpha_1p0", "screen_objective": 0.5,
                    "status": "RESTRICTED_UPDATE_NOT_ACCEPTED"}
    case = {"run_id": "candidate", "freeze_blocks_0based": [1], "expected_screen_J_total": 0.5}
    monkeypatch.setattr(summary, "_load_restricted_confirmation", lambda *_:
                        ({"run_id": "parent"}, manifest, {}, case, confirmation, {}))
    joins = []

    def join(root, *_args, **kwargs):
        joins.append((root, kwargs.get("trial", False)))
        return candidate if root == run else baseline

    monkeypatch.setattr(summary, "_join_manifest", join)
    monkeypatch.setattr(summary, "_read_capture_arrays", lambda _root, entry, _names:
                        ({"native_after_qv": zero[entry["start"]:entry["stop"]],
                          "cloud_qc": zero[entry["start"]:entry["stop"]]}, {}))
    monkeypatch.setattr(summary, "export_restricted_tendencies", lambda *_: {"new_model_calls": 0})
    result = summary.summarize_restricted_confirmation(parent, run, out, make_plots=False)
    assert joins == [(parent, False), (run, True)]
    assert result["actual_objective"] == cost
    assert result["accepted_input_delta_artifact"] is None
    assert result["frozen_native_columns"] == 512
    assert result["applied_tendencies"]["new_model_calls"] == 0
    with np.load(out / "channel_comparison.npz") as archive:
        assert archive["final_bt"].tobytes() == baseline["bt"].tobytes()
    with np.load(out / "candidate_applied_tq.npz") as archive:
        assert archive["qv_after"].shape == (n, levels)
        assert "t_new_after" in archive.files  # NativeFinishResult's perturbation coordinate.
    assert not (run / "BASELINE.json").exists()
