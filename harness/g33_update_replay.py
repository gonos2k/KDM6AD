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

    Fortran branches on `t <= t0c` (F:2638). The C++ gates on `supcol > 0` with
    `supcol = t0c - t`, which is `t < t0c` — the two disagree at exactly t == t0c.
    Deriving the branch here rather than trusting a producer-emitted flag means the
    flag is EVIDENCE about the producer instead of the definition of the answer.
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


def branch_active_fields(cold: bool) -> frozenset:
    """Which operands the taken arm actually reads (owner review §3).

    A cell at 243 K takes the cold arm, whose qr line never reads `paacw`,
    `pseml` or `pgeml`. A difference in those is a diagnostic about the rate
    blocks; it is not causal for that cell's qr, and reporting it as a first
    divergence would name a value the update did not use.
    """
    return frozenset(n for _s, n in (COLD_TERMS if cold else WARM_TERMS))
