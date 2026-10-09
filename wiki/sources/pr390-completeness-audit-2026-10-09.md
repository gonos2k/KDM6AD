---
title: PR390 team completeness audit
type: source
date_modified: 2026-10-09
---
# PR390 team completeness audit

The [Green/Red audit](../../harness/evidence/REPORT_completeness_pr390_2026-10-09.md)
at PR390 `ada6fc42` plus the local diagnostic packet independently checked
RTTOV source/object/input/output identity and actual extinction arrays, and the
MPI/short-host source, receipts and saved arrays. The minimum diagnostics are
complete in their stated scopes. Both smoke files are finite and their two
frames have all 254 variables bit-identical. The host path is experimental
mp337/variant2/dry-number1/value-only1, not operational mp137 or host AD.

Zero hydrometeor content/fraction was clarified separately from nonzero size
parameters. MPI runner hashing is explicitly post-run metadata-source hashing;
the original orchestration-source hash was not captured (Red's P2 evidence limit).
A new minimum MPI witness pins current Python/Fortran sources before/after
execution and preserves the October 8 result/logs. It supplies current captured
evidence without reconstructing the old missing source hash.
RTTOV's logged base is after the 1e-10 km^-1 minimum floor; the >20 km^-1 trigger
values are unaffected. Numerical data and
executed source captures are unchanged. No required production P1/P2 finding
was identified in this bounded review; earlier numerical closures retain their
original attribution.

The broader research remains incomplete: valid target-time native/independent
observation correspondence (R2), physical coordinate/admission policies (R1),
applied budgets (P1/S17), timestep dependence (T1), native multicolumn and unused
validation (C1/V1). The historical exit1 remains unexplained; a new independently
valid target experiment would not certify the old artifacts. Forecast/cycling,
release and calibrated sigma/bias are not introduced as first-attempt gates.

Related: [[pr390-small-diagnostics-2026-10-08]],
[[review388389-local-resolution-2026-10-08]],
[[native-target-artifact-diagnostic-2026-10-08]].

The user requested a PR at 2026-10-09 09:10 JST. Its
[decision checklist](../../harness/evidence/DECISIONS_pr390_followup_2026-10-09.md)
separates proposed sequencing/admission/regime/validation choices from executed
evidence. D1–D4 are OPEN; 1 K/zero bias remains the established exploratory baseline.
