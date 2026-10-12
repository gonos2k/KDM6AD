---
title: Actual DOM nine-channel analysis and matched seven-channel case
type: source
date_ingested: 2026-10-13
source_type: native-rttov-analysis-and-independent-checks
tags: [KDM6AD, AMI, RTTOV, DOM, gradient, provenance]
---
# Actual DOM nine-channel analysis and matched seven-channel case

[[KDM6AD]] follow-up to [[pr418-nine-channel-closeout-2026-10-12]] and
[[pr419-postmerge-verification-2026-10-12]] uses the retained
[[pr412-natural-native-process-case-2026-10-12]] native–AMI case.
The [report](../../harness/evidence/pr420_nine_channel_analysis_2026-10-13/REPORT.md)
records actual9 and matched7 analyses under explicitly opt-in RTTOV DOM1.
Controls, local20s M, prior and bounded optimizer settings are unchanged;
all selected model-quality values are zero, audits crosschecked and returned
State/control/full gradient saved. DOM9 initial zero-control J=13.2247006976
and final Jtotal=11.4686595552.
Different support sizes prohibit comparing raw J9 versus J7 as a performance gain.

The separate historical07 MP137 passive trace localizes the Edd3 warning to
gas/clear extinction exceeding20km⁻¹ in the bottom two RTTOV layers. No
hydrometeor contribution occurs in that profile. This source is different
from the 05:55:40 retained MP337 analysis. Original Edd3 defaults/results are
preserved, and DOM1 is a separate research H rather than a repaired Edd3 map.

Saved-state joint M diagnostics cover both supports: DOM7/DOM9 IR105
R_M=+0.531204550/+0.531380474K and G_M−G0=1.592393064/1.592544829.
At this same saved case, QC/NC vanish after the local M20 step in both returned
slots while remaining in the background slot; host-dry-mass finite-water
increments are zero for each initial→slot pair. Rates and cloud-only
attribution remain unmeasured.
One actual CWT→M→H central-direction check agrees with saved full gradient
to1.2e−9 relative error. Neither result proves higher derivatives or strict
convergence: DOM9 final gradient L∞0.2929647968 exceeds1e−10.

Pixel UTC/interface identity, native number basis, reference/surface/SRF
qualifications, other dates and atmospheric truth remain bounded limits.
The original pair did not pre/post bind its calibration JSON; a current
unmodified hash is only post hoc evidence. Later direction/process checks
bind it explicitly. KST is the display convention; model times remain UTC.
This optional nine-channel completion does not reopen the existing seven-channel
functional closeout or certify forecast/cycling performance.
