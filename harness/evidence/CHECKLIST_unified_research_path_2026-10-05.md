# Whole-codebase review: one explicit research path

Review baseline: `d0e2e14b` (PR #371). The PR #370–#371 single-NC optical
cost/VJP result remains closed. This checklist addresses the upper assembly
identified in the whole-codebase review; it does not reopen that experiment.

| Review item | Resolution and evidence | Status |
| --- | --- | --- |
| Window cannot select the normalized dry-number transition | Appended opt-in flag in `WindowConfig`; collection, forward and recomputation capture the same choice. Two-step pure-map, VJP and independent FD tests. | CLOSED, bounded code verification |
| Retained linearization uses a different transition | The same opt-in flag selects the same runtime map in `WindowLinearization`. Retained/recompute comparison tests. | CLOSED, bounded code verification |
| Parallel window drops the transition choice | `ShardSpec`, builder, sensitivity worker and value-only worker carry the flag. Serial/sharded value comparison uses all 12 fields. | CLOSED, bounded code verification |
| All-sky worker cannot inherit optical number/BT settings | Explicit `dry_number` selects optics; explicit `ami_kma_bt` selects the existing factory. Default calls retain their previous keywords. | CLOSED, bounded code verification |
| Upper caller mixes observation coordinates/support | Research mode declares KMA v3.0 observations, thermal AMI 8–16, diagnostic sigma/Huber=1, zero bias and a frozen binary gate. IR105 position follows the nine-channel order. Unsupported pseudo-RH is rejected. | CLOSED, bounded code verification |
| Native pressure grids can be silently replaced | Research paths require an explicit fixture and retained native centers on the shared grid; different native grids are rejected. Interfaces are caller-owned source inputs, not inferred from centers. | CLOSED for the declared input boundary |
| Thermal surface rejected by a solar-only requirement | The actual C5 attempt exposed zero wind-fetch rejection. Thermal research validation now disables the solar requirement; legacy validation is preserved and tested. | CLOSED, reproduced boundary fix |
| Frozen callback identity omits BT coordinate | `bt_coordinate` is captured and fingerprinted. Native/KMA identities and mutation-safe freezing are tested. | CLOSED, bounded code verification |
| Actual assembled caller and long window | Fresh full-domain-entry optimization and 180-step recomputed-window cost/VJP/FD receipt are being collected. | PENDING execution receipt |
| Scientific number/threshold, product compatibility, B/R/bias policy | Existing S2/S11 questions remain; diagnostic settings do not resolve calibration or physical accuracy. | OPEN |
| Host writeback, MPI/restart/cycling and operational approval | No host state is applied by this research path. Existing operational gates remain separate. | OPEN |

The optical measure is frozen from the original background and forcing,
while microphysics uses its established per-call entry-density conversion.
This defines an explicit numerical operator; it is not the live optical
entry-density contract of the earlier one-hour experiment. Forward, trial
evaluation and recomputed adjoints must preserve this same policy.

The supported pressure contract can include declared reference atmosphere above
the model top. It does not certify the atmospheric suitability of that reference,
the supplied interfaces, sensor response, pixel acquisition time or footprint.
The selected C5 interfaces must be checked against their retained P8W source in
the execution receipt. A successful computation remains a diagnostic result.
