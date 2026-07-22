#!/usr/bin/env python3
"""Fortran bindings for the G3.3-M overlay: for each schema (role, op_id, field),
the Fortran expression that captures that operand bit-for-bit, plus the canonical
source anchors and SHA pins per variant.

This is the ONLY place that knows the reference source's variable names and line
anchors. The field VOCABULARY is not decided here — `make_fortran_overlay.py`
validates every binding against the public schema (`g33_schema.op_fields`), so a
binding that names a field the schema does not have (or omits one it does) fails
loudly. Expressions are faithful to the C++ overlays
(harness/g33_overlay/sedimentation{,_conservative}.cpp.overlay): same rung
decomposition, same left-to-right f32 order; the Fortran cell-above index is k+1
(bottom-up) where the C++ top-first index is k-1.

Each binding is (field, dtype, expr). For u8, `expr` is the BOOLEAN condition the
C++ producer emits ((pre_cap > reservoir), (preclamp < 0)); the comparator
derives the authoritative branch state independently from the two operands.
`g33_fqb`/`g33_fnb` are fall/falln captured into scratch temps at cell entry.
"""

# ── shared rungs (identical in both variants) ─────────────────────────────────
QR_FALK = [
    ("mul_dend_q", "f32", "dend(i,k)*qrs(i,k,1)"),
    ("mul_work1", "f64", "dend(i,k)*qrs(i,k,1)*work1(i,k,1)"),
    ("div_mstep", "f64", "dend(i,k)*qrs(i,k,1)*work1(i,k,1)/mstep(i)"),
    ("falk_precast", "f64", "dend(i,k)*qrs(i,k,1)*work1(i,k,1)/mstep(i)"),
    ("shadow_falk_f32", "f32", "real(dend(i,k)*qrs(i,k,1)*work1(i,k,1)/mstep(i),4)"),
    ("falk_f32", "f32", "falk(i,k,1)"),
]
QR_OUTFLOW = [
    ("mul_dt", "f32", "falk(i,k,1)*dtcld"),
    ("outflow_pre_cap", "f32", "falk(i,k,1)*dtcld/dend(i,k)"),
    ("source_reservoir", "f32", "qrs(i,k,1)"),
    ("cap_active", "u8", "falk(i,k,1)*dtcld/dend(i,k) > qrs(i,k,1)"),
    ("dq_out", "f32", "dqr(i,k)"),
]
NR_FALK = [
    ("mul_workn", "f64", "nrs(i,k,1)*workn(i,k,1)"),
    ("div_mstep", "f64", "nrs(i,k,1)*workn(i,k,1)/mstep(i)"),
    ("falk_precast", "f64", "nrs(i,k,1)*workn(i,k,1)/mstep(i)"),
    ("shadow_falk_f32", "f32", "real(nrs(i,k,1)*workn(i,k,1)/mstep(i),4)"),
    ("falk_f32", "f32", "falkn(i,k,1)"),
]
NR_OUTFLOW = [
    ("outflow_pre_cap", "f32", "falkn(i,k,1)*dtcld"),
    ("source_reservoir", "f32", "nrs(i,k,1)"),
    ("cap_active", "u8", "falkn(i,k,1)*dtcld > nrs(i,k,1)"),
    ("dn_out", "f32", "dnr(i,k)"),
]

# ── LEGACY: min-capped Δz-only inflow, raw-falk accumulator, positivity clamp ──
_LEG_INT = {
    "QR_FALK": QR_FALK, "QR_OUTFLOW": QR_OUTFLOW,
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
        ("q_post", "f32", "qrs(i,k,1)"),
    ],
    "NR_FALK": NR_FALK, "NR_OUTFLOW": NR_OUTFLOW,
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
        ("n_post", "f32", "nrs(i,k,1)"),
    ],
}
_LEG_TOP = {   # legacy TOP clamps directly: no OUTFLOW/INFLOW rung
    "QR_FALK": QR_FALK,
    "QR_FALLACC": _LEG_INT["QR_FALLACC"],
    "QR_UPDATE": [
        ("q_before", "f32", "qrs(i,k,1)"),
        ("q_minus_out", "f32", "qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k)"),
        ("clamp_active", "u8", "(qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k)) < 0."),
        ("q_post", "f32", "qrs(i,k,1)"),
    ],
    "NR_FALK": NR_FALK,
    "NR_FALLACC": _LEG_INT["NR_FALLACC"],
    "NR_UPDATE": [
        ("n_before", "f32", "nrs(i,k,1)"),
        ("n_minus_out", "f32", "nrs(i,k,1)-falkn(i,k,1)*dtcld"),
        ("clamp_active", "u8", "(nrs(i,k,1)-falkn(i,k,1)*dtcld) < 0."),
        ("n_post", "f32", "nrs(i,k,1)"),
    ],
}

# ── CONSERVATIVE: ρΔz inflow (numbers dz-only), actual-outflow-rate accumulator,
#    NO positivity clamp. src_metric/dst_metric are the source's own variables. ──
_CON_INT = {
    "QR_FALK": QR_FALK, "QR_OUTFLOW": QR_OUTFLOW,
    "QR_FALLACC": [
        ("fall_before", "f32", "g33_fqb"),
        ("dq_out", "f32", "dqr(i,k)"),
        ("mul_dend_safe", "f32", "dqr(i,k)*dend(i,k)"),
        ("fall_increment", "f32", "dqr(i,k)*dend(i,k)/dtcld"),
        ("fall_after", "f32", "fall(i,k,1)"),
    ],
    "QR_INFLOW": [
        ("prev_out", "f32", "dqr(i,k+1)"),
        ("dend_safe_src", "f32", "dend(i,k+1)"),
        ("delz_raw_src", "f32", "delz(i,k+1)"),
        ("dend_safe_dst", "f32", "dend(i,k)"),
        ("delz_safe_dst", "f32", "delz(i,k)"),
        ("src_metric", "f32", "src_metric"),
        ("dst_metric", "f32", "dst_metric"),
        ("mul_src", "f32", "dqr(i,k+1)*src_metric"),
        ("inflow_final", "f32", "dqr(i,k+1)*src_metric/dst_metric"),
    ],
    "QR_UPDATE": [   # conservative: NO positivity clamp
        ("q_before", "f32", "qrs(i,k,1)"),
        ("q_minus_out", "f32", "qrs(i,k,1)-dqr(i,k)"),
        ("q_plus_in_preclamp", "f32", "qrs(i,k,1)-dqr(i,k)+dqr(i,k+1)*src_metric/dst_metric"),
        ("q_post", "f32", "qrs(i,k,1)"),
    ],
    "NR_FALK": NR_FALK, "NR_OUTFLOW": NR_OUTFLOW,
    "NR_FALLACC": [
        ("fall_before", "f32", "g33_fnb"),
        ("dn_out", "f32", "dnr(i,k)"),
        ("fall_increment", "f32", "dnr(i,k)/dtcld"),
        ("fall_after", "f32", "falln(i,k,1)"),
    ],
    "NR_INFLOW": [   # numbers: dz-only, no dtcld, no cap
        ("prev_out_nr", "f32", "dnr(i,k+1)"),
        ("delz_raw_src", "f32", "delz(i,k+1)"),
        ("delz_safe_dst", "f32", "delz(i,k)"),
        ("mul_delz_src", "f32", "dnr(i,k+1)*delz(i,k+1)"),
        ("inflow_final", "f32", "dnr(i,k+1)*delz(i,k+1)/delz(i,k)"),
    ],
    "NR_UPDATE": [
        ("n_before", "f32", "nrs(i,k,1)"),
        ("n_minus_out", "f32", "nrs(i,k,1)-dnr(i,k)"),
        ("n_plus_in_preclamp", "f32", "nrs(i,k,1)-dnr(i,k)+dnr(i,k+1)*delz(i,k+1)/delz(i,k)"),
        ("n_post", "f32", "nrs(i,k,1)"),
    ],
}
_CON_TOP = {   # conservative TOP DOES compute an outflow; no inflow, no clamp
    "QR_FALK": QR_FALK, "QR_OUTFLOW": QR_OUTFLOW,
    "QR_FALLACC": _CON_INT["QR_FALLACC"],
    "QR_UPDATE": [
        ("q_before", "f32", "qrs(i,k,1)"),
        ("q_minus_out", "f32", "qrs(i,k,1)-dqr(i,k)"),
        ("q_post", "f32", "qrs(i,k,1)"),
    ],
    "NR_FALK": NR_FALK, "NR_OUTFLOW": NR_OUTFLOW,
    "NR_FALLACC": _CON_INT["NR_FALLACC"],
    "NR_UPDATE": [
        ("n_before", "f32", "nrs(i,k,1)"),
        ("n_minus_out", "f32", "nrs(i,k,1)-dnr(i,k)"),
        ("n_post", "f32", "nrs(i,k,1)"),
    ],
}

FIELD_EXPR = {
    "legacy": {"INTERIOR": _LEG_INT, "TOP": _LEG_TOP},
    "conservative": {"INTERIOR": _CON_INT, "TOP": _CON_TOP},
}

# q_post/n_post are the ACTUAL stored qrs/nrs — emitted by the generator's POST
# phase AFTER the update statement completes (all other fields are pre-update).
# This makes the offline replay a real check: recomputing q_post from the dumped
# operands and matching the STORED value proves the actual update used them; a
# recompute would match its own operands vacuously.
POST_FIELDS = ("q_post", "n_post")

# Scratch temps declared once (fall/falln captured at cell entry) + the capture.
DECL_ANCHOR = "   real, dimension(its:ite,kts:kte,4) :: falk, fall"
DECL_BLOCK = [
    "#ifdef KDM6_G33_FORTRAN_DUMP",
    "   real :: g33_fqb, g33_fnb   ! G3.3-M: fall/falln captured at cell entry",
    "#endif",
]
IND = "             "  # 13-space body indent
CAP_BLOCK = [
    "#ifdef KDM6_G33_FORTRAN_DUMP",
    f"{IND}g33_fqb = fall(i,k,1)",
    f"{IND}g33_fnb = falln(i,k,1)",
    "#endif",
]

# Per-variant SHA pin + WHOLE-LINE anchors (matched as complete lines, so the
# 11-space vs 13-space update forms are distinct and unique). Emission is PER
# SPECIES: the conservative source runs the qr chain (incl. its update) before
# the nr chain, so no single anchor sees both species pre-update. The capture
# anchors are the substep guards (top: 9-space `if`, interior: 11-space `if`).
VARIANTS = {
    "legacy": {
        "sha": "9354141b9e93aceb4a1c35e06bf673a5d4d916028877c0f84f729a301876b7dc",
        "cap_top": "         if(n.le.mstep(i)) then",
        "cap_int": "           if(n.le.mstep(i)) then",
        "emit": {
            ("TOP", "qr"): "           qrs(i,k,1) = max(qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k),0.)",
            ("TOP", "nr"): "           nrs(i,k,1) = max(nrs(i,k,1)-falkn(i,k,1)*dtcld,0.)",
            ("INTERIOR", "qr"): "             qrs(i,k,1) = max(qrs(i,k,1)-dqr(i,k)+dqr(i,k+1),0.)",
            ("INTERIOR", "nr"): "             nrs(i,k,1) = max(nrs(i,k,1)-dnr(i,k)+dnr(i,k+1),0.)",
        },
        # q_post/n_post emitted AFTER the update line (legacy updates are single
        # lines, so the post anchor is the update line itself).
        "post": {
            ("TOP", "qr"): "           qrs(i,k,1) = max(qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k),0.)",
            ("TOP", "nr"): "           nrs(i,k,1) = max(nrs(i,k,1)-falkn(i,k,1)*dtcld,0.)",
            ("INTERIOR", "qr"): "             qrs(i,k,1) = max(qrs(i,k,1)-dqr(i,k)+dqr(i,k+1),0.)",
            ("INTERIOR", "nr"): "             nrs(i,k,1) = max(nrs(i,k,1)-dnr(i,k)+dnr(i,k+1),0.)",
        },
    },
    "conservative": {
        "sha": "364a1319d0099bdb474a752a2a017defaf008babbe85dd03da872c603b2e7e3e",
        "cap_top": "         if(n.le.mstep(i)) then",
        "cap_int": "           if(n.le.mstep(i)) then",
        "emit": {
            ("TOP", "qr"): "           qrs(i,k,1) = qrs(i,k,1)-dqr(i,k)",
            ("TOP", "nr"): "           nrs(i,k,1) = nrs(i,k,1)-dnr(i,k)",
            ("INTERIOR", "qr"):
                "             qrs(i,k,1) = qrs(i,k,1)-dqr(i,k)                                  &",
            ("INTERIOR", "nr"):
                "             nrs(i,k,1) = nrs(i,k,1)-dnr(i,k)                                  &",
        },
        # conservative TOP updates are single lines (post anchor = update line);
        # INTERIOR updates are two-line continued statements, so q_post/n_post go
        # AFTER the continuation line (inserting between the two would be a syntax
        # error — the statement is not yet complete).
        "post": {
            ("TOP", "qr"): "           qrs(i,k,1) = qrs(i,k,1)-dqr(i,k)",
            ("TOP", "nr"): "           nrs(i,k,1) = nrs(i,k,1)-dnr(i,k)",
            ("INTERIOR", "qr"): "                          +dqr(i,k+1)*src_metric/dst_metric",
            ("INTERIOR", "nr"): "                          +dnr(i,k+1)*delz(i,k+1)/delz(i,k)",
        },
    },
}
