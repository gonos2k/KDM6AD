# Green review: PR408 synthetic-H addendum

Reviewed the revised PR409 central document, its addendum report and wiki note
against the existing PR408 source and saved receipt. The addendum is consistent;
no blocker or unsupported expansion of the synthetic evidence remains.

The fixture at `oracle/tests/test_da_single_column.py:86-100` computes one scalar
from theta, qv and qc, then expands that value to seven channels. Therefore its
H Jacobian has identical rows, and composition with KDM and the control map has
source-derived rank at most one on a differentiable branch. This is an upper
bound for that synthetic fixture, not a measured rank for AMI/RTTOV. Given equal
channel scales and a full equal mask, permuting the seven targets leaves the
summed synthetic loss and state pullback invariant. Separate channel metadata
checks do not alter that limitation.

The saved PR408 initial objective record (`CAPTURE.json`, call `c1`) has repeated
BT 281.1793945959209 K, targets 282 through 288 K, all seven channels supported,
and sigma 1 K / Huber delta 1. The first absolute residual is about 0.8206 K;
the remaining six exceed 1 K. Thus the initial Huber sum has one quadratic and
six linear terms. The zero-mask background-quality probe is separately recorded
and is not the initial objective. The central text preserves this distinction.

The direct NC statement is correctly scoped to the synthetic H, which reads
theta/qv/qc and has no direct NC input. It leaves possible M-mediated pathways
open. The production all-sky source remains different: `rttov_obs_operator.py`
lists NC/NI among connected fields via effective diameter, while NCCN has no
direct BT path; this PR408 fixture does not validate those production paths.
The density distinction also remains correct: runtime KDM derives
`rho_m/(1+qv)` from fixed supplied moist-air density and trial vapor, while the
separate optical `rho_d` is frozen from the background.

The optional notation is coherent: `R_M(x)` is a one-state observation change
under evolution, and `I_M` is explicitly the difference of that response
between accepted and background initial states. It is not claimed as an
executed diagnostic. Starting from the four retained background/analysis
initial/slot states and matching existing process/BT records is appropriate;
extra H calls are limited to values missing for a stated claim. PR408 remains
one synthetic diagnostic success, not real RTTOV, weather improvement, or a
new score contribution.

The source path was checked against the cached graph query and then verified in
authoritative source. No source, test, result or receipt was changed. No tests,
calculations, H/M calls, native runs, optimizer calls or data requests were
performed.
