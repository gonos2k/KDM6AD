# Native-grid thermal-IR staging corrections

Preparing the frozen liquid input exposed two executable-boundary mismatches.
The writer required positive wind fetch even with solar disabled, and copied
the fixture interface count rather than the staged grid's count.

RTTOV `rttov_check_profiles` requires positive sea fetch only for active solar
sea-glint calculations. The writer now accepts the zero initializer only when
the copied case has one explicit solar-disabled setting in a single complete
namelist. Missing, duplicate, unknown or out-of-namelist settings keep the
positive-fetch guard. Negative and nonfinite input rejection remains in place.
No measured surface value is fabricated to satisfy the schema.

The copied namelist now gets `nlevels=nlayers+1`. The C5 packet has 39 native
layers plus 24 separately declared above-top reference layers: 63 layer values
and 64 interfaces. Retargeting this dimension does not remap the native grid or
change any physical field. Each count/precision assignment must be unique.

Validation uses the existing writer checks and three focused regressions:
zero versus negative/solar fetch, staged interface count, and actual full-writer
handling of false/true/ambiguous solar settings before filesystem mutation.
The original 71-check set passed before the final parser tightening; the three
directly affected checks then passed, including a copied-fixture staging test.
Some existing writer tests execute historical RTTOV fixtures; those are not
the new C5 liquid case. No C5 radiative or observational approval follows from
these input-boundary corrections. Numerical derivative and QC gates are intact.

The bounded next operator uses the current volume-coordinate research option
(10/10 cutoffs and unchanged coefficients), paired dry number/mass moments and
fixed observation density. An NC-only direction has zero qv/density tangent.
This defines that conditional experiment; it neither establishes the original
threshold calibration nor switches operational defaults or grants general S2,
S8, S11 or cycling approval. Deployment remains deferred.
