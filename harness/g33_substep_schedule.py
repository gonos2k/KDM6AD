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

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_number_transport as nt  # noqa: E402


def analysis(stream: str) -> dict:
    """{chain: {col: sub-steps}} for one member, with the step it ran at."""
    calls = list(nt.calls(stream))
    if not calls:
        raise nt.StreamError("no calls in this stream")

    # (chain, col) -> every count seen. A column is free to schedule
    # differently on different calls, and collapsing that to one number would
    # hide it -- the same reason `metric_trajectory` keys an interface by its
    # identity rather than trusting a position.
    seen: dict = {}
    for call in calls:
        for (_loop, chain, col), n in call["mstep"].items():
            seen.setdefault((chain, col), set()).add(int(n))

    if not seen:
        raise nt.StreamError(
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
    # VERIFIED, not read once. `delt` is a PER-CALL quantity and the counts
    # above are aggregated over every call, so taking it from `calls[0]` and
    # dividing all of them by it is only right while every call agrees --
    # which nothing checked. A run whose calls carry different external steps
    # would have produced an effective sub-step computed from one call's delt
    # and another call's mstep (Codex).
    #
    # The repository already does this correctly for rho/delz in
    # `window_cell_mass`: they are forcing, verified identical in each call
    # rather than assumed. Same treatment here.
    delts = {c["delt"] for c in calls}
    # DOMAIN first. The effective sub-step is delt/mstep, so a delt of 0 gave
    # a sub-step of zero duration, a negative one gave negative time and an
    # infinite one gave infinity -- all reported as ordinary numbers (Codex).
    #
    # NaN has to be caught here too, and not by the equality check below: NaN
    # is never equal to itself, so N calls carrying it produce N distinct set
    # entries and the check reported "different external steps [nan, nan, ...]"
    # -- failing closed for the wrong reason, and passing outright on a
    # single-call run.
    bad = sorted(d for d in delts if not math.isfinite(d) or d <= 0.0)
    if bad:
        raise nt.StreamError(
            f"external step {bad} is not a positive finite duration -- the "
            f"effective sub-step is delt/mstep, so this is not a schedule")
    if len(delts) != 1:
        raise nt.StreamError(
            f"the calls carry different external steps {sorted(delts)} -- the "
            f"effective sub-step is delt/mstep, so a single schedule for this "
            f"member is not defined and one call's delt must not be applied "
            f"to another call's count")
    delt = delts.pop()
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
            # Recorded so a reader can see the check happened rather than
            # trusting that it did.
            "external_delt_constant_across_calls": True,
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
