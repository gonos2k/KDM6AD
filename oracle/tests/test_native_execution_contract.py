"""Record-completeness contract for rank-owned native SELECT/CONSUME events."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from native_execution_contract import validate_census  # noqa: E402


I_BOUNDS = (2, 3)
J_BOUNDS = (4, 6)
TERRITORIES = {0: (2, 3, 4, 5), 1: (2, 3, 6, 6)}


def census(steps=(1, 2)):
    rows = []
    for step in steps:
        for lat in range(J_BOUNDS[0], J_BOUNDS[1] + 1):
            rank = 0 if lat < 6 else 1
            for i in range(I_BOUNDS[0], I_BOUNDS[1] + 1):
                mstep = 1 + ((step + lat + i) % 2)
                rows.append(("SELECT", step, rank, lat, i, 0, mstep))
                rows.extend(
                    ("CONSUME", step, rank, lat, i, n, mstep)
                    for n in range(1, mstep + 1)
                )
    return rows


def validate(rows, *, steps=(1, 2), territories=None):
    return validate_census(
        rows,
        steps=steps,
        i_bounds=I_BOUNDS,
        j_bounds=J_BOUNDS,
        rank_count=2,
        rank_territories=territories,
    )


def test_tiny_two_rank_census_has_complete_select_and_consume_coverage():
    result = validate(census(), territories=TERRITORIES)
    assert result["selected_columns"] == 12
    assert result["consumer_rows"] == 18
    assert result["min_selected_mstep"] == 1
    assert result["max_selected_mstep"] == 2
    assert "not independently recomputed" in result["mstep_source"]
    assert result["physics_across_ranks_certified"] is False


def test_record_order_does_not_define_expected_schedule():
    rows = census()
    random.Random(17).shuffle(rows)
    assert validate(rows, territories=TERRITORIES)["consumer_rows"] == 18


def test_missing_global_owner_is_rejected():
    rows = census()
    rows.remove(next(row for row in rows if row[0] == "SELECT"))
    with pytest.raises(ValueError, match="missing SELECT owner"):
        validate(rows)


def test_duplicate_halo_or_global_owner_is_rejected():
    rows = census()
    select = next(row for row in rows if row[0] == "SELECT")
    rows.append(("SELECT", select[1], 1, select[3], select[4], 0, select[6]))
    with pytest.raises(ValueError, match="duplicate owner|configured column"):
        validate(rows)


def test_swapped_rank_is_rejected_against_configured_territory():
    rows = census()
    index = next(i for i, row in enumerate(rows) if row[0] == "SELECT" and row[3] == 4)
    row = rows[index]
    rows[index] = (row[0], row[1], 1, *row[3:])
    with pytest.raises(ValueError, match="does not own configured column"):
        validate(rows, territories=TERRITORIES)


def test_missing_first_consumer_is_rejected():
    rows = census()
    selected = next(row for row in rows if row[0] == "SELECT" and row[6] == 2)
    first = ("CONSUME", selected[1], selected[2], selected[3], selected[4], 1, 2)
    rows.remove(first)
    with pytest.raises(ValueError, match="missing CONSUME ordinal"):
        validate(rows)


def test_consumer_after_selected_mstep_is_rejected():
    rows = census()
    selected = next(row for row in rows if row[0] == "SELECT" and row[6] == 1)
    rows.append(("CONSUME", selected[1], selected[2], selected[3], selected[4], 2, 1))
    with pytest.raises(ValueError, match="exceeds finished mstep"):
        validate(rows)


def test_consistent_mstep_counter_tamper_is_not_physics_rederived():
    """Coverage can verify declarations, not independently reproduce selection."""
    rows = census(steps=(2,))
    selected = next(row for row in rows if row[0] == "SELECT" and row[6] == 2)
    key = selected[1], selected[3], selected[4]
    changed = []
    for row in rows:
        if (row[1], row[3], row[4]) != key:
            changed.append(row)
        elif row[0] == "SELECT":
            changed.append((*row[:6], 1))
        elif row[5] == 1:
            changed.append((*row[:6], 1))
    result = validate(changed, steps=(2,))
    assert result["mstep_source"].endswith("not independently recomputed from velocity")
    assert result["selected_columns"] == 6


def test_halo_and_unexpected_step_are_rejected():
    rows = census()
    rows.append(("SELECT", 1, 0, 3, 2, 0, 1))
    with pytest.raises(ValueError, match="unexpected step or non-owned"):
        validate(rows)


def test_string_rows_and_comments_parse_without_changing_record_order():
    rows = census(steps=(2,))
    text = ["# native census", *(" ".join(map(str, row)) for row in rows)]
    result = validate(text, steps=(2,))
    assert result["selected_columns"] == 6


def test_malformed_enormous_mstep_rejects_without_expanding_ordinals():
    # One SELECT and one CONSUME cannot satisfy a billion-step declaration.
    rows = ["SELECT 1 0 2 2 0 1000000000", "CONSUME 1 0 2 2 1 1000000000"]
    with pytest.raises(ValueError, match="missing CONSUME ordinal"):
        validate_census(
            rows, steps=(1,), i_bounds=(2, 2), j_bounds=(2, 2), rank_count=1
        )
