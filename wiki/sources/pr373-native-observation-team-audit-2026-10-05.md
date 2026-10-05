---
title: PR373 native observation and cloud-shard audit (2026-10-05)
type: source
date_modified: 2026-10-05
---

The [fresh Green/Red audit](../../harness/evidence/CHECKLIST_pr373_team_audit_2026-10-05.md)
found that matching native pressure centers was insufficient to preserve native
T/Q: the historical reference blend still attenuated model layers and removed
top-level sensitivity. It also found the normalized cloud OSSE worker called a
clear-only receiver; the earlier mock hid that integration failure. These are
explicit corrections to the earlier assembly claims, without changing the
recorded numerical results of the earlier blended operator.

The normalized entry points now use reference T/Q only above the model top.
The normalized shard generates all-sky truth observations and uses the existing
frozen cloud evaluator and window. The generic normalized cloud callback checks
number/density/reference policy before freezing and binds its model mode to the
minimizer. Untagged custom callbacks and historical defaults retain their stated
caller-owned contracts.

The [new actual receipt](../../harness/evidence/REPORT_native_KMA_window_2026-10-05.md)
checks one retained column, two optimizer iterations and a separate 180-step
fixed-forcing window. Six fixed-parameter model-state endpoint arrays remain
bitwise equal to the earlier run, while the observation operator and its
covectors have changed. Actual serial/spawn cost and QV covector agree bitwise.
These results do not establish all-field decomposition parity, convergence,
forecast skill or physical observation/error calibration.
