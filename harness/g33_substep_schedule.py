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
            "substeps": max(counts),
            # Reported, not assumed away: if a column ran a different number of
            # sub-steps on different calls, `substeps` is a summary of a thing
            # that moved, and a reader has to be told.
            "varies_across_calls": len(counts) > 1,
            "seen": sorted(counts),
        }
    delt = calls[0]["delt"]
    return {"by_chain": out, "delt": delt, "calls": len(calls),
            # Which columns ever needed the chain subdivided, per chain. The
            # claim is about where a chain reaches ONE.
            "subdivided": {c: sorted(k for k, v in cols.items()
                                     if v["substeps"] > 1)
                           for c, cols in out.items()}}
