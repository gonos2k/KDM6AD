"""Focused guards for the source-pinned S5 RK input probe."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import s5_rk_producer_probe as probe  # noqa: E402


def test_guarded_rk_probe_strips_to_original_source():
    source = "\n".join(anchor for anchor, _ in probe.ANCHORS.values())
    overlay = probe.render(source)
    assert overlay.count(f"#ifdef {probe.GUARD}") == len(probe.STAGES) == 8
    assert probe.strip(overlay) == source


def test_input_schedule_rejects_missing_file_and_point(tmp_path):
    rows = probe.expected_rows("1x1")
    files = []
    for stage in probe.STAGES:
        for rank, its, ite, jts, jte in probe.TILES["1x1"]:
            tile = (stage, rank, its, ite, jts, jte)
            path = tmp_path / f"w.{stage}.r{rank}.i{its}-{ite}.j{jts}-{jte}.txt"
            records = sorted(row for row in rows if row[:6] == tile)
            path.write_text(
                f"STAGE {stage} {rank} {its} {ite} {jts} {jte}\n"
                + "".join(f"POINT {name} {i} {j} {k} 0\n"
                          for _, _, _, _, _, _, name, i, j, k in records))
            files.append(path)
    assert len(probe.parse_capture("1x1", files)) == len(rows) == 80
    with pytest.raises(ValueError, match="declared schedule"):
        probe.parse_capture("1x1", files[:-1])
    first = files[0]
    lines = first.read_text().splitlines()
    first.write_text("\n".join(lines[:-1]) + "\n")
    with pytest.raises(ValueError, match="declared schedule"):
        probe.parse_capture("1x1", files)
