---
title: Jul19 actual ten-minute local observation window
type: source
date: 2026-10-12
---
# Jul19 actual ten-minute local observation window

Before other-date work, the user requested a window using Jul19 forecasts.
[[pr412-natural-native-process-case-2026-10-12]] supplies the admitted native
05:55:40 ocean39-layer background. The existing dual/window solver now runs61
20s local transitions with its forcing held, and observes actual separate AMI
nominal05:56/06:06/06:16 at indices1/31/61. One initial51-coordinate T/Q prior
and21 equal-scale Huber terms are used. Native centre/interface pressure,
surface/reference/geometry and background optical dry density are held;
internal M dry density remains state-dependent. This is a longer conditional
local experiment, not saved later host states/full host cycling. Additive time
errors and nominal filename-as-model-UTC are explicit research assumptions:
pixel UTC remains null; raw scene OBT has56s offset and planned UTC is earlier.

One actual RTTOV/KDM/AD/minimizer run returned all-slot audit/state/control/full
gradient checkpoint. TotalJ26.649841376→20.294560081 (23.84735% reduction),
prior0.199648864, gradientLinf0.385080631, strict convergence unmet/UNKNOWN.
Actual2iterations/4evaluations+1audit give15 logical H callbacks, all7 quality0.
Accepted QC is0 at each slot and local BT repeats after the first transition;
three actual observation vectors differ. No process-rate attribution, new
R_M/I_M contrast, atmosphere truth or full-host forecast claim follows.

[[pr413-cloud-bounded-convergence-2026-10-12]] remains a separate single20s
budget comparison. Only Jul19 has completed actual analyses; Jul20/21 have L1B
intake but remain native-pending. Extra directory metadata search found a
Jul19 hourly00–12 candidate lacking separate completion/identity proof and a
Dec23 MP8 candidate with different lineage; neither is admitted silently.

Evidence: [report](../../harness/evidence/pr414_ami_window_2026-10-12/REPORT.md),
[time/input inventory](../../harness/evidence/pr414_ami_window_2026-10-12/INPUT_AND_TIME_INVENTORY.md),
[actual result](../../harness/evidence/pr414_ami_window_2026-10-12/RESULT.json),
[channel table](../../harness/evidence/pr414_ami_window_2026-10-12/WINDOW_CHANNELS.csv).
