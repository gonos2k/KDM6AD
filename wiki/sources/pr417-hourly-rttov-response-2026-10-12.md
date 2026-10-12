---
title: Historical06/07 snapshot AMI forward response
type: source
date: 2026-10-12
---
# Historical06/07 snapshot AMI forward response

[[pr416-hourly-native-column-2026-10-12]] supplied saved06/07profiles for exactly
two real all-sky H calls,7AMI channels quality0, noM/native/optimizer/newobs.
IR10507−06=+0.769501K; IR087=+0.857550K; all channels increase. Each call uses its
own native pressure/interface/density/surface and freezes optical density within
that call; coefficient/BT/geometry/gas-source/discretization rules are common.
This joint input response is not cloud-only attribution, PR415's same-case
20minute counterpart, observed temporal fit or forecast skill. Dummy y values
are shape-only, dummy cost discarded; gradFalse does not certify no internal K.

QC path is EOS sum(qc*rho_d*dz), not eta mass or fixed-analysis mass. Cloud-layer
k3 warms/moistens asqc falls, while max cooling is20km aloft; no isolated
process/flux budget is inferred. Preparation API/geometry issues were resolved
beforeH. Legacy producer-byte/number/wind-basis/time ambiguities persist, and
no06:06/06:16 state is interpolated. Existing bounded analyses and historical79
remain unchanged; no additional05H or new solver is started.

Evidence: [report](../../harness/evidence/pr417_hourly_rttov_2026-10-12/REPORT.md),
[result](../../harness/evidence/pr417_hourly_rttov_2026-10-12/RESULT.json),
[channels](../../harness/evidence/pr417_hourly_rttov_2026-10-12/CHANNEL_RESPONSE.csv).
