# Calibration input binding and DOM comparison qualifications

Follow-up to the 2026-10-13 KST review of main `741172da` (PR419/420).
The completed Edd7 baseline and finite-budget DOM9 analysis/audit/checkpoint,
matched DOM7 comparison, joint M response and one gradient direction remain
closed in their stated scopes. This follow-up performs no native integration,
RTTOV call, optimizer run, additional directional check or new data acquisition.

Future shared capture now hashes the **actual calibration JSON path read by
`ami_bt_coordinate.read_kma_calibration`**, in addition to its Python reader.
The same input is included in the case driver's preflight before preparation
and carried into the live capture checks for both seven and nine channels.
The existing receipt's source-hash field now includes that input hash. Missing
inputs at capture entry are recorded as missing and rejected before analysis;
modification or disappearance during capture prevents checkpoint publication
and remains visible in the failure receipt. Checks cover preparation and
whole-capture boundaries, not every internal RTTOV subprocess or transient
change-and-revert between checks.

The original DOM pair's calibration-JSON pre/post history remains unproven.
Neither its PLAN nor recorded hashes, BTs, checkpoints or executed PR420
scripts are rewritten. Future changes to the shared capture/helper sources
are attributed to this commit; historical source claims remain tied to
`741172da` and the earlier recorded revisions. This is an input-provenance
fix, not a change to CWT, KDM, AD, loss, solver, priors, channel support or
the original Edd3 default.

[DOM_EFFECTIVE_SETTINGS.json](DOM_EFFECTIVE_SETTINGS.json) reads the twelve
retained DOM7/DOM9 case configurations. Each requests DOM1, **eight streams**,
`dom_accuracy=0`, `dom_opdep_threshold=0` and solar off. The configured
`plane_parallel=False` and `lambertian=False` flags are preserved as input
metadata. DOM applies strict plane-parallel propagation and a Lambertian
thermal surface boundary under its own rules; a false input flag does not
establish spherical propagation or a non-Lambertian DOM boundary. These are
documented/source-confirmed DOM rules, not newly instrumented effective flags
of the original binary. See the [RTTOV14 user guide, §8.4.2 and Table8.11](https://nwp-saf.eumetsat.int/site/download/documentation/rtm/docs_rttov14/users_guide_rttov14_v1.1.pdf).
Source-to-original-executable attestation remains unavailable.

Edd7 versus DOM7 therefore changes the thermal method and its coupled effective
geometry/surface treatment. Identical supplied angles, surface inputs and
fixture bytes except the solver value do not establish an identical internal
H. DOM7 versus DOM9 changes support within the same DOM variant. The recorded
Edd3 warning remains preserved; DOM success is not a repair to that method.

[NUMERIC_REVIEW.json](NUMERIC_REVIEW.json) recomputes the review's arithmetic
from public captures, channel residuals and direction endpoints only:

| Quantity | Value |
|---|---:|
| Final common-seven Jo, DOM9 minus DOM7 | −0.0109116234811 |
| Final state-prior difference, DOM9 minus DOM7 | +0.0126360322078 |
| Final common-seven Jo plus prior, DOM7 | 6.3318615335731 |
| Final common-seven Jo plus prior, DOM9 | 6.3335859422999 |
| Common-seven plus-prior difference, DOM9 minus DOM7 | **+0.0017244087267** |
| Added-two Jo decrease | 0.0597634072434 |
| Added-two decrease / its initial Jo | 1.15044% |
| Added-two decrease / total DOM9 Jo decrease | 3.18588% |
| Original returned DOM9 J | 11.4686595551827 |
| Existing negative-direction diagnostic J | 11.4681507087259 |
| Returned J minus negative-direction J | **0.0005088464568** |
| Saved full-gradient L2 / prior-gradient L2 | 1.0404023400 |

The small common-channel Jo decrease does not establish superiority after
including the unchanged prior. The two optimized points have different
objective support and neither is stationary; there is also no saved nine-channel
evaluation of the DOM7 returned point. Filling that value is unnecessary for
the present claims. The loss fraction is arithmetic, not causal information
or a process attribution. The lower diagnostic endpoint remains a diagnostic
and does not replace the original returned checkpoint. The original pair's
unbound calibration history qualifies cross-run comparisons as before.

The source/guard tests use temporary inputs and synthetic H with real KDM,
minimizer and capture where applicable. They do not reproduce the private
analysis. Relevant oracle tests pass **55**, and the existing seven-channel
synthetic capture test passes **1**. They cover valid input binding, missing
calibration before preflight/capture, preparation mutation and modification/
deletion during capture for both selected supports. No failed calibration
run is attributed to the original PR420 experiment. Ruff and diff checks pass;
CI and graph coverage are recorded in [VALIDATION.json](VALIDATION.json).

The [Green](GREEN_REVIEW.md) and [Red](RED_REVIEW.md) reviews check these scopes.
Strict convergence, calibrated B/R, actual pixel UTC/interface identity,
independent dates, observed state truth and forecast/cycling skill remain
separate follow-up questions. No new completion gates are added here. A later
convergence experiment would retain the original background/observations/prior/
DOM and predeclare a bounded budget; this follow-up does not start it.
