#!/usr/bin/env python3
"""Replay the qr state-update line from recorded evidence, per backend.

    qr_post == max(fl32(qr_pre + fl32(S * dtcld)), 0)

with S the branch-appropriate rate sum in the source's own left-to-right f32
association. This runs on ONE leg at a time and compares that leg against
itself, which is the point: it is a FIDELITY check on the evidence, not a
comparison between backends.

Why it has to exist (owner review §2). `micro_qr_operands` seals the rate
operands. Its note argued the set was closed because the incoming qr comes from
`outer_post_sed` — it does not: D1 melt, homogeneous freeze, the post-melt
re-slope, D2–D4 freeze, the post-freeze re-slope, the rate blocks and the
conservation scaling all run between that snapshot and the update. So "all
operands equal ⇒ the difference is in the summation" was unavailable. With
`micro_pre_state_update` recording the actual base, the line can be replayed
instead of reasoned about.

And it is self-validating, which matters more than the arithmetic. Three
placement defects in this protocol so far have all had the same shape: two
backends recording instants that are not the same instant, with nothing failing
because both instants are real program points. A replay that reproduces
`micro_post_state_update.qr` from `micro_pre_state_update.qr` and the operands,
on each backend independently, can only succeed if those three stages sit at
mutually consistent points in THAT backend. A cross-backend claim built on
stages that fail this is worth nothing, so the gate runs first.

The association is a CLAIM about the source and is checked the same way: it has
to reproduce every cell of every leg. An association that were wrong would fail
broadly rather than subtly, since f32 addition is not associative.
"""
from __future__ import annotations

import struct

import numpy as np

#: Fortran `REAL, PARAMETER :: t0c = 273.15` (module_mp_kdm6.F:3756).
T0C = np.float32(273.15)

#: Cold arm, Fortran F:2803:
#:   qrs(1) = max(qrs(1)+(praut+pracw+prevp-piacr-pgacr-psacr-pmulrs-pmulrg)*dtcld, 0.)
COLD_TERMS = (("+", "praut"), ("+", "pracw"), ("+", "prevp"),
              ("-", "piacr"), ("-", "pgacr"), ("-", "psacr"),
              ("-", "pmulrs"), ("-", "pmulrg"))

#: Warm arm, Fortran F:2922:
#:   qrs(1) = max(qrs(1)+(praut+pracw+prevp+paacw+paacw-pseml-pgeml)*dtcld, 0.)
#: `paacw` appears TWICE as two separate f32 adds, not as 2*paacw — the C++ mirror
#: says so explicitly and the association differs between the two forms.
WARM_TERMS = (("+", "praut"), ("+", "pracw"), ("+", "prevp"),
              ("+", "paacw"), ("+", "paacw"),
              ("-", "pseml"), ("-", "pgeml"))


def f32(bits: int) -> np.float32:
    return np.float32(struct.unpack("<f", struct.pack("<I", bits))[0])


def bits32(x) -> int:
    return struct.unpack("<I", struct.pack("<f", np.float32(x)))[0]


def is_cold(t_bits: int) -> bool:
    """The branch, recomputed from the recorded temperature (owner review §3).

    Fortran branches on `t <= t0c` (F:2638); the C++ `cold_mask` is
    `pre.supcol >= 0` (coordinator.cpp:1737) with `supcol = t0c - t`, i.e. also
    `t <= t0c`. They AGREE, including at the boundary: near t0c the subtraction
    `t0c - t` is exact in f32 by Sterbenz, so `supcol` carries no rounding of its
    own. An earlier version of this docstring said the C++ gated on `supcol > 0`
    and that the two disagreed at exactly t == t0c; that was taken from a review
    note and never checked against the code, and it is wrong.

    Deriving the branch here rather than trusting a producer-emitted flag still
    matters, and for the original reason: the flag is then EVIDENCE about the
    producer instead of the definition of the answer.
    """
    return bool(f32(t_bits) <= T0C)


def rate_sum(operands: dict, cold: bool) -> np.float32:
    """S, in the source's left-to-right f32 association. Not reordered, not fused."""
    s = np.float32(0.0)
    for sign, name in (COLD_TERMS if cold else WARM_TERMS):
        v = np.float32(operands[name])
        s = np.float32(s + v) if sign == "+" else np.float32(s - v)
    return s


def replay_qr(qr_pre_bits: int, operands: dict, dtcld, cold: bool,
              clamp: bool = True) -> int:
    """Predicted qr_post bits. `clamp` mirrors the `max(..., 0.)` the source applies."""
    s = rate_sum(operands, cold)
    inc = np.float32(s * np.float32(dtcld))
    out = np.float32(f32(qr_pre_bits) + inc)
    if clamp:
        out = np.float32(max(out, np.float32(0.0)))
    return bits32(out)


def verify_leg(pre: dict, operands: dict, post: dict, dtcld) -> list[dict]:
    """Every (col, k) of one leg. Returns the cells whose replay misses.

    `pre` / `post` are {(field, col, k): bits}; `operands` the same for the rate
    stage. A missing operand is a defect in the evidence, not a reason to skip the
    cell, so it raises rather than returning a pass.
    """
    cells = sorted({(c, k) for (f, c, k) in pre if f == "qr"})
    if not cells:
        raise ValueError("no qr cells in micro_pre_state_update — nothing to replay")
    bad = []
    for c, k in cells:
        cold = is_cold(pre[("t", c, k)])
        names = {n for _s, n in (COLD_TERMS if cold else WARM_TERMS)}
        try:
            ops = {n: f32(operands[(n, c, k)]) for n in names}
        except KeyError as e:
            raise ValueError(
                f"col{c} k{k}: micro_qr_operands is missing {e.args[0]}, which the "
                f"{'cold' if cold else 'warm'} arm reads") from None
        want = post[("qr", c, k)]
        got = replay_qr(pre[("qr", c, k)], ops, dtcld, cold)
        if got != want:
            bad.append({"col": c, "k": k, "branch": "cold" if cold else "warm",
                        "replayed": f"{got:#010x}", "recorded": f"{want:#010x}",
                        "qr_pre": f'{pre[("qr", c, k)]:#010x}'})
    return bad


def coverage(pre: dict, operands: dict, post: dict, dtcld) -> dict:
    """How much of a passing replay is load-bearing.

    "144 cells, 0 misses" reads as 144 checks and is not. Where every rate is
    zero the replay reduces to `qr_post == qr_pre` and confirms nothing about the
    arithmetic; on this fixture that is every cell of outer loop 3. Where the
    `max(…, 0)` clamp binds, the sum is discarded and the check is weaker again.

    Reported by the tool rather than worked out afterwards, because the
    overstatement it prevents is one this protocol already made.

    Returns cells / moved (qr changed) / zero_sum (vacuous) / clamped, and
    `load_bearing` = cells that are neither vacuous nor clamped.
    """
    cells = sorted({(c, k) for (f, c, k) in pre if f == "qr"})
    moved = zero_sum = clamped = 0
    for c, k in cells:
        cold = is_cold(pre[("t", c, k)])
        ops = {n: f32(operands[(n, c, k)]) for n in branch_active_fields(cold)}
        if rate_sum(ops, cold) == 0:
            zero_sum += 1
        if pre[("qr", c, k)] != post[("qr", c, k)]:
            moved += 1
        if replay_qr(pre[("qr", c, k)], ops, dtcld, cold, clamp=False) \
                != post[("qr", c, k)]:
            clamped += 1
    return {"cells": len(cells), "moved": moved, "zero_sum": zero_sum,
            "clamped": clamped,
            "load_bearing": len(cells) - zero_sum - clamped}


def branch_active_fields(cold: bool) -> frozenset:
    """Which operands the taken arm actually reads (owner review §3).

    A cell at 243 K takes the cold arm, whose qr line never reads `paacw`,
    `pseml` or `pgeml`. A difference in those is a diagnostic about the rate
    blocks; it is not causal for that cell's qr, and reporting it as a first
    divergence would name a value the update did not use.
    """
    return frozenset(n for _s, n in (COLD_TERMS if cold else WARM_TERMS))


# ── the D2–D4 freeze heat term (protocol v14) ────────────────────────────────
#
# Fortran F:1618 / F:1648 / F:1679, three sequential stores into the REAL(4) t:
#
#     c  = f32(xlf / cpm)
#     t2 = f32(t_pre + c*pinuc)      pinuc   DOUBLE (F:758)
#     t3 = f32(t2    + c*pfrzdtc)    pfrzdtc DOUBLE (F:781-782)
#     t4 = f32(t3    + c*pfrzdtr)    pfrzdtr DOUBLE (F:781-782)
#
# Each rate is DOUBLE, so `c * rate` is evaluated in double and the store rounds
# ONCE. Replaying it in f32 throughout would round twice and would not reproduce
# either backend — which is the point: the arithmetic is a claim, and it has to
# reproduce the reference before any difference between the two is interpreted.

FREEZE_TERMS = ("pinuc", "pfrzdtc", "pfrzdtr")


def replay_freeze_t(operands: dict, as_f32_rates: bool = False) -> int:
    """Predicted post-freeze `t` bits for one cell.

    `as_f32_rates` narrows each rate to f32 before the multiply — the shape a
    backend would have if it treated the reference's DOUBLE rate as f32. It is
    here so the difference between the two forms is measurable rather than argued.
    """
    import numpy as _np
    c = np.float32(np.float32(operands["xlf"]) / np.float32(operands["cpm"]))
    t = np.float32(operands["t_pre_freeze"])
    for name in FREEZE_TERMS:
        r = operands[name]
        r = np.float32(r) if as_f32_rates else np.float64(r)
        step = np.float32(c) * r          # f32*f64 -> f64 (or f32*f32 -> f32)
        t = np.float32(np.float64(t) + step) if not as_f32_rates \
            else np.float32(t + np.float32(step))
    return bits32(t)


def verify_freeze_heat(operands: dict, post_t: dict) -> list[dict]:
    """Every cell of one leg. `operands` and `post_t` are {(field,col,k): bits}.

    phom must be zero: the C++ chain has no homogeneous-freeze term, so a fixture
    that reaches −40 °C would have the two backends replaying different chains.
    Raising is the point — a silent pass there would compare two different things.
    """
    cells = sorted({(c, k) for (f, c, k) in operands if f == "t_pre_freeze"})
    if not cells:
        raise ValueError("no micro_freeze_heat cells — nothing to replay")
    bad = []
    for c, k in cells:
        if f32(operands[("phom", c, k)]) != 0.0:
            raise ValueError(
                f"col{c} k{k}: phom is non-zero, so the Fortran t chain has a "
                f"homogeneous-freeze term the C++ chain does not. This replay does "
                f"not cover that fixture.")
        vals = {"xlf": f32(operands[("xlf", c, k)]),
                "cpm": f32(operands[("cpm", c, k)]),
                "t_pre_freeze": f32(operands[("t_pre_freeze", c, k)])}
        for name in FREEZE_TERMS:
            vals[name] = struct.unpack(
                "<d", struct.pack("<Q", operands[(name, c, k)]))[0]
        got, want = replay_freeze_t(vals), post_t[("t", c, k)]
        if got != want:
            bad.append({"col": c, "k": k, "replayed": f"{got:#010x}",
                        "recorded": f"{want:#010x}"})
    return bad
