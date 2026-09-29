# ProgB volume after a sedimentation substep (2026-09-30)

The Python oracle previously applied a second gate after the per-substep
`ProgB` call: if both `qg<=qcrmin` and `brs<=BRS_MIN`, it replaced ProgB's
returned volume with zero. Inactive Fortran `ProgB_param` keeps its incoming
`brs`, and the current C++ coordinator already forwards `pre.progb.bg`
directly. The Python sedimentation reslope now does the same.

A focused float64 test with zero fall speeds, `qg=0` and
`brs=5e-16<BRS_MIN` failed before the change. It now preserves the exact
volume at the handoff and gives its local derivative 1. This is a numerical
source-semantics check on a deliberately trace/inactive state, not approval
of that moment pair as a physical graupel population. A fresh local C++
library also passed the existing two fixed cross-tree JVP/VJP fixtures; it
does not establish general f64–f32 raw-bit parity.

Related: [[KDM6AD]] and [[KDM6AD Differentiability Audit]].
