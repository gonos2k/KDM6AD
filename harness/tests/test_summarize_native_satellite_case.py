"""Small-grid saved-artifact tests for native satellite case summarization."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from harness.summarize_native_satellite_case import summarize


def _objective(bt, obs, mask, weights):
    residual = bt[mask] - obs[mask]
    w = weights[mask]
    absolute = np.abs(residual)
    loss = np.where(absolute <= 1.0, 0.5 * residual**2, absolute - 0.5)
    return float(np.sum(w * loss) / np.sum(weights))


def _artifact_arrays(start, stop, *, trial=False):
    b, levels, channels = stop - start, 2, 7
    flat = np.arange(start, stop, dtype=np.int64)
    obs = (270.0 + flat[:, None] * 0.01 + np.arange(channels)[None, :]).astype(
        np.float64
    )
    quality = np.zeros((b, channels), dtype=np.int16)
    source_eligible = np.ones((b, channels), dtype=np.bool_)
    profile_valid = np.ones(b, dtype=np.bool_)
    if start <= 5 < stop:
        source_eligible[5 - start] = False
        if not trial:
            profile_valid[5 - start] = False
    if start <= 1 < stop:
        quality[1 - start, 2] = 1
    if start <= 4 < stop:
        # Source-invalid channel: quality happens to be zero, but fixed mask is off.
        source_eligible[4 - start, 5] = False
    mask = source_eligible & (quality == 0)
    weights = mask.astype(np.float64)
    baseline_bt = obs + 1.0
    baseline_bt[~mask] = np.nan
    qv = np.array(
        [[0.0, 1.0e-4] if row % 2 == 0 else [2.0e-4, 0.0] for row in flat],
        dtype=np.float64,
    )
    active = np.zeros((2, b, levels), dtype=np.bool_)
    active[0] = mask.any(axis=1)[:, None]
    active[1] = active[0] & (qv > 0.0)
    arrays = {
        "flat_index": flat,
        "obs_bt": obs,
        "bt": baseline_bt.copy(),
        "quality": quality,
        "mask": mask,
        "weights": weights,
        "source_eligible": source_eligible,
        "profile_valid": profile_valid,
        "reasons": np.array(["included"] * b, dtype="U24"),
        "theta_m": np.full((b, levels), 290.0, dtype=np.float64),
        "qv": qv,
        "grad_theta_numerator": np.full((b, levels), 0.01, dtype=np.float64),
        "grad_qv_numerator": np.full((b, levels), -0.02, dtype=np.float64),
        "active": active,
        "direction_theta": np.full((b, levels), -0.5, dtype=np.float64) * active[0],
        "direction_qv": np.zeros((b, levels), dtype=np.float64),
        "bt_jvp": np.full((b, channels), 0.1, dtype=np.float64),
        "finish": np.zeros((5, b, levels), dtype=np.float64),
    }
    if trial:
        arrays["quality"] = quality.copy()
        if start <= 1 < stop:
            arrays["quality"][1 - start, 2] = (
                0  # newly valid, still ignored by frozen mask
            )
        arrays["bt"] = obs + 0.5
        arrays["bt"][~mask] = np.nan
        arrays["delta_theta"] = np.full((b, levels), -0.1, dtype=np.float64)
        arrays["delta_qv"] = np.zeros((b, levels), dtype=np.float64)
        arrays["z"] = np.zeros((2, b, levels), dtype=np.float64)
    return arrays


def _save_chunk(root, arm, chunk_index, start, stop, *, trial=False, mutate=None):
    chunk_dir = root / arm / f"chunk_{chunk_index:05d}"
    attempt_dir = chunk_dir / "attempt_fixture"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    receipt_rel = f"{arm}/chunk_{chunk_index:05d}/receipt.json"
    receipt = {"chunk_index": chunk_index, "start": start, "stop": stop}
    (root / receipt_rel).write_text(json.dumps(receipt) + "\n")
    arrays = _artifact_arrays(start, stop, trial=trial)
    if mutate:
        mutate(arrays)
    artifact = attempt_dir / "result.npz"
    np.savez_compressed(artifact, **arrays)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return {
        "chunk_index": chunk_index,
        "start": start,
        "stop": stop,
        "receipt": receipt_rel,
        "artifact": str(artifact.relative_to(root)),
        "sha256": digest,
    }


def _write_run(
    root,
    *,
    bad_coverage=None,
    lose_support=False,
    no_acceptable=False,
    actual_schema=False,
):
    root.mkdir()
    ranges = [(0, 4), (4, 6)]
    trial_arm = "TRIAL_alpha_1p0" if actual_schema else "trial"
    baseline_chunks = []
    trial_chunks = []
    for chunk_index, (start, stop) in enumerate(ranges):
        baseline_chunks.append(_save_chunk(root, "baseline", chunk_index, start, stop))

        def mutate(arrays, start=start):
            if lose_support and start == 0:
                arrays["quality"][0, 0] = 2

        trial_chunks.append(
            _save_chunk(
                root,
                trial_arm,
                chunk_index,
                start,
                stop,
                trial=True,
                mutate=mutate if lose_support else None,
            )
        )
    # Reopen fixture arrays to compute the exact objective included in the manifests.
    base_bt = np.concatenate([_artifact_arrays(a, b)["bt"] for a, b in ranges])
    obs = np.concatenate([_artifact_arrays(a, b)["obs_bt"] for a, b in ranges])
    mask = np.concatenate([_artifact_arrays(a, b)["mask"] for a, b in ranges])
    weights = mask.astype(np.float64)
    if bad_coverage == "duplicate":
        # Make the second chunk claim one earlier flat index while preserving a valid hash.
        with np.load(
            root / baseline_chunks[1]["artifact"], allow_pickle=False
        ) as archive:
            arrays = {key: archive[key].copy() for key in archive.files}
        arrays["flat_index"][0] = 3
        artifact = root / baseline_chunks[1]["artifact"]
        np.savez_compressed(artifact, **arrays)
        baseline_chunks[1]["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if bad_coverage == "missing":
        baseline_chunks[1]["stop"] = 5
    j_base = _objective(base_bt, obs, mask, weights)
    trial_bt = obs + 0.5
    trial_bt[~mask] = np.nan
    j_trial = _objective(trial_bt, obs, mask, weights)
    z = float(weights.sum())
    if actual_schema:
        run_id = "fixture-run-id"

        def binding(stage, index, baseline_sha=None, controls_sha=None):
            payload = {
                "run_id": run_id,
                "stage": stage,
                "chunk": index,
                "baseline_sha": baseline_sha,
                "controls_sha": controls_sha,
            }
            return hashlib.sha256(
                json.dumps(
                    payload, sort_keys=True, allow_nan=False, separators=(",", ":")
                ).encode()
            ).hexdigest()

        baseline_sha = {
            entry["chunk_index"]: entry["sha256"] for entry in baseline_chunks
        }
        controls_sha = "abc123"
        for entry in baseline_chunks:
            entry.pop("receipt")
            entry["artifact"] = str((root / entry["artifact"]).resolve())
            entry["artifact_sha256"] = entry.pop("sha256")
            entry["binding"] = binding("baseline", entry["chunk_index"])
        for entry in trial_chunks:
            entry.pop("receipt")
            entry["artifact"] = str((root / entry["artifact"]).resolve())
            entry["artifact_sha256"] = entry.pop("sha256")
            entry["binding"] = binding(
                "TRIAL_alpha_1p0",
                entry["chunk_index"],
                baseline_sha[entry["chunk_index"]],
                controls_sha,
            )
        for entry, is_trial in [(row, False) for row in baseline_chunks] + [
            (row, True) for row in trial_chunks
        ]:
            with np.load(entry["artifact"], allow_pickle=False) as archive:
                arrays = {key: archive[key].copy() for key in archive.files}
            local_mask = arrays["mask"]
            entry["Z_partial"] = float(arrays["weights"].sum())
            entry["observation_numerator"] = (
                _objective(
                    arrays["bt"], arrays["obs_bt"], local_mask, arrays["weights"]
                )
                * entry["Z_partial"]
            )
            if is_trial:
                entry["support_preserved"] = bool(
                    not np.any(local_mask & (arrays["quality"] != 0))
                    and np.isfinite(arrays["bt"][local_mask]).all()
                )
        (root / "CASE_MANIFEST.json").write_text(json.dumps({"run_id": run_id}) + "\n")
    baseline = {
        "globalZ": z,
        "objective": {"J_observation": j_base, "J_background": 0.0, "J_total": j_base},
        "dot": {"lhs": 0.125, "rhs": 0.125, "relative_error": 0.0},
        "chunks": baseline_chunks,
    }
    trial = {
        "globalZ": z,
        "objective": None
        if lose_support
        else (
            {
                "observation_numerator": j_trial * z,
                "regularization_numerator": 0.0,
                "numerator": j_trial * z,
                "Z": z,
                "cost": j_trial,
            }
            if actual_schema
            else {
                "J_observation": j_trial,
                "J_background": 0.0,
                "J_total": j_trial,
            }
        ),
        "objective_valid": not lose_support,
        "controls_sha256": controls_sha if actual_schema else None,
        "chunks": trial_chunks,
    }
    (root / "BASELINE.json").write_text(json.dumps(baseline) + "\n")
    trial_name = "TRIAL_alpha_1p0.json" if actual_schema else "TRIAL_alpha_1.json"
    (root / trial_name).write_text(json.dumps(trial) + "\n")
    decision = {
        "status": (
            "COMPLETED_NO_ACCEPTABLE_UPDATE" if no_acceptable else "COMPLETED_ACCEPTED"
        ),
        "accepted_trial": None if no_acceptable else trial_name,
        "trials": [trial_name],
    }
    decision_file = "RUN_DECISION.json" if actual_schema else "FINAL.json"
    (root / decision_file).write_text(json.dumps(decision) + "\n")


def test_summarize_joins_tail_chunk_uses_fixed_mask_and_writes_new_outputs(tmp_path):
    run = tmp_path / "run"
    _write_run(run)
    output = tmp_path / "summary"
    summary = summarize(run, output, nx=3, ny=2, make_plots=False)
    assert summary["grid"]["profiles"] == 6
    assert summary["status"] == "COMPLETED_ACCEPTED"
    assert (
        summary["trials"]["TRIAL_alpha_1.json"]["quality_zero_outside_m0_ignored"] == 9
    )
    assert summary["source_coverage"]["profile_valid_count"] == 5
    assert summary["source_coverage"]["final_profile_valid_count"] == 6
    assert summary["per_channel"][0]["matched_count"] == 5
    assert summary["per_channel"][2]["matched_count"] == 4
    assert summary["per_channel"][0]["baseline"]["mae"] == 1.0
    assert summary["per_channel"][0]["final"]["mae"] == 0.5
    with np.load(output / "assembled.npz", allow_pickle=False) as archive:
        np.testing.assert_array_equal(archive["flat_index"], np.arange(6))
        np.testing.assert_array_equal(archive["mask"], archive["weights"] > 0.0)
        assert archive["delta_theta"].shape == (6, 2)
        assert archive["profile_valid"].sum() == 5
        assert archive["final_profile_valid"].sum() == 6
    assert (output / "summary.json").is_file()
    with pytest.raises(ValueError, match="must be new"):
        summarize(run, output, nx=3, ny=2, make_plots=False)


@pytest.mark.parametrize("bad_coverage", ["missing", "duplicate"])
def test_summarizer_rejects_missing_or_duplicate_grid_coverage(tmp_path, bad_coverage):
    run = tmp_path / "run"
    _write_run(run, bad_coverage=bad_coverage)
    output = tmp_path / "summary"
    with pytest.raises(ValueError, match="range|flat_index|receipt"):
        summarize(run, output, nx=3, ny=2, make_plots=False)
    assert not output.exists()


def test_summarizer_rejects_trial_that_loses_baseline_support(tmp_path):
    run = tmp_path / "run"
    _write_run(run, lose_support=True)
    with pytest.raises(ValueError, match="quality|mask|objective"):
        summarize(run, tmp_path / "summary", nx=3, ny=2, make_plots=False)


def test_invalid_unaccepted_trial_is_reported_but_final_maps_use_baseline(tmp_path):
    run = tmp_path / "run"
    _write_run(run, lose_support=True, no_acceptable=True)
    output = tmp_path / "summary"
    summary = summarize(run, output, nx=3, ny=2, make_plots=False)
    assert summary["status"] == "COMPLETED_NO_ACCEPTABLE_UPDATE"
    trial = summary["trials"]["TRIAL_alpha_1.json"]
    assert not trial["objective_valid"]
    assert not trial["support_preserved"]
    with np.load(output / "assembled.npz", allow_pickle=False) as archive:
        np.testing.assert_array_equal(archive["final_bt"], archive["baseline_bt"])
        assert np.all(archive["delta_theta"] == 0.0)


def test_summarizer_rejects_artifact_hash_mismatch_and_incomplete_run(tmp_path):
    run = tmp_path / "run"
    _write_run(run)
    baseline = json.loads((run / "BASELINE.json").read_text())
    baseline["chunks"][0]["sha256"] = "0" * 64
    (run / "BASELINE.json").write_text(json.dumps(baseline))
    with pytest.raises(ValueError, match="hash mismatch|changed while reading"):
        summarize(run, tmp_path / "summary", nx=3, ny=2, make_plots=False)

    run2 = tmp_path / "incomplete"
    _write_run(run2)
    (run2 / "FINAL.json").write_text(
        json.dumps({"status": "INCOMPLETE", "accepted_trial": None})
    )
    with pytest.raises(ValueError, match="incomplete"):
        summarize(run2, tmp_path / "summary2", nx=3, ny=2, make_plots=False)


def test_small_grid_plot_outputs_are_created_when_requested(tmp_path):
    pytest.importorskip("matplotlib")
    run = tmp_path / "run"
    _write_run(run)
    output = tmp_path / "summary"
    summarize(run, output, nx=3, ny=2, make_plots=True)
    assert len(list(output.glob("channel_*.png"))) == 7
    assert (output / "control_updates_and_reasons.png").is_file()


def test_summarizer_accepts_inline_runner_receipts_and_runroot_summary_output(tmp_path):
    run = tmp_path / "run"
    _write_run(run, actual_schema=True)
    summary = summarize(run, run / "summary", nx=3, ny=2, make_plots=False)
    assert summary["status"] == "COMPLETED_ACCEPTED"
    assert summary["accepted_trial"] == "TRIAL_alpha_1p0.json"
    assert summary["final_objective"]["J_total"] == pytest.approx(0.125)
