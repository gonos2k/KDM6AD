# Green post-run consistency and coverage review

## Scope reviewed

I checked the PR418 `REPORT.md`, `RESULT.json`, `CHANNEL_RESPONSE.csv`,
`WARNING_SOURCE.json`, `GEOMETRY_CORRECTION.json`, `GEOMETRY_CORRECTION.md`,
`PLAN.json`, execution log and exit receipt against the opt-in driver, capture
wrapper, synthetic regressions, and `docs/INTERNAL_RESEARCH_CLOSEOUT_2026-10-12.md`.
This review made no H, model, RTTOV, or optimizer calls and did not rerun tests.

## Evidence consistency

PR418 declares two new value-only H calls, for time indices 6 and 7, with only
channels 8 and 9 selected. `EXECUTION.log` and `RESULT.json` contain exactly
those two calls. Both return finite BTs and `rad_quality=32768` for WV063 and
WV069 at both times. The nine-channel table marks channels 8 and 9 as new and
10–16 as reused from PR417; those seven reused rows match the hash-bound PR417
result and retain zero quality flags. `RESULT.json` records that no
simultaneous nine-channel H ran, no M/optimizer ran, the dummy cost was
discarded, and no observation fit was assessed. The failed all-nine
quality-zero gate is reported plainly, and no nine-channel analysis or accepted
checkpoint is claimed.

The warning receipt maps bit 15 to RTTOV's `qflag_delta_edd_ext_limits`
(Delta-Eddington extinction limits exceeded). I checked the recorded hashes
against the installed source files and executable. The receipt also says the
source-to-executable build is unattested and the triggering layer or
constituent was not diagnosed; the report preserves both limits and does not
waive the flags.

The geometry correction separates the native-column centre used for viewing
angles (j=103, i=48) from the AMI pixel used as a GEOS navigation donor
(row=289, column=49). Both stored time contexts retain the same geometry
values. No angle perturbation or added-channel H rerun was used to estimate a
pixel-centre geometry effect. The closeout document keeps this distinction and
does not claim an observed temporal fit, strict convergence, atmospheric truth,
forecast skill, or operational acceptance.

The PR418 plan digest matches `RESULT.json`, the recorded original PR417 result
digest matches the composite binding, all PR418 plan bindings match, and every
entry in the geometry correction's PR417 preservation hash list matches. The
installed warning source and recorded executable hashes also match. The
bound PR407 driver is restored to its PR417-pinned hash.

## Implementation and test coverage

The new driver verifies the full L1B channel order and payload hash for the
supplemental 8–16 path, compares selected BT and DQF values with the bound
point, and records the supplemental binding. The capture helper carries the
selected IDs and count through its trace audit, frozen-mask checks, receipt,
and private checkpoint. The default remains channels 10–16. The synthetic
capture regression confirms a successful nine-channel private/public
roundtrip and fails a background `rad_quality` flag of 32768 before LBFGS and
checkpoint publication. Separate extraction checks cover both spectra and
reject mismatched order, payload hash, and channel quality. The PR418 driver
now performs its own channel-count-aware receipt audit instead of calling the
legacy seven-channel audit; the new regression checks a valid nine-channel
cross-check and rejects altered support counts, frozen-mask loss, and loss of
the zero-cost probe mask. A separate import-guard regression confirms the
driver loads the hash-bound PR407 capture adapter by explicit path even when a
different `case_capture_adapter` is already cached.

Previously executed focused checks were:

| Check | Result |
|---|---:|
| PR418 nine-channel case, driver audit, import guard, and synthetic capture tests | 7 passed in 1.90 s |
| Existing capture storage regressions | 12 passed in 3.77 s |
| Original PR407 case adapter regressions | 8 passed in 3.10 s |
| Single-column oracle tests | 25 passed in 6.85 s |

The PR418 test name distinguishes RTTOV `rad_quality` from observation DQF.

## Remaining boundary

The actual added-channel H calls failed the quality-zero gate, so the
implementation's successful nine-channel path is demonstrated only with a
synthetic observation operator. The available actual evidence is a composite
of two added-channel H calls and the earlier seven-channel PR417 result, not a
single nine-channel execution. No actual nine-channel analysis, observation
fit, layer-level cause, or pixel-centre geometry sensitivity was established.
