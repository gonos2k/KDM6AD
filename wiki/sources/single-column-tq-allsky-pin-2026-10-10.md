---
title: Single-column T/Q all-sky routing and fixed microphysics parameters
type: source
date_modified: 2026-10-10
---
# Single-column T/Q all-sky route and parameter pin

The [integration report](../../harness/evidence/REPORT_pr393_tq_integration_2026-10-09.md)
resolves two conditional preparation gaps on reviewed e619. Original full-domain
analysis classifies background clear/cloudy H and activates four warm parameter
controls; that remains a valid existing joint-study path. The new bounded
`run_single_column_analysis` always selects all-sky at the singleton position,
keeps the physical background classifier as metadata, and fixes the parameter
prior with active=(). It reuses existing CVT, window, frozen factory and dual
solver without modifying physics, clear defaults, or adding pseudo-RH/retry.

T/Q-only initial controls retain full microphysical response through M; the
actual observation-slot M(xb) sets fixed seven-channel support. New synthetic-H
tests pass through two real KDM steps and show nonzero controls/prior, component
accounting, a direct QC covector, strict support rejection and a total-cost
directional relative difference 1.81e-9. Native interface identity remains a
caller obligation; the 39-level test uses synthetic dimensions.

The saved weak-state prior-adjusted cost 23.1226955332 and 13.035224% decrease
are conditional arithmetic, not an accepted analysis. The new native case and
real observation study remain unexecuted/open. The management score remains
54/75 after PR393 merged, with no extra points for this code/test contribution.

Related: [[pr393-residual-failure-preparation-2026-10-09]],
[[pr392-branch-coordinate-support-2026-10-09]].
