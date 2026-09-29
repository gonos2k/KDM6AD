# ProgB volume at three microphysics handoffs (2026-09-30)

The Python one-step coordinator applied a second activation gate after each
of the entry, post-melt and post-freeze ProgB calls. That gate replaced the
returned `brs` with zero for an inactive cell, although Fortran ProgB leaves
its `INTENT(INOUT)` volume untouched and the C++ port already forwards each
returned volume directly.

A focused float64 case with `qg=0`, `brs=5e-16<BRS_MIN` and otherwise zero
hydrometeors showed that D1, D2–D4 and cold each received zero before the
change. They now receive the trace volume and its local input derivative 1.
The final `brs` remains zero under a separate output gate, which this change
does not address. The test checks source handoff semantics on a deliberately
inactive moment pair; it does not approve that pair physically or establish
general float64-to-float32 raw-bit parity.

Related: [[KDM6AD]] and [[KDM6AD Differentiability Audit]].
