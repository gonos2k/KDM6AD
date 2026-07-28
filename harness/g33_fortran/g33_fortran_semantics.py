#!/usr/bin/env python3
"""Intra-run SEMANTIC validation of a parsed FortranRun (owner P0-2/3/4).

Structural completeness (record universe, dtype, finiteness, domain) is
g33_fortran_dump's job. This module proves the pre-sed + surface snapshots are
CAUSALLY consistent with the real op ladder and mstep — that they observe the
actual evolving state, not a self-consistent-but-wrong fabrication. Without it a
producer-evidence defect (e.g. a stale mstep in a stage record, or a surface fall
that does not match the bottom-cell accumulator) would reach the comparator and
be misread as a backend divergence.

Checks (all bit-exact; f32 arithmetic via numpy.float32 in the reference order):
  3  substep_pre mstep == MSTEP record; gate == [n<=mstep] in {0,1}; dtcld == dt.
  4  substep_pre(n=1) qr/nr == outer_pre_sed qr/nr, in EVERY outer loop.
  5  substep_pre(n+1) qr/nr == QR/NR_UPDATE.q_post/n_post of substep n (continuity).
  6  QR_FALLACC.fall_after at (bottom cell, last substep) == surface.bottom_fall_qr.
  7  bottom_fall_total == (((qr+qs)+qg)+qi); rain PREC == sum_L of the per-loop
     surface increments (it is the whole-step accumulator, not one loop's value).
  9  outer_post_micro(N) == the returned STATE, for every carried field the state
     also carries — the last loop's exit is bound to the subroutine's output.
  8  outer_post_micro(L) == outer_pre_sed(L+1) for every carried prognostic — the
     outer-loop carry is evidence, not an assumption (owner P0-C1). Skipped for a
     pre-v4 stream, which carries no bridge records at all; whether their absence
     is admissible is the record-universe validator's call, keyed off the banner.
"""
import struct

import numpy as np


#: The carried fields that the FINAL STATE also carries, so the last loop's exit can
#: be bound to what the subroutine actually returned. `t` is excluded on purpose: the
#: state carries `th`, and th = t/pii is a computation, not a copy — asserting bit
#: equality there would be asserting the conversion, not the binding.
#: stage field -> the name the returned STATE uses for it. Only `brs`/`bg` differ,
#: and that is a rename across a copy, not a computation — unlike t/th, which is why
#: `t` stays out.
_FINAL_BOUND = {"qv": "qv", "qc": "qc", "qr": "qr", "qi": "qi", "qs": "qs",
                "qg": "qg", "nr": "nr", "nc": "nc", "ni": "ni", "nccn": "nccn",
                "brs": "bg"}

#: What the outer loop carries from one cloud sub-cycle to the next. The INTERSECTION
#: of the two bridge snapshots' field sets, since the carry can only be stated about
#: fields both of them observe.
_CARRIED_FIELDS = ("qr", "nr", "qv", "t", "qc", "qi", "qs", "qg",
                   "nc", "ni", "nccn", "brs")


class SemanticError(ValueError):
    """A stage/surface record is not causally consistent with the op ladder."""


def _f32(bits):
    return np.float32(struct.unpack(">f", bits.to_bytes(4, "big"))[0])


def _f32_bits(v):
    return struct.unpack(">I", struct.pack(">f", float(np.float32(v))))[0]


def _signed_i32(u):
    return u - 0x100000000 if u >= 0x80000000 else u


_CHAIN = {"outer_pre_sed": "-", "surface": "-", "substep_pre": "main",
          "outer_post_sed": "-", "outer_post_micro": "-"}


def _sv(stages, stage, n, field, col, k, loop=1):
    """Stage lookup. The stage key carries (outer_loop, chain) so multi-loop records
    cannot collide; these causal checks are scoped to the single main-chain outer
    loop the overlay emits, so the loop defaults to 1."""
    return stages[(loop, _CHAIN[stage], stage, n, field, col, k)]


def _f32_of(bits):
    return np.float32(struct.unpack(">f", struct.pack(">I", bits))[0])


def verify_semantics(run):
    B, K, S = run.B, run.K, run.stages
    scopes = sorted({(lp, ch) for lp, ch, _c in run.mstep})
    loops = sorted({lp for lp, _ch in scopes})
    # The cloud timestep is the host step divided by the number of outer loops, so
    # `dtcld == dt` holds only at loops == 1.
    dt = run.params["dt"]                                  # f32 bits
    want_dtcld = (dt if len(loops) == 1 else
                  struct.unpack(">I", struct.pack(">f", _f32_of(dt) / np.float32(len(loops))))[0])

    # (3) mstep / gate / dtcld are the ACTUAL run's, not a self-report.
    for loop, chain in scopes:
        top = max(v for (lp, ch, _c), v in run.mstep.items() if (lp, ch) == (loop, chain))
        for c in range(1, B + 1):
            m = run.mstep[(loop, chain, c)]
            for n in range(1, top + 1):
                if _signed_i32(_sv(S, "substep_pre", n, "mstep", c, -1, loop)[1]) != m:
                    raise SemanticError(f"substep_pre.mstep(L{loop},c={c},n={n}) != MSTEP record")
                g = _sv(S, "substep_pre", n, "gate", c, -1, loop)[1]
                if g not in (0, 1) or g != (1 if n <= m else 0):
                    raise SemanticError(f"substep_pre.gate(L{loop},c={c},n={n})={g} != [n<=mstep]")
                if _sv(S, "substep_pre", n, "dtcld", c, -1, loop)[1] != want_dtcld:
                    raise SemanticError(
                        f"substep_pre.dtcld(L{loop},c={c},n={n}) != f32(dt/{len(loops)})")

    # (4) EVERY loop's first substep entry state IS that loop's pre-sed snapshot.
    # This omitted the loop argument, so it checked loop 1 and defaulted the rest:
    # a stale or mislinked loop-2 entry snapshot passed unexamined.
    for loop, _chain in scopes:
        for c in range(1, B + 1):
            for k in range(K):
                for sp in ("qr", "nr"):
                    if _sv(S, "substep_pre", 1, sp, c, k, loop)[1] != \
                            _sv(S, "outer_pre_sed", 0, sp, c, k, loop)[1]:
                        raise SemanticError(
                            f"substep_pre(n=1).{sp} != outer_pre_sed.{sp} "
                            f"L{loop} c={c} k={k}")

    # (5) each substep's entry state is the previous substep's stored update.
    # Keyed by the OUTER LOOP too: the same (col,k,n) recurs in every cloud
    # subcycle, so a loop-blind map would silently compare one loop's entry state
    # against another loop's stored update.
    qpost = {(o.loop, o.chain, o.col, o.k, o.n): o.bits for o in run.ops
             if o.op_id == "QR_UPDATE" and o.field == "q_post"}
    npost = {(o.loop, o.chain, o.col, o.k, o.n): o.bits for o in run.ops
             if o.op_id == "NR_UPDATE" and o.field == "n_post"}
    for loop, chain in scopes:
        for c in range(1, B + 1):
            for n in range(1, run.mstep[(loop, chain, c)]):   # n and n+1 both active
                for k in range(K):
                    if _sv(S, "substep_pre", n + 1, "qr", c, k, loop)[1] != \
                            qpost[(loop, chain, c, k, n)]:
                        raise SemanticError(
                            f"qr continuity broken L{loop} c={c} k={k} n={n}->{n+1}")
                    if _sv(S, "substep_pre", n + 1, "nr", c, k, loop)[1] != \
                            npost[(loop, chain, c, k, n)]:
                        raise SemanticError(
                            f"nr continuity broken L{loop} c={c} k={k} n={n}->{n+1}")

    # (6) the seed reaches the surface, in EVERY loop: each loop's bottom-cell
    # accumulator at its own final substep is that loop's surface fall. The surface
    # record is per loop, so comparing only the last one left the earlier loops'
    # bottom-fall values linked to nothing.
    fall_after = {(o.loop, o.col, o.k, o.n): o.bits for o in run.ops
                  if o.op_id == "QR_FALLACC" and o.field == "fall_after"}
    for loop, _chain in scopes:
        for c in range(1, B + 1):
            if fall_after[(loop, c, K - 1, run.mstep[(loop, "main", c)])] != \
                    _sv(S, "surface", 0, "bottom_fall_qr", c, -1, loop)[1]:
                raise SemanticError(
                    f"bottom qr fall_after != surface.bottom_fall_qr L{loop} c={c}")

    # (7) surface species sum + rain increment, replayed bit-exact.
    dtcld = _f32(want_dtcld)
    for c in range(1, B + 1):
        # PREC is CUMULATIVE over the whole micro step: the surface accumulation runs
        # once per outer loop and adds into rainncv, which starts at 0. So the replay
        # sums the per-loop increments in loop order, in the same left-associated f32
        # the Fortran uses — a single-surface replay only happens to work at loops==1.
        rain = np.float32(0.0)
        for loop in loops:
            qr, qs, qg, qi = (_f32(_sv(S, "surface", 0, f, c, -1, loop)[1]) for f in
                              ("bottom_fall_qr", "bottom_fall_qs",
                               "bottom_fall_qg", "bottom_fall_qi"))
            total = np.float32(np.float32(np.float32(qr + qs) + qg) + qi)
            if _f32_bits(total) != _sv(S, "surface", 0, "bottom_fall_total", c, -1, loop)[1]:
                raise SemanticError(f"bottom_fall_total != (((qr+qs)+qg)+qi) L{loop} c={c}")
            tot = _f32(_sv(S, "surface", 0, "bottom_fall_total", c, -1, loop)[1])
            delz_b = _f32(_sv(S, "surface", 0, "delz_bottom", c, -1, loop)[1])
            denr = _f32(_sv(S, "surface", 0, "surface_denr", c, -1, loop)[1])
            # rainncv = fallsum*delz/denr*dtcld*1000 + rainncv, guarded by fallsum>0
            if tot > np.float32(0.0):
                rain = np.float32(np.float32(np.float32(np.float32(np.float32(tot * delz_b)
                                                                   / denr) * dtcld)
                                             * np.float32(1000.0)) + rain)
        if _f32_bits(rain) != run.precip[(1, c)]:
            raise SemanticError(f"PREC rain replay mismatch c={c}")

    # (8) THE OUTER-LOOP CARRY. What loop L ends with is what loop L+1 begins with,
    # for every prognostic the loop carries. Without this the outer loops are a
    # sequence of snapshots with nothing linking them: a divergence first visible at
    # loop 2's pre-sed entry could have been born in loop 1's sedimentation, in the
    # microphysics that follows it, or in the carry itself, and the evidence could
    # not tell those apart. Bit-exact, because a carry is a copy and not a
    # computation — anything but equality is a defect in the evidence, not a
    # tolerance question.
    has_bridge = any(key[2] == "outer_post_micro" for key in S)
    for loop in (loops[:-1] if has_bridge else ()):
        for c in range(1, B + 1):
            for k in range(K):
                for f in _CARRIED_FIELDS:
                    if _sv(S, "outer_post_micro", 0, f, c, k, loop)[1] != \
                            _sv(S, "outer_pre_sed", 0, f, c, k, loop + 1)[1]:
                        raise SemanticError(
                            f"outer carry broken: outer_post_micro(L{loop}).{f} != "
                            f"outer_pre_sed(L{loop + 1}).{f} c={c} k={k}")

    # (9) THE LAST LOOP'S EXIT IS WHAT THE SUBROUTINE RETURNED. Without this the
    # bridge would chain the loops to each other but leave the final one attached to
    # nothing, and a difference introduced after the last outer_post_micro — in the
    # pack-out — would be invisible to every check above.
    if has_bridge and run.state:
        last = max(loops)
        for c in range(1, B + 1):
            for k in range(K):
                for f, state_name in _FINAL_BOUND.items():
                    got = run.state.get((state_name, c, k))
                    if got is None:
                        continue                  # not a state field on this protocol
                    if _sv(S, "outer_post_micro", 0, f, c, k, last)[1] != got:
                        raise SemanticError(
                            f"final state not bound: outer_post_micro(L{last}).{f} "
                            f"!= STATE.{f} c={c} k={k}")
    return True
