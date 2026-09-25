"""Large native census gets an independently fixed bounded-memory schedule."""

import gzip
import hashlib
import lzma
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from streaming_ice_census import (  # noqa: E402
    CensusPlan, replay_file, validate_streaming_census,
)


PLAN = CensusPlan((1, 2), (2, 3), (2, 2), 0)
ROWS = (
    "SELECT 1 0 2 2 0 1",
    "CONSUME 1 0 2 2 1 1",
    "SELECT 1 0 2 3 0 2",
    "CONSUME 1 0 2 3 1 2",
    "CONSUME 1 0 2 3 2 2",
    "SELECT 2 0 2 2 0 1",
    "CONSUME 2 0 2 2 1 1",
    "SELECT 2 0 2 3 0 1",
    "CONSUME 2 0 2 3 1 1",
)


def test_complete_schedule_finds_first_natural_multistep_without_activity_claim():
    result = validate_streaming_census(iter(ROWS), PLAN)
    assert result.selected_rows == result.expected_columns == 4
    assert result.consumed_rows == 5
    assert result.multistep_selected == 1
    assert result.maximum_mstep == 2
    assert result.mstep_histogram == {1: 3, 2: 1}
    assert result.first_multistep == {"step": 1, "rank": 0, "j": 2, "i": 3,
                                      "mstep": 2}


def test_missing_selection_or_consumer_cannot_shrink_expected_schedule():
    with pytest.raises(ValueError, match="incomplete SELECT"):
        validate_streaming_census(iter(ROWS[:-2]), PLAN)
    with pytest.raises(ValueError, match="missing CONSUME"):
        validate_streaming_census(iter(ROWS[:4] + ROWS[5:]), PLAN)


def test_duplicate_selection_consumer_and_mismatch_reject():
    with pytest.raises(ValueError, match="duplicate or malformed SELECT"):
        validate_streaming_census(iter(ROWS + (ROWS[0],)), PLAN)
    with pytest.raises(ValueError, match="duplicate CONSUME"):
        validate_streaming_census(iter(ROWS + (ROWS[4],)), PLAN)
    with pytest.raises(ValueError, match="matching SELECT"):
        validate_streaming_census(iter(ROWS[:3] + ("CONSUME 1 0 2 3 1 1",) + ROWS[4:]), PLAN)


def test_wrong_rank_coordinate_step_and_unbounded_mstep_reject():
    for row in ("SELECT 1 1 2 2 0 1", "SELECT 3 0 2 2 0 1",
                "SELECT 1 0 2 4 0 1"):
        with pytest.raises(ValueError, match="outside independently declared"):
            validate_streaming_census(iter(ROWS + (row,)), PLAN)
    with pytest.raises(ValueError, match="supported 1..63"):
        validate_streaming_census(iter(("SELECT 1 0 2 2 0 64",)), PLAN)
    with pytest.raises(ValueError, match="bounded-memory"):
        validate_streaming_census(iter(()), CensusPlan(tuple(range(1, 1000)),
                                                 (2, 233), (2, 281), 0))


@pytest.mark.parametrize("suffix", ("gz", "xz"))
def test_compressed_replay_binds_lossless_file_hash_and_scope(tmp_path, suffix):
    path = tmp_path / f"rank0.log.{suffix}"
    if suffix == "gz":
        with gzip.GzipFile(filename=str(path), mode="wb", mtime=0) as stream:
            stream.write(("\n".join(ROWS) + "\n").encode())
    else:
        with lzma.open(path, "wb") as stream:
            stream.write(("\n".join(ROWS) + "\n").encode())
    report = replay_file(path, PLAN)
    assert report["audit"]["selected_rows"] == 4
    assert report["audit"]["multistep_selected"] == 1
    assert report["file_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert "not active ice" in report["scope"]
