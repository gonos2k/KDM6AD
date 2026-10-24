# Restricted-block confirmation: preparation and execution evidence

Parent PR #447 remains `COMPLETED_NO_ACCEPTABLE_UPDATE`. This separate,
post-hoc experiment retains all 381,528 baseline-supported channel cells and
freezes T/Q controls in 25 whole original blocks. It evaluates the selected
alpha=1 candidate once over all 65,988 columns; it does not extend the old
three-trial budget.

The selected specification is `restricted_candidate_sourcebound.json`.
`restricted_candidate.json` is its preserved earlier specification, explicitly
bound by the selected file's superseding hash. `restricted_block_screen.json`
is independent arithmetic screening, not a new model run. The exact z-only
NPZ is hash-bound by both specifications. See
[the execution contract](../../../docs/NATIVE_RESTRICTED_CONFIRMATION.md).

The actual source_v2 forward completed with `RESTRICTED_UPDATE_ACCEPTED`.
All 129 blocks preserve the same support; measured J=11.144979224162192
matches screening exactly and is about 0.0760% below the parent baseline.
Full native state/rate exports, independent saved-output checks and public
arithmetic replay are available in [REPORT.md](REPORT.md) and `data/`.
No host cycle, convergence, forecast skill or physical-budget closure is
certified by this single post-hoc case.
