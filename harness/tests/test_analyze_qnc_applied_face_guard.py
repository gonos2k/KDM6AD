"""Regression for the positive-f32/negative-face-residual counterexample."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from pathlib import Path

import pytest

from harness.analyze_qnc_applied_face_guard import first_passing_scale
from harness.native_qnc_advect_qi_trace_records import read_qnc_producer_trace
from harness.native_qnc_star_qi_records import read_qnc_star_trace, read_star_qi_writer_trace


EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"


def _inputs(case: str):
    star = EVIDENCE / "native_qnc_star_qi_2026-10-28/data" / case
    prior = EVIDENCE / "native_qnc_advect_qi_2026-10-28/data" / case
    return (read_qnc_star_trace(star / "qnc_star.tsv"),
            read_star_qi_writer_trace(star / "qnc_star_qi_moments.tsv"),
            read_qnc_producer_trace(prior / "qnc_producer.tsv"))


def test_positive_f32_alone_does_not_pass_selected_star_guard():
    result = first_passing_scale(*_inputs("alpha025"), max_decrements=2)
    assert result["first_passing_decrements"] == 2
    one, two = result["checked"][1:]
    center_one = one["cells"]["i113_j70_k12"]
    center_two = two["cells"]["i113_j70_k12"]
    assert center_one["compatible_f32_words"] == ["3ADDE41C"]
    assert Fraction(center_one["exact_residual"]) < 0
    assert not one["passes_selected_star_predicate"]
    assert center_two["compatible_f32_words"] == ["3ADDE41C"]
    assert Fraction(center_two["exact_residual"]) > 0
    assert two["passes_selected_star_predicate"]
    assert Fraction(two["exact_weighted_internal_face_change"]) == 0
    assert Fraction(two["rounded_weighted_state_change"]) != 0


def test_control_needs_no_selected_star_backoff():
    result = first_passing_scale(*_inputs("control"), max_decrements=2)
    assert result["first_passing_decrements"] == 0
    assert len(result["checked"]) == 1


def test_original_shared_face_mismatch_is_rejected():
    shared, writer, producer = _inputs("alpha025")
    changed = deepcopy(shared)
    key = (shared["owner_call_id"], "RK3_POST", 112, 12, 70, "FX_EAST")
    changed["records"][key] ^= 1
    with pytest.raises(ValueError, match="original shared face/scale differs"):
        first_passing_scale(changed, writer, producer, max_decrements=2)
