#!/usr/bin/env python3
"""Which PROCESS carries a qr difference, decomposed rather than attributed.

`FINDING_ncmin_scalar_vs_percell` said a higher droplet floor "suppresses
autoconversion", and the tool printed it as the mechanism. That was a process
attribution a final-state comparison cannot make: `ncmin` gates 18 sites --
autoconversion (praut), three accretion branches, graupel melting/evaporation
(pgeml), and the max(ncmin,nci) floors that set the diameters those rates
consume -- so the sign could belong to any of them (owner §7).

The reference already emits the operands. `micro_qr_operands` carries every term
of the qr update, per cell, with `cold_gate` recording which branch the cell
took:

    cold (F:2803)  qrs(1) += (praut+pracw+prevp-piacr-pgacr-psacr
                              -pmulrs-pmulrg)*dtcld
    warm (F:2922)  qrs(1) += (praut+pracw+prevp+paacw+paacw
                              -pseml-pgeml)*dtcld

So the decomposition needs no new instrumentation, only reading. The SIGNS here
are the update statement's, not a convention chosen to make a total agree: a
term is added or subtracted exactly as the reference adds or subtracts it.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_refine_analyze as ra  # noqa: E402

#: The qr update's operands, per branch, with the sign the reference applies.
COLD = {"praut": +1, "pracw": +1, "prevp": +1, "piacr": -1, "pgacr": -1,
        "psacr": -1, "pmulrs": -1, "pmulrg": -1}
WARM = {"praut": +1, "pracw": +1, "prevp": +1, "paacw": +1, "pseml": -1,
        "pgeml": -1}

STAGE = "micro_qr_operands"


def _f32(hexword: str) -> float:
    return struct.unpack(">f", bytes.fromhex(hexword))[0]


def read_operands(text: str, *, label: str) -> dict:
    """{(col, k): {term: value}} for every cell the stage emitted.

    Through the strict parser first, for the same reason every other reader
    here does: a truncated or duplicated stream must be refused, not summed.
    """
    ra.read_text(text, nsplit=1, label=label)
    out: dict = {}
    for p in (ln.split() for ln in text.splitlines()):
        if len(p) >= 11 and p[:2] == ["G33F", "STAGE"] and p[4] == STAGE:
            out.setdefault((int(p[7]), int(p[8])), {})[p[6]] = _f32(p[10])
    if not out:
        raise ra.RefineError(
            f"{label}: no `{STAGE}` records -- this needs the instrumented "
            f"build, without which the operands are not emitted")
    return out


def column_terms(cells: dict, col: int) -> tuple:
    """({branch: n cells}, {term: signed column sum}) for one column.

    PER CELL, because the update statement sits inside the k loop and
    `cold_gate` is `t(i,k) .le. t0c`: one column carries warm cells and cold
    cells, and they apply DIFFERENT operand sets. Summing a column under one
    set would include terms its cells never applied -- which is what the first
    version did, until the both-branches guard refused it.
    """
    keys = [k for k in cells if k[0] == col]
    if not keys:
        raise ra.RefineError(f"column {col} emitted no {STAGE} records")
    gates = {cells[k].get("cold_gate") for k in keys}
    if gates - {0.0, 1.0}:
        raise ra.RefineError(f"column {col}: cold_gate is {gates}, not 0/1")

    totals: dict = {}
    branches: dict = {"cold": 0, "warm": 0}
    for k in keys:
        cold = cells[k].get("cold_gate") == 1.0
        branches["cold" if cold else "warm"] += 1
        for term, s in (COLD if cold else WARM).items():
            totals[term] = totals.get(term, 0.0) + cells[k].get(term, 0.0) * s
    return (branches, totals)


def decompose(base_text: str, got_text: str, width: int) -> dict:
    """Per column, which terms move between two runs and by how much."""
    a = read_operands(base_text, label="base")
    b = read_operands(got_text, label="got")
    out = {}
    for col in range(1, width + 1):
        arm_a, ta = column_terms(a, col)
        arm_b, tb = column_terms(b, col)
        if arm_a != arm_b:
            raise ra.RefineError(
                f"column {col} split {arm_a} across branches in one run and "
                f"{arm_b} in the other, so the two are not term-comparable")
        delta = {t: tb.get(t, 0.0) - ta.get(t, 0.0) for t in set(ta) | set(tb)}
        total = sum(delta.values())
        out[col] = {
            "branches": arm_a,
            "base": ta, "got": tb, "delta": delta, "total_delta": total,
            # The SHARE each term carries of the change. Reported only where
            # there IS a change: a share of a zero total is not a number, and
            # printing 0/0 as a percentage is how a null result acquires a
            # spurious mechanism.
            "share": ({t: d / total for t, d in delta.items() if d}
                      if total else {}),
        }
    return out
