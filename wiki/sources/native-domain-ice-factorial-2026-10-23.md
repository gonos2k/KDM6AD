---
title: Executed native-domain ice factorial
type: source
date: 2026-10-23
---

# Executed native-domain ice factorial

The [four-arm execution](../../harness/evidence/domain_ice_factorial_2026-10-23/REPORT.md)
uses the endpoint packet from [[native-ice-factorial-2026-10-23]]: all 65,988
native columns and 39 levels, fixed 129 chunks, 516 actual KDM calls plus four
pilot calls. Ten single-thread workers execute each arm, arms sequentially.
This is offline dt20 physics from an MP137 endpoint, not the next native MP
input or a host/RK forecast/DA cycle.

Changing the first-ice handoff and/or arrival reduces the unweighted column
mean raw-state/reported-precipitation residual from about −6.44e−4 to −1.09e−4
kg/m² per column. Residuals remain; no arm closes the physical water budget.
Main-chain Legacy behavior, raw-flux units and historical number basis remain
conditional. Uniform offline interior cleanup/finish changes moist-theta memory;
no RK consumption or BT response was measured.

The source/manifest/executable and per-chunk request/response hashes, public
per-column diagnostics and selected raw response slices permit separate
coverage and arithmetic checks. [[native-ice-boundary-2026-10-23]] explains the
one-column loss mechanism, but endpoint regional records do not attribute all
remaining residuals. No alternate-map derivative certificate or operational
candidate adoption is claimed.

A subsequent [CLI output guard](../../harness/evidence/plan_output_guard_2026-10-24/REPORT.md)
rejects existing/aliased report files and input/run-tree overlap before dispatch,
then publishes exclusively. Temporary-file regression tests replace the model;
no regional physics rerun or altered scientific result is attributed to this fix.
