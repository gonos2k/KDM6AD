#!/usr/bin/env python3
"""Write a TEMPORARY G3.3-M instrumentation overlay of a reference Fortran variant.

Protocol §5.1: the canonical Fortran is NEVER edited (frozen). This reads a
canonical microphysics module (legacy `module_mp_kdm6.F` or conservative
`module_mp_kdm6_cons.F`), verifies its SHA against the pin (a drift = re-derive,
fail-loud), inserts `#ifdef KDM6_G33_FORTRAN_DUMP`-guarded op-record emission at
unique anchors in the sedimentation sub-cycle, and writes a throw-away patched
copy. Compiled WITHOUT the macro it is byte-identical behaviour; WITH it, the sed
ladder is dumped to stdout as G33OP lines the four-case comparator's normalizer
reads.

    make_fortran_overlay.py <canonical.F> <out_overlay.F> [--algo legacy|conservative]

The emitted FIELD VOCABULARY is not chosen here — it is DERIVED from the single
authoritative schema `harness/g33_expectation._op_fields(algorithm, role, op_id)`,
the same schema the C++ container and the P4 comparator use. The per-(role,op,
field) Fortran expressions reproduce each operand bit-for-bit, faithful to the
C++ overlays (harness/g33_overlay/sedimentation{,_conservative}.cpp.overlay):
same rung decomposition, same left-to-right f32 order. The Fortran cell-above
index is k+1 (bottom-up) where the C++ top-first index is k-1.
`_validate_against_schema()` asserts the emitted field list equals the schema's,
in order — a schema change fails this generator loudly rather than silently
producing an incomparable dump.

Each emitted line is  G33OP <i> <k_topfirst> <n> <op_id>.<field> <dtype> <hex>
(dtype in {f32,f64,u8}; Z8.8 / Z16.16 / Z2.2). Fortran k is bottom-up (kts..kte);
we emit k = kte - k (kte -> 0). Physical emission order is irrelevant: the
normalizer canonicalizes op_seq by sorting on (k, species, op, field).
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import g33_expectation as ge  # noqa: E402

# ── field -> (dtype, Fortran expr), shared across variants ────────────────────
# FALK and OUTFLOW are IDENTICAL in both variants (the conservative change is only
# the inflow transfer + the fall accumulator + the dropped positivity clamp).
# u8 entries carry the BOOLEAN condition the overlay emits ((pre_cap > reservoir),
# (preclamp < 0)) — matching the actual overlay, not the schema comment's enum.
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
        ("q_post", "f32", "max(qrs(i,k,1)-dqr(i,k)+dqr(i,k+1),0.)"),
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
        ("n_post", "f32", "max(nrs(i,k,1)-dnr(i,k)+dnr(i,k+1),0.)"),
    ],
}
_LEG_TOP = {   # legacy TOP clamps directly: no OUTFLOW/INFLOW rung
    "QR_FALK": QR_FALK,
    "QR_FALLACC": _LEG_INT["QR_FALLACC"],
    "QR_UPDATE": [
        ("q_before", "f32", "qrs(i,k,1)"),
        ("q_minus_out", "f32", "qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k)"),
        ("clamp_active", "u8", "(qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k)) < 0."),
        ("q_post", "f32", "max(qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k),0.)"),
    ],
    "NR_FALK": NR_FALK,
    "NR_FALLACC": _LEG_INT["NR_FALLACC"],
    "NR_UPDATE": [
        ("n_before", "f32", "nrs(i,k,1)"),
        ("n_minus_out", "f32", "nrs(i,k,1)-falkn(i,k,1)*dtcld"),
        ("clamp_active", "u8", "(nrs(i,k,1)-falkn(i,k,1)*dtcld) < 0."),
        ("n_post", "f32", "max(nrs(i,k,1)-falkn(i,k,1)*dtcld,0.)"),
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
        ("q_post", "f32", "qrs(i,k,1)-dqr(i,k)+dqr(i,k+1)*src_metric/dst_metric"),
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
        ("n_post", "f32", "nrs(i,k,1)-dnr(i,k)+dnr(i,k+1)*delz(i,k+1)/delz(i,k)"),
    ],
}
_CON_TOP = {   # conservative TOP DOES compute an outflow; no inflow, no clamp
    "QR_FALK": QR_FALK, "QR_OUTFLOW": QR_OUTFLOW,
    "QR_FALLACC": _CON_INT["QR_FALLACC"],
    "QR_UPDATE": [
        ("q_before", "f32", "qrs(i,k,1)"),
        ("q_minus_out", "f32", "qrs(i,k,1)-dqr(i,k)"),
        ("q_post", "f32", "qrs(i,k,1)-dqr(i,k)"),
    ],
    "NR_FALK": NR_FALK, "NR_OUTFLOW": NR_OUTFLOW,
    "NR_FALLACC": _CON_INT["NR_FALLACC"],
    "NR_UPDATE": [
        ("n_before", "f32", "nrs(i,k,1)"),
        ("n_minus_out", "f32", "nrs(i,k,1)-dnr(i,k)"),
        ("n_post", "f32", "nrs(i,k,1)-dnr(i,k)"),
    ],
}

_FIELD_EXPR = {
    "legacy": {"INTERIOR": _LEG_INT, "TOP": _LEG_TOP},
    "conservative": {"INTERIOR": _CON_INT, "TOP": _CON_TOP},
}

_EMIT = {  # dtype -> (value expr wrapping the operand, Z format width)
    "f32": ("transfer({e}, 0)",   "Z8.8"),
    "f64": ("transfer({e}, 0_8)", "Z16.16"),
    "u8":  ("merge(1, 0, {e})",   "Z2.2"),
}
_IND = "             "  # 13-space body indent

# ── per-variant config: SHA pin + full-line anchors ───────────────────────────
# Anchors are matched as WHOLE LINES (not substrings), so 11-space vs 13-space
# forms are distinct and unique. Emission is PER SPECIES: the conservative source
# runs the qr chain fully (incl. its update) before the nr chain, so one anchor
# cannot see both species pre-update. `emit_before` anchors are the (first line
# of the) prognostic update; capture anchors are the substep guard.
_VARIANTS = {
    "legacy": {
        "sha": "9354141b9e93aceb4a1c35e06bf673a5d4d916028877c0f84f729a301876b7dc",
        "decl": "   real, dimension(its:ite,kts:kte,4) :: falk, fall",
        "cap_top": "         if(n.le.mstep(i)) then",
        "cap_int": "           if(n.le.mstep(i)) then",
        "emit": {  # (role, species): full-line update anchor (insert emission BEFORE)
            ("TOP", "qr"): "           qrs(i,k,1) = max(qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k),0.)",
            ("TOP", "nr"): "           nrs(i,k,1) = max(nrs(i,k,1)-falkn(i,k,1)*dtcld,0.)",
            ("INTERIOR", "qr"): "             qrs(i,k,1) = max(qrs(i,k,1)-dqr(i,k)+dqr(i,k+1),0.)",
            ("INTERIOR", "nr"): "             nrs(i,k,1) = max(nrs(i,k,1)-dnr(i,k)+dnr(i,k+1),0.)",
        },
    },
    "conservative": {
        "sha": "364a1319d0099bdb474a752a2a017defaf008babbe85dd03da872c603b2e7e3e",
        "decl": "   real, dimension(its:ite,kts:kte,4) :: falk, fall",
        "cap_top": "         if(n.le.mstep(i)) then",
        "cap_int": "           if(n.le.mstep(i)) then",
        "emit": {
            ("TOP", "qr"): "           qrs(i,k,1) = qrs(i,k,1)-dqr(i,k)",
            ("TOP", "nr"): "           nrs(i,k,1) = nrs(i,k,1)-dnr(i,k)",
            # interior update is a two-line continued statement; the FIRST line is
            # a unique whole line and emission (complete statements) goes ahead of it.
            ("INTERIOR", "qr"):
                "             qrs(i,k,1) = qrs(i,k,1)-dqr(i,k)                                  &",
            ("INTERIOR", "nr"):
                "             nrs(i,k,1) = nrs(i,k,1)-dnr(i,k)                                  &",
        },
    },
}

_DECL_BLOCK = [
    "#ifdef KDM6_G33_FORTRAN_DUMP",
    "   real :: g33_fqb, g33_fnb   ! G3.3-M: fall/falln captured at cell entry",
    "#endif",
]
_CAP_BLOCK = [
    "#ifdef KDM6_G33_FORTRAN_DUMP",
    f"{_IND}g33_fqb = fall(i,k,1)",
    f"{_IND}g33_fnb = falln(i,k,1)",
    "#endif",
]


def _validate_against_schema(algo):
    """Emitted field list MUST equal ge._op_fields(...), in order, for every
    (role, species, op) in scope — ties this overlay to the one schema."""
    for role in ("TOP", "INTERIOR"):
        for species in ("qr", "nr"):
            for op_id in ge._ops_for_species(algo, role, species):
                want = [f for f, _ in ge._op_fields(algo, role, op_id)]
                got = [f for f, _, _ in _FIELD_EXPR[algo][role][op_id]]
                if got != want:
                    raise SystemExit(
                        f"schema drift: {algo}/{role}/{op_id} overlay fields {got} "
                        f"!= g33_expectation {want}")


def _emit_lines(algo, role, species):
    """The op-emission lines for one (role, species) — top-first k = kte-k."""
    lines = ["#ifdef KDM6_G33_FORTRAN_DUMP"]
    for op_id in ge._ops_for_species(algo, role, species):
        for field, dtype, expr in _FIELD_EXPR[algo][role][op_id]:
            val, zf = _EMIT[dtype]
            lines.append(
                f"{_IND}write(*,'(A,3(1X,I0),1X,A,1X,A,1X,{zf})') "
                f"'G33OP', i, kte-k, n, '{op_id}.{field}', '{dtype}', "
                f"{val.format(e=expr)}")
    lines.append("#endif")
    return lines


def build_overlay(algo, text):
    """Return the patched source text for `algo`, or raise SystemExit on any
    anchor that is not present EXACTLY once (a source change)."""
    cfg = _VARIANTS[algo]
    lines = text.split("\n")

    # (whole-line anchor, place, block-lines). place: 'after' | 'before'.
    edits = [(cfg["decl"], "after", _DECL_BLOCK),
             (cfg["cap_top"], "after", _CAP_BLOCK),
             (cfg["cap_int"], "after", _CAP_BLOCK)]
    for (role, species), anchor in cfg["emit"].items():
        edits.append((anchor, "before", _emit_lines(algo, role, species)))

    # resolve each anchor to a unique line index up front (indices are on the
    # ORIGINAL lines; we rebuild in one pass so shifts never corrupt a later one).
    plan = {}
    for anchor, place, block in edits:
        idx = [i for i, ln in enumerate(lines) if ln == anchor]
        if len(idx) != 1:
            raise SystemExit(
                f"anchor matched {len(idx)} whole lines, expected 1 — the source "
                f"changed:\n  {anchor}")
        plan[idx[0]] = (place, block)

    out = []
    for i, ln in enumerate(lines):
        pl = plan.get(i)
        if pl and pl[0] == "before":
            out.extend(pl[1])
        out.append(ln)
        if pl and pl[0] == "after":
            out.extend(pl[1])
    return "\n".join(out)


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    algo = "legacy"
    for a in sys.argv[1:]:
        if a.startswith("--algo"):
            algo = a.split("=", 1)[1] if "=" in a else sys.argv[sys.argv.index(a) + 1]
    if algo not in _VARIANTS:
        raise SystemExit(f"--algo must be one of {sorted(_VARIANTS)}, got {algo!r}")
    src_path, dst_path = argv[0], argv[1]

    _validate_against_schema(algo)
    raw = open(src_path, "rb").read()
    got = hashlib.sha256(raw).hexdigest()
    if got != _VARIANTS[algo]["sha"]:
        raise SystemExit(
            f"canonical {algo} SHA {got} != pinned {_VARIANTS[algo]['sha']} — the "
            f"reference changed; re-verify anchors and re-pin")

    open(dst_path, "w", encoding="utf-8").write(build_overlay(algo, raw.decode("utf-8")))
    print(f"wrote {algo} overlay: {dst_path}")


if __name__ == "__main__":
    main()
