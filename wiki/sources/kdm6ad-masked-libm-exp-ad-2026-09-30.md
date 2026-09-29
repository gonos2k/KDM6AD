# Masked libm-exp adjoint (2026-09-30)

The float32 `ops::libm_exp` forward can produce `Inf` on a branch later
masked out by `torch::where`. Its old backward multiplied the zero cotangent
by `exp(100)=Inf`, returning NaN. A focused C++ test reproduced this failure.

The backward now substitutes a finite input only where the incoming
cotangent is zero **and** the local exponential slope is nonfinite. This
keeps the first and input-side second derivatives finite for the fixed masked
lane in the test; a nonzero cotangent
through the overflowing branch still produces `Inf`. The value-only forward
and other gradients are unchanged. This closes one AD dead-branch failure,
not general higher-order behavior when an upstream cotangent happens to cross
zero, whole-host AD, or physical input validity.

Related: [[KDM6AD Differentiability Audit]] and [[KDM6AD]].
