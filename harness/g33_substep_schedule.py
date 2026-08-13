#!/usr/bin/env python3
"""The per-column SUB-STEP SCHEDULE, by chain.

`mstep` governs the qr/nr/qs/qg chain and `mstep_i` governs qi/ni, and the two
are chosen independently: a column can need the main chain subdivided while the
ice chain runs the whole step in one.

The records were always there. The strict parser already files both families
under `call["mstep"]`, keyed by `(loop, chain, col)` with chain "main" or
"ice" -- `metric_trajectory` reads exactly that to know how many sub-steps to
walk. What was missing was a reduction: `extension_protocol` reported
`record_counts.mstep`, how MANY records a run emitted, which says nothing about
the schedule they describe. So G33-MSTEPI-001 had no artifact to bind, and the
blocker I first wrote for it -- "no substep size is stored" -- was wrong about
why.

The schedule is a property of the step the run was made at, so a claim about
where a chain REACHES one sub-step needs several runs, not a better reading of
one (dtcld = 300/nsplit).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_number_transport as nt  # noqa: E402


def analysis(stream: str) -> dict:
    """{chain: {col: sub-steps}} for one member, with the step it ran at."""
    calls = list(nt.calls(stream))
    if not calls:
        raise nt.TransportError("no calls in this stream")

    # (chain, col) -> every count seen. A column is free to schedule
    # differently on different calls, and collapsing that to one number would
    # hide it -- the same reason `metric_trajectory` keys an interface by its
    # identity rather than trusting a position.
    seen: dict = {}
    for call in calls:
        for (_loop, chain, col), n in call["mstep"].items():
            seen.setdefault((chain, col), set()).add(int(n))

    if not seen:
        raise nt.TransportError(
            "no mstep/mstepi records -- this needs the instrumented build, "
            "whose `--nflux` overlay emits them")

    out: dict = {}
    for (chain, col), counts in sorted(seen.items()):
        out.setdefault(chain, {})[str(col)] = {
            # BOTH ends, and whether the column held ONE schedule. `substeps`
            # was a maximum over calls presented as the column's sub-step
            # count: at h = 25 s column 3's main chain ran 1, 2 AND 3, so
            # "needs 3" was true of its worst call and of no other (owner §8).
            # Kept under its old name, as the maximum it always was, beside the
            # fields that say so.
            "substeps": max(counts),
            "min_substeps": min(counts),
            "max_substeps": max(counts),
            "unique_substeps": sorted(counts),
            "constant_across_calls": len(counts) == 1,
            "varies_across_calls": len(counts) > 1,
            "seen": sorted(counts),
        }
    delt = calls[0]["delt"]
    for cols in out.values():
        for r in cols.values():
            # The SUB-STEP, which is what a schedule is about. `delt` is the
            # duration of the EXTERNAL call and the sub-step is delt/mstep, so
            # reporting only `delt` invited it to be read as the step the chain
            # integrates on (owner §8).
            r["effective_dt_max"] = delt / r["min_substeps"]
            r["effective_dt_min"] = delt / r["max_substeps"]
    return {"by_chain": out,
            # RENAMED, with `delt` kept so existing bindings still resolve.
            # "delt" read as "the timestep"; it is the external call duration,
            # and each chain subdivides it differently.
            "external_delt": delt, "delt": delt, "calls": len(calls),
            "subdivided": {c: sorted(k for k, v in cols.items()
                                     if v["max_substeps"] > 1)
                           for c, cols in out.items()},
            # Where a chain runs the whole call in ONE step on EVERY call.
            # "reaches one" needs both facts: a maximum of 1 says no call
            # subdivided, and constancy says that is the schedule rather than
            # its best case.
            "single_step": {c: sorted(k for k, v in cols.items()
                                      if v["max_substeps"] == 1
                                      and v["constant_across_calls"])
                            for c, cols in out.items()}}
