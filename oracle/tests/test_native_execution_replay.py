"""Bounded replay tests for the published seven-run G4 evidence bundle."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from native_execution_contract import validate_census  # noqa: E402
from replay_native_execution import (  # noqa: E402
    EVIDENCE,
    _archive_rows,
    replay,
    validate_metadata,
)


def _evidence():
    return json.loads(EVIDENCE.read_text())


def test_replays_all_census_files_and_boundaries_once():
    result = replay()
    assert result["schema"] == "native-execution-replay-v1"
    assert result["metadata"]["run_cases"] == 7
    assert result["metadata"]["census_capture_cases"] == 4
    assert set(result["census"]) == {"serial", "x-capture", "y-capture", "restart"}
    assert result["census"]["serial"]["selected_columns"] == 129920
    assert result["census"]["restart"]["steps"] == [2]
    assert result["checkpoint"]["time"] == "2025-07-19_00:00:20"
    assert result["checkpoint"]["bytes_reopened"] is False
    assert (
        result["metadata"]["heldout_profiles"]["mpi_layout_frames_bitwise_equal"]
        is True
    )
    assert (
        result["metadata"]["heldout_profiles"][
            "restart_continuation_profiles_different_at_40s"
        ]
        == 5
    )
    assert result["same_physics_across_decompositions"] is False
    assert result["restart_equals_continuous_trajectory"] is False
    assert result["mstep_independently_recomputed"] is False
    assert result["netcdf_reopened"] is False


def test_missing_required_run_case_fails_before_any_archive_read():
    data = _evidence()
    del data["runs"]["restart-control"]
    with pytest.raises(ValueError, match="missing or unexpected run case"):
        validate_metadata(data)


def test_missing_rank_file_is_not_allowed_to_shrink_coverage():
    data = _evidence()
    data["runs"]["x-capture"]["raw_census"].pop()
    with pytest.raises(ValueError, match="missing or unexpected census rank file"):
        validate_metadata(data)


def test_false_physical_or_operational_approval_is_rejected():
    data = _evidence()
    data["acceptance"]["physical_number_basis_resolved"] = True
    with pytest.raises(ValueError, match="unsupported acceptance flag"):
        validate_metadata(data)


def test_deleting_boundary_from_both_input_identity_records_is_rejected():
    data = _evidence()
    for case in ("x-control", "x-capture"):
        entry = data["runs"][case]
        identity = entry["input_identity"]
        identity["records"] = [
            r for r in identity["records"] if r["kind"] != "boundary"
        ]
        # Even a self-consistent recomputed digest cannot redefine required inputs.
        from run_ss_case import canonical_input_sha256

        identity["canonical_sha256"] = canonical_input_sha256(identity)
        entry["run_identity"]["controls"]["input_canonical_sha256"] = identity[
            "canonical_sha256"
        ]
    with pytest.raises(ValueError, match="active input record set is incomplete"):
        validate_metadata(data)


def test_global_executable_must_match_all_seven_run_records():
    data = _evidence()
    entry = data["runs"]["serial"]
    lines = entry["executable_sha256"].splitlines()
    false_hash = "f" * 64
    entry["executable_sha256"] = "\n".join(
        [false_hash, f"before {false_hash}", f"after  {false_hash}", *lines[3:]]
    )
    with pytest.raises(ValueError, match="common native binary"):
        validate_metadata(data)


def test_checkpoint_hash_must_match_restart_input_before_and_after():
    data = _evidence()
    data["checkpoint"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checkpoint hash before/after mismatch"):
        validate_metadata(data)


def test_tiny_replay_rejects_schedule_coordinate_and_rank_mutations():
    expected_territories = {0: (2, 2, 4, 4), 1: (3, 3, 4, 4)}
    rows = [
        ("SELECT", 2, 0, 4, 2, 0, 2),
        ("CONSUME", 2, 0, 4, 2, 1, 2),
        ("CONSUME", 2, 0, 4, 2, 2, 2),
        ("SELECT", 2, 1, 4, 3, 0, 1),
        ("CONSUME", 2, 1, 4, 3, 1, 1),
    ]

    def validate(events):
        return validate_census(
            events,
            steps=(2,),
            i_bounds=(2, 3),
            j_bounds=(4, 4),
            rank_count=2,
            rank_territories=expected_territories,
        )

    assert validate(rows)["selected_columns"] == 2
    with pytest.raises(ValueError, match="unexpected step or non-owned"):
        validate([tuple([row[0], 1, *row[2:]]) for row in rows])
    outside = rows[:-1] + [("CONSUME", 2, 1, 4, 4, 1, 1)]
    with pytest.raises(ValueError, match="unexpected step or non-owned"):
        validate(outside)
    swapped = rows[:-1] + [("CONSUME", 2, 0, 4, 3, 1, 1)]
    with pytest.raises(ValueError, match="rank does not own configured column"):
        validate(swapped)


def test_missing_census_file_is_rejected_without_reconstructing_case_schedule(tmp_path):
    metadata = {"gzip_sha256": "0" * 64, "raw_sha256": "0" * 64, "records": 1}
    with pytest.raises(ValueError, match="census file missing"):
        list(_archive_rows(path=tmp_path / "absent.gz", rank=0, metadata=metadata))


def test_corrupted_gzip_is_rejected_even_if_its_compressed_hash_is_recorded(tmp_path):
    path = tmp_path / "corrupt.gz"
    payload = b"not a gzip stream\n"
    path.write_bytes(payload)
    metadata = {
        "gzip_sha256": hashlib.sha256(payload).hexdigest(),
        "raw_sha256": hashlib.sha256(b"").hexdigest(),
        "records": 0,
    }
    with pytest.raises(ValueError, match="corrupt gzip census archive"):
        list(_archive_rows(path=path, rank=0, metadata=metadata))


def test_changing_both_decomposition_input_seals_cannot_hide_a_new_initial_file():
    from run_ss_case import canonical_input_sha256

    data = _evidence()
    for case in ("x-control", "x-capture"):
        run = data["runs"][case]
        identity = run["input_identity"]
        record = next(r for r in identity["records"] if r["kind"] == "init")
        for key in ("sha256", "sha256_before", "sha256_after"):
            record[key] = "a" * 64
        identity["canonical_sha256"] = canonical_input_sha256(identity)
        run["run_identity"]["controls"]["input_canonical_sha256"] = identity[
            "canonical_sha256"
        ]
    with pytest.raises(ValueError, match="decomposition input differs"):
        validate_metadata(data)


def test_rehashed_physics_change_cannot_hide_inside_matching_pair():
    data = _evidence()
    for case in ("x-control", "x-capture"):
        run = data["runs"][case]
        text = run["effective_namelist_text"]
        assert "mp_physics                          = 237," in text
        text = text.replace(
            "mp_physics                          = 237,",
            "mp_physics                          = 37,",
        )
        run["effective_namelist_text"] = text
        run["effective_namelist_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        without = "\n".join(
            line
            for line in text.splitlines()
            if "nproc_x" not in line and "nproc_y" not in line
        )
        run["run_identity"]["controls"]["namelist_without_grid_sha256"] = (
            hashlib.sha256(without.encode()).hexdigest()
        )
    with pytest.raises(ValueError, match="unplanned namelist difference"):
        validate_metadata(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("selection_recomputed_equal", False),
        ("final_selector_sha256", "0" * 64),
        ("original_selector_sha256", "0" * 64),
    ],
)
def test_selector_validation_receipt_is_not_silently_ignored(field, value):
    data = _evidence()
    data["selection_validation"][field] = value
    with pytest.raises(ValueError, match="selector|selection"):
        validate_metadata(data)


@pytest.mark.parametrize("change", ["duplicate_field", "alarm", "boundary_window"])
def test_comparison_counts_and_restart_clock_receipts_are_checked(change):
    data = _evidence()
    if change == "duplicate_field":
        rows = data["comparisons"]["serial_to_x"][1]["different_fields"]
        rows[1] = dict(rows[0])
    elif change == "alarm":
        data["checkpoint"]["attributes"]["WRF_ALARM_SECS_TIL_NEXT_RING_01"] += 1
    else:
        data["checkpoint"]["boundary_times"] = [
            "2025-07-20_00:00:00",
            "2025-07-20_03:00:00",
        ]
    with pytest.raises(ValueError, match="unique|alarm metadata|bracket"):
        validate_metadata(data)
