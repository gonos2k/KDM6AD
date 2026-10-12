# Red review: PR419 post-merge verification fixes

## Disposition

Both reported verification omissions are resolved in the reviewed worktree. No
new physics, AD, solver, or radiative-result finding was demonstrated.

## Source provenance

The new nine-channel driver now includes `legacy.NATIVE_READER` in the shared
direct-source set used by preflight and capture. Preparation compares the
reader hash again after geometry/input construction; capture snapshots return
live hashes before and after the analysis. A mismatch prevents accepted-state
checkpoint publication and is retained in the failure receipt.

I independently reproduced both boundaries with a temporary staged reader;
the original hash-bound reader was untouched. Changing the staged reader after
the synthetic geometry use fails before the one-shot marker and capture. A
change during fake capture makes the final source audit fail. The separate
portable capture test also changes a staged reader during synthetic H and
verifies the capture failure receipt has differing before/after hashes and no
checkpoint. PR417's original plan separately binds the reader used by its
historical H preparation.

## CI coverage

The new nine-channel capture/audit and source-binding tests now live under
`oracle/tests`, which public oracle CI collects. The tests use synthetic H and
staged or mocked provenance; they need no private native/reference inputs and
make no RTTOV call. Root reports the combined focused set passed 39 tests in
5.02 seconds. The local full-driver synthetic-H check also returned
`RETURNED_CASE_DIAGNOSTIC` with the nine-channel audit `CROSSCHECKED`; it used
the existing private reference/template, real KDM M and L-BFGS, and zero actual
RTTOV calls. That local check is separate from portable CI evidence.

## Evidence still bounded

The source guard and tests do not change the saved WV063/WV069 values or their
quality flags. Both added channels remain at model `rad_quality=32768` at both
saved times, so the all-nine quality-zero analysis gate still fails for these
inputs. No accepted nine-channel analysis or checkpoint was produced. There was
no new actual H/RTTOV call, H05, native host run, observation acquisition,
06/07 observation pairing, or scientific-case optimization in this audit.
Strict convergence, other-date repeatability, temporal fit, atmospheric truth,
process attribution, forecast skill, and cycling remain outside the evidence.

The original PR417 plan, BT, flags, and packet records remain bound to their
committed source version. PR419 changes only future nine-channel driver
provenance and portable test coverage.

The two-document Graphify fragment is a manual extraction with no paid external
model call. Exact manual token usage is unavailable; the fragment token fields
are zero rather than an estimated count.

The packet's `VALIDATION.json` is still pending the root full-oracle run as of
this review. The 39-pass count above is the completed combined focused set, not
the full oracle result.
