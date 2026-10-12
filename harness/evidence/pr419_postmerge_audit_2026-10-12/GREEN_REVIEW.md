# Green review: PR419 post-merge verification fixes

## Scope

I reviewed the PR419 report, source-binding changes, portable oracle tests,
current PR418 result records, and the linked wiki note. Source checks confirm
the new direct-source list includes `legacy.NATIVE_READER`, and both preflight
and capture use that list. The failure snapshot returns live hashes, allowing
`run_capture` to record the changed reader hash without failing a second time
while constructing the receipt.

This review covers the PR418 driver, capture audit/source snapshot, saved
channel receipts, and affected test discovery. It is not whole-model or
operational certification.

## Source-provenance coverage

The staged-reader tests cover two different boundaries. The source-binding
tests use a fake capture to verify that mutation after geometry/input
preparation is rejected before the one-shot marker, and mutation during capture
fails the final audit. The portable capture test runs the real capture body
with a synthetic H, mutates only a temporary reader copy during a callback,
and verifies that the failure receipt records different before/after hashes,
retains the returned numerical state, and publishes no checkpoint. No original
reader is edited or imported from the staged copy.

The local full-driver probe in `graphify-out/full_synthetic_driver.log` reports
`RETURNED_CASE_DIAGNOSTIC`, a `CROSSCHECKED` nine-channel audit, IDs 8–16, five
synthetic H callbacks, and zero actual RTTOV calls. Its probe script uses real
KDM/L-BFGS with an injected synthetic H and the existing private reference and
template inputs. This is stronger integration coverage than the portable
tests, but it remains a synthetic-observation run, not an actual nine-channel
RTTOV analysis.

The staged-reader baseline reproduction in
`graphify-out/baseline_reader_gap.log` demonstrates the prior omission: the
driver returned `RETURNED_CASE_DIAGNOSTIC` after a copied geometry reader was
changed during preparation, and the reader was absent from `case_sources`. The
reproduction made no H, M, or RTTOV calls and left the original source intact.

## Channel and saved-result consistency

The two actual added-channel value-only calls remain the only post-PR417 H
execution: channels 8/9 at saved indices 6/7, with `rad_quality=32768` for
both channels at both times. Channels 10–16 remain the hash-bound PR417 values.
The result remains a channel-wise composite; the all-nine quality-zero gate
fails, and no accepted nine-channel analysis or new scientific-case
checkpoint is claimed. The L1B source check binds nine channels and source
DQF0 separately from the returned RTTOV model-quality flags.

PR418's old `ARTIFACT_MANIFEST.json` and PLAN are correctly treated as records
of the merged 569892ae tree. The fixed driver now differs from that committed
hash because it includes the reader binding; the old H, BT, plan, quality flags
and PR417 packet files remain preserved. The report and wiki distinguish this
new source fix from the old execution receipts.

## Test discovery and current CI boundary

The new source-binding and capture regressions are under `oracle/tests`, which
the Oracle workflow collects with `cd oracle && python -m pytest`. The capture
test uses synthetic H plus a mocked, explicitly synthetic provenance gate, so
it does not require the private references that make the older PR408
seven-channel capture test skip in public CI. The g33 harness workflow remains
scoped to `harness/tests`; the new tests are intentionally in the Oracle test
tree.

The portable additions are seven collected cases: three source-binding cases
and four capture cases, including staged-reader modification and removal. The
final affected local run passed 32 and skipped one in 4.16 seconds: those seven
cases, 25 single-column core tests, and the older private-reference PR408
capture test. The source-removal case verifies a present before-hash, a `None`
after-hash in the failure receipt, retained numerical return, and no
checkpoint. The earlier combined 39-pass/5.02-second run and full 1846-pass/
33-skip oracle run predate this last missing-reader snapshot refinement; they
remain explicitly earlier stages in `VALIDATION.json`, not final verification
of this corner case.

At this review, GitHub main checks for 569892ae were green for oracle-ci,
g33-harness-ci, and port-ci. Those runs predate the uncommitted PR419 fix and
therefore do not validate the seven new cases. The final 32-pass/one-skip local
run and the local full-driver probe are separate from those main CI runs. The
next Oracle CI run after these changes are committed is the public check that
will collect the new cases.

The recorded local full-oracle run passed 1846 and skipped 33. In that run the
older PR408 capture test skipped because both pinned WRF `wrf_timeseries.F`
and `.f90` paths were absent; replay of the old PR417 source guard is therefore
currently unavailable. The reason for these path absences is not established,
and no substitute source was restored. This current dependency limit does not
invalidate the saved PR417/PR418 BT or flag results, nor the earlier focused
private-reference checks. Validation timestamps carry both UTC and KST because
this packet began on Oct 12 KST and completed after midnight Oct 13.

## Remaining limits

No new scientific-case RTTOV/H evaluation or native-model run occurred during
this post-merge fix. The synthetic H callback did run five times in the local
full-driver probe, and that probe did execute KDM M and L-BFGS. The actual
WV063/WV069 flags remain 32768; strict convergence, observed temporal fit,
atmospheric truth, process attribution, forecast skill, and other-date
repeatability remain outside this evidence.
