---
title: Frozen adaptive QNC donor-scale pilot — 2026-10-29
type: source
date: 2026-10-29
---
# Frozen adaptive QNC donor-scale pilot

Following [[native-qnc-candidate-inputs-2026-10-28]], a source-pinned offline
analysis searches lower positive f32 limiter-scale words for each of the 54
selected liquid failure donors. It accepts a donor trial only when the exact
residual of rounded applied faces and all original-compatible f32 RK outputs
are positive, then applies every chosen shared-face change simultaneously
and checks the 382-cell donor/receiver capture.

Control needs one ULP at seven donors and none at 47. α needs one, two,
three or four ULP at 30, 19, four and one donors respectively. All 54
donors pass in each frozen case; 39 control and 306 α outgoing face words
change. Four QC-positive receiver cells remain exact-zero/QNC `+0` in both
baseline and candidate, with no new receiver failures. A fixed common
max-step table would change 297 control face words and overstep control's
own first passing choice at 50 donors.

This is a selected-neighborhood numerical counterfactual, not an executed
host correction or a coordinate-independent runtime rule. Full fixed-M0
support, physical number units, changed tile/MPI seams, optical cost and
the separate QI boundary case remain open. See the
[report](../../docs/NATIVE_QNC_SELECTED_ADAPTIVE_PILOT_20261029.md) and
[packet](../../harness/evidence/native_qnc_selected_adaptive_2026-10-29/README.md).
