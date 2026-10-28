from __future__ import annotations

from pathlib import Path

import pytest

from harness.analyze_qnc_advect_qi_trace import analyze
from harness.native_qnc_advect_qi_trace_records import (
    read_qi_writer_trace,
    read_qnc_producer_trace,
)
from harness.native_qnc_representative_trace_records import read_representative_trace


ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "evidence/native_qnc_advect_qi_2026-10-28/data"
PARENT = ROOT / "evidence/native_qnc_representative_boundaries_2026-10-28/data"


def _inputs():
    cases = ("control", "alpha025")
    producer = {case: read_qnc_producer_trace(PACKET / case / "qnc_producer.tsv") for case in cases}
    writer = {case: read_qi_writer_trace(PACKET / case / "qi_writer_moments.tsv") for case in cases}
    previous = {case: read_representative_trace(PARENT / case / "representative_moments.tsv")
                for case in cases}
    return producer, writer, previous


def test_rk2_axis_word_must_join_source_order():
    producer, writer, previous = _inputs()
    key = (2, "RK2_AFTER_X", 113, 12, 70, "TENDENCY")
    producer["alpha025"].values[key] ^= 1
    with pytest.raises(ValueError, match="FMA candidate differs"):
        analyze(producer, writer, previous)


def test_rk2_start_requires_recorded_positive_zero():
    producer, writer, previous = _inputs()
    key = (2, "RK2_START", 113, 12, 70, "TENDENCY")
    producer["alpha025"].values[key] = 0x80000000
    with pytest.raises(ValueError, match="start from zero tendency"):
        analyze(producer, writer, previous)


def test_old_representative_stage_word_must_survive_new_recorder():
    producer, writer, previous = _inputs()
    key = (3, "RKSCALAR_BEFORE", 113, 12, 70, "QNC")
    writer["control"].values[key] ^= 1
    with pytest.raises(ValueError, match="prior representative stage words changed"):
        analyze(producer, writer, previous)
