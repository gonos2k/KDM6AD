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

`dtype` is the SEMANTIC width -- what the field means, and what the C++ mirror
declares. It is NOT how many bytes the build gives it; `storage_class` below is,
and the two only agree at the reference precision.
"""
import re
import g33_arms

#: What a narrowing cast LOOKS like. Kept only as a cross-check on the
#: declarations below -- it must never be the thing that decides, because the
#: forms it does not match are exactly the ones that would be misclassified:
#: `real(expr, kind=4)`, `real(expr, real32)`, a `real(kind=real32)` temporary.
_LOOKS_PINNED = re.compile(r"^real\(.*,\s*4\)$")

#: Bindings whose expression PINS its own storage width, DECLARED.
#:
#: `real(<expr>,4)` is an explicit KIND, so -fdefault-real-8 does not widen it,
#: and the semantic dtype cannot say so: the field is semantically f32 either
#: way. Which bindings those are is now a STATEMENT rather than an inference
#: from the expression text (owner priority 6).
#:
#: Keyed by the expression, because the expression is what decides. Two rungs
#: sharing a field name take the same class only if they compute the same thing.
STORAGE_OVERRIDES = {
    "real(dend(i,k)*qrs(i,k,1)*work1(i,k,1)/mstep(i),4)": "real32",
    "real(nrs(i,k,1)*workn(i,k,1)/mstep(i),4)": "real32",
}

#: Any Fortran construct that can change a value's KIND. An expression carrying
#: one and NOT declared above is refused rather than assumed to be a default
#: real -- which is the whole point: the risk was never the two casts already
#: here, it was the next binding written in a form the pattern does not match.
#: Measured over the whole table: exactly two expressions carry one, and both
#: are declared.
_CONVERSION = re.compile(r"\b(real|dble|dfloat|int|nint|cmplx|kind)\s*[(=]",
                         re.I)

#: semantic dtype -> storage class, where the two cannot diverge. `f64` is
#: `double precision`, which -fdefault-double-8 holds at eight bytes in BOTH
#: builds; integers and logicals are not promoted at all.
_FIXED_CLASS = {"f64": "real64", "i32": "int32", "u8": "logical"}

#: Every class `storage_class` can return. Enumerated so a caller can map the
#: whole vocabulary rather than the cases it happened to think of.
STORAGE_CLASSES = frozenset({"default_real", "real32", "real64", "int32",
                             "logical"})


def storage_class(dtype: str, expr: str) -> str:
    """How many bytes the BUILD gives this binding, as a class rather than a
    width -- because `default_real` has no width until a build says so.

    This is the whole of D6 applied to the op ladder. A schema-f32 field is a
    DEFAULT REAL in almost every binding, so under -fdefault-real-8 it is eight
    bytes; `shadow_falk_f32` is the exception, and it is an exception in the
    other direction -- an explicit `real(...,4)` that stays four bytes in an
    f64 build. One label was carrying both jobs, so a blanket promotion and a
    blanket non-promotion are each wrong for one of them.

    FAIL-CLOSED on the forms it cannot read. Deciding this by matching
    `real(...,4)` worked on the table as written and would have silently called
    `real(expr, kind=4)` a default real -- the same value, spelled the way the
    standard also allows. So an expression carrying ANY kind-conversion
    construct must be declared in `STORAGE_OVERRIDES`, and one that is not is
    refused. Everything else is a default real, which is a rule about the
    absence of a construct rather than about the presence of a pattern.

    Refuses a dtype it does not know for the same reason: a new dtype would
    otherwise land silently on whichever branch is written last.
    """
    if dtype in _FIXED_CLASS:
        return _FIXED_CLASS[dtype]
    if dtype != "f32":
        raise KeyError(f"no storage class for dtype {dtype!r} ({expr!r})")
    e = expr.strip()
    if e in STORAGE_OVERRIDES:
        return STORAGE_OVERRIDES[e]
    if _CONVERSION.search(e):
        raise KeyError(
            f"{e!r} carries a kind-conversion construct, so its storage width "
            f"is not the build's default real and cannot be inferred from the "
            f"text -- declare it in STORAGE_OVERRIDES")
    return "default_real"


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
    # `nmass` IS legacy with two lines changed, and neither is an anchor: the
    # instrumentation keys on the UPDATE lines, and the emitted expression is
    # `dnr(i,k+1)` itself -- whose value the arm changes and whose spelling it
    # does not. So the ladder is legacy's, and only the SHA differs.
    "nmass": {"INTERIOR": _LEG_INT, "TOP": _LEG_TOP},
    "nmass_dry": {"INTERIOR": _LEG_INT, "TOP": _LEG_TOP},
    "nmass_dry_window": {"INTERIOR": _LEG_INT, "TOP": _LEG_TOP},

    # ARM L changes no transfer line at all -- only which threshold each
    # column is compared against -- so the sedimentation ladder is legacy's
    # unchanged.
    "lncmin": {"INTERIOR": _LEG_INT, "TOP": _LEG_TOP},
    "nmasslncmin": {"INTERIOR": _LEG_INT, "TOP": _LEG_TOP},
    "cons_nmass": {"INTERIOR": _CON_INT, "TOP": _CON_TOP},
    "cons_lncmin": {"INTERIOR": _CON_INT, "TOP": _CON_TOP},
    "cons_nmasslncmin": {"INTERIOR": _CON_INT, "TOP": _CON_TOP},
    "conservative": {"INTERIOR": _CON_INT, "TOP": _CON_TOP},
}


def all_bindings() -> list:
    """Every (field, dtype, expr) triple this module declares, wherever it lives.

    SCANNED, not listed. The op ladder is validated against the schema by name,
    but the twenty-odd STAGE lists are not -- so a list added here and left out
    of a validation list would be exactly the one whose storage class nobody
    ever asked for. The shape IS the filter: a list of 3-string tuples is a
    binding table and nothing else in this module is one.
    """
    out = []
    for name, v in sorted(globals().items()):
        if (isinstance(v, list) and v
                and all(isinstance(t, tuple) and len(t) == 3
                        and all(isinstance(x, str) for x in t) for t in v)):
            out += [(name, *t) for t in v]
    for algo, roles in FIELD_EXPR.items():
        for role, ops in roles.items():
            for op_id, rungs in ops.items():
                out += [(f"{algo}/{role}/{op_id}", *t) for t in rungs]
    return out

# q_post/n_post are the ACTUAL stored qrs/nrs — emitted by the generator's POST
# phase AFTER the update statement completes (all other fields are pre-update).
# This makes the offline replay a real check: recomputing q_post from the dumped
# operands and matching the STORED value proves the actual update used them; a
# recompute would match its own operands vacuously.
POST_FIELDS = ("q_post", "n_post")

# ── pre-sed STAGE snapshots (owner P0-7): so the comparator can tell a divergence
# BORN in sedimentation from one already present at sed entry / in the fall-speed
# + gating chain. Emitted as injected whole-K loops (variant-independent — the
# sed-entry variables are the same in both). Fortran has NO density/thickness
# floor, so dend_raw==dend_safe and delz_raw==delz_safe; qcrmin has no Fortran
# counterpart in kdm62D and is intentionally omitted.
STAGE_ANCHOR = "      do n = 1, mstepmax"
SUBSTEP_PRE_K = [   # whole-K, per substep n
    ("qr", "f32", "qrs(i,k,1)"), ("nr", "f32", "nrs(i,k,1)"),
    ("work1_qr", "f64", "work1(i,k,1)"), ("workn_qr", "f64", "workn(i,k,1)"),
    ("dend_safe", "f32", "dend(i,k)"), ("delz_safe", "f32", "delz(i,k)"),
]
SUBSTEP_PRE_COL = [  # per-column scalar (k=-1), per substep n
    ("mstep", "i32", "mstep(i)"), ("gate", "u8", "n.le.mstep(i)"),
    ("dtcld", "f32", "dtcld"),
]

# ── outer-loop CAUSAL BRIDGE (owner P0-C1). outer_pre_sed alone shows the state at
# each loop's sedimentation entry but nothing links loop L's exit to loop L+1's
# entry, so a divergence appearing at loop 2's outer_pre_sed had no attributable
# origin: it could have been born in loop 1's sedimentation, in the microphysics
# that follows it, or in the carry between them. These two snapshots close that.
#
#   outer_post_sed    end of the ice chain — the sedimentation result
#   outer_post_micro  end of the outer loop body — what loop L+1 starts from
#
# and the semantics check requires outer_post_micro(L) == outer_pre_sed(L+1)
# bit-for-bit, so the carry itself is evidence rather than an assumption.
#
# Species indices are read from kdm62D's own pack (module_mp_kdm6.F:380-384 and
# module_mp_kdm6_cons.F:400-404 — identical in both), not from WRF convention:
#   qc = qci(:,:,1)  qi   = qci(:,:,2)  qr  = qrs(:,:,1)
#   qs = qrs(:,:,2)  qg   = qrs(:,:,3)  nr  = nrs(:,:,1)
#   nc = nci(:,:,1)  ni   = nci(:,:,2)  nccn = nci(:,:,3)   (packed from `nn`)
#   brs = brs(i,k)   -- 2-D, packed from `bg`; the C++ state calls it brs
#: THE kdm6init-DERIVED CONSTANTS (owner P0-1.1, the `I_F = I_C` condition).
#:
#: `kdm6init` builds these module-level values and kdm62D reads them, so two legs can
#: agree on every call ARGUMENT and still be solving different problems. The C++ port
#: reproduces the same block f32-stepwise on purpose (fconst.h, struct F32Consts) because
#: a double-then-demote differs by 1 ULP — measured as the step-45 divergence seed — and
#: nothing had ever compared that reproduction against the actual Fortran values.
#:
#: Carried as a STAGE rather than as its own record class, so the four-case comparator
#: does the cross-tree comparison with the machinery it already has. A second channel
#: would be a second path to disagree on.
#:
#: Emitted from INSIDE the module, where they are in scope and initialized; the driver
#: cannot see them.
#: `ele2` is deliberately EXCLUDED. fconst.h groups it with the F32Consts family for
#: convenience, but in the Fortran it is not a kdm6init product at all — it is computed
#: inside kdm62D at :1601, well after this injection point, so recording it here reads
#: zero on the Fortran side and the real value on the C++ side. Measured: 0x00000000.
#: That is a difference in WHEN, not in WHAT, and including it would manufacture a
#: divergence out of the instrumentation.
INIT_CONSTANTS = [
    ("pi", "f32", "pi"),
    ("cmc", "f32", "cmc"),
    ("cmr", "f32", "cmr"),
    ("cmi", "f32", "cmi"),
    ("g1pmc", "f32", "g1pmc"),
    ("g3pmc", "f32", "g3pmc"),
    ("g4pmc", "f32", "g4pmc"),
    ("g6pmc", "f32", "g6pmc"),
    ("g1pmr", "f32", "g1pmr"),
    ("g2pmr", "f32", "g2pmr"),
    ("g4pmr", "f32", "g4pmr"),
    ("g7pmr", "f32", "g7pmr"),
    ("g1pdrmr", "f32", "g1pdrmr"),
    ("g1pmi", "f32", "g1pmi"),
    ("g4pmi", "f32", "g4pmi"),
    ("g1pdimi", "f32", "g1pdimi"),
    ("pidnc", "f32", "pidnc"),
    ("pidnr", "f32", "pidnr"),
    ("pidni", "f32", "pidni"),
    ("pidn0s", "f32", "pidn0s"),
]

#: WHAT THE MICROPHYSICS IS HANDED besides the 12 prognostics (owner P0-1.3).
#:
#: Recorded immediately after ProgB_param (:1504) and its first consumer slope_kdm6
#: (:1509), which takes the bundle intent(in).
#: The 5th of the seven identical `slope_kdm6` continuation lines (:1714), which follows
#: the POST-FREEZE ProgB_param at :1707 — the LAST one before the rate loop.
#:
#: My first version anchored on the 4th (:1511), after the POST-MELT ProgB at :1504. That
#: is a different point in the chain and not what the rates read, so the stage would have
#: compared a mid-chain bundle against the C++ side and any difference would have been an
#: artifact of the placement. Determined from the pinned source, NOT from the C++
#: comments, which cite :1469 and :1664 — neither is a ProgB_param call in the pinned
#: file, so those line numbers are from another revision:
#:
#:   :1440   fort_substep_postmelt.bin opens   -> the :1504 ProgB is POST-MELT
#:   :1594-1651  pinuc / pinui / pgfrz         -> the :1707 ProgB is POST-FREEZE
#:   :1864   praut                             -> the rate loop starts, reading :1707's
#:
#: slope_kdm6 takes pidn0g/pvtg/bvtg/rslopegbmax as intent(in), so recording just after
#: it is the same values — and it is OUTSIDE the do-loops, which the nearby unique
#: `! pihmf:` comment is not (a whole-K emission there nests i and k).
#: idx 4 (0-BASED) = the FIFTH slope_kdm6 call, the one after the post-freeze
#: ProgB_param at F:1707. Verified against the pinned source, and pinned by the
#: landmark below so it stays verified rather than re-counted.
MICRO_CALL_AUX_ANCHOR = (
    "                   ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax)", (4, 7),
    "fort_substep_postfreeze.bin")
MICRO_CALL_AUX = [
    ("rhox", "f32", "rhox(i,k)"),
    ("bg", "f32", "brs(i,k)"),
    ("cmg", "f32", "cmg(i,k)"),
    ("pidn0g", "f32", "pidn0g(i,k)"),
    ("avtg", "f32", "avtg(i,k)"),
    ("bvtg", "f32", "bvtg(i,k)"),
    ("bvtg1", "f32", "bvtg1(i,k)"),
    ("bvtg2", "f32", "bvtg2(i,k)"),
    ("bvtg3", "f32", "bvtg3(i,k)"),
    ("bvtg4", "f32", "bvtg4(i,k)"),
    ("g1pbg", "f32", "g1pbg(i,k)"),
    ("g3pbg", "f32", "g3pbg(i,k)"),
    ("g4pbg", "f32", "g4pbg(i,k)"),
    ("g5pbgo2", "f32", "g5pbgo2(i,k)"),
    ("g1pdgbgmg", "f32", "g1pdgbgmg(i,k)"),
    ("dgbgmug1", "f32", "dgbgmug1(i,k)"),
    ("rslopegbmax", "f32", "rslopegbmax(i,k)"),
    ("pvtg", "f32", "pvtg(i,k)"),
    ("precg2", "f32", "precg2(i,k)"),
]

POST_SED_ANCHOR = "      enddo ! do n = 1, mstepmax_i"
POST_MICRO_ANCHOR = "   enddo                  ! big loops"

#: Every prognostic the outer loop carries. qr/nr alone would leave the observed
#: loop-2 qv/t divergence outside the bridge — which is the divergence that made the
#: bridge necessary.
_CARRIED = [
    ("qr", "f32", "qrs(i,k,1)"), ("nr", "f32", "nrs(i,k,1)"),
    ("qv", "f32", "q(i,k)"), ("t", "f32", "t(i,k)"),
    ("qc", "f32", "qci(i,k,1)"), ("qi", "f32", "qci(i,k,2)"),
    ("qs", "f32", "qrs(i,k,2)"), ("qg", "f32", "qrs(i,k,3)"),
    # v5: the NUMBER concentrations and the graupel volume. With only the mass
    # fields, "the sedimentation result matched" was a statement about 8 of the 12
    # state members, and a difference in one of these could have crossed
    # outer_post_sed unobserved (owner P0-6).
    ("nc", "f32", "nci(i,k,1)"), ("ni", "f32", "nci(i,k,2)"),
    ("nccn", "f32", "nci(i,k,3)"), ("brs", "f32", "brs(i,k)"),
]
OUTER_POST_SED = list(_CARRIED)
OUTER_POST_MICRO = list(_CARRIED)

#: THE BISECTION of the microphysics step, at the sixth of the seven ProgB_param
#: calls (F:3032) — after the two-branch state update and its brs re-clamp, before
#: Picons/Nicons and the saturation adjustment. The pinned source already dumps
#: exactly this instant to fort_substep_poststateupdate.bin four lines below,
#: describing itself as mirroring the C++ `poststateupdate`, so the correspondence
#: between the backends is one that already exists and was reconciled rather than
#: one established here. That matters: both placement defects this protocol has
#: produced came from a site where it had to be established fresh.
#:
#: Derived from _CARRIED, so the twelve expressions are literally the ones
#: outer_post_micro already uses. A separate list would be a second mapping to keep
#: correct, which is how the pre-sed and post snapshots drifted apart at v5.
#: idx is 0-BASED: the SIXTH ProgB_param call (F:3032) is index 5. Written as 6
#: first, which resolved to the seventh (F:3146, post-satadj) and compared a
#: different instant than the C++ side without anything failing. The landmark is
#: the pinned source's own dump at that site, so the intended place is stated in
#: terms of the source rather than by an index the reader has to count.
MICRO_POST_STATE_UPDATE_ANCHOR = (
    "                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1)", (5, 7),
    "fort_substep_poststateupdate.bin")
MICRO_POST_STATE_UPDATE = list(_CARRIED)

#: THE OPERANDS OF THE qr UPDATE LINE, as the update reads them — a CLOSED set.
#:
#: The v10 bisection put the first divergence at micro_post_state_update L2 col3
#: k0 qr with the incoming state and the ProgB bundle bit-identical, so the seed
#: is in this line and nowhere else for that cell:
#:
#:   cold (F:2803)  qrs(1) += (praut+pracw+prevp-piacr-pgacr-psacr-pmulrs-pmulrg)*dtcld
#:   warm (F:2922)  qrs(1) += (praut+pracw+prevp+paacw+paacw-pseml-pgeml)*dtcld
#:
#: Closed matters: the incoming qrs(1) is already compared (it comes from
#: outer_post_sed) and dtcld is a sealed scalar, so if every operand here matches
#: and qr still differs, the difference is in the SUMMATION — order, or the fused
#: multiply-add the C++ uses — not in any operand. That is a decisive outcome
#: either way, which a partial set would not give.
#:
#: Emitted in BOTH arms of the F:2638 `if (t<=t0c)` branch. The rates are scaled
#: per-arm (cold F:2649-2730, warm F:2846-2859), so the scaled values only exist
#: inside; every cell passes through exactly one arm, so each still emits exactly
#: once and the expectation stays uniform over all cells.
#:
#: NAMING. Fortran adjusts three of these IN PLACE after the Hallett-Mossop block
#: -- psacr -= pmulrs (F:2383), pgacr -= pmulrg (F:2436), paacw -= pmulcs/pmulcg
#: (F:2368/F:2420) -- so by the update the array holds the post-HM value. The C++
#: carries that same quantity under a different name (psacr_adj, pgacr_adj,
#: paacw_adj, "post-HM" in coordinator.h). The names differ and the quantities do
#: not; that was established from the two sources, not from the suffix.
#:
#: cold_gate is recorded because the two arms read different operands: a branch
#: that disagreed between the backends would otherwise show up as several rates
#: differing at once, with nothing saying why.
#: THE MELT-FREEZE CHAIN, bisected (protocol v13).
#:
#: v12 put the first divergence at the update base, in ONE field -- t, by one ULP
#: -- with every other prognostic bit-identical. t matches at outer_post_sed, so
#: it acquires that difference in D1 melt, the homogeneous freeze, the post-melt
#: re-slope, D2-D4 freeze or the post-freeze re-slope. These two snapshots split
#: that span at the two points where BOTH backends already have a reconciled dump:
#: fort_substep_postmelt (F:1440) against the C++ `postmelt` on working1, and
#: fort_substep_postfreeze (F:1722) against `postfreeze` on working.
#:
#: post-melt sits inside `do k`/`do i` (the loop closes two lines later and the
#: pinned dump runs after it), so it emits per cell; post-freeze is at the top
#: level, on the same anchor micro_call_progb_aux uses, emitted AFTER it so both
#: backends order the two records the same way.
MICRO_POST_MELT_ANCHOR = (
    "          endif  !supcol", None, "fort_substep_postmelt.bin")
MICRO_POST_MELT = list(_CARRIED)
MICRO_POST_FREEZE = list(_CARRIED)

#: THE EXACT BASE state_update READS (owner review §2).
#:
#: micro_qr_operands seals the RATE operands of the qr update line and nothing
#: else. Its own note claimed the base was already compared because the incoming
#: qrs(1) comes from outer_post_sed -- it does not: D1 melt, homogeneous freeze,
#: the post-melt re-slope, D2-D4, the post-freeze re-slope, the rate blocks and
#: the conservation scaling all run in between. Without this stage the converse
#: ("all operands equal => the difference is in the summation") is unavailable.
#:
#: Injected BEFORE the F:2638 branch, so one record per cell whichever arm it
#: takes, and the state is unmodified between there and either `!     update`.
#: The C++ already dumps exactly this instant as the `prestate` substep forensic,
#: describing it as "the EXACT state_update base".
#:
#: supcol is NOT recorded: it is a scalar local reassigned in earlier loops, so at
#: this point it holds another iteration's value. The branch is recomputed by the
#: comparator from this stage's `t` and t0c instead -- which is also what owner
#: review §3 asks for, since a producer-emitted gate is the producer's claim about
#: its own branch rather than an independent check of it.
MICRO_PRE_STATE_UPDATE_ANCHOR = (
    "          if(t(i,k).le.t0c) then", None, "!     cloud water")
MICRO_PRE_STATE_UPDATE = list(_CARRIED)

MICRO_QR_OPERANDS_COLD_ANCHOR = (
    "              bsdep(i,k)=psdep(i,k)/dens", (0, 1), "!     update")
MICRO_QR_OPERANDS_WARM_ANCHOR = (
    "            bgeml(i,k)=pgeml(i,k)/rhox(i,k)", (0, 1), "!     update")
MICRO_QR_OPERANDS = [
    # common to both arms (F:2803 and F:2922)
    ("praut", "f32", "praut(i,k)"), ("pracw", "f32", "pracw(i,k)"),
    ("prevp", "f32", "prevp(i,k)"),
    # cold arm only
    ("piacr", "f32", "piacr(i,k)"), ("pgacr", "f32", "pgacr(i,k)"),
    ("psacr", "f32", "psacr(i,k)"), ("pmulrs", "f32", "pmulrs(i,k)"),
    ("pmulrg", "f32", "pmulrg(i,k)"),
    # warm arm only
    ("paacw", "f32", "paacw(i,k)"), ("pseml", "f32", "pseml(i,k)"),
    ("pgeml", "f32", "pgeml(i,k)"),
    # which arm this cell took
    ("cold_gate", "f32", "merge(1.0,0.0,t(i,k).le.t0c)"),
]

#: Pre-sed forcings: not carried between loops, so not part of the bridge identity —
#: but they ARE part of the problem the kernel is given. `p` was missing: pressure
#: enters saturation vapour pressure, the diffusion/thermodynamic coefficients and
#: several process rates, so two backends entering the kernel with different pressure
#: would show it only as a rate difference much later, at a place with no visible
#: connection to the cause (owner P0-4).
_FORCINGS = [("p", "f32", "p(i,k)"),
             ("rho", "f32", "dend(i,k)"), ("delz", "f32", "delz(i,k)")]

#: DERIVED from _CARRIED, not maintained beside it. Keeping a parallel list is how
#: the two drifted at v5: the post snapshots gained the number concentrations and
#: this one did not, so the carry was checked over fields one end never emitted.
OUTER_PRE_SED = _CARRIED + _FORCINGS

#: AFTER THE ENTRY CLAMP (owner P0-3/P0-6). The clamp block (F:822-864) ends two lines
#: above `! imsi`, but injecting there would record `rho` from `dend`, which the very
#: next loop assigns — so the anchor is the line after that copy. `dend(i,k)=den(i,k)`
#: is a pure forcing copy and touches none of the twelve carried fields, so the interval
#: this snapshot closes is the padding and nothing else.
AFTER_ENTRY_CLAMP_ANCHOR = "! 20250205 ncmin setting"
AFTER_ENTRY_CLAMP = _CARRIED + _FORCINGS

# ── surface causal operands (owner P0-8): the per-species bottom fall that feeds
# rain/snow/graupel increments, so the qr-seed -> precip path is an operand set,
# not just the final PREC. Emitted per column at the surface accumulation (k=-1).
SURFACE_ANCHOR = "        fallsum = fall(i,kts,1)+fall(i,kts,2)+fall(i,kts,3)+fall(i,kts,4)"
SURFACE_FIELDS = [
    ("bottom_fall_qr", "f32", "fall(i,kts,1)"),
    ("bottom_fall_qs", "f32", "fall(i,kts,2)"),
    ("bottom_fall_qg", "f32", "fall(i,kts,3)"),
    ("bottom_fall_qi", "f32", "fall(i,kts,4)"),
    ("bottom_fall_total", "f32", "fallsum"),
    ("delz_bottom", "f32", "delz(i,kts)"),
    # the water density the rain-increment arithmetic divides by — the last
    # surface operand that was source-knowledge-only, now bound (owner P0-8).
    ("surface_denr", "f32", "denr"),
]

#: Surface NUMBER flux operands (owner §5). `falln` accumulates falkn = nrs*workn,
#: and nrs IS the prognostic number MIXING ratio (`nrs(i,k,1) = nr(i,k,j)`, F:388),
#: so falln is [# kg-1 s-1] and the per-area flux is falln*den*delz*dtcld [# m-2].
#: Raw operands only -- forming the product here would bury that reasoning in a
#: Fortran expression nobody reviews.
SURFACE_NUMBER_FIELDS = [
    ("bottom_falln_nr", "falln(i,kts,1)"),
    ("bottom_falln_ni", "falln(i,kts,2)"),
    ("nflux_den", "den(i,kts)"),
    ("nflux_delz", "delz(i,kts)"),
    ("nflux_dtcld", "dtcld"),
]

#: `dq?(i,k+1)` is written TWICE with different caps: at iteration k+1 as that
#: cell's own outflow, capped against its PRE-update content, and again at
#: iteration k as the inflow below, capped against its POST-update content. The
#: second is what arrives; the first is what left. Emitting both of a cell's
#: transfers at each iteration lets the two be paired across the interface, which
#: is where the mass goes missing.
#: Sites are PER ALGORITHM (owner §11). The conservative variant rewrote the
#: sedimentation update -- its interior inflow is the source cell's ACTUAL capped
#: outflow converted by `src_metric/dst_metric` for mass, while number keeps the
#: dz-only ratio -- so the legacy anchors do not exist in it and the overlay
#: failed loudly rather than instrumenting the wrong statement.
#:
#: TOP: the top cell is updated outside the interior loop, so its departure has
#: no `dq?(i,k)` record and the topmost interface would be invisible. Emitted
#: BEFORE the update, where the pre-update content is still available.
TOP_SITES = {
    "legacy": [
        ("           qrs(i,k,1) = max(qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k),0.)",
         "main", "min(falk(i,k,1)*dtcld/dend(i,k),qrs(i,k,1))",
         "min(falkn(i,k,1)*dtcld,nrs(i,k,1))"),
        ("           qci(i,k,2) = max(qci(i,k,2)-falk(i,k,4)*dtcld/dend(i,k),0.)",
         "ice", "min(falk(i,k,4)*dtcld/dend(i,k),qci(i,k,2))",
         "min(falkn(i,k,2)*dtcld,nci(i,k,2))"),
    ],
    "conservative": [
        # already the ACTUAL capped outflow in this variant
        ("           nrs(i,k,1) = nrs(i,k,1)-dnr(i,k)", "main",
         "dqr(i,k)", "dnr(i,k)"),
        ("           nci(i,k,2) = nci(i,k,2)-dni(i,k)", "ice",
         "dqi(i,k)", "dni(i,k)"),
    ],
}

#: `dq?(i,k+1)` in LEGACY is written twice with different caps: at iteration k+1
#: as that cell's own outflow (PRE-update cap) and again at iteration k as the
#: inflow below (POST-update cap). The second is what arrives, the first is what
#: left, and the difference is destroyed. The conservative variant computes the
#: inflow ONCE, from the source cell's actual outflow, so this pairing measures a
#: defect that variant does not have -- which is exactly what makes it a control.
CAP_SITES = {
    "legacy": [
        ("             qrs(i,k,1) = max(qrs(i,k,1)-dqr(i,k)+dqr(i,k+1),0.)",
         "main", "dqr(i,k)", "dqr(i,k+1)", "dnr(i,k)", "dnr(i,k+1)"),
        ("             qci(i,k,2) = max(qci(i,k,2)-dqi(i,k)+dqi(i,k+1),0.)",
         "ice", "dqi(i,k)", "dqi(i,k+1)", "dni(i,k)", "dni(i,k+1)"),
    ],
    "conservative": [
        ("                          +dnr(i,k+1)*delz(i,k+1)/delz(i,k)",
         "main", "dqr(i,k)", "dqr(i,k+1)", "dnr(i,k)", "dnr(i,k+1)"),
        ("                          +dni(i,k+1)*delz(i,k+1)/delz(i,k)",
         "ice", "dqi(i,k)", "dqi(i,k+1)", "dni(i,k)", "dni(i,k+1)"),
    ],
}

#: The bottom cell's ACTUAL capped transfer, per sub-step: what the kernel really
#: moved, so nothing is reconstructed from endpoints and `mstep > 1` is
#: measurable.
XFER_SITES = {
    "legacy": [
        ("             qrs(i,k,1) = max(qrs(i,k,1)-dqr(i,k)+dqr(i,k+1),0.)",
         "main", "dqr(i,k)", "dnr(i,k)"),
        ("             qci(i,k,2) = max(qci(i,k,2)-dqi(i,k)+dqi(i,k+1),0.)",
         "ice", "dqi(i,k)", "dni(i,k)"),
    ],
    "conservative": [
        ("                          +dnr(i,k+1)*delz(i,k+1)/delz(i,k)",
         "main", "dqr(i,k)", "dnr(i,k)"),
        ("                          +dni(i,k+1)*delz(i,k+1)/delz(i,k)",
         "ice", "dqi(i,k)", "dni(i,k)"),
    ],
}

# Scratch temps declared once (fall/falln captured at cell entry) + the capture.
DECL_ANCHOR = "   real, dimension(its:ite,kts:kte,4) :: falk, fall"
DECL_BLOCK = [
    "#ifdef KDM6_G33_FORTRAN_DUMP",
    "   real :: g33_fqb, g33_fnb   ! G3.3-M: fall/falln captured at cell entry",
    "   ! v14 freeze-heat operands. pinuc/pfrzdtc/pfrzdtr are per-cell DOUBLE",
    "   ! SCALARS set inside branches (F:758, F:781-782), so they cannot be read",
    "   ! from the top-level emission point — captured at the site of use, zeroed",
    "   ! per cell, which is what a skipped branch means numerically. DOUBLE here",
    "   ! deliberately: an f32 cast (as the source's own dbg_d4a does) would erase",
    "   ! the precision difference this stage exists to look for.",
    "   double precision, dimension(its:ite,kts:kte) :: g33_pinuc, g33_pfrzdtc, g33_pfrzdtr",
    "   real, dimension(its:ite,kts:kte) :: g33_xlf, g33_tprefrz, g33_phom",
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
    "nmass": {
        "sha": "ea539880f853553f35d987a77b56a73e2583023c7c65525070c47d565371b5e7",
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
    "nmasslncmin": {
        "sha": "ac614415807d9a600352af085136cac2d4ab217f014e51bb9e974add881e6840",
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
    "lncmin": {
        "sha": "07bd3a82eec7b7d11d370289c5a92c64261d70ac129a077577cb39b18f6f6728",
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
    "cons_nmasslncmin": {
        "sha": "20c5840222645b37c9cd8d5c29f13a83f8b12cd0bc667f5dad2eb1118b6851e6",
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
    "cons_lncmin": {
        "sha": "a97e0cb507401209d9569ccc8959fdbf0a48c673130ee1c0951f4767c10d578f",
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
    "cons_nmass": {
        "sha": "8e3df235f506f84f0598cb71d2468a08ef5a2decacfea9228f446b06f84edd9a",
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


# ── v14: the freeze heat term ────────────────────────────────────────────────
#: The three sequential t-stores of the D2-D4 freeze, as a CLOSED operand set:
#:
#:   c  = f32(xlf/cpm)
#:   t2 = f32(t_pre + c*pinuc)      F:1618   pinuc   DOUBLE
#:   t3 = f32(t2    + c*pfrzdtc)    F:1648   pfrzdtc DOUBLE
#:   t4 = f32(t3    + c*pfrzdtr)    F:1679   pfrzdtr DOUBLE
#:
#: t4 must equal micro_post_freeze.t. Every other input is already compared
#: (micro_post_melt.t) or recorded here, so the set is closed for those three
#: statements the way micro_qr_operands is for the qr line — and this time the
#: base IS sealed, which v12 established is the precondition.
#:
#: phom (F:1529, homogeneous freeze at T < -40 C) is recorded and REQUIRED TO BE
#: ZERO. The C++ handles homogeneous freezing outside apply_melt_freeze_inline, so
#: that term is not in its t chain; on a fixture where it fires the two sides would
#: cover different arithmetic. Asserting zero makes such a fixture fail loudly
#: rather than compare different things quietly. On arithmetic_multisubcycle_v1 no
#: cell reaches 233.15 K, so it is zero throughout.
#: The landmark must sit within the builder's window (12 lines); `prevp(i,k) = 0.`
#: is the natural name for this block but is 17 lines below, and the guard said
#: so rather than injecting somewhere unintended. bgacr is inside the window and
#: in the same zero-init run.
FREEZE_ZERO_ANCHOR = ("          biacr(i,k) =0.", None, "bgacr(i,k) =0.")
FREEZE_ZERO_BLOCK = [
    "#ifdef KDM6_G33_FORTRAN_DUMP",
    "          g33_pinuc(i,k) = 0.d0",
    "          g33_pfrzdtc(i,k) = 0.d0",
    "          g33_pfrzdtr(i,k) = 0.d0",
    "          g33_xlf(i,k) = 0.",
    "          g33_tprefrz(i,k) = 0.",
    "          g33_phom(i,k) = 0.",
    "#endif",
]
#: idx 1 (0-BASED) = the SECOND `if(supcol.lt.0.) xlf = xlf0`, at the head of the
#: FREEZE loop (F:1517); the first (F:1366) heads the melt loop. The landmark is
#: the pihmf comment two lines below, so the wrong one cannot be taken silently.
FREEZE_BASE_ANCHOR = ("          if(supcol.lt.0.) xlf = xlf0", (1, 2), "pihmf")
FREEZE_BASE_BLOCK = [
    "#ifdef KDM6_G33_FORTRAN_DUMP",
    "          g33_tprefrz(i,k) = t(i,k)",
    "          g33_xlf(i,k) = xlf",
    "#endif",
]
#: Each capture goes BEFORE its t-store, because the store's own operand is
#: consumed there (qci(i,k,1) is zeroed on the next line).
FREEZE_CAPTURES = [
    ("            t(i,k) = t(i,k) + xlf/cpm(i,k)*qci(i,k,1)",
     "g33_phom(i,k) = qci(i,k,1)"),
    ("            t(i,k) = t(i,k) + xlf/cpm(i,k)*pinuc ",
     "g33_pinuc(i,k) = pinuc"),
    ("            t(i,k) = t(i,k) + xlf/cpm(i,k)*(pfrzdtc)",
     "g33_pfrzdtc(i,k) = pfrzdtc"),
    ("            t(i,k) = t(i,k) + xlf/cpm(i,k)*pfrzdtr",
     "g33_pfrzdtr(i,k) = pfrzdtr"),
]
MICRO_FREEZE_HEAT = [
    ("t_pre_freeze", "f32", "g33_tprefrz(i,k)"),
    ("xlf", "f32", "g33_xlf(i,k)"),
    ("cpm", "f32", "cpm(i,k)"),
    ("phom", "f32", "g33_phom(i,k)"),
    ("pinuc", "f64", "g33_pinuc(i,k)"),
    ("pfrzdtc", "f64", "g33_pfrzdtc(i,k)"),
    ("pfrzdtr", "f64", "g33_pfrzdtr(i,k)"),
]


#: ARM N reuses legacy's SITE TABLES too. It changes what two transfer lines
#: COMPUTE, not where anything sits, so every anchor, cap site, top site and
#: transfer site is legacy's -- and saying so here, once, beats discovering
#: each missing table one KeyError at a time.
#: Derived arms inherit their BASE's site tables: N and L change what a line
#: computes, not where anything sits.
#: `nmass_dry` sits with them: its edit is INSIDE the `dnr(i,k+1) = min(...)`
#: expression, and every legacy anchor is on an update line, so none of them
#: moves. Checked rather than assumed -- CAP, TOP and XFER all anchor on
#: `qrs(...)`/`qci(...)` assignments.
#: ... and the same for the overlay's own per-arm record. `nmass_dry` shares
#: every anchor with `nmass` -- both edit inside the `min(...)`, neither moves
#: an update line -- so it is DERIVED from that entry rather than copied, with
#: its own source sha. A copied block is a second place for the anchors to
#: drift, which is the defect this file has already paid for twice.
#: melt_g1: the graupel-melt counterfactual. Its instrumentation sites
#: are legacy's -- the edit touches only the melt block, which carries
#: none of them -- so it inherits legacy's bindings and pins its own sha.
VARIANTS["melt_g1"] = dict(
    VARIANTS["legacy"],
    sha="5f5a4c73dbb0be9163d0c64511f2a632b6d6fbe8d0e36c68dbc64b2a0b8c759a")
#: melt_g2: the graupel-melt counterfactual. Its instrumentation sites
#: are legacy's -- the edit touches only the melt block, which carries
#: none of them -- so it inherits legacy's bindings and pins its own sha.
VARIANTS["melt_g2"] = dict(
    VARIANTS["legacy"],
    #: Re-pinned 2026-08-25. The generator's emitted comment described g2 as
    #: computing a PRE-melt density, which it does not -- the mass update runs
    #: first, so on a complete melt its guard is false. Comment-only edit,
    #: proved: 0 non-comment lines differ from the 08-24 source.
    sha="9c7fd270c13efd019d2ccb7593f5a2df759eed8ab0e45ca2ce17e5335663eba6")
#: melt_g3: the graupel-melt counterfactual. Its instrumentation sites
#: are legacy's -- the edit touches only the melt block, which carries
#: none of them -- so it inherits legacy's bindings and pins its own sha.
VARIANTS["melt_g3"] = dict(
    VARIANTS["legacy"],
    sha="3acf8bcbdad4218309e20686415691072c69682392f36ce44db1614a401f32f8")
#: melt_g4: the PRE-melt density counterfactual g2 was named as and is not.
#: It replaces the whole melt transaction, so the density comes from the mass
#: and volume the melt started with. Instrumentation sites are still legacy's.
VARIANTS["melt_g4"] = dict(
    VARIANTS["legacy"],
    sha="c0da77ba3fe009a97289cf70f80f07bafcb03516b962f6f5de102c1306b7c642")
#: melt_g5: the window-only proportional-volume transaction. Outside the
#: window it is legacy to the bit; inside it scales the volume by the mass
#: fraction, so no clamp and no floor.
VARIANTS["melt_g5"] = dict(
    VARIANTS["legacy"],
    sha="6a1de0ca0ab1520a16da6e4f90163e98a19180704274e965186dd4f70d8e171f")
VARIANTS["nmass_dry_window"] = dict(
    VARIANTS["nmass"],
    sha="a3330ad13b99460e305c01e4e9f02848cc74779ed0acf463b7865d6e6146ee60")
VARIANTS["nmass_dry"] = dict(
    VARIANTS["nmass"],
    sha="c0e9465d03ee107fb50ba67d0f1798b92d417572e2cdaef3ffa568c684e19273")

_DERIVED = g33_arms.derived()   # arm -> base, from the one registry
for _t in (CAP_SITES, TOP_SITES, XFER_SITES):
    for _arm, _base in _DERIVED.items():
        _t[_arm] = _t[_base]

#: ...EXCEPT where the arm edits the very line the base anchors on.
#:
#: Legacy puts the number ratio inside `dnr(i,k+1) = min(...)` and anchors on
#: the UPDATE line, so Arm N leaves its anchors alone. Conservative applies the
#: ratio AT the update, which is exactly where its anchor sits -- so on a
#: conservative base the N edit moves the anchor out from under the overlay,
#: and the generator's whole-line match found 0 of 1. Loudly, which is what
#: that check is for.
#:
#: Rewritten mechanically from the same substitution the variant generator
#: applies, so the anchor cannot drift from the source it is meant to match.
_N_OLD = "+dnr(i,k+1)*delz(i,k+1)/delz(i,k)"
_N_NEW = "+dnr(i,k+1)*dend(i,k+1)*delz(i,k+1)/(dend(i,k)*delz(i,k))"


def _with_n_edit(obj):
    """The same structure with the N substitution applied to every string."""
    if isinstance(obj, str):
        return (obj.replace(_N_OLD, _N_NEW)
                   .replace(_N_OLD.replace("dnr", "dni"),
                            _N_NEW.replace("dnr", "dni")))
    if isinstance(obj, tuple):
        return tuple(_with_n_edit(x) for x in obj)
    if isinstance(obj, list):
        return [_with_n_edit(x) for x in obj]
    if isinstance(obj, dict):
        return {_with_n_edit(k): _with_n_edit(v) for k, v in obj.items()}
    return obj


for _arm in ("cons_nmass", "cons_nmasslncmin"):
    for _t in (CAP_SITES, TOP_SITES, XFER_SITES):
        _t[_arm] = _with_n_edit(_t["conservative"])
    FIELD_EXPR[_arm] = _with_n_edit(FIELD_EXPR["conservative"])
    VARIANTS[_arm] = dict(VARIANTS[_arm],
                          emit=_with_n_edit(VARIANTS["conservative"]["emit"]),
                          post=_with_n_edit(VARIANTS["conservative"]["post"]))
del _t


# THE MELT COUNTERFACTUALS INHERIT LEGACY'S BINDINGS WHOLE. A partial copy --
# just INTERIOR and TOP -- passed every table check and then failed the schema
# validation on `QR_OUTFLOW`, because that entry carries the per-operation field
# lists too. The edits touch only the graupel melt block, which holds none of
# these sites, so the right relationship is "identical to legacy", stated once.
for _g in ("melt_g1", "melt_g2", "melt_g3", "melt_g4", "melt_g5"):
    FIELD_EXPR[_g] = FIELD_EXPR["legacy"]
    XFER_SITES[_g] = XFER_SITES["legacy"]
