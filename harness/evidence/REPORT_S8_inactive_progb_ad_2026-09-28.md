# S8 inactive ProgB f32 derivative guard

`progb_param_torch` evaluated `qg/bg` before choosing the inactive output.
At an inactive `qg=bg=0` cell, the f32 operator path therefore formed `0/0`
even though `where(active, ...)` hid that value in the forward result. Its
backward graph could still receive a nonfinite derivative.

The C++ operator now uses a divisor of one only where `active` is false. The
inactive published outputs remain the existing midpoint density and unchanged
`bg`; active cells keep the original f32 division and clamp. This defines no
new derivative at a branch boundary and does not change the f64 oracle path.

A focused C++ test mixes one zero/zero inactive cell with an active cell,
backpropagates through all returned ProgB outputs, and requires finite input gradients.
`ctest -R '^progb$'` passed in a local macOS CPU build. This is a local
branch fix, not evidence that every masked division in the full KDM graph or
the native host AD path is finite. S8 remains OPEN.
