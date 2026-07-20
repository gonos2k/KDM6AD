#!/usr/bin/env python3
"""Write a mutated copy of an overlay for the standing kill gate.

Kept as a file (not an inline heredoc) so the exact C++ replacement strings —
with their parentheses, slashes and newlines — are not mangled by shell
quoting. Each mutant injects ONE defect and must be killed by the self-check at
a predicted site; a mutation the gate cannot kill means the check is vacuous.

    make_mutant.py shadow  <in.overlay> <out.overlay>   # legacy FALK gate rung
    make_mutant.py cons_inflow <in.overlay> <out.overlay>  # conservative rho*dz transfer
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
else:
    sys.exit(f"unknown mutant kind {KIND!r}")

open(DST, "w", encoding="utf-8").write(s)
