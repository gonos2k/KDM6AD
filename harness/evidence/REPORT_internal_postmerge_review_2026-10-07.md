# Internal research post-merge Green/Red review

Baseline: PR #382 merge `a4566024e25fe23d6e72fc73e14301cd0e5fbe7e`.
The current source and first-observation packet were reviewed separately from
the dirty canonical/private-host tree. No model/reanalysis data was acquired,
no institution was contacted, and no new native/RTTOV/host forecast run occurred.

## Reproduced and resolved input-validation gap

`_freeze_fixed_obs_errors(y, [True, 1.0], None)` accepted sigma `[1.0, 1.0]`.
The same mixed-type bias accepted `True` as a 1 K observation correction. The
old dtype check rejected pure boolean inputs, but a mixed sequence had already
promoted booleans to real values before the check.

A small pre-coercion check now rejects surviving Python/NumPy booleans, boolean
tensors/arrays and boolean elements in nested sequences/object arrays. It only
validates static nuisance inputs; accepted numerical weights, loss arithmetic
and legacy defaults are unchanged. A caller's already-coerced float array
cannot reveal its former boolean origin, and the guard does not claim otherwise.

Ten additional regressions include the upper-entry rejection before membership
selection or RTTOV preparation. **56 focused tests passed**, including existing
cost/VJP/FD, snapshot, channel/worker routing and state-prior checks. Comparing
the original baseline function against the guarded function over **36 accepted
numeric input combinations** gives identical raw binary64 sigma/bias snapshots,
including the unchanged default None pair.

[Comparison producer](VERIFY_fixed_error_input_guard_2026-10-07.py) extracts the
unaltered original function from the pinned Git commit and declares those inputs.

The first full-suite attempt included an incorrectly configured new test
(omitted normalized Huber delta=1); its failure was the expected earlier policy
rejection, not a production failure. The test was corrected and the 56 focused
tests rerun. The historical PR #380/#381 live execution pins still refer to
their original pre-guard source. They were not relabelled or rerun as current
native evidence. The clean final public-only suite passed **1668 tests**, with **93 skips** and
**51 warnings**. Counts overlap with the focused suite and are not summed.
Private RTTOV fixtures and unbuilt C++/private-input cases are explicitly skipped
in this local suite. Final CI is attributed to this revision separately.

## Collection facts and unfinished paths

All **59** observation receipt members match the manifest's byte sizes and
SHA-256; ZIP CRC validation passes. Nine distinct LA thermal originals total
4,414,025 bytes. No cloud science QA or pixel DQF was inspected in this review.
The Anmado nominal/release-time distinction and noncollocated C5 distance remain.

Source review and file headers reveal a practical R2 gap: KO/FD readers reject
the acquired LA020GE product family. LA GEOS/header calibration metadata exists,
and all nine calibration tuples match the shipped decoder table, but an explicit
LA ingest and time-provenance bridge remains absent. Relabelling LA as FD/KO is
not a valid fix.

The EarthCARE frame start is not the time of its intersection with Korea.
Catalogue polygon/interval overlap cannot establish a pixel-time match. The
[first acquisition checklist](CHECKLIST_first_observation_collection_2026-10-07.md)
now makes the remaining original SRF/GSICS, independent LWP, winter search,
cloud QA and region-specific scan/native-model correspondence explicit. These
are substeps of the already-declared observation task, not new approval gates.

## Closure and remaining research work

A1/A2/A3 remain closed within their demonstrated numeric-integration scopes;
the invalid-input gap above is resolved separately. No new production KDM
formula or AD arithmetic failure was reproduced. This was a bounded review,
not certification of every file, state, direction or meteorological regime.

R1 physical units/threshold/admissible-state policy remains conditional. R2
observation correspondence is open. P1 signed state inventory remains partial
without full boundary/work closure; T1 timestep dependence, C1 distinct native
grids and V1 independent settings/validation cases remain open. H1 remains an
optional supervised prediction study. No scientific B/R/bias or operational
approval follows from this review.

[Machine-readable result](INTERNAL_postmerge_review_result_2026-10-07.json)
records source hashes, numeric comparison scope and packet verification.

[Validation receipts](INTERNAL_postmerge_review_receipts_2026-10-07.zip) preserve
the final focused/full logs, numeric snapshot comparison and the earlier test
configuration failure separately. Graphify structural refresh and bounded
semantic update trace the new guard to its fixed-input consumers; graph coverage
does not replace source or private-host validation.
