"""Published native-case arithmetic is replayable without private executables."""

import json
import hashlib
from pathlib import Path

import pytest
import numpy as np

from harness.replay_native_satellite_case import (
    _candidate_finish_numpy,
    _restricted_bundle,
    _restricted_objective,
    replay,
    main,
)


EVIDENCE = (
    Path(__file__).resolve().parents[1]
    / "evidence"
    / "native_satellite_case_2026-10-25"
    / "data"
)


def test_actual_published_case_cost_controls_and_lost_support():
    result = replay(EVIDENCE)
    assert result["status"] == "REPLAY_PASSED"
    assert result["native_columns"] == 65988
    assert result["blocks"] == 129
    assert result["globalZ"] == 381528
    assert result["baseline_J"] == 11.153458878209252
    assert result["published_dot_relative_error"] <= 1e-10
    assert [
        (v["alpha"], v["lost_profiles"], v["lost_channel_cells"])
        for v in result["trials"]
    ] == [(1.0, 29, 203), (0.5, 18, 126), (0.25, 13, 91)]
    assert result["new_KDM_RTTOV_host_calls"] == 0


def test_manifest_cannot_redirect_arithmetic_input_outside_bundle(tmp_path):
    outside = tmp_path / "outside.npz"
    outside.write_bytes(b"this must not be opened as an NPZ")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    names = [
        "../outside.npz",
        "scope.json",
        "summary.json",
        "channel_bt.npz",
        "observation_support.npz",
        "native_state_controls.npz",
        "baseline_native_gradient_cost.npz",
        "baseline_native_tangent.npz",
        "native_control_delta.npz",
        "trials/trials.json",
    ]
    (bundle / "publication_manifest.json").write_text(
        json.dumps(
            {
                "schema": "kdm6.native_satellite_publication_pack.v1",
                "artifacts": {name: {} for name in names},
            }
        )
    )
    with pytest.raises(ValueError, match="escapes the evidence directory"):
        replay(bundle)


def test_restricted_manifest_cannot_redirect_artifacts_outside_bundle(tmp_path):
    outside = tmp_path / "outside.npz"
    outside.write_bytes(b"do not read")
    bundle = tmp_path / "restricted"
    bundle.mkdir()
    (bundle / "publication_manifest.json").write_text(
        json.dumps(
            {
                "schema": "kdm6.native_satellite_restricted_publication.v1",
                "artifacts": {
                    "../outside.npz": {
                        "bytes": outside.stat().st_size,
                        "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="not relative"):
        _restricted_bundle(bundle)


def test_restricted_manifest_requires_all_hashed_arithmetic_inputs(tmp_path):
    bundle = tmp_path / "restricted"
    bundle.mkdir()
    summary = bundle / "summary.json"
    summary.write_text("{}")
    raw = summary.read_bytes()
    (bundle / "publication_manifest.json").write_text(
        json.dumps(
            {
                "schema": "kdm6.native_satellite_restricted_publication.v1",
                "artifacts": {
                    "summary.json": {
                        "bytes": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="lacks a required hashed input"):
        _restricted_bundle(bundle)


def test_restricted_finish_numpy_replay_preserves_ordered_clipping_and_receivers():
    theta0 = np.array([[300.0, 300.2]], dtype=np.float64)
    theta1 = np.array([[300.1, 300.0]], dtype=np.float64)
    qv0 = np.array([[0.002, 0.001]], dtype=np.float64)
    qv1 = np.array([[0.003, 0.0005]], dtype=np.float64)
    qc0 = np.array([[1.0e-4, 2.0e-4]], dtype=np.float64)
    qc1 = np.array([[2.0e-4, 1.0e-4]], dtype=np.float64)
    cfg = {"dt_seconds": 20.0, "alpha": 0.005, "t0_K": 300.0, "mp_tend_lim_K_s": 0.0025}
    result = _candidate_finish_numpy(theta0, theta1, qv0, qv1, qc0, qc1, cfg)
    raw = theta1 - theta0
    bound = cfg["mp_tend_lim_K_s"] * cfg["dt_seconds"]
    m = np.where(
        raw >= bound,
        np.full_like(raw, bound),
        np.where(raw <= -bound, np.full_like(raw, -bound), raw),
    )
    dq = qv1 - qv0
    a = 1.0 + cfg["alpha"] * qv0
    b = 1.0 + cfg["alpha"] * qv1
    n = m * b + cfg["alpha"] * dq * theta1
    full = theta0 * a + n
    assert result["H_RATE"].tobytes() == (n / cfg["dt_seconds"]).tobytes()
    assert result["QV_RATE"].tobytes() == (dq / cfg["dt_seconds"]).tobytes()
    assert result["QC_RATE"].tobytes() == ((qc1 - qc0) / cfg["dt_seconds"]).tobytes()
    assert result["T_NEW_AFTER"].tobytes() == (full - cfg["t0_K"]).tobytes()


def test_restricted_objective_uses_one_normalizer_and_prior_in_same_cost():
    bt = np.array([[2.0], [0.5]], dtype=np.float64)
    obs = np.zeros_like(bt)
    mask = np.ones((2, 1), dtype=np.bool_)
    weights = np.ones((2, 1), dtype=np.float64)
    z = np.array([[[0.5], [0.0]], [[0.0], [0.25]]], dtype=np.float64)
    active = np.ones_like(z, dtype=np.bool_)
    result = _restricted_objective(bt, obs, mask, weights, z, active)
    obs_num = (2.0 - 0.5) + 0.5 * 0.5**2
    prior_num = 0.5 * (0.5**2 + 0.25**2)
    assert result["observation_numerator"] == obs_num
    assert result["regularization_numerator"] == prior_num
    assert result["Z"] == 2.0
    assert result["cost"] == (obs_num + prior_num) / 2.0


def test_cli_keeps_old_replay_and_routes_optional_restricted_replay(
    monkeypatch, tmp_path
):
    import harness.replay_native_satellite_case as module

    calls = []
    monkeypatch.setattr(
        module,
        "replay",
        lambda parent: calls.append(("parent", parent)) or {"status": "PARENT"},
    )
    monkeypatch.setattr(
        module,
        "replay_restricted_case",
        lambda parent, restricted: calls.append(("restricted", parent, restricted))
        or {"status": "RESTRICTED"},
    )
    main([str(tmp_path / "parent")])
    assert calls.pop(0)[0] == "parent"
    main([str(tmp_path / "parent"), "--restricted-evidence", str(tmp_path / "new")])
    assert calls.pop(0) == ("restricted", tmp_path / "parent", tmp_path / "new")
