# S8 ProgB f32 zero-denominator derivative

The f32 ProgB operator intentionally computes raw `qg/bg` before the
`[RHO_MIN,RHO_MAX]` clamp. At an active cell with `qg>qcrmin` and `bg=+0` or
`-0`, the forward quotient is infinite and clamps to the appropriate endpoint,
but the raw division can leave nonfinite input gradients.

A focused test uses one inactive zero/zero cell, one regular active cell, and
two active cells with positive and negative zero `bg`. It backpropagates the
sum of all ProgB outputs. The unmodified source fails the finite-gradient
assertion; the guarded source passes `ctest -R '^progb$'` in the same local
macOS CPU build. This baseline failure and candidate pass were both executed.

The change divides by one where `bg==0`, then explicitly selects the old
clamped endpoint for active zero-denominator cells according to the sign of
zero. Other active f32 cells still use the original quotient. Inactive public
outputs stay masked as before. This defines a finite derivative on the exact
zero-denominator branch; it does not claim differentiability across the branch
or validate all masked divisions in the full KDM/host graph. S8 remains OPEN.
