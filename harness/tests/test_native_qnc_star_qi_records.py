from __future__ import annotations

from pathlib import Path

import pytest

from harness.native_qnc_star_qi_records import read_qnc_star_trace, read_star_qi_writer_trace


DATA = Path(__file__).resolve().parents[1] / "evidence/native_qnc_star_qi_2026-10-28/data"


def test_shared_reader_rejects_missing_neighbor_face(tmp_path: Path):
    lines = (DATA / "alpha025/qnc_star.tsv").read_text().splitlines(keepends=True)
    marker = "VAL 1 RK3_POST 112 12 70 FX_EAST f32 "
    assert sum(row.startswith(marker) for row in lines) == 1
    changed = tmp_path / "missing_face.tsv"
    changed.write_text("".join(row for row in lines if not row.startswith(marker)))
    with pytest.raises(ValueError, match="inventory or order differs"):
        read_qnc_star_trace(changed)


def test_writer_reader_rejects_donor_float_as_integer(tmp_path: Path):
    source = (DATA / "alpha025/qnc_star_qi_moments.tsv").read_text()
    marker = "DONOR_QI\tf32\t00000002"
    assert source.count(marker) == 1
    changed = tmp_path / "wrong_type.tsv"
    changed.write_text(source.replace(marker, "DONOR_QI\ti32\t00000002", 1))
    with pytest.raises(ValueError, match="inventory differs"):
        read_star_qi_writer_trace(changed)
