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

The actual source_v2 forward is in progress. No accepted-update claim is made
until all 129 actual blocks, fixed support, global cost, state/rate exports,
figures and provenance checks are complete.
