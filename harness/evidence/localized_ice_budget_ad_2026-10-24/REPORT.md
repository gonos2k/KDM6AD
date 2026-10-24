# Two residual witnesses and bounded norm_actual derivatives

The output-path P2 is handled separately in PR #439. This evidence follows
PR #438's completed value comparison, using two original native B512 blocks.
There is no operational physics/default/install change and no new host, DA or
RTTOV run. The previous Legacy/native/RTTOV milestones remain within their
accepted scope.

## 1. Four original-block trace replays

The frozen executable `b8051d8b…` evaluated `norm_actual` and `raw_actual` at
chunks 34 and 40. Each new trace-on response is byte-identical to that mode's
original domain response. The trace controller source was frozen before the
four calls. Each call took about 1.20–1.23 s and emitted about 42 MB of trace;
raw bulk traces remain private. Each has 59,904 water-stage rows, 19,968 ice
recurrence rows and 512 common bottom records, all verified against the
request/response/source and captured receipt hashes.

Every selected water field at `pre_sed` equals the original request bits;
`post_micro` equals the raw output bits. DEND/DELZ equal request DEN/DELZ at all
512×39 cells; QV/QC are unchanged across sedimentation. The accounting order
matches the earlier deterministic delta-product contract. Public stage archives
and per-case selected profiles preserve both variants separately.

For `norm_actual`, all water entries below are kg/m² per column:

| Witness | Main QR change | Total reported precip | Post-sed→post-micro six-species change | Raw final residual |
| --- | ---: | ---: | ---: | ---: |
| (113,76), chunk34 row254 | −0.04893712319213363 | +0.05399563761291434 | −1.633593431311421e−15 | +0.005058514420779037 |
| (131,88), chunk40 row8 | −0.1817715693076849 | 0 | +8.396960349509847e−16 | −0.18177156930768423 |

At these witnesses QS/QG transport changes are only rounding scale; ice QI
changes are zero or about 1e−21 kg/m². The corresponding raw_actual witness
residuals agree to rounding. All 512 columns per case have ice state-change
plus actual bottom departure within the diagnostic roundoff gate. Actual and
reported bottom ice contributions are zero throughout these blocks. This
bounds the present evidence: a nonzero ice-ground flux conversion is not tested.

The two large residuals are localized to **main QR transport/surface
accounting**, while the later six-species microphysics totals cancel to
rounding at these witnesses. This does not isolate an internal main-rain
interface rule; actual main-rain departures/arrivals are the next measurement.
Cleanup remains separate: witness34 removes zero; witness40 norm_actual removes
6.949570699756783e−12 kg/m². This is a fixed input DEN×DELZ ledger, not a physical
regional mass integral, RK measure or conservation certificate.

## 2. B512 state+forcing and applied thermo-finish AD

An isolated dylib (`e412328b…`) links the already frozen v6 core archive
`0bf2c94d…` and existing C bridge object `a95211b6…`. No physics TU was rebuilt
and no library was installed. The fresh-process ABI layout is im=1/kme=39/
jme=512. Both value-only and recorded forward match the original norm_actual
state bits across the entire block before derivatives are used.

The operator returns raw12 + thermo-finish5, with explicit old-state finish
pullback and QC/QV cleanup. It does **not** differentiate precipitation, water
closure, all-hydrometeor cleanup, native dynamics, retained-memory consumption,
profile/RTTOV cost, or HVPs. Directions/cotangents are localized to row254 or 8,
but every forward, adjoint, tangent and FD comparison retains all 512 columns.

### Original raw-direction failures retained

All raw JVP/VJP dot checks agree, but cloud_mass/number/mixed fail the centered
FD gate in both chunks. The failure reports and full products remain under
`raw_034`/`raw_040`, with `passed=false`.

The source/data show why these are unsuitable unrestricted smoothness samples.
Many NN inputs equal the entry clamp minimum 1e8. An actual B512 probe with
NN direction 1e6 and epsilon 1e−4 gives:

| Quantity | Both witnesses |
| --- | ---: |
| Baseline NN | 100000000 |
| Positive endpoint | 100000100 |
| Negative endpoint after clamp | 100000000 |
| JVP / inward one-sided FD | 1000000 |
| Outward one-sided FD | 0 |
| Centered FD | 500000 |

The selected AD branch is an inward-side clamp Jacobian; the map has no single
classical derivative for both raw directions at that tie. Cloud-mass raw seeds
hold BG fixed while QG changes; their QG/BG ratios sit at/near900 and the tested
steps cross the ProgB density clamp. These checks identify concrete clamp-crossing
contributions, without proving a unique explanation for every v1 field
discrepancy. Dot consistency alone would not establish forward accuracy.
No physical formula or tolerance was changed to turn these failed tests green.

### Separate entry-interior/pair-direction evidence

The same native base and same library are tested with paired entry moment
scaling and NN entry-interior support. Number-only NC/NI/NR components remain.
The exact support/limits are in the [operator contract](../../../docs/LOCALIZED_ICE_BUDGET_AD.md).

| Direction | Chunk34 best FD tolerance ratio | Chunk40 best FD tolerance ratio |
| --- | ---: | ---: |
| T/Q | 0.00006808 | 0.00013525 |
| Paired active moments | 0.00299655 | 0.00315510 |
| Number; restricted NN support | 0.16633905 | 0.02696305 |
| DEN | 0.04826786 | 0.04407059 |
| PII | 0.00007342 | 0.00011021 |
| P | 0.00017271 | 0.00015822 |
| DELZ | 0.19613591 | 0.07462085 |
| Mixed | 0.00010861 | 0.00021224 |

Ratio≤1 passes. **All 16 direction/case gates pass**, with worst dot relative
error1.2533539430096044e−15. Only **66/80 individual epsilon trials pass**;
14 failed trials remain in the JSON/NPZ. Each direction has at least two
passing epsilons; success requires all 17 fields at one common epsilon, not
an average over fields. The worst best-per-direction ratio is0.19614, not the
maximum over every trial. All stored off-target products are zero for these
seeds only.

This is bounded subspace evidence for two native B512 maps. It does not close
the failed raw directions, every downstream clamp, all moment coordinates,
physical number units, or the prior unscaled NCCN stress limitation. The
explicit thermo branch masks are checked, while internal KDM limiter/schedule
signatures are not exhaustively recorded. The existing whole-reference-pressure
RTTOV discrepancy and observation-time limitations are unchanged.

## 3. Provenance, noninterference and validation

Public product archives expose the full input, cotangent, adjoints, eight
seed/tangent sets and every FD array. Raw v1's exact executed verifier source
is archived; the current verifier implements both families and has additional
trace/tie guards. Its pair-run source hash matches the current file. The
one-sided probe is tied to the admitted requests/responses by a separate
provenance receipt. Complete raw trace streams and dylib stay private.

Within-variant trace off/on first-order comparisons are recorded separately;
the mixed direction comparison is not a full-Jacobian noninterference proof.
The final CLI returns nonzero on a failed scientific gate after writing its
negative evidence. That CLI hardening left the mathematical functions
AST-identical; the final pair sweep reproduces every prior pair product bit.
The exploratory pair source is archived separately. Call accounting totals
512 localized KDM forward evaluations (including retained exploratory sweeps),
not a repeat of the 129-block full-domain campaign. Final checks and per-task
counts are in `validation.json` and the manifest.

Current next steps are main-rain boundary transfer tracing and candidate
integration with native prep/EOS/profile/RTTOV. No unrestricted derivative,
closed-water, native full-host AD or forecast-improvement claim is made here.

The numerical map and derivative evidence here are fp64 research calculations;
operational f32 rounding and Legacy parity are separate contracts. Archived
directions are replayed as stored, rather than requiring cross-platform
transcendental seed regeneration to be bit-identical.
