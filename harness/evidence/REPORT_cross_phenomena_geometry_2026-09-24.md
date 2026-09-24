# X6: changing measure and conservative overlap remap

The derivative part of this item already has a bounded G3 result. The retained
`oracle/tests/test_moment_transfer_probe.py` uses state, dry density and layer
thickness directions and checks, for its declared inventory coordinate,

    δ(rho*x*dz) = rho*dz*δx + x*dz*δrho + rho*x*δdz.

It also compares a nonuniform-direction JVP, VJP and independent central
difference for the two moment arrays. This is an **analysis-only**, opt-in
conservative ice function at fixed branch and selected direction. It is not a
native changing-grid or production-transport derivative. The retained 9
tests passed locally; 18 existing `torch.jit.script` deprecation warnings
appear in that suite. Its -W error run is not claimed: the inherited warning
becomes an error under that optional warning policy. No existing tolerance
was changed to hide it.

The new part checks a separately supplied synthetic linear remap matrix `P`
on a declared common overlap. It does not invent or run an operational
remapper. Source and destination weights and coverage fractions are explicit.
Their measures are assumed to use the **same physical unit and basis** before
entry; this small checker has no unit algebra or conversion label that could
detect otherwise equal-looking numbers from different measure units.
For `covered_area` normalization, destination value means the average over
covered area, and conservation checks `(w_dst*f_dst)ᵀP=w_src*f_src` plus
constant-field row sums of one on covered destination cells. For
`destination_area` normalization, uncovered area contributes zero to the
whole-cell value; the check uses `w_dstᵀP=w_src*f_src` and row sums `f_dst`.

In the 2-source-to-1-destination example, source measures are `(1,1)`, source
overlap fractions `(0.5,1)`, destination measure is `2` with overlap fraction
`0.75`, and source values are `(10,20)`. The common-overlap integral is 25.
Covered-area `P=(1/3,2/3)` gives destination value 16.6666666667 and
weighted total 25; destination-area `P=(0.25,0.5)` gives value 12.5 and
full-destination total 25. Reinterpreting either matrix with the other
normalization fails. Inactive source/destination overlap slots cannot carry
weights, and nonfinite/masked/non-float64 inputs are rejected at this
consumer boundary. By default the column and overlap measures use a
dimensionless relative criterion with **zero absolute measure tolerance**;
an optional absolute tolerance must be explicitly supplied in the same
units as the measure. This prevents a tiny covered area from disappearing
under an unrelated fixed numerical threshold. A positive overlap whose
measure product rounds to zero is refused rather than certified as zero.
Boolean tolerances are rejected.

The eleven new synthetic tests passed with warnings treated as errors. The
retained nine G3 tests passed without warning escalation. These two evidence
tiers are not nineteen independent meteorological cases. No native model
levels, RTTOV profile or operational pressure writer were changed, and the
synthetic remap is not a validation of a real host regridding operation.
