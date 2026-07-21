#!/usr/bin/env python3
"""Write a mutated copy of an overlay for the standing kill gates.

Kept as a file (not an inline heredoc) so the exact C++ replacement strings —
with their parentheses, slashes and newlines — are not mangled by shell
quoting. Each mutant injects ONE defect and must be killed by the focused check
at a predicted site; a mutation the gate cannot kill means the check is vacuous.

    make_mutant.py shadow <in.overlay> <out.overlay>
    make_mutant.py cons_inflow <in.overlay> <out.overlay>
    make_mutant.py cons_prevout <in.overlay> <out.overlay>
    make_mutant.py cons_poststate <in.overlay> <out.overlay>
    make_mutant.py cons_fallacc <in.overlay> <out.overlay>
    make_mutant.py surface_omit_qi <sedimentation.overlay> <out.overlay>
    make_mutant.py surface_wrong_bottom <coordinator.overlay> <out.overlay>
"""
import sys

KIND, SRC, DST = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(SRC, encoding="utf-8").read()


def require(old, n):
    """Fail loud even under python -O when the pinned anchor count drifts."""
    got = s.count(old)
    if got != n:
        raise SystemExit(
            f"{KIND}: anchor count {got}, expected {n} — overlay changed, "
            f"re-derive the mutant")


if KIND == "shadow":
    # The legacy shadow gate rung appears once in TOP and once in INTERIOR code.
    old = "auto s4 = s3 * gate_col;"
    require(old, 2)
    s = s.replace(old, "auto s4 = s3 * 1.0;  // MUTANT", 2)
elif KIND == "cons_inflow":
    old = ("auto dq_in = s->prev_out * (dend_safe_col(k - 1) * delz_col(k - 1))\n"
           "                             / (dend_safe_col(k) * delz_safe_col(k));")
    require(old, 1)
    s = s.replace(
        old,
        "auto dq_in = s->prev_out * (dend_safe_col(k - 1) * delz_col(k - 1));"
        "  // MUTANT: dropped /dst_metric",
        1)
elif KIND == "cons_prevout":
    old = "s->prev_out = dq_out;"
    require(old, 1)
    s = s.replace(old, "s->prev_out = dq_out * 1.03125f;  // MUTANT: wrong neighbour", 1)
elif KIND == "cons_poststate":
    old = ("        prev_out_nr = dn_out;\n"
           "    }\n"
           "\n"
           "#ifdef KDM6_G33_OP_DUMP")
    require(old, 1)
    s = s.replace(
        old,
        "        prev_out_nr = dn_out;\n"
        "    }\n"
        "\n"
        "    qr.cols[1] = qr.cols[1] * 1.03125f;  // MUTANT: wrong returned column\n"
        "\n"
        "#ifdef KDM6_G33_OP_DUMP",
        1)
elif KIND == "cons_fallacc":
    old = "s->fall[k] = s->fall[k] + dq_out * dend_safe_col(k) / dtcld;"
    require(old, 1)
    s = s.replace(
        old,
        "s->fall[k] = s->fall[k] + dq_out * dend_safe_col(k) / dtcld "
        "* 1.03125f;  // MUTANT: fall accumulator",
        1)
elif KIND == "surface_omit_qi":
    # Actual surface rain total silently omits ice fallout.  The coordinator dump
    # still records all four operands, so only the independent surface replay can
    # kill this defect at rain_increment.
    old = "auto fallsum = fall_qr_bottom + fall_qs_bottom + fall_qg_bottom + fall_qi_bottom;"
    require(old, 1)
    s = s.replace(
        old,
        "auto fallsum = fall_qr_bottom + fall_qs_bottom + fall_qg_bottom;"
        "  // MUTANT: omitted qi fallout",
        1)
elif KIND == "surface_wrong_bottom":
    # Use K-2 instead of the true bottom K-1.  Every surface record remains
    # internally self-consistent; only the cross-container QR_FALLACC link sees it.
    old = "auto bottom = K - 1;"
    require(old, 1)
    s = s.replace(old, "auto bottom = K - 2;  // MUTANT: wrong surface layer", 1)
else:
    sys.exit(f"unknown mutant kind {KIND!r}")

open(DST, "w", encoding="utf-8").write(s)
