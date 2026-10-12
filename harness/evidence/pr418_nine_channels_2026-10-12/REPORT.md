# WV063/WV069 extension and internal research closeout

Baseline main `b07af3fe` / PR417. Two actual value-only H callbacks evaluated
**only channels 8/9** at the existing saved native 06/07 snapshots. Seven
channels 10–16 are reused from the hash-bound PR417 result. No repeated
seven-channel H, H05, M, optimization, native run or L1B acquisition occurred.

| Added channel | BT06 K | BT07 K | 07−06 K | RTTOV quality at both times |
|---|---:|---:|---:|---:|
| WV063 / 8 | 237.834959443 | 238.062412572 | +0.227453129 | 32768 |
| WV069 / 9 | 248.626546473 | 248.807081427 | +0.180534953 | 32768 |

Both callbacks returned finite values, but neither added channel passes the
quality-zero rule. [RESULT](RESULT.json) and [nine-channel table](CHANNEL_RESPONSE.csv)
retain every flag and label added versus reused values. This is a channel-wise
composite, **not a simultaneous nine-channel H execution**. The existing seven
channels retain their original quality zero and BT. Returned flag values are
not converted to DQF, cleared or removed from the selected support.

Installed RTTOV source checked for this report defines bit15
`qflag_delta_edd_ext_limits`, Delta-Eddington extinction limits exceeded.
The current source and pinned executable are recorded separately in
[warning receipt](WARNING_SOURCE.json); source inspection does not attest that
executable's build or identify this run's triggering layers/gas/hydrometeor
contributions. No instrumented extinction rerun or warning waiver was made.

The optional nine-channel **implementation and saving connection** are complete;
the all-nine quality-zero **scientific execution gate fails for these inputs**.
No actual nine-channel analysis or new accepted checkpoint was attempted.
The default seven-channel analysis remains the existing supported path.

## Implementation and validation boundaries

`run_single_column_analysis(..., channels=range(8,17))` explicitly opts into
nine ordered physical channels. The only supported spectra are 10–16 and
8–16; default selection remains 10–16. Shapes, clear/H configurations, frozen
background support and returned IDs follow the selection. All selected
channels must pass source/model quality; trial loss of support raises rather
than shrinking it.

The new [case driver](run_case_analysis_nine.py) reuses the unchanged V4 native
input gate, then validates the full nine-channel payload order/hash, exact
selected point values and all selected DQF0s. Its supplemental selection is
recorded separately from the original seven-channel intake manifest. The
capture wrapper carries selected IDs/counts through audit signatures, final
mask validation, public receipt and private checkpoint metadata. Synthetic
regressions exercise these boundaries and saving; they are separate from
the two actual additional-channel RTTOV calls.

[Existing L1B binding check](L1B_BINDING_CHECK.json) also verifies all nine
ordered channels against the original hash-bound Jul19 05:56 selected payload,
with source DQF0. It reads existing data only; no residual or pairing to the
historical06/07 endpoints is calculated. Source DQF0 and RTTOV model quality32768
are separate flags with separate admission rules.

Red found the final driver cost audit still required7 after capture supported9.
The new driver now owns a selected-count audit, and regressions check valid9
and mismatched count/support/probe masks. Its adapter import is also bound to
the explicit PR407 path. A full-collection test failure from a PR406/PR407
Python module-name collision reproduced at baseline b07af3fe; the oracle
test loader now isolates the intended PR407 dependency. Archived executed
drivers and old audit helpers remain preserved. [Green](GREEN_POSTRUN.md)
and [Red](RED_POSTRUN.md) distinguish these synthetic fixes from actual H.

The original PR407 driver and all PR417 packet files remain byte-identical to
`b07af3fe`. An initial source guard rejected an in-progress change to the old
driver **before H and before an output marker**. That change was moved to the
new driver and the original restored; [pre-execution rejection](PRE_EXECUTION_SOURCE_GUARD.log)
is preserved. Exactly two actual callbacks were then made once, with original
sources/assets/fixtures checked before and after. Internal RTTOV direct/K
launch counts remain unmeasured; `grad=False` does not imply no internal K.

[Additive geometry correction](GEOMETRY_CORRECTION.md) identifies the actual
native-centre viewing calculation and separate AMI navigation donor without
altering PLAN/hash/BT. [Functional closeout](../../../docs/INTERNAL_RESEARCH_CLOSEOUT_2026-10-12.md)
fixes the completed scope and separates convergence, other dates, observed
temporal fit and truth/forecast validation. Old pending receipts describe their
bound inputs; they are not evidence of universal current archive absence.

No new observed residual, temporal matchup, solver, or operational acceptance
claim is made. The warning does not reopen the completed seven-channel
historical comparison or justify accepting flagged channels in analysis.
