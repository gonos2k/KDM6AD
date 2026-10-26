---
title: Native trace guards and saved QNC budget — 2026-10-27
type: source
date: 2026-10-27
---
# Native trace guards and saved QNC budget

The post-PR457 review found that the V2 moment overlay could overwrite a
pinned Fortran input through `--report`, even after a blocked plan. The fix
validates the report destination before planning/applying, creates only a fresh
report, refuses input aliases and source-directory symlink escapes, and keeps
source mode bits on apply. The QNC reader now rejects mislabeled `LIMIT_HIT`
records and fractional/boolean/string run settings. The 28-file PR457 packet
is unchanged; its original replay remains pinned to its original reader. A
separate companion replay checks that the hardened reader reproduces both
saved cases exactly without changing that historical packet.

Using the saved target-cell binary32 operands as exact rationals, the
alpha0.25 post-limiter local residual is approximately `−165,989.840` in the
host mass-coordinate raw number arithmetic; control is `+25,776.334`. The
new-mass-normalized values are `−1.838040504` and `+0.285426801`, distinct
from the executed REAL4 final QNC values `−3.814399242` and `+3.442540646`.
The saved-operand comparison excludes upstream changes a higher-precision
integration might create. It does not establish physical NC units or a
shared-face/domain number budget. No new model, RTTOV, accepted update, or
second assimilation call was made.

See [review and equations](../../docs/NATIVE_TRACE_GUARDS_AND_QNC_BUDGET_20261027.md).
