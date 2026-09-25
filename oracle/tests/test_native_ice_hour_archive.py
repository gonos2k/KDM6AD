"""Public one-hour rank log has a fixed complete negative schedule."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from streaming_ice_census import CensusPlan, replay_file  # noqa: E402


ARCHIVE = (Path(__file__).resolve().parents[2] / "harness" / "evidence"
           / "native_ice_census_1hour_rank0_2026-09-25.txt.xz")
ARCHIVE_SHA256 = "f7a4d6666f69b8f217eb5e6c4307f4441dabb46ad9d86e00a0985f432b33c4ad"
PLAN = CensusPlan(tuple(range(1, 181)), (2, 233), (2, 281), 0)


def test_full_hour_census_is_complete_but_has_no_second_ice_substep():
    result = replay_file(ARCHIVE, PLAN)
    audit = result["audit"]
    assert result["file_sha256"] == ARCHIVE_SHA256
    assert audit["selected_rows"] == audit["expected_columns"] == 11_692_800
    assert audit["consumed_rows"] == 11_692_800
    assert audit["mstep_histogram"] == {1: 11_692_800}
    assert audit["maximum_mstep"] == 1
    assert audit["multistep_selected"] == 0
    assert audit["first_multistep"] is None
    assert "not active ice" in result["scope"]
