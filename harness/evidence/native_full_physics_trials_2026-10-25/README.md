# Native full-physics T/Q backtrack admission summary

**Outcome:** NO_ADMISSIBLE_TESTED_FULL_HOST_UPDATE (3 trials)

Three full-domain candidate T/Q updates were applied in separate one-step full-physics runs from the same 00:00:40 origin restart. Each trial reproduced the no-analysis control READY40 checkpoint bitwise across all 652 serialized variables and 322,426,586 numeric elements before the update. Each trial ended at 00:01:00 / itimestep 3. Two integrated MP137 wrapper entries were observed per host step.

The updates used the original restricted accepted direction, scaled once by alpha. The fixed baseline observation support came from a complete direct-only M0 run: 377,342 supported channel cells, 53,906 in each of channels 10–16. The current native profile guard rejected supported candidate rows with positive QC but nonpositive NC. The three trials lost 371, 441 and 385 fixed-M0 channel cells respectively.

Candidate RTTOV quality and candidate objective cost were not evaluated, so trial cost is undefined. This is an admission result, not optimization convergence, a full-host gradient, C5 completion, or a forecast-skill claim. No support mask was reduced and no cloud-number floor was applied.

The evidence artifact is [trial_summary.json](trial_summary.json), SHA-256 `2c71828bbc739fb3e49a363fb198c68846d9636e7f3bc222ff7d3cf8512ba07c`. It contains plan/result/checkpoint hashes, strict ACK row counts, actual runtime flags and RSL marker counts, complete M0 provenance, and three representative field-level examples. Full host checkpoints and detailed per-row audits remain in the private research evidence area.
