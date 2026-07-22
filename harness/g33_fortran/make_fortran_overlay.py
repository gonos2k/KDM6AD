#!/usr/bin/env python3
"""Write a TEMPORARY G3.3-M instrumentation overlay of the reference Fortran.

Protocol §5.1: the canonical Fortran is NEVER edited (frozen). This reads the
canonical `module_mp_kdm6.F`, verifies its SHA against the pin (a drift =
re-derive, fail-loud), inserts `#ifdef KDM6_G33_FORTRAN_DUMP`-guarded op-record
emission at unique anchors in the sedimentation sub-cycle, and writes a
throw-away patched copy. Compiled WITHOUT the macro it is byte-identical
behaviour; WITH it, the sed ladder is dumped to stdout as G33OP lines the
four-case comparator's normalizer reads.

    make_fortran_overlay.py <canonical.F> <out_overlay.F>

The emitted FIELD VOCABULARY is not chosen here — it is DERIVED from the single
authoritative schema `harness/g33_expectation._op_fields(algorithm, role, op_id)`,
the same schema the C++ container and the P4 comparator use. `_FIELD_EXPR` maps
each (role, op_id, field) to the Fortran expression that reproduces that operand
bit-for-bit (all-f32 arithmetic under -ffp-contract=off; f64 for the work1/mstep
chain). `_validate_against_schema()` asserts the emitted field list equals the
schema's, in order — so a schema change fails this generator loudly rather than
silently producing an incomparable dump.

Each emitted line is:
    G33OP <i> <k_topfirst> <n> <op_id>.<field> <dtype> <hex>
where dtype in {f32,f64,u8}; hex is the raw IEEE/int bits (Z8.8 / Z16.16 / Z2.2).
The Fortran k is bottom-up (kts..kte); the C++ evidence is top-first, so we emit
k = kte - k (kte -> 0). Physical emission order is irrelevant: the normalizer
canonicalizes op_seq by sorting on (k, species, op, field).
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import g33_expectation as ge  # noqa: E402

# Pin: the reference module this overlay was derived against. A mismatch means
# the reference changed and the anchors/instrumentation must be re-verified.
CANONICAL_SHA256 = "9354141b9e93aceb4a1c35e06bf673a5d4d916028877c0f84f729a301876b7dc"
ALGORITHM = "legacy"

# ── field -> Fortran expression, per (cell_role, op_id) ───────────────────────
# Faithful to the C++ overlay (harness/g33_overlay/sedimentation.cpp.overlay):
# same rung decomposition, same left-to-right f32 order. Fortran cell-above index
# is k+1 (bottom-up) where the C++ top-first index is k-1. u8 entries carry the
# BOOLEAN condition the overlay emits ((pre_cap > reservoir), (preclamp < 0)) —
# matching the actual overlay, not the 4-state enum the schema comment aspires to.
# `g33_fqb`/`g33_fnb` are the fall/falln values captured at cell entry (temps).
_INT = {  # INTERIOR (and BOTTOM — same op set; the emitted k distinguishes them)
    "QR_FALK": [
        ("mul_dend_q", "f32", "dend(i,k)*qrs(i,k,1)"),
        ("mul_work1", "f64", "dend(i,k)*qrs(i,k,1)*work1(i,k,1)"),
        ("div_mstep", "f64", "dend(i,k)*qrs(i,k,1)*work1(i,k,1)/mstep(i)"),
        ("falk_precast", "f64", "dend(i,k)*qrs(i,k,1)*work1(i,k,1)/mstep(i)"),
        ("shadow_falk_f32", "f32", "real(dend(i,k)*qrs(i,k,1)*work1(i,k,1)/mstep(i),4)"),
        ("falk_f32", "f32", "falk(i,k,1)"),
    ],
    "QR_OUTFLOW": [
        ("mul_dt", "f32", "falk(i,k,1)*dtcld"),
        ("outflow_pre_cap", "f32", "falk(i,k,1)*dtcld/dend(i,k)"),
        ("source_reservoir", "f32", "qrs(i,k,1)"),
        ("cap_active", "u8", "falk(i,k,1)*dtcld/dend(i,k) > qrs(i,k,1)"),
        ("dq_out", "f32", "dqr(i,k)"),
    ],
    "QR_FALLACC": [
        ("fall_before", "f32", "g33_fqb"),
        ("fall_increment", "f32", "falk(i,k,1)"),
        ("fall_after", "f32", "fall(i,k,1)"),
    ],
    "QR_INFLOW": [
        ("stored_falk_prev", "f32", "falk(i,k+1,1)"),
        ("delz_raw_src", "f32", "delz(i,k+1)"),
        ("delz_safe_dst", "f32", "delz(i,k)"),
        ("dend_safe_dst", "f32", "dend(i,k)"),
        ("mul_delz_src", "f32", "falk(i,k+1,1)*delz(i,k+1)"),
        ("div_delz_dst", "f32", "falk(i,k+1,1)*delz(i,k+1)/delz(i,k)"),
        ("mul_dt", "f32", "falk(i,k+1,1)*delz(i,k+1)/delz(i,k)*dtcld"),
        ("inflow_pre_cap", "f32", "falk(i,k+1,1)*delz(i,k+1)/delz(i,k)*dtcld/dend(i,k)"),
        ("source_reservoir", "f32", "qrs(i,k+1,1)"),
        ("inflow_cap_active", "u8",
         "falk(i,k+1,1)*delz(i,k+1)/delz(i,k)*dtcld/dend(i,k) > qrs(i,k+1,1)"),
        ("inflow_final", "f32", "dqr(i,k+1)"),
    ],
    "QR_UPDATE": [
        ("q_before", "f32", "qrs(i,k,1)"),
        ("q_minus_out", "f32", "qrs(i,k,1)-dqr(i,k)"),
        ("q_plus_in_preclamp", "f32", "qrs(i,k,1)-dqr(i,k)+dqr(i,k+1)"),
        ("clamp_active", "u8", "(qrs(i,k,1)-dqr(i,k)+dqr(i,k+1)) < 0."),
        ("q_post", "f32", "max(qrs(i,k,1)-dqr(i,k)+dqr(i,k+1),0.)"),
    ],
    "NR_FALK": [
        ("mul_workn", "f64", "nrs(i,k,1)*workn(i,k,1)"),
        ("div_mstep", "f64", "nrs(i,k,1)*workn(i,k,1)/mstep(i)"),
        ("falk_precast", "f64", "nrs(i,k,1)*workn(i,k,1)/mstep(i)"),
        ("shadow_falk_f32", "f32", "real(nrs(i,k,1)*workn(i,k,1)/mstep(i),4)"),
        ("falk_f32", "f32", "falkn(i,k,1)"),
    ],
    "NR_OUTFLOW": [
        ("outflow_pre_cap", "f32", "falkn(i,k,1)*dtcld"),
        ("source_reservoir", "f32", "nrs(i,k,1)"),
        ("cap_active", "u8", "falkn(i,k,1)*dtcld > nrs(i,k,1)"),
        ("dn_out", "f32", "dnr(i,k)"),
    ],
    "NR_FALLACC": [
        ("fall_before", "f32", "g33_fnb"),
        ("fall_increment", "f32", "falkn(i,k,1)"),
        ("fall_after", "f32", "falln(i,k,1)"),
    ],
    "NR_INFLOW": [
        ("stored_falk_nr_prev", "f32", "falkn(i,k+1,1)"),
        ("delz_raw_src", "f32", "delz(i,k+1)"),
        ("delz_safe_dst", "f32", "delz(i,k)"),
        ("mul_delz_src", "f32", "falkn(i,k+1,1)*delz(i,k+1)"),
        ("div_delz_dst", "f32", "falkn(i,k+1,1)*delz(i,k+1)/delz(i,k)"),
        ("inflow_pre_cap", "f32", "falkn(i,k+1,1)*delz(i,k+1)/delz(i,k)*dtcld"),
        ("source_reservoir", "f32", "nrs(i,k+1,1)"),
        ("inflow_cap_active", "u8",
         "falkn(i,k+1,1)*delz(i,k+1)/delz(i,k)*dtcld > nrs(i,k+1,1)"),
        ("inflow_final", "f32", "dnr(i,k+1)"),
    ],
    "NR_UPDATE": [
        ("n_before", "f32", "nrs(i,k,1)"),
        ("n_minus_out", "f32", "nrs(i,k,1)-dnr(i,k)"),
        ("n_plus_in_preclamp", "f32", "nrs(i,k,1)-dnr(i,k)+dnr(i,k+1)"),
        ("clamp_active", "u8", "(nrs(i,k,1)-dnr(i,k)+dnr(i,k+1)) < 0."),
        ("n_post", "f32", "max(nrs(i,k,1)-dnr(i,k)+dnr(i,k+1),0.)"),
    ],
}
# TOP: legacy clamps directly (no separate OUTFLOW/INFLOW rung — the positivity
# clamp IS the update). FALK is identical to interior.
_TOP = {
    "QR_FALK": _INT["QR_FALK"],
    "QR_FALLACC": _INT["QR_FALLACC"],
    "QR_UPDATE": [
        ("q_before", "f32", "qrs(i,k,1)"),
        ("q_minus_out", "f32", "qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k)"),
        ("clamp_active", "u8", "(qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k)) < 0."),
        ("q_post", "f32", "max(qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k),0.)"),
    ],
    "NR_FALK": _INT["NR_FALK"],
    "NR_FALLACC": _INT["NR_FALLACC"],
    "NR_UPDATE": [
        ("n_before", "f32", "nrs(i,k,1)"),
        ("n_minus_out", "f32", "nrs(i,k,1)-falkn(i,k,1)*dtcld"),
        ("clamp_active", "u8", "(nrs(i,k,1)-falkn(i,k,1)*dtcld) < 0."),
        ("n_post", "f32", "max(nrs(i,k,1)-falkn(i,k,1)*dtcld,0.)"),
    ],
}
_FIELD_EXPR = {"INTERIOR": _INT, "TOP": _TOP}

_EMIT = {  # dtype -> (value expr wrapping the operand, Z format width)
    "f32": ("transfer({e}, 0)",   "Z8.8"),
    "f64": ("transfer({e}, 0_8)", "Z16.16"),
    "u8":  ("merge(1, 0, {e})",   "Z2.2"),
}
_IND = "             "  # 13-space body indent


def _validate_against_schema():
    """Emitted field list MUST equal ge._op_fields(...), in order, for every
    (role, species, op) in scope — ties this overlay to the one schema."""
    for role in ("TOP", "INTERIOR"):
        for species in ("qr", "nr"):
            for op_id in ge._ops_for_species(ALGORITHM, role, species):
                want = [f for f, _ in ge._op_fields(ALGORITHM, role, op_id)]
                got = [f for f, _, _ in _FIELD_EXPR[role][op_id]]
                if got != want:
                    raise SystemExit(
                        f"schema drift: {role}/{op_id} overlay fields {got} != "
                        f"g33_expectation {want}")


def _emit_block(role):
    """The op-emission block for a cell role (top-first k = kte-k)."""
    lines = ["#ifdef KDM6_G33_FORTRAN_DUMP"]
    for species in ("qr", "nr"):
        for op_id in ge._ops_for_species(ALGORITHM, role, species):
            for field, dtype, expr in _FIELD_EXPR[role][op_id]:
                val, zf = _EMIT[dtype]
                lines.append(
                    f"{_IND}write(*,'(A,3(1X,I0),1X,A,1X,A,1X,{zf})') "
                    f"'G33OP', i, kte-k, n, '{op_id}.{field}', '{dtype}', "
                    f"{val.format(e=expr)}")
    lines.append("#endif")
    return "\n".join(lines)


# ── anchors (exact text; each is asserted to occur EXACTLY once) ──────────────
# Declarations for the entry-capture temps (fall/falln before this substep's add).
_DECL_ANCHOR = "   real, dimension(its:ite,kts:kte,4) :: falk, fall"
_DECL_BLOCK = "\n".join([
    "#ifdef KDM6_G33_FORTRAN_DUMP",
    "   real :: g33_fqb, g33_fnb   ! G3.3-M: fall/falln captured at cell entry",
    "#endif",
])
_CAP_BLOCK = "\n".join([
    "#ifdef KDM6_G33_FORTRAN_DUMP",
    f"{_IND}g33_fqb = fall(i,k,1)",
    f"{_IND}g33_fnb = falln(i,k,1)",
    "#endif",
])
# TOP capture: after the top-cell guard (k=kte, before the fall accumulation).
_TOP_CAP_ANCHOR = ("      do n = 1, mstepmax\n        k = kte\n"
                   "        do i = its, ite\n         if(n.le.mstep(i)) then")
# INTERIOR capture: after the interior-loop guard (mstep, not mstep_i — the ice
# loop's guard reads mstep_i, so this three-line block is unique to the main loop).
_INT_CAP_ANCHOR = ("       do k = kte_in-1,kts,-1\n         do i = its,ite\n"
                   "           if(n.le.mstep(i)) then")
# TOP emission: before the top qr positivity clamp (state still at cell entry).
_TOP_EMIT_ANCHOR = "           qrs(i,k,1) = max(qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k),0.)"
# INTERIOR emission: before the interior nr update (qrs/nrs both still pre-update,
# every dqr/dnr/falk/fall already assigned for this cell).
_INT_EMIT_ANCHOR = "             nrs(i,k,1) = max(nrs(i,k,1)-dnr(i,k)+dnr(i,k+1),0.)"


def main():
    _validate_against_schema()
    src_path, dst_path = sys.argv[1], sys.argv[2]
    raw = open(src_path, "rb").read()
    got = hashlib.sha256(raw).hexdigest()
    if got != CANONICAL_SHA256:
        raise SystemExit(
            f"canonical Fortran SHA {got} != pinned {CANONICAL_SHA256} — the "
            f"reference changed; re-verify anchors and re-pin")
    text = raw.decode("utf-8")

    # (anchor, insert_before?, block) — insert_before True puts the block ahead of
    # the anchor line (needed when the anchor line consumes the pre-update state).
    edits = [
        (_DECL_ANCHOR, False, _DECL_BLOCK),
        (_TOP_CAP_ANCHOR, False, _CAP_BLOCK),
        (_INT_CAP_ANCHOR, False, _CAP_BLOCK),
        (_TOP_EMIT_ANCHOR, True, _emit_block("TOP")),
        (_INT_EMIT_ANCHOR, True, _emit_block("INTERIOR")),
    ]
    for anchor, before, block in edits:
        if text.count(anchor) != 1:
            raise SystemExit(
                f"anchor count {text.count(anchor)}, expected 1 — the source "
                f"changed near:\n{anchor.splitlines()[0]}")
        repl = (block + "\n" + anchor) if before else (anchor + "\n" + block)
        text = text.replace(anchor, repl, 1)

    open(dst_path, "w", encoding="utf-8").write(text)
    print(f"wrote overlay: {dst_path}")


if __name__ == "__main__":
    main()
