from __future__ import annotations

import numpy as np
import pytest

from harness import audit_effective_analysis as audit
from harness.native_analysis_control import prepare_effective_analysis


def test_scalar_f32_update_preserves_zero_components_and_filters_pair_noops():
    background_t = np.array([[1.0, 16777216.0, -0.0]], dtype=np.float64)
    background_q = np.array([[0.25, 0.5, 0.125]], dtype=np.float64)
    requested_t = np.array([[1.0e-8, 2.0, 0.0]], dtype=np.float64)
    requested_q = np.array([[0.0, 0.0, 0.01]], dtype=np.float64)
    result = audit._scalar_f32_update(background_t, background_q, requested_t, requested_q)
    assert result["requested_pair_mask"].tolist() == [[True, True, True]]
    assert result["changed_theta_mask"].tolist() == [[False, True, False]]
    assert result["changed_qv_mask"].tolist() == [[False, False, True]]
    assert result["changed_pair_mask"].tolist() == [[False, True, True]]
    assert result["effective_theta_f32"][0, 0].view(np.uint32) == np.float32(1.0).view(np.uint32)
    assert np.signbit(result["effective_theta_f32"][0, 2])


def test_independent_scalar_recipe_is_bitwise_equal_to_public_effective_helper():
    old_theta = np.array([[[1.0], [16777216.0], [-0.0]]], dtype=np.float32)
    old_qv = np.array([[[0.25], [0.5], [0.125]]], dtype=np.float32)
    request_theta = np.array([[[1.0e-8], [2.0], [0.0]]], dtype=np.float64)
    request_qv = np.array([[[0.0], [0.0], [0.01]]], dtype=np.float64)
    unchanged = np.array([[[False], [False], [False]]], dtype=np.bool_)
    scalar = audit._scalar_f32_update(
        old_theta.reshape(1, 3), old_qv.reshape(1, 3),
        request_theta.reshape(1, 3), request_qv.reshape(1, 3),
    )
    actual = prepare_effective_analysis(
        old_theta, old_qv, request_theta, request_qv, unchanged,
        bounds=(1, 1, 1, 3, 1, 1),
    )
    assert audit.same_bits(actual.effective_theta_m, scalar["effective_theta_f32"].reshape(1, 3, 1))
    assert audit.same_bits(actual.effective_qv, scalar["effective_qv_f32"].reshape(1, 3, 1))
    assert actual.counts["requested_points"] == 3
    assert actual.counts["noop_points"] == 1
    assert actual.counts["applied_points"] == 2


def test_effective_analysis_evidence_output_is_new_only(tmp_path):
    output_dir = tmp_path / "evidence"
    output_dir.mkdir()
    with pytest.raises(FileExistsError, match="must be new"):
        audit._output_files(output_dir, {"schema": audit.SCHEMA}, {"delta": np.zeros(1)})


def test_public_baseline_loader_labels_public_input_without_receipt_claim(monkeypatch, tmp_path):
    monkeypatch.setattr(audit, "COLUMNS", 3)
    monkeypatch.setattr(audit, "LEVELS", 2)
    path = tmp_path / "native_state_controls.npz"
    theta = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]], dtype=np.float64)
    qv = np.full((3, 2), 0.25, dtype=np.float64)
    np.savez(path, flat_index=np.arange(3, dtype=np.int32), theta_m=theta, qv=qv)
    got_theta, got_qv, pins, info = audit._load_full_parent_baseline(path)
    assert audit.same_bits(got_theta, theta)
    assert audit.same_bits(got_qv, qv)
    assert pins == []
    assert info["mode"] == "public_native_state_controls_npz"
    assert info["baseline_npz_sha256"] == audit.sha256_file(path)
    assert info["case_manifest_sha256"] is None


def test_npz_reader_decodes_the_exact_bytes_it_hashed(monkeypatch, tmp_path):
    from pathlib import Path
    path = tmp_path / "input.npz"
    np.savez(path, value=np.array([1.0]))
    original_read = Path.read_bytes
    expected = audit.sha256(original_read(path))

    def read_then_replace(self):
        checked_bytes = original_read(self)
        if self == path:
            np.savez(path, value=np.array([99.0]))
        return checked_bytes

    monkeypatch.setattr(Path, "read_bytes", read_then_replace)
    arrays, digest = audit._load_npz(path, expected)
    assert digest == expected
    assert arrays["value"].tolist() == [1.0]
