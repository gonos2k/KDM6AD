---
title: Native-domain KO7 bounded T/Q case
type: source
date: 2026-10-25
---

# Native-domain KO7 bounded T/Q case

The [fixed July 19 case](../../harness/evidence/native_satellite_case_2026-10-25/REPORT.md)
completed the offline chain from native prep through full-B KDM, cleanup/finish,
post-finish EOS, native pressure/cloud profiles and actual RTTOV cost. All
65,988 columns and the original 128×512 + 452 partition are retained. The native
input is the saved MP137 00:00:40 state; the provided KO slot is nominal 00:00.
The 20-second map is not another host timestep or a new forecast valid time.

Baseline source QC is valid at every native column. Profile admission rejects
448 columns; RTTOV quality excludes 11,036 more. The fixed cost support is
54,504 columns × 7 channels, with global Z=381,528 and baseline J=11.153458878209252.
Independent saved-array replay confirms the cost and masks. The global dot
relative error is 2.02e-16; sparse central differences on four original blocks
pass at both recorded epsilons. Gradients are baseline first-order results.

Three baseline-relative proposals use the same direction with alpha 1, 0.5 and
0.25. Each evaluates the complete domain. They lose 29, 18 and 13 supported
profiles because positive QC lacks positive native NC. The masks/weights are
not reduced or repaired. All proposals are rejected, so the recorded state is
`COMPLETED_NO_ACCEPTABLE_UPDATE` and accepted input-control increments are zero.
This establishes the prescribed bounded experiment, not a stationary solution
or improved satellite fit.

The [bundle](../../harness/evidence/native_satellite_case_2026-10-25/data/publication_manifest.json)
contains full-grid BT, support, gradients and control products, all candidate
BT/quality/reason fields, physical replay diagnostics and source hashes. The
NumPy-only public replayer verifies published arithmetic without executing
private kernels or RTTOV. A separate 129-call value-only replay reproduces the
saved applied outputs bitwise. Water changes use actual replay DEN×DELZ;
across-column sums have no horizontal area weighting or regional-mass meaning,
and precipitation/closed water, energy and number budgets are not certified.

This extends [[norm-actual-observation-2026-10-24]] and
[[actual-qr-transport-2026-10-24]] to a complete spatial case. It preserves their
local derivative/forward findings and the selected-map qualifications. Pixel
UTC, original navigation, historical number units, arbitrary whole-reference
pressure controls and full-host/RK/retained-memory adjoints remain outside this
evidence. [[KDM6AD Differentiability Audit]] and [[KDM6AD Forward Parity]] retain
their distinct derivative and operational f32 contracts.
