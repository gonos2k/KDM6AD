# X9: executed branch, finite crossing and event-time sensitivity

The retained KDM freeze-control tests already exercise a specific discrete
limiter. `test_freeze_cap_one_sided_derivatives` checks JVP and reverse
gradient on both smooth sides of its cap; `test_freeze_share_numerics` checks
a selected binding-share direction with JVP, VJP and independent central
difference. The two retained files passed **40/40** locally, with 18 inherited
`torch.jit.script` deprecation warnings. These results concern the executed
discrete map on selected branches, not a universal smooth derivative across
all physical regimes.

The new synthetic pilot keeps two other questions separate.

For continuous cooling `T(t)=T0-a*t` and a declared interior transverse
threshold crossing `T(t*)=T*`, the analytic event time is
`t*=(T0-T*)/a`. With `T0-T*=1 K` and `a=0.02 K/s`, `t*=50 s`,
`dt*/dT0=50 s/K` and `dt*/da=-2500 s²/K`. A separate temperature finite
difference matches the first derivative. Events on the window boundary,
outside it, or with zero/non-transverse cooling are **not** given this
interior-event derivative. No host cooling-event or reset equation is implied.
The rate derivative is evaluated as `-t*/a`, algebraically equal to
`-(T0-T*)/a²`. This avoids squaring a very large or small finite rate first:
the synthetic `a=1e155 K/s` example retains a representable derivative near
`-1e-308 s²/K` instead of incorrectly returning zero after `a²` overflow.
An unrepresentable final derivative is refused.
Likewise, a mathematically nonzero event time or rate derivative that rounds
to zero in binary64 is marked under-resolved, rather than reported as a
physical zero.

For the distinct **discrete** cap `C(x)=min(x,20)` with a strict `x>20`
branch, code selection at exactly 20 gives tangent 1. The left and right
one-sided differences are 1 and 0; a symmetric difference is 0.5. The kink
has no unique ordinary derivative. A finite input change from 19.9 to 20.1
changes the capped output by 0.1, whereas blindly multiplying the left
local tangent by 0.2 predicts 0.2. The former is a branch-changing finite
response, not a failed same-branch AD test.

Fourteen new synthetic tests passed with warnings treated as errors. They
cover the interior event time and its difference check, boundary/outside
classification, one-sided/crossing behavior, invalid rate/threshold inputs
and under-resolved event-time refusal. No KDM branch was smoothed and no
AD/FD tolerance was relaxed. A continuous saltation/reset derivative would
require an actual continuous event and reset model, which this project has
not supplied; the current KDM and RTTOV derivatives remain derivatives of
their implemented discrete operators.
