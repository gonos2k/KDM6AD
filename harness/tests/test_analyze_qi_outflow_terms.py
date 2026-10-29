"""Regression checks for the pinned lower-owner QI flux explanation."""
from __future__ import annotations

from pathlib import Path

import pytest

from harness.analyze_qi_face_producer import read_trace as read_parent
from harness.analyze_qi_outflow_terms import PARENT, PACKET, analyze, analyze_case, read_trace


def test_published_outflow_replays_both_cases() -> None:
    result = analyze()
    assert result["record_count_per_case"] == 63
    assert result["cases"]["control"]["recorded_FLUX_OUT_word"] == "0707A41E"
    assert result["cases"]["alpha025"]["recorded_FLUX_OUT_word"] == "004C147C"


def test_wrong_six_face_aggregate_is_rejected(tmp_path: Path) -> None:
    source = (PACKET / "data/control/qi_outflow.tsv").read_text()
    changed = source.replace("PRE 2 32 168 FZ_BOTTOM f32 01B121C9",
                             "PRE 2 32 168 FZ_BOTTOM f32 00000000")
    assert changed != source
    path = tmp_path / "qi_outflow.tsv"
    path.write_text(changed)
    with pytest.raises(ValueError, match="FLUX_OUT differs"):
        analyze_case(read_trace(path), read_parent(PARENT / "data/control/qi_face.tsv"))


def test_changed_metric_is_rejected_before_replay(tmp_path: Path) -> None:
    source = (PACKET / "data/control/qi_outflow.tsv").read_text()
    changed = source.replace("INPUT 2 32 168 DT f32 41A00000",
                             "INPUT 2 32 168 DT f32 41A00001")
    assert changed != source
    path = tmp_path / "qi_outflow.tsv"
    path.write_text(changed)
    with pytest.raises(ValueError, match="DT differs"):
        analyze_case(read_trace(path), read_parent(PARENT / "data/control/qi_face.tsv"))


def test_wrong_vertical_producer_stencil_is_rejected(tmp_path: Path) -> None:
    source = (PACKET / "data/control/qi_outflow.tsv").read_text()
    changed = source.replace("VERT 2 32 168 FIELD_M2 f32 92092E22",
                             "VERT 2 32 168 FIELD_M2 f32 00000000")
    assert changed != source
    path = tmp_path / "qi_outflow.tsv"
    path.write_text(changed)
    with pytest.raises(ValueError, match="vertical high-order face"):
        analyze_case(read_trace(path), read_parent(PARENT / "data/control/qi_face.tsv"))
