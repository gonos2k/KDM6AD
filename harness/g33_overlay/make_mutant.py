#!/usr/bin/env python3
"""Write a mutated copy of an overlay for the standing kill gate.

Kept as a file (not an inline heredoc) so the exact C++ replacement strings —
with their parentheses, slashes and newlines — are not mangled by shell
quoting. Each mutant injects ONE defect and must be killed by the self-check at
a predicted site; a mutation the gate cannot kill means the check is vacuous.

    make_mutant.py shadow  <in.overlay> <out.overlay>   # legacy FALK gate rung
    make_mutant.py cons_inflow <in.overlay> <out.overlay>  # conservative rho*dz transfer
    make_mutant.py cons_prevout <in.overlay> <out.overlay>  # wrong-neighbour interface link
    make_mutant.py cons_poststate <in.overlay> <out.overlay>  # returned state != diagnostic q_post
"""
import sys

KIND, SRC, DST = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(SRC, encoding="utf-8").read()

if KIND == "shadow":
    # legacy SHADOW ladder drops the gate rung — kills the shared FALK proof
    old = "auto s4 = s3 * gate_col;"
    assert s.count(old) >= 1, f"shadow anchor count {s.count(old)}"
    s = s.replace(old, "auto s4 = s3 * 1.0;  // MUTANT")
elif KIND == "cons_inflow":
    # conservative ACTUAL transfer drops the /dst_metric division — the rho*dz
    # interface transfer that is conservative-ONLY. Mutating the STATE-carrying
    # dq_in (not the diagnostic recompute) makes the dumped inflow_final diverge
    # from the offline rho*dz replay.
    old = ("auto dq_in = s->prev_out * (dend_safe_col(k - 1) * delz_col(k - 1))\n"
           "                             / (dend_safe_col(k) * delz_safe_col(k));")
    assert s.count(old) == 1, f"cons_inflow anchor count {s.count(old)}"
    s = s.replace(old,
                  "auto dq_in = s->prev_out * (dend_safe_col(k - 1) * delz_col(k - 1));"
                  "  // MUTANT: dropped /dst_metric")
elif KIND == "cons_prevout":
    # The outflow that the NEXT cell will pull in as its inflow is carried in
    # s->prev_out. Perturbing the CARRIED value (not the record, not the metric)
    # keeps every within-record recompute self-consistent — the offline rho*dz
    # replay still matches the dumped inflow_final, because both use this same
    # wrong prev_out. Only the cross-record interface link
    # (QR_INFLOW.prev_out(k) == QR_OUTFLOW.dq_out(k-1)) can see the mismatch:
    # the recorded prev_out is now dq_out*1.03125, but dq_out(k-1) is untouched.
    # This is the defect the causal-link layer exists to catch and the single-
    # record arithmetic proof cannot.
    old = "s->prev_out = dq_out;"
    assert s.count(old) == 1, f"cons_prevout anchor count {s.count(old)}"
    s = s.replace(old, "s->prev_out = dq_out * 1.03125f;  // MUTANT: wrong neighbour")
elif KIND == "cons_poststate":
    # Perturb the RETURNED qr column AFTER every per-cell op record is written
    # but BEFORE the substep_post dump and the function return. The diagnostic
    # QR_UPDATE.q_post records stay correct; the value the function actually
    # returns (== substep_post, == the next substep's pre) is wrong. Every
    # within-record equation and cross-substep continuity still pass — only the
    # per-cell-q_post == substep_post link (PR B2.2 §2.1) can see it. Injected in
    # the always-compiled path right after the cell loop closes.
    old = ("        prev_out_nr = dn_out;\n"
           "    }\n"
           "\n"
           "#ifdef KDM6_G33_OP_DUMP")
    assert s.count(old) == 1, f"cons_poststate anchor count {s.count(old)}"
    s = s.replace(old,
                  "        prev_out_nr = dn_out;\n"
                  "    }\n"
                  "\n"
                  "    qr.cols[1] = qr.cols[1] * 1.03125f;  // MUTANT: wrong returned column\n"
                  "\n"
                  "#ifdef KDM6_G33_OP_DUMP")
else:
    sys.exit(f"unknown mutant kind {KIND!r}")

open(DST, "w", encoding="utf-8").write(s)
