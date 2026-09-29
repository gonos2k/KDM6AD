# ProgB volume at three microphysics handoffs (2026-09-30)

The Python one-step coordinator applied a second activation gate after each
of the entry, post-melt and post-freeze ProgB calls. That gate replaced the
returned `brs` with zero for an inactive cell, although Fortran ProgB leaves
its `INTENT(INOUT)` volume untouched and the C++ port already forwards each
returned volume directly.

A focused float64 case with `qg=0`, `brs=5e-16<BRS_MIN` and otherwise zero
hydrometeors showed that D1, D2–D4 and cold each received zero before the
change. They now receive the trace volume and its local input derivative 1.
The final output gate was addressed separately later the same day. Its former
`qg>qcrmin` mask erased ProgB's active volume for positive trace `qg`. The
default Python path now keeps that result when `qg>0`, while clearing volume
and its derivative in exactly empty cells. The opt-in midpoint path retains
ProgB's direct output. The focused test covers both default lanes. An initial
unconditional handoff failed the built-library cross-tree JVP check because
one empty cell retained an f64-only derivative of order `1e-21` where C++
returned zero. The historical `qg<=qcrmin => bg=0` census describes its
measured f32 trajectory, not a universal ProgB output rule.
The older low-`qg` residue regression has no retained cellwise partition by
exact zero versus positive `qg`, so this change does not close that parity
question.

This is an output-boundary rule, not physical approval of trace-sized moment
pairs or general host parity. The physical trace-density and applied-budget
questions remain open under S10. Some older comments in pinned C++
`coordinator.cpp` describe a qg-only output mask; its executed final
assignment is `new_state.brs = bg4`.

Related: [[KDM6AD]] and [[KDM6AD Differentiability Audit]].
