# Red review: PR421 follow-up

Reviewed the current additive follow-up against its sources and the preserved
PR420 records. I found no remaining actionable issue in the reviewed claims or
calibration guard scope.

The calibration binding targets the same `_CAL_PATH` that
`ami_bt_coordinate.read_kma_calibration()` reads. The seven/nine-channel driver
preflights that file before creating output, and the shared capture snapshots
it at entry and after analysis. Missing-at-entry is rejected before H or
optimizer callbacks and leaves a failure receipt without a checkpoint;
mutation or removal during capture is retained in the failure receipt and
prevents checkpoint publication. The 55 related oracle tests cover both
supports for preflight, preparation mutation, and modification/removal during
capture. The existing synthetic seven-channel capture also passes. These are
portable/synthetic guard checks, not a replay of the private PR420 analysis.

The source/record review supports the DOM wording with one important scope
condition: RTTOV enables its strict plane-parallel DOM path when aerosol or
hydrometeor scattering is enabled; the captured cloud fixture enables
hydrometeors. DOM's own routine documents a Lambertian surface assumption, and
the guide says DOM ignores the configured Lambertian option. Thus the report
properly preserves `plane_parallel=False` and `lambertian=False` as configured
inputs while describing documented DOM-effective behavior separately. The
original executable was not instrumented for these internal flags, so no
source-to-executable attestation is claimed.

The public-file arithmetic in `NUMERIC_REVIEW.json` matches the recorded
captures and direction endpoints. It does not imply common-objective
improvement, strict convergence, or causal attribution. The calibration JSON
was not hash-bound in the original PR420 run; the new guard cannot repair that
historical gap. PR420's plan, captures, outputs, executed scripts and all 41
manifest entries remain unchanged. No KDM/AD/loss/solver/prior/support-map
change or new private RTTOV, native-model, optimizer or finite-difference call
was part of this review.

Remaining limits are accurately stated: original-pair calibration history,
source-to-original-executable attestation, strict convergence, pixel UTC and
interface identity, independent-date replication, observed-state truth and
forecast/cycling skill. `VALIDATION.json` records 55 related tests passing, one
legacy synthetic seven-channel capture passing, Ruff and diff checks passing;
GitHub CI had not yet been captured at review time. Graph coverage does not
include the private RTTOV source; that source and the public user guide were
checked separately.
