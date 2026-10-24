"""Execution-boundary checks; no private data or physical executable required."""

import json

import numpy as np
import pytest

from harness.run_native_satellite_case import (
    CASE_SETTINGS,
    PROFILE_FIELDS,
    baseline_summary,
    chunk_binding,
    contract_k,
    load_arrays,
    publish_json,
    read_chunk,
    save_chunk,
    validate_request,
    execute_jobs,
)


def test_case_request_cannot_silently_change_quality_controls_or_time():
    request = {
        "schema": "kdm6.native_satellite_case_request.v1",
        "settings": CASE_SETTINGS.copy(),
        "fd_epsilons": [0.001, 0.0003],
    }
    validate_request(request)
    for key, value in (
        ("model_quality_required", 1),
        ("theta_m_scale_K", 0.8),
        ("KO_nominal_slot", "202507190002"),
        ("fixed_baseline_support", False),
    ):
        changed = dict(request, settings=dict(CASE_SETTINGS, **{key: value}))
        with pytest.raises(ValueError, match="case settings differ"):
            validate_request(changed)


def test_resume_requires_exact_case_stage_support_and_control_identity(tmp_path):
    folder = tmp_path / "baseline" / "chunk_00000"
    binding = chunk_binding("case_A", "baseline", 0)
    receipt = save_chunk(
        folder, {"flat_index": np.arange(3)}, {"chunk_index": 0}, binding
    )
    assert read_chunk(folder, binding) == receipt
    assert np.array_equal(load_arrays(receipt)["flat_index"], np.arange(3))
    for wrong in (
        chunk_binding("case_B", "baseline", 0),
        chunk_binding("case_A", "trial", 0),
        chunk_binding("case_A", "baseline", 0, baseline_sha="different"),
        chunk_binding("case_A", "baseline", 0, controls_sha="different"),
    ):
        with pytest.raises(ValueError, match="different run/stage"):
            read_chunk(folder, wrong)


def test_resume_refuses_changed_artifact_and_partial_attempt(tmp_path):
    folder = tmp_path / "chunk"
    (folder / "attempt_interrupted").mkdir(parents=True)
    assert read_chunk(folder, "binding") is None
    receipt = save_chunk(folder, {"value": np.arange(3)}, {}, "binding")
    with open(receipt["artifact"], "ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="artifact changed"):
        read_chunk(folder, "binding")
    with pytest.raises(ValueError, match="bytes changed"):
        load_arrays(receipt)


def test_json_publication_does_not_replace_an_existing_file_or_link(tmp_path):
    source = tmp_path / "source.json"
    source.write_text('{"preserved":true}')
    link = tmp_path / "alias.json"
    link.symlink_to(source)
    with pytest.raises(FileExistsError):
        publish_json(source, {"different": True})
    with pytest.raises(FileExistsError):
        publish_json(link, {"different": True})
    assert json.loads(source.read_text()) == {"preserved": True}


def _full_receipts():
    result = []
    start = 0
    for index in range(129):
        count = 512 if index < 128 else 452
        result.append(
            {
                "chunk_index": index,
                "start": start,
                "stop": start + count,
                "columns": count,
                "Z_partial": float(7 * count),
                "observation_numerator": float(14 * count),
                "dot": {"lhs": 0.1 * count, "rhs": 0.1 * count, "relative_error": 0.0},
                "calls": {"KDM_forward": 1, "RTTOV_K": 1},
            }
        )
        start += count
    return result


def test_global_cost_uses_tail_support_instead_of_an_average_of_chunk_averages():
    rows = _full_receipts()
    rows[-1]["observation_numerator"] = 0.0
    summary = baseline_summary(rows, full_domain=True)
    expected = (128 * 512 * 14) / (65988 * 7)
    assert summary["objective"]["J_total"] == expected
    assert summary["objective"]["J_total"] != pytest.approx(128 * 2 / 129, abs=1e-8)
    assert summary["globalZ"] == 461916
    assert summary["processed_columns"] == 65988
    assert summary["call_totals"] == {"KDM_forward": 129, "RTTOV_K": 129}


@pytest.mark.parametrize("mode", ["missing", "duplicate", "range"])
def test_full_baseline_refuses_missing_or_duplicate_tail_and_overlapping_ranges(mode):
    rows = _full_receipts()
    if mode == "missing":
        rows.pop()
    elif mode == "duplicate":
        rows[-1] = rows[-2].copy()
    else:
        rows[-1]["start"] -= 1
    with pytest.raises(ValueError, match="missing|duplicates|overlapping"):
        baseline_summary(rows, full_domain=True)


def test_profile_k_contraction_preserves_each_selected_native_row():
    rows = np.array([0, 3])
    kernels, tangents = {}, {}
    for j, name in enumerate(PROFILE_FIELDS):
        levels = 4 if name == "P_HALF" else 3
        kernels[name] = np.full((2, 7, levels), j + 1.0)
        tangents[name] = np.stack((np.full(levels, 1.0), np.full(levels, 2.0)))
    full, components = contract_k(kernels, tangents, rows, 5)
    expected = sum(
        (4 if name == "P_HALF" else 3) * (j + 1)
        for j, name in enumerate(PROFILE_FIELDS)
    )
    assert np.array_equal(full[0], np.full(7, expected))
    assert np.array_equal(full[3], np.full(7, 2 * expected))
    assert not full[[1, 2, 4]].any()
    assert set(components) == set(PROFILE_FIELDS)


def test_empty_profile_block_keeps_full_native_rows_without_an_rttov_k_call():
    full, components = contract_k({}, {}, np.array([], dtype=np.int64), 452)
    assert full.shape == (452, 7)
    assert not full.any()
    assert set(components) == set(PROFILE_FIELDS)
    assert all(value.shape == (0, 7) for value in components.values())


def test_parallel_resume_preserves_identity_and_returns_native_chunk_order(tmp_path):
    pytest.importorskip("torch", reason="worker initializer restricts Torch to one thread")
    jobs = []
    for index in (2, 0, 1):
        folder = tmp_path / "baseline" / f"chunk_{index:05d}"
        binding = chunk_binding("case", "baseline", index)
        save_chunk(
            folder,
            {"flat_index": np.array([index])},
            {
                "chunk_index": index,
                "columns": 1,
                "wall_seconds": 0.0,
                "observation_numerator": float(index),
                "dot": None,
                "support_preserved": True,
            },
            binding,
        )
        jobs.append(
            ({}, str(tmp_path), "case", index, "baseline", None, None, None, None)
        )
    result = execute_jobs(jobs, 2)
    assert [item["chunk_index"] for item in result] == [0, 1, 2]
