from __future__ import annotations

from pathlib import Path

import pytest

from harness.native_qnc_advect_qi_trace_records import (
    read_qi_writer_trace,
    read_qnc_producer_trace,
)


PACKET = Path(__file__).resolve().parents[1] / "evidence/native_qnc_advect_qi_2026-10-28/data"


def test_producer_reader_rejects_missing_first_differing_axis_record(tmp_path: Path):
    lines = (PACKET / "control/qnc_producer.tsv").read_text().splitlines(keepends=True)
    marker = "VAL 20 2 RK2_AFTER_X 113 12 70 TENDENCY "
    assert sum(line.startswith(marker) for line in lines) == 1
    changed = tmp_path / "missing_axis.tsv"
    changed.write_text("".join(line for line in lines if not line.startswith(marker)))
    with pytest.raises(ValueError, match="inventory differs"):
        read_qnc_producer_trace(changed)


def test_writer_reader_rejects_boolean_flag_as_float(tmp_path: Path):
    source = (PACKET / "alpha025/qi_writer_moments.tsv").read_text()
    marker = "SPECIFIED\tbool\t01"
    assert source.count(marker) == 5
    changed = tmp_path / "wrong_flag_type.tsv"
    changed.write_text(source.replace(marker, "SPECIFIED\tf32\t3F800000", 1))
    with pytest.raises(ValueError, match="inventory differs"):
        read_qi_writer_trace(changed)
