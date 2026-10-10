---
title: Team audit of native intake and analysis capture boundaries
type: source
date_modified: 2026-10-10
---
# Team intake/capture boundary audit

The [team report](../../harness/evidence/pr396_team_audit_2026-10-10/REPORT.md)
records source and synthetic-file checks from merged PR395. CLI input overrides,
paired receipt/checkpoint publication, selected masked-fill rejection, archived
namelist controls, final signature and failure-state evidence were repaired.
No physics, optimizer algorithm or historical artifact reader was changed.

Eight storage checks and an isolated NetCDF/mock-main flow demonstrate these
boundaries, not a native or RTTOV experiment. The actual running model remained
untouched while its pending continuation was replaced before any consumer ran.
The successful-run gate and fixed observation support remain required.

Physical matchup and unit/number-basis limitations remain separately declared;
the management score stays 54/75. Source identities, synthetic evidence and
pending real execution must remain distinct.

The follow-up separates the zero-mask quality-probe cost from the actual first
zero-control objective, corrects PH/PHB geopotential units without changing
arrays, and preserves original native float32 host eta layer masses. A saved
array reader can split host/local temperature differences into potential
temperature and Exner terms, and analysis/model water increments on the fixed
first-frame mass measure. Its synthetic algebra checks are preparation;
actual native output and analysis diagnostics remain pending. Unmeasured
boundary terms are not interpreted as zero or as a closed water budget.

Related: [[native-tq-case-progress-2026-10-10]],
[[real-tq-artifact-diagnostic-2026-10-10]].
