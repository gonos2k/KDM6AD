#!/usr/bin/env python3
"""Which recorded operands the arithmetic at a cell actually consumes.

A stage records every field at every cell so the expectation stays uniform. Not
every one of them is read: a cold cell's qr update never touches `paacw`, and a
cell with no freeze happening multiplies `xlf/cpm` by zero. A difference in such
a value is a diagnostic about the producer, not a cause of anything downstream —
and reporting it as a FIRST DIVERGENCE names a number the arithmetic did not use.

That is not hypothetical. The v14 gate named `xlf` at loop 1 column 1 as the
first divergence: a 289 K cell where the reference applies its `xlf = xlf0`
override and the port does not, and where all three freeze rates are zero. The
causally meaningful divergence was two loops and two columns away. Owner review
§3 raised the same shape for `micro_qr_operands`.

The REFERENCE defines activity. Both legs record the same identities, so the
question "did this cell's arithmetic read this field" has one answer, and it is
the Fortran's — taking it from the port would let a port bug decide which port
bugs are visible.

Non-causal records are not dropped. They are routed to the same
diagnostics-only channel the gate-inactive op lanes already use, so they stay
in the artifact and out of the verdict.
"""
from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_update_replay as _rp   # noqa: E402  (branch rule + T0C, one definition)

#: Fields of `micro_freeze_heat` that are only read when something freezes.
#: The three rates are always causal: a rate that differs, differs.
_FREEZE_COEFFICIENTS = ("xlf", "cpm")
_FREEZE_RATES = ("pinuc", "pfrzdtc", "pfrzdtr")


def _by_cell(run, stage):
    """{(loop, col, k): {field: bits}} for one stage of one normalized run."""
    out = {}
    for r in run["stages"]:
        if r["stage"] == stage:
            out.setdefault((r["loop"], r["col"], r["k"]), {})[r["field"]] = r["bits"]
    return out


def _f64(bits):
    return struct.unpack("<d", struct.pack("<Q", bits))[0]


def _moves_t(mine: dict, theirs: dict) -> bool:
    """Does swapping in the other backend's coefficient change the STORED t?

    The exact test, replacing "is some rate nonzero". Same base and same rates —
    only the coefficient differs — so what this isolates is precisely whether the
    coefficient difference survives the three f32 stores. It answers correctly for
    a rate that is exactly zero, for one that is subnormal, and for one that is
    simply too small to tip the rounding.
    """
    base = {"t_pre_freeze": _rp.f32(mine["t_pre_freeze"]),
            **{n: _f64(mine[n]) for n in _FREEZE_RATES}}
    with_mine = _rp.replay_freeze_t(
        {**base, "xlf": _rp.f32(mine["xlf"]), "cpm": _rp.f32(mine["cpm"])})
    with_theirs = _rp.replay_freeze_t(
        {**base, "xlf": _rp.f32(theirs["xlf"]), "cpm": _rp.f32(theirs["cpm"])})
    return with_mine != with_theirs


def noncausal_stage_records(run, other=None) -> frozenset:
    """Identities in `run` whose value that cell's arithmetic does not consume.

    Identity layout is the comparator's: (stage, loop, chain, n, col, k, field,
    dtype). Only the fields this function knows a rule for are ever excluded —
    a stage with no rule contributes nothing, so adding a stage cannot silently
    start hiding differences.

    `other` is the opposite backend's run. When supplied, the freeze coefficients
    are judged by an EXACT COUNTERFACTUAL rather than by whether a rate is nonzero:
    replay the three t-stores with each backend's coefficient and ask whether the
    stored f32 differs. A nonzero rate can still be too small for the coefficient
    difference to survive the rounding, and such a cell is read by the formula but
    is not load-bearing for the divergence. Without `other` the weaker
    any-rate-nonzero rule applies, which is conservative in the safe direction: it
    excludes less.
    """
    out = set()

    for (loop, col, k), fields in _by_cell(run, "micro_freeze_heat").items():
        if not all(n in fields for n in _FREEZE_RATES):
            continue                      # incomplete record: leave it visible
        if not all(n in fields for n in ("t_pre_freeze", "xlf", "cpm")):
            continue
        if other is not None:
            o = _by_cell(other, "micro_freeze_heat").get((loop, col, k))
            if o and all(n in o for n in ("xlf", "cpm")):
                if _moves_t(fields, o):
                    continue              # load-bearing: keep it in the verdict
            elif any(_f64(fields[n]) != 0.0 for n in _FREEZE_RATES):
                continue                  # no counterpart record: fall back
        elif any(_f64(fields[n]) != 0.0 for n in _FREEZE_RATES):
            continue                      # something freezes here
        for name in _FREEZE_COEFFICIENTS:
            if name in fields:
                out.add(("micro_freeze_heat", loop, "-", 0, col, k, name, "f32"))

    # micro_qr_operands: the two arms of F:2638 read different operands, and the
    # branch comes from the state the update reads — recomputed here from `t`,
    # not taken from the producer's own cold_gate flag.
    base = _by_cell(run, "micro_pre_state_update")
    for (loop, col, k), fields in _by_cell(run, "micro_qr_operands").items():
        t = base.get((loop, col, k), {}).get("t")
        if t is None:
            continue                      # no base recorded: leave it visible
        active = _rp.branch_active_fields(_rp.is_cold(t))
        for name in fields:
            if name == "cold_gate":       # the producer's own claim: always shown
                continue
            if name not in active:
                out.add(("micro_qr_operands", loop, "-", 0, col, k, name, "f32"))

    return frozenset(out)
