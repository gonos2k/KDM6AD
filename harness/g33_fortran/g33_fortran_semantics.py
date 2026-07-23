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
  4  substep_pre(n=1) qr/nr == outer_pre_sed qr/nr (sed-entry linkage).
  5  substep_pre(n+1) qr/nr == QR/NR_UPDATE.q_post/n_post of substep n (continuity).
  6  QR_FALLACC.fall_after at (bottom cell, last substep) == surface.bottom_fall_qr.
  7  bottom_fall_total == (((qr+qs)+qg)+qi); rain PREC == the surface increment.
"""
import struct

import numpy as np


class SemanticError(ValueError):
    """A stage/surface record is not causally consistent with the op ladder."""


def _f32(bits):
    return np.float32(struct.unpack(">f", bits.to_bytes(4, "big"))[0])


def _f32_bits(v):
    return struct.unpack(">I", struct.pack(">f", float(np.float32(v))))[0]


def _signed_i32(u):
    return u - 0x100000000 if u >= 0x80000000 else u


def verify_semantics(run):
    B, K, S = run.B, run.K, run.stages
    mm = max(run.mstep.values())

    # (3) mstep / gate / dtcld are the ACTUAL run's, not a self-report.
    dt = run.params["dt"]                                  # f32 bits
    for c in range(1, B + 1):
        for n in range(1, mm + 1):
            if _signed_i32(S[("substep_pre", n, "mstep", c, -1)][1]) != run.mstep[c]:
                raise SemanticError(f"substep_pre.mstep(c={c},n={n}) != MSTEP record")
            g = S[("substep_pre", n, "gate", c, -1)][1]
            if g not in (0, 1) or g != (1 if n <= run.mstep[c] else 0):
                raise SemanticError(f"substep_pre.gate(c={c},n={n})={g} != [n<=mstep]")
            if S[("substep_pre", n, "dtcld", c, -1)][1] != dt:
                raise SemanticError(f"substep_pre.dtcld(c={c},n={n}) != PARAM dt")

    # (4) the first substep's entry state IS the pre-sed snapshot.
    for c in range(1, B + 1):
        for k in range(K):
            for sp in ("qr", "nr"):
                if S[("substep_pre", 1, sp, c, k)][1] != S[("outer_pre_sed", 0, sp, c, k)][1]:
                    raise SemanticError(
                        f"substep_pre(n=1).{sp} != outer_pre_sed.{sp} c={c} k={k}")

    # (5) each substep's entry state is the previous substep's stored update.
    qpost = {(o.col, o.k, o.n): o.bits for o in run.ops
             if o.op_id == "QR_UPDATE" and o.field == "q_post"}
    npost = {(o.col, o.k, o.n): o.bits for o in run.ops
             if o.op_id == "NR_UPDATE" and o.field == "n_post"}
    for c in range(1, B + 1):
        for n in range(1, run.mstep[c]):                   # n and n+1 both active
            for k in range(K):
                if S[("substep_pre", n + 1, "qr", c, k)][1] != qpost[(c, k, n)]:
                    raise SemanticError(f"qr continuity broken c={c} k={k} n={n}->{n+1}")
                if S[("substep_pre", n + 1, "nr", c, k)][1] != npost[(c, k, n)]:
                    raise SemanticError(f"nr continuity broken c={c} k={k} n={n}->{n+1}")

    # (6) the seed reaches the surface: bottom-cell accumulator == surface fall.
    fall_after = {(o.col, o.k, o.n): o.bits for o in run.ops
                  if o.op_id == "QR_FALLACC" and o.field == "fall_after"}
    for c in range(1, B + 1):
        if fall_after[(c, K - 1, run.mstep[c])] != S[("surface", 0, "bottom_fall_qr", c, -1)][1]:
            raise SemanticError(f"bottom qr fall_after != surface.bottom_fall_qr c={c}")

    # (7) surface species sum + rain increment, replayed bit-exact.
    for c in range(1, B + 1):
        qr, qs, qg, qi = (_f32(S[("surface", 0, f, c, -1)][1]) for f in
                          ("bottom_fall_qr", "bottom_fall_qs", "bottom_fall_qg", "bottom_fall_qi"))
        total = np.float32(np.float32(np.float32(qr + qs) + qg) + qi)
        if _f32_bits(total) != S[("surface", 0, "bottom_fall_total", c, -1)][1]:
            raise SemanticError(f"bottom_fall_total != (((qr+qs)+qg)+qi) c={c}")
        tot = _f32(S[("surface", 0, "bottom_fall_total", c, -1)][1])
        delz_b = _f32(S[("surface", 0, "delz_bottom", c, -1)][1])
        denr = _f32(S[("surface", 0, "surface_denr", c, -1)][1])
        dtcld = _f32(dt)
        # rainncv(i) = fallsum*delz(i,kts)/denr*dtcld*1000. + rainncv(i), rainncv0=0,
        # guarded by fallsum>0. Left-associated f32.
        rain = np.float32(0.0)
        if tot > np.float32(0.0):
            rain = np.float32(np.float32(np.float32(np.float32(tot * delz_b) / denr)
                                         * dtcld) * np.float32(1000.0))
        if _f32_bits(rain) != run.precip[(1, c)]:
            raise SemanticError(f"PREC rain replay mismatch c={c}")
    return True
