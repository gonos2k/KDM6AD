# Fixed candidate: three separate physical questions

Baseline: PR #390 `ada6fc42`. This note synthesizes retained evidence; it is not
a new forecast, observation acquisition, retrieval-QA approval or causal diagnosis.
The selected native `(j=86,i=48)`, VIIRS `(row=205,col=27)` and AMI
`(row=320,col=48)` remain fixed. No neighbor is chosen using its BT residual.
Sigma stays 1 K, bias 0 and the existing seven-channel support stays fixed.

## 1. Why does RTTOV flag 32768?

The [source audit](NATIVE_warning_source_audit_result_2026-10-08.json) establishes
the source-defined total-layer-extinction limit of 20 km^-1. Gas participates;
this is distinct from the optical-depth limit 30. The stored zero hydrometeor
content and fractions therefore do not preclude this warning. Size parameters
include nonzero entries; zero content/fraction does not mean every hydrometeor-related
input is zero. The old lower-layer estimates
are proxies, not actual `ext/ltick` measurements. The [same-input isolated diagnostic](rttov_actual_extinction_2026-10-08/actual_extinction_profile_summary.json)
now records actual thickness and clear-sky/total extinction before/after clipping:
channel 8 triggers in one-based layers 65–66, channel 9 in 64–66, with zero
additional hydrometeor contribution. Retained direct/K outputs are byte-identical
to the original executable's rerun. These are actual arrays from the new
diagnostic build, not an attestation of historical binary internals; individual
gas species were not decomposed.

## 2. Are the instruments and model sampling the same cloud?

The [candidate report](REPORT_VIIRS_native_candidate_2026-10-07.md) records selection
from nominal centers and category/QA screening before looking at model BTs.
The [context report](REPORT_VIIRS_context_2026-10-07.md) provides same-overpass
retrieved cloud-top height 587.736938 m, temperature 296.570679 K and pressure
940.985229 hPa. These are retrievals, with unapproved cloud-height datum and QA;
they do not prove a single warm layer. DCOMP `EQualityFlag=17` remains undecoded.
CloudPhase byte 0 and AMI DQF 0 alone do not approve common physical sampling.

The VIIRS zenith angle is 68.926689 degrees. Its retained parallax coordinate is
about 1,525.19 m from the nominal center; it has not been applied as an AMI
correction or a model reassignment. The actual VIIRS scan bracket is
05:56:08.986512–05:56:10.773095Z under its product clock anchoring. Actual pixel
UTC, certified AMI clock conversion, footprint and common sampling remain open.
The previously reported AMI–VIIRS clock separation remains conditional. Nominal
AMI–native distance correction is closed and does not resolve these questions.

## 3. Why is the selected model column clear?

The [target artifact report](REPORT_native_target_artifact_2026-10-08.md) records
zero selected hydrometeor mass in all eight saved states, whereas the nearby
VIIRS retrieval reports a liquid category. Its KMA-coordinate IR105 model value
is 296.232817251 K in the first saved state, versus observed 291.302592155 K.
The reference O3/CO2, upper-atmosphere extension and surface assumptions remain
declared inputs. The residual does not identify cloud, ozone or number
concentration as a cause.

The historical native launcher returned 1. These arrays can guide diagnosis,
but a successful short control does not validate the target integration or
reproduce its cloud state. Temperature/humidity, ascent, mixing and applied
condensate changes along the fixed native trajectory have not been attributed
by this follow-up. Establishing those causes requires the corresponding native
trajectory and a separately valid run; warning attribution alone does not
answer that meteorological question.

## Acceptance boundary

New MPI and single-profile RTTOV controls answer narrow runtime questions.
They do not establish a first valid native–independent-observation case. Keep
R2, physical QA/time/footprint and the long-run termination cause open unless
their own evidence is obtained. Existing bounded AD/numerical closures and the
closed distance P3 do not need repeated arithmetic checks for this work.
