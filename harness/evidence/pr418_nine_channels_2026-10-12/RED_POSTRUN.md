# Red post-run review: PR418 channel extension and closeout

## Disposition

The initial source review found a nine-channel driver audit gap; Green
resolved it in the new driver without modifying the original PR395 helper.
`run_case_analysis_nine.py` now uses
`_audit_initial_objectives_selected(..., expected_channels=len(selected_channels))`.
The selected audit applies the same expected count to shape, closure support,
frozen-mask cardinality, and the zero-control probe cross-check. Focused Green
coverage reports a nine-channel `CROSSCHECKED` synthetic receipt and rejects a
wrong count and altered masks. The original seven-channel helper remains
unchanged. The current flagged input still stops before any nine-channel
analysis, so this fix establishes the audit path synthetically rather than a
real accepted analysis.

The report, geometry correction, result, warning receipt, response table,
functional closeout and wiki source keep the executed evidence distinct from
the scientific gates that remain open.

## Added-channel result and quality boundary

`RESULT.json` records two new logical, value-only H calls at saved indices 6
and 7. Each call requests channels 8/9 only; all four returned BTs are finite,
and all four model `rad_quality` values are 32768. The channel table preserves
those values and flags, then reuses channels 10–16 from the hash-bound PR417
result. I recomputed the nine-channel 07−06 deltas from the saved composite;
they match `RESULT.json` and `CHANNEL_RESPONSE.csv`. The result correctly says
this is a channel-wise composite, not a simultaneous nine-channel H run, and
sets the all-nine quality-zero gate to false. It reports no M, optimizer,
observation-fit or nine-channel analysis result.

I checked all 14 original PR417 packet hashes listed in
`GEOMETRY_CORRECTION.json`; each matches the current file. The PR407 intake
driver also has no diff from `b07af3fe`. The additive geometry correction is
supported by the bound preparation source: PR417 passed the native `j=103,
i=48` center to `ami_geometry`, while the AMI row 289/column 49 supplied the
separate GEOS navigation reference. The correction preserves the old files and
does not claim a measured BT effect for a different angle point.

The warning receipt’s three RTTOV source hashes and executable hash match the
installed files. Source defines bit 15 as `qflag_delta_edd_ext_limits`, sets it
when extinction exceeds the Delta-Eddington maximum, and clips extinction.
The receipt correctly does not claim source-to-executable build attestation or
identify the triggering layer or constituent. The report does not turn this
source interpretation into a warning waiver or claim that the flagged WV BTs
are valid analysis support.

## Source-only review of the nine-channel analysis path

`run_case_analysis_nine.py` validates the nine-channel payload hash and exact
physical channel order, compares selected BT/DQF values with the bound point,
requires source DQF zero, and carries the selected channel IDs into both H
configurations. Its observation-linked geometry calculation uses the selected
AMI pixel point; this is a separate run from the historical PR417 native-center
geometry described above. The capture wrapper carries the selected count and
IDs through final mask checks, audit signatures, the zero-control closure,
receipt and private checkpoint metadata. Background support is checked before
the minimizer; nonzero model quality cannot silently remove a channel.

The old helper remains a seven-channel API and is no longer used for the new
nine-channel driver's final audit. The new local audit is read-only over saved
receipt fields, uses the selected count, and performs no H/M/optimizer work.
Its focused test also checks a good nine-channel cross-check plus mismatched
count, frozen support and probe-mask counterexamples.

Green reports seven focused tests passed, including the synthetic
nine-channel capture/checkpoint round trip and pre-optimizer rejection for
quality 32768, alongside the original seven-channel and driver regressions. I
reviewed the changed source and test assertions but did not execute them. These
synthetic results remain separate from the two actual added-channel H calls.
No accepted nine-channel analysis occurred on these inputs because the real
added-channel quality gate fails.

## Closeout claims and limits

The functional closeout is bounded to the cited internal runs. Its PR412 and
PR415 descriptions distinguish returned/audited points from strict
convergence; PR415 records gradient L-infinity 0.002606100 against the
unchanged 1e-10 criterion and termination `UNKNOWN`. Other-date repeatability,
the actual 06/07 observed temporal fit, atmospheric truth, process attribution,
forecast skill and cycling remain expressly unassessed. The documents make no
new build-certification claim and do not turn pending Jul20/21 receipts into a
claim of universal archive absence.

The graph fragment at `graphify-out/.graphify_chunk_pr418.json` is valid JSON,
references only the four requested Markdown sources, and has internally valid
node/edge/hyperedge IDs. Its token fields are zero because this was a manual
semantic extraction without a metered Graphify model call; Graphify merging and
the final structural refresh remain with the root agent.
