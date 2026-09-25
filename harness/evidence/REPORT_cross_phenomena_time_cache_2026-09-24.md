# X5: variable intervals, restart origin and cache dependencies

This verification-only pilot uses two declared radiation-like exchange
intervals. The rate unit is **W/m²** and the accumulated-unit label is
**J/m²**; it does not assume all process rates have unit s⁻¹. The independent
plan specifies exact interval IDs, start/end times and consumer revisions.
Each sample is a piecewise constant or intentionally held rate over its
declared interval; `rate × duration` is not an exact integral of unmeasured
within-interval variation.
Received producer records cannot remove an expected interval by shrinking
their own manifest.

For the synthetic rates `F=(2,8) W/m²` over durations `(0.2,0.8) s`, the
correct integrated amount is `2*0.2+8*0.8=6.8 J/m²`. Multiplying the summed
rates by the final interval would give 8 and is rejected by the test's
independent expectation. A checkpoint after interval `a` records 0.4 J/m²
as of 0.2 s. Integrating only interval `b` yields the same 6.8 J/m²; a replay
that supplies `a` again is refused. The checkpoint must name an exact plan
prefix, its declared cumulative-origin time and the complete independent
plan's SHA-256 (including dependency revisions). A same-named plan with
changed earlier optics is rejected. An empty completed prefix cannot carry a
nonzero prior exchange. Its **numeric** prior amount
is a trusted checkpoint input, not independently reconstructed from a prior
native run.

A record may intentionally reuse a rate across both intervals when its
producer time precedes them, its validity window covers each complete
interval, and its required dependency revisions match the consumer plan.
The pilot declares `state`, `geometry`, `parameters`, `optics` and `units` as
required dependencies for this example. Changing any one, using a record
after its validity horizon, or accepting an unexpected/missing/duplicate
interval is rejected. This distinguishes a declared held coefficient from an
accidentally stale cache. It does **not** prove that the upstream producer
increments those revisions whenever the underlying data change.

Thirteen focused synthetic tests passed locally with warnings treated as errors.
They include signed rates, nonfinite/boolean payload rejection, rate-unit
mismatch, schedule gaps, restart double-counting, and overflow refusal. The
unit labels and rate-to-amount dimensional relationship are declared by the
example; the generic checker compares labels but is not a general unit
algebra package. No RTTOV, real radiation solver, native host restart, or
physical time-convergence experiment was executed. X7/X11/X12 retain those
separate completion conditions.
