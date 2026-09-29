# Masked Wilt ratio adjoint (2026-09-30)

The float32 cold-process path computes raw mass ratios such as `qr/qi` to
match Fortran. At `qr=qi=0`, the raw ratio is NaN, the Wilt limiter maps its
forward contribution to zero, and the process gate is inactive. Previously
the hidden division still sent NaN into the input gradient. A focused C++
ice-accretion test reproduced that failure.

`wilt_arg` now keeps the original raw forward ratio. When both operands and
the quotient are finite and the denominator is nonzero, it differentiates
the same division.
An invalid raw ratio is a value-only branch with zero input derivative, so a
masked `0/0` cannot poison active cells. The test includes one inactive and
one active cell and checks forward equality against the value-only call,
finite gradients, an unchanged positive active rate and the valid ratio's
local derivative. The local cold and
end-to-end AD tests pass.

This is a branch-local derivative convention, not differentiation through a
zero denominator or approval of invalid physical inputs. S8 remains open.

Related: [[KDM6AD Differentiability Audit]] and [[KDM6AD]].
