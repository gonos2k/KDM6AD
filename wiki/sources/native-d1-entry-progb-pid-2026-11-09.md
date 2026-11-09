---
title: Native D1-entry ProgB number-intercept tangents
type: source
date: 2026-11-09
---

# Native D1-entry ProgB number-intercept tangents

The [evidence packet](../../harness/evidence/native_d1_progb_pid_cpp_ad_2026-11-09/README.md) traces initial QG17 and BRS17 directions through the selected D1-entry `pre` ProgB state, before the later `pre1` and `pre2` rebuilds. On the active f64 branch, the merged `rhox` produces `cmg=(PI*rhox)/6`, then `pidn0g=((cmg*n0g)*g1pdgmg)/g1pmg` in source order. The recorded `g1pdgmg` is `6.000000000000001`; replacing it with 6 changes the baseline output by one f64 ULP. The 25 selected cases check source-order values; the resulting `pidn0g` is linked to the parent #564 entry slope and #563 factor. Opposing single-direction `pidn0g` tangents nearly cancel in the joint direction.

Existing native captures anchor baseline and joint endpoint entry QG/BRS and density; newly retained `cmg` and `pidn0g` lack separate independent native-host producer taps. Ten accepted pairs provide ten independent `cmg` differences, with a declared four-output-ULP floor for the small joint residual. Previously captured upstream native-17 density-cap crossings are distinct from the native-16 entry density boundary. Small extra pairs lack independent native cap capture.

This is conditional selected-column f64 evidence. Inactive ProgB retention, active boundary derivatives, melt amount `A` production, operational f32, physical units and budgets, host AD and GK2A–RTTOV cost sensitivity remain open. Scientific and physical-unit statuses remain `INCONCLUSIVE`; public CI replays archived evidence rather than rebuilding the private executable.
