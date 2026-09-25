"""Bounded-memory replay of a declared native SELECT/CONSUME schedule.

Unlike the fixed G4 replayer, this checks an independently configured set of
outer steps and owned coordinates. It proves event coverage/ordinals only;
SELECT mstep is a measured value, not a recomputed physical velocity, and an
ice loop can execute with zero ice or zero transferred number.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import gzip
import hashlib
import json
import lzma
from pathlib import Path
from typing import Iterable

import numpy as np

from native_execution_contract import parse_census_row


MAX_EXPECTED_COLUMNS = 20_000_000
MAX_ORDINAL = 63


@dataclass(frozen=True)
class CensusPlan:
    steps: tuple[int, ...]
    i_bounds: tuple[int, int]
    j_bounds: tuple[int, int]
    rank: int = 0


@dataclass(frozen=True)
class CensusAudit:
    selected_rows: int
    consumed_rows: int
    expected_columns: int
    multistep_selected: int
    maximum_mstep: int
    mstep_histogram: dict[int, int]
    first_multistep: dict[str, int] | None


def _plan_shape(plan: CensusPlan) -> tuple[int, int, int]:
    if (not isinstance(plan, CensusPlan) or not isinstance(plan.steps, tuple)
            or not plan.steps or any(type(x) is not int or x < 1 for x in plan.steps)
            or len(set(plan.steps)) != len(plan.steps)
            or any(type(x) is not int for x in (*plan.i_bounds, *plan.j_bounds))
            or type(plan.rank) is not int or plan.rank < 0):
        raise ValueError("declare positive unique steps, integer bounds and rank")
    i0, i1 = plan.i_bounds
    j0, j1 = plan.j_bounds
    if i0 > i1 or j0 > j1:
        raise ValueError("owned bounds must be increasing inclusive coordinates")
    shape = (len(plan.steps), j1 - j0 + 1, i1 - i0 + 1)
    expected = shape[0] * shape[1] * shape[2]
    if expected > MAX_EXPECTED_COLUMNS:
        raise ValueError("declared census exceeds bounded-memory replay size")
    return shape


def validate_streaming_census(lines: Iterable[str], plan: CensusPlan) -> CensusAudit:
    """Require one SELECT and every 1..mstep CONSUME for every planned cell."""
    shape = _plan_shape(plan)
    index_by_step = {step: index for index, step in enumerate(plan.steps)}
    selected = np.zeros(shape, dtype=bool)
    msteps = np.zeros(shape, dtype=np.uint8)
    consumed = np.zeros(shape, dtype=np.uint64)
    selected_rows = consumed_rows = multistep = 0
    first_multi: dict[str, int] | None = None
    histogram: dict[int, int] = {}
    i0, i1 = plan.i_bounds
    j0, j1 = plan.j_bounds

    for line in lines:
        row = parse_census_row(line)
        if row is None:
            continue
        if (row.step not in index_by_step or row.rank != plan.rank
                or not i0 <= row.i <= i1 or not j0 <= row.lat <= j1):
            raise ValueError("event is outside independently declared step/owner cells")
        index = (index_by_step[row.step], row.lat - j0, row.i - i0)
        if not 1 <= row.mstep <= MAX_ORDINAL:
            raise ValueError("mstep is outside supported 1..63 ordinal range")
        if row.tag == "SELECT":
            if row.n != 0 or selected[index]:
                raise ValueError("duplicate or malformed SELECT")
            selected[index] = True
            msteps[index] = row.mstep
            selected_rows += 1
            histogram[row.mstep] = histogram.get(row.mstep, 0) + 1
            if row.mstep > 1:
                multistep += 1
                if first_multi is None:
                    first_multi = {"step": row.step, "rank": row.rank,
                                   "j": row.lat, "i": row.i,
                                   "mstep": row.mstep}
        else:
            if (not selected[index] or row.mstep != int(msteps[index])
                    or not 1 <= row.n <= row.mstep):
                raise ValueError("CONSUME lacks a matching SELECT or valid ordinal")
            bit = np.uint64(1) << np.uint64(row.n - 1)
            if consumed[index] & bit:
                raise ValueError("duplicate CONSUME ordinal")
            consumed[index] |= bit
            consumed_rows += 1

    if not selected.all():
        raise ValueError("incomplete SELECT coverage of the declared schedule")
    expected_mask = (np.uint64(1) << msteps.astype(np.uint64)) - np.uint64(1)
    if not np.array_equal(consumed, expected_mask):
        raise ValueError("missing CONSUME ordinal in declared schedule")
    if consumed_rows != int(msteps.sum(dtype=np.int64)):
        raise ValueError("consumer count differs from selected mstep sum")
    return CensusAudit(selected_rows, consumed_rows, selected.size,
                       multistep, int(msteps.max()), histogram, first_multi)


def replay_file(path: Path, plan: CensusPlan) -> dict[str, object]:
    opener = ({".gz": gzip.open, ".xz": lzma.open}.get(path.suffix, open))
    with opener(path, "rt") as stream:
        audit = validate_streaming_census(stream, plan)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return {
        "schema": "streaming-ice-census-v1",
        "scope": "declared event coverage and ordinals, not active ice or rate physics",
        "plan": asdict(plan),
        "audit": asdict(audit),
        "file_sha256": digest.hexdigest(),
        "source_file": path.name,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--i-bounds", type=int, nargs=2, default=(2, 233))
    parser.add_argument("--j-bounds", type=int, nargs=2, default=(2, 281))
    parser.add_argument("--rank", type=int, default=0)
    args = parser.parse_args()
    plan = CensusPlan(tuple(range(1, args.steps + 1)),
                      tuple(args.i_bounds), tuple(args.j_bounds), args.rank)
    print(json.dumps(replay_file(args.log, plan), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
