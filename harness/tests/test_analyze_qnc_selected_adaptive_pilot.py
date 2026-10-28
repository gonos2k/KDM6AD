from __future__ import annotations

import json
from pathlib import Path

import pytest
from itertools import product

from harness.analyze_qnc_selected_adaptive_pilot import (
    _f32, _mode_sets, _rk_update, _word, _writer_word,
    analyze_pilot, load_v2_inputs,
)


ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "evidence/native_qnc_candidate_inputs_2026-10-28"
FAILURES = ROOT / "evidence/native_qnc_host_backoff_review_2026-10-28/residual_reason_rows.json"


@pytest.fixture(scope="module")
def pilot():
    inputs = load_v2_inputs(PACKET, FAILURES)
    return analyze_pilot(inputs[0], inputs[1], inputs[2], inputs[3], inputs[4], max_ulp=256)


def test_each_case_scans_sequentially_to_first_passing_scale(pilot):
    expected = {"control": {"0": 47, "1": 7},
                "alpha025": {"1": 30, "2": 19, "3": 4, "4": 1}}
    for case, histogram in expected.items():
        search = pilot["cases"][case]["scale_search"]
        assert search["step_histogram"] == histogram
        assert search["unresolved"] == []
        assert len(search["choice_rows"]) == 54
        for row in search["choice_rows"]:
            steps = row["ulp_steps"]
            assert row["checked_steps"] == list(range(steps + 1))
            assert all(not item["passes"] for item in row["checked_candidates"][:-1])
            assert row["checked_candidates"][-1]["passes"]
            assert row["checked_candidates"][-1]["scale_hex"] == row["candidate_scale_hex"]


def test_case_specific_simultaneous_face_mirror_and_receiver_delta(pilot):
    for case, changed in (("control", 39), ("alpha025", 306)):
        result = pilot["cases"][case]
        candidate = result["case_specific_candidate"]
        assert candidate["counts"]["cells"] == 382
        assert candidate["changed_face_word_count"] == changed
        assert candidate["counts"]["joint_positive_cells"] == 378
        assert candidate["counts"]["exact_nonpositive_cells"] == 4
        assert candidate["counts"]["some_compatible_f32_nonpositive_cells"] == 4
        assert result["baseline_to_candidate_failures"]["new_qc_positive_receiver_failures_ikj"] == []
        failures = candidate["failures_ikj"]
        assert failures["donors"] == []
        assert len(failures["receivers"]) == 4
        for coord in failures["all"]:
            name = f"i{coord[0]}_j{coord[2]}_k{coord[1]}"
            row = candidate["cells"][name]
            assert row["exact_residual"]["exact"] == "0"
            assert row["compatible_f32_qnc_words"] == ["00000000"]


def test_same_operator_table_is_coordinatewise_max_and_control_is_distinct(pilot):
    common = pilot["same_operator"]
    assert common is not None
    assert common["step_histogram"] == {"1": 30, "2": 19, "3": 4, "4": 1}
    assert common["max_ulp_steps"] == 4
    assert common["median_ulp_steps"] == 1.0
    table = {tuple(row["coord_ikj"]): row["n_ulp"] for row in common["n_i_table"]}
    control = {tuple(row["coord_ikj"]): row["ulp_steps"]
               for row in pilot["cases"]["control"]["scale_search"]["choice_rows"]}
    alpha = {tuple(row["coord_ikj"]): row["ulp_steps"]
             for row in pilot["cases"]["alpha025"]["scale_search"]["choice_rows"]}
    assert len(table) == 54
    assert table == {coord: max(control[coord], alpha[coord]) for coord in table}
    assert common["cases"]["control"]["scale_offsets_different_from_case_specific"] == 50
    assert common["cases"]["control"]["same_operator_candidate"]["changed_face_word_count"] == 297
    assert common["cases"]["alpha025"]["scale_offsets_different_from_case_specific"] == 0
    assert common["cases"]["alpha025"]["same_operator_candidate"]["changed_face_word_count"] == 306


def test_results_keep_exact_fractions_and_f32_words_json_safe(pilot):
    encoded = json.dumps(pilot, sort_keys=True, allow_nan=False)
    assert "candidate_scale_hex" in encoded
    assert "exact_residual" in encoded
    assert pilot["limits"]["candidate_host_executed"] is False


def test_rk_compatibility_enumerates_all_four_independent_sites(pilot):
    inputs = load_v2_inputs(PACKET, FAILURES)
    writer = inputs[1]
    coord = (57, 3, 159)
    _, compatible = _mode_sets(inputs[0]["values"][coord], writer, coord)
    advect = _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", "ADVECT_TEND"))
    observed = _writer_word(writer, coord, "RKSCALAR_AFTER", "QNC")
    all_patterns = tuple((*site_modes, numerator_mode)
                         for site_modes in product((False, True), repeat=3)
                         for numerator_mode in range(3))
    expected = tuple(pattern for pattern in all_patterns
                     if _word(_rk_update(writer, coord, advect, pattern)) == observed)
    assert compatible == expected
    assert len(all_patterns) == 24
    assert any(pattern[3] == 2 for pattern in compatible)  # FMA-right matches stored QNC.
    assert any(len(set(pattern[:3])) == 2 for pattern in compatible)
    modes = pilot["cases"]["control"]["scale_search"]["compatible_modes"]
    assert all(item["rk_per_site_pattern_count"] ==
               len(item["rk_patterns_tendency_old_new_numerator"])
               for item in modes.values())


def test_zero_search_cap_reports_unresolved_donors():
    inputs = load_v2_inputs(PACKET, FAILURES)
    result = analyze_pilot(*inputs[:4], inputs[4], max_ulp=0)
    assert result["cases"]["control"]["scale_search"]["unresolved"]
    assert len(result["cases"]["alpha025"]["scale_search"]["unresolved"]) == 54
    assert result["same_operator"] is None
