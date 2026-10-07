---
title: Internal research fixed error and bias integration (2026-10-07)
type: source
date_modified: 2026-10-07
---

The [internal checklist](../../harness/evidence/CHECKLIST_internal_research_2026-10-07.md)
keeps code integration separate from physical/data decisions and experiments.
An explicit fixed-error option in the normalized KMA full-domain route now
snapshots ordered channel sigma and full-field observation-additive bias for
both clear and all-sky loss/VJP. Defaults retain the old operation path.

The [actual C5 check](../../harness/evidence/REPORT_fixed_obs_errors_2026-10-07.md)
records cost/VJP/FD agreement (2.42e-9 relative in the new policy), with unchanged
support and no calibration claim. Raw innovations remain distinct from corrected
and standardized metrics. The full public-only suite is 1,644 passed / 93 skipped;
counts overlap with focused tests.

No new calibration data was supplied. The retained case has unresolved product,
pixel-time and measured geometry correspondence, so science approval is OPEN.
Prior/control choices, physical budget/time accuracy, different native grids and
independent initializations remain separate checklist rows.
