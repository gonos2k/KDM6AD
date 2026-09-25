"""Validate a native column-selection/consumer census against caller geometry.

The validator proves record coverage and declared execution pairing only. It
does not recompute the native velocity producer or certify equal physics across
MPI decompositions.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CensusRow:
    tag: str
    step: int
    rank: int
    lat: int
    i: int
    n: int
    mstep: int


def parse_census_row(row: str | Sequence[object]) -> CensusRow | None:
    """Parse ``tag step rank lat i n mstep``; ignore blank/comment lines."""
    if isinstance(row, str):
        text = row.strip()
        if not text or text.startswith("#"):
            return None
        fields: Sequence[object] = text.split()
    else:
        fields = row
    if len(fields) != 7:
        raise ValueError("census row must contain tag plus six integers")
    tag = str(fields[0]).upper()
    if tag not in {"SELECT", "CONSUME"}:
        raise ValueError(f"unknown census tag: {tag}")
    try:
        values = tuple(_integer(x) for x in fields[1:])
    except (TypeError, ValueError) as exc:
        raise ValueError("census coordinates and counts must be integers") from exc
    return CensusRow(tag, *values)


def _integer(value: object) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str):
        return int(value.strip())
    raise ValueError("integer field required")


def expected_columns(
    *, steps: Sequence[int], i_bounds: tuple[int, int], j_bounds: tuple[int, int]
) -> frozenset[tuple[int, int, int]]:
    """Independent schedule as ``(step, lat/j, i)`` keys."""
    if not steps or any(type(step) is not int or step < 1 for step in steps):
        raise ValueError("steps must be a nonempty sequence of positive integers")
    if len(set(steps)) != len(steps):
        raise ValueError("steps must be unique")
    i0, i1 = _bounds(i_bounds, "i_bounds")
    j0, j1 = _bounds(j_bounds, "j_bounds")
    return frozenset(
        (step, lat, i)
        for step in steps
        for lat in range(j0, j1 + 1)
        for i in range(i0, i1 + 1)
    )


def _bounds(bounds: Sequence[int], name: str) -> tuple[int, int]:
    if len(bounds) != 2 or any(type(value) is not int for value in bounds):
        raise ValueError(f"{name} must be an inclusive pair of integers")
    lower, upper = bounds
    if lower > upper:
        raise ValueError(f"{name} lower bound exceeds upper bound")
    return lower, upper


def _territory_owners(
    columns: Iterable[tuple[int, int, int]],
    rank_territories: Mapping[int, Sequence[int]],
    rank_count: int,
) -> dict[tuple[int, int, int], int]:
    territories: dict[int, tuple[int, int, int, int]] = {}
    for rank, bounds in rank_territories.items():
        if type(rank) is not int or not 0 <= rank < rank_count:
            raise ValueError("territory rank outside configured rank range")
        if len(bounds) != 4 or any(type(value) is not int for value in bounds):
            raise ValueError("territory bounds must be inclusive (i0,i1,j0,j1)")
        i0, i1, j0, j1 = bounds
        if i0 > i1 or j0 > j1:
            raise ValueError("territory lower bound exceeds upper bound")
        territories[rank] = (i0, i1, j0, j1)

    owner_by_column: dict[tuple[int, int], int] = {}
    for _step, lat, i in columns:
        owner_hits = [
            rank
            for rank, (i0, i1, j0, j1) in territories.items()
            if i0 <= i <= i1 and j0 <= lat <= j1
        ]
        if len(owner_hits) != 1:
            raise ValueError(
                f"configured territories cover column {(lat, i)} {len(owner_hits)} times"
            )
        owner_by_column[lat, i] = owner_hits[0]
    return {key: owner_by_column[key[1], key[2]] for key in columns}


def validate_census(
    rows: Iterable[str | Sequence[object]],
    *,
    steps: Sequence[int],
    i_bounds: tuple[int, int] = (2, 233),
    j_bounds: tuple[int, int] = (2, 281),
    rank_count: int,
    rank_territories: Mapping[int, Sequence[int]] | None = None,
) -> dict[str, object]:
    """Require one SELECT and every 1..mstep CONSUME for each expected column.

    ``steps``, global bounds, rank count, and optional inclusive territories
    come from the caller's domain/decomposition configuration. None is inferred
    from received rows. ``rank_territories`` maps rank to ``(i0,i1,j0,j1)``.
    """
    if type(rank_count) is not int or rank_count < 1:
        raise ValueError("rank_count must be a positive integer")
    expected = expected_columns(steps=steps, i_bounds=i_bounds, j_bounds=j_bounds)
    territories = (
        _territory_owners(expected, rank_territories, rank_count)
        if rank_territories is not None
        else None
    )
    i0, i1 = _bounds(i_bounds, "i_bounds")
    j0, j1 = _bounds(j_bounds, "j_bounds")

    selected: dict[tuple[int, int, int], CensusRow] = {}
    consumed: dict[tuple[int, int, int, int], CensusRow] = {}
    for record in rows:
        event = parse_census_row(record)
        if event is None:
            continue
        key = event.step, event.lat, event.i
        if key not in expected:
            raise ValueError(f"unexpected step or non-owned global coordinate: {key}")
        if not 0 <= event.rank < rank_count:
            raise ValueError(f"rank outside configured range: {event.rank}")
        if not i0 <= event.i <= i1 or not j0 <= event.lat <= j1:
            raise ValueError(f"halo or out-of-domain coordinate: {key}")
        if event.mstep < 1:
            raise ValueError("mstep must be positive")
        if territories is not None and event.rank != territories[key]:
            raise ValueError(f"rank does not own configured column {key}")

        if event.tag == "SELECT":
            if event.n != 0:
                raise ValueError("SELECT row must use n=0")
            if key in selected:
                raise ValueError(f"duplicate owner/selection for global column {key}")
            selected[key] = event
        else:
            if event.n < 1:
                raise ValueError("CONSUME row must use n>=1")
            consume_key = (*key, event.n)
            if consume_key in consumed:
                raise ValueError(f"duplicate consumer ordinal {consume_key}")
            consumed[consume_key] = event

    missing_selection = expected - selected.keys()
    if missing_selection:
        first = min(missing_selection)
        raise ValueError(f"missing SELECT owner record for global column {first}")

    for key, event in consumed.items():
        column_key = key[:3]
        if column_key not in selected:
            raise ValueError(f"CONSUME has no SELECT owner record: {column_key}")
        selection = selected[column_key]
        if event.rank != selection.rank:
            raise ValueError(f"consumer rank differs from selected owner: {column_key}")
        if event.mstep != selection.mstep:
            raise ValueError(f"consumer mstep differs from selection: {column_key}")
        if event.n > selection.mstep:
            raise ValueError(f"consumer ordinal exceeds finished mstep: {key}")

    # Uniqueness and the bounded ordinal check above imply completeness when
    # the number of consumers equals mstep. Avoid expanding a malformed huge
    # mstep into a range before the evidence has been validated.
    consumer_counts = {key: 0 for key in selected}
    for step, lat, i, _n in consumed:
        consumer_counts[step, lat, i] += 1
    for key, selection in selected.items():
        if consumer_counts[key] != selection.mstep:
            raise ValueError(
                f"missing CONSUME ordinal for {key}: expected {selection.mstep}, "
                f"found {consumer_counts[key]}"
            )

    msteps = [event.mstep for event in selected.values()]
    return {
        "schema": "native-execution-contract-v1",
        "steps": list(steps),
        "i_bounds": [i0, i1],
        "j_bounds": [j0, j1],
        "rank_count": rank_count,
        "selected_columns": len(selected),
        "consumer_rows": len(consumed),
        "min_selected_mstep": min(msteps),
        "max_selected_mstep": max(msteps),
        "mstep_source": "captured SELECT field; not independently recomputed from velocity",
        "ownership_scope": (
            "configured rank territories checked"
            if territories is not None
            else "unique recorded owner within configured rank range; territory map not supplied"
        ),
        "physics_across_ranks_certified": False,
    }
