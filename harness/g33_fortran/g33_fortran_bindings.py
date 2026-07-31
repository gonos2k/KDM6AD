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
