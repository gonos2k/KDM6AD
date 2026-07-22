#!/usr/bin/env python3
"""Write a TEMPORARY G3.3-M instrumentation overlay of the reference Fortran.

Protocol §5.1: the canonical Fortran is NEVER edited (frozen). This reads the
canonical `module_mp_kdm6.F`, verifies its SHA against the pin (a drift =
re-derive, fail-loud), inserts `#ifdef KDM6_G33_FORTRAN_DUMP`-guarded op-record
emission at unique anchors in the sedimentation sub-cycle, and writes a
throw-away patched copy. Compiled WITHOUT the macro it is byte-identical
behaviour; WITH it, the sed ladder is dumped to stdout as G33OP lines the
four-case comparator reads.

    make_fortran_overlay.py <canonical.F> <out_overlay.F>

Emitted per active (column i, top-first k = kte-k, substep n):
    G33OP <i> <k> <n> QR_FALK.falk_f32     <hex8>
    G33OP <i> <k> <n> QR_OUTFLOW.dq_out    <hex8>
    G33OP <i> <k> <n> QR_INFLOW.dq_in      <hex8>
    G33OP <i> <k> <n> QR_FALLACC.fall_after<hex8>
    G33OP <i> <k> <n> QR_UPDATE.q_post     <hex8>
"""
import hashlib
import sys

# Pin: the reference module this overlay was derived against. A mismatch means
# the reference changed and the anchors/instrumentation must be re-verified.
CANONICAL_SHA256 = "9354141b9e93aceb4a1c35e06bf673a5d4d916028877c0f84f729a301876b7dc"

# The interior rain (QR) update — a UNIQUE line in the sub-cycle. We insert the
# emission right after it, still inside `if(n.le.mstep(i)) then`, so only active
# substeps dump (mirrors the C++ gate). Fortran k is bottom-up (kts..kte); the
# C++ evidence is top-first, so we emit k = kte - k (kte -> 0).
QR_INTERIOR_ANCHOR = "             qrs(i,k,1) = max(qrs(i,k,1)-dqr(i,k)+dqr(i,k+1),0.)"

_W = "             "  # 13-space body indent, matching the anchor
def _emit(field, expr):
    return (f"{_W}write(*,'(A,3(1X,I0),1X,A,1X,Z8.8)') 'G33OP', i, kte-k, n, "
            f"'{field}', transfer({expr}, 1_4)")

QR_INTERIOR_BLOCK = "\n".join([
    "#ifdef KDM6_G33_FORTRAN_DUMP",
    _emit("QR_FALK.falk_f32",      "falk(i,k,1)"),
    _emit("QR_OUTFLOW.dq_out",     "dqr(i,k)"),
    _emit("QR_INFLOW.dq_in",       "dqr(i,k+1)"),
    _emit("QR_FALLACC.fall_after", "fall(i,k,1)"),
    _emit("QR_UPDATE.q_post",      "qrs(i,k,1)"),
    "#endif",
])

# The interior NUMBER (NR) update — the dz-ONLY number transport (dnr(i,k+1) uses
# delz(k+1)/delz(k), no density), the op the release number-budget blocker lives
# in. Unique line, same 13-space indent.
NR_INTERIOR_ANCHOR = "             nrs(i,k,1) = max(nrs(i,k,1)-dnr(i,k)+dnr(i,k+1),0.)"
NR_INTERIOR_BLOCK = "\n".join([
    "#ifdef KDM6_G33_FORTRAN_DUMP",
    _emit("NR_FALK.falk_f32",      "falkn(i,k,1)"),
    _emit("NR_OUTFLOW.dn_out",     "dnr(i,k)"),
    _emit("NR_INFLOW.dn_in",       "dnr(i,k+1)"),
    _emit("NR_FALLACC.fall_after", "falln(i,k,1)"),
    _emit("NR_UPDATE.n_post",      "nrs(i,k,1)"),
    "#endif",
])


def main():
    src_path, dst_path = sys.argv[1], sys.argv[2]
    raw = open(src_path, "rb").read()
    got = hashlib.sha256(raw).hexdigest()
    if got != CANONICAL_SHA256:
        raise SystemExit(
            f"canonical Fortran SHA {got} != pinned {CANONICAL_SHA256} — the "
            f"reference changed; re-verify anchors and re-pin")
    text = raw.decode("utf-8")

    for name, anchor, block in (
            ("QR interior", QR_INTERIOR_ANCHOR, QR_INTERIOR_BLOCK),
            ("NR interior", NR_INTERIOR_ANCHOR, NR_INTERIOR_BLOCK)):
        if text.count(anchor) != 1:
            raise SystemExit(
                f"{name} anchor count {text.count(anchor)}, expected 1 — "
                f"the sub-cycle changed")
        text = text.replace(anchor, anchor + "\n" + block, 1)

    open(dst_path, "w", encoding="utf-8").write(text)
    print(f"wrote overlay: {dst_path}")


if __name__ == "__main__":
    main()
