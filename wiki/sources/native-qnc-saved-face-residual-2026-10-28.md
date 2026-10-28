---
title: Native QNC saved-face residual — 2026-10-28
type: source
date: 2026-10-28
---
# Native QNC saved-face residual

Following [[native-qnc-advect-qi-producer-2026-10-28]], an offline companion
replayed the frozen RK3 QNC face and state words at native `(113,70,12)`.
All six target correction faces match binary32 multiplication by the recorded
limiter scale, and low-order faces keep their stored words. No model or RTTOV
call was made.

Exact real arithmetic on those already stored words gives control state
availability minus applied outflow **+164.537023** and α=0.25
**−409.781200**. The limiter's own `PH_LOW−FLUX_OUT×SCALE` is a distinct
quantity: control **−44.020630**, alpha **+28.576782**. A positive proxy
margin does not certify a positive residual after the rounded faces are
applied to the RK state.

Lowering the target scale one binary32 ULP leaves the α exact saved-face
residual **−111.694129**, while all four arithmetic modes compatible with
the original recording give positive binary32 QNC **+0.001692894381**.
This is a frozen-input counterfactual. Its six neighboring cells do not have
counterfactual state updates, and raw NC has no certified physical unit.
The observed candidate still loses 54 fixed-M0 profiles and 378 channel
cells, so its full-support RTTOV cost remains undefined.

See the [report](../../docs/NATIVE_QNC_SAVED_FACE_RESIDUAL_20261028.md) and
[versioned replay packet](../../harness/evidence/native_qnc_saved_face_probe_2026-10-28/README.md).
