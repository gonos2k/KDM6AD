# PR406: case-bound native intake and analysis connection

Basis: main `2a7c09d8` (PR405), user review 2026-10-11. Satellite observations remain GK2A AMI L1B only. No external model/reanalysis substitution or archive rescan.

- [x] Preserve the historical July19-only PR395 intake and its executed records.
- [x] Add a bounded case consumer for run identity, initialization/valid time, column, native State/Forcing, pressure, surface and original decoded L1B bindings.
- [x] Separate the required saved background from optional saved diagnostic frames. A local20s model slot is explicitly derived, not advertised as a saved host state.
- [x] Adapt only the case/provenance boundary on an isolated legacy capture module. Reuse the all-sky seven-channel T/Q helper, fixed physics, 1K sigma, zero bias, prior, final audit and private state/gradient writer.
- [x] Require the established GK2A-AMI fixture, a finite DQF0 seven-channel point and native-to-L1B distance within2.5km before analysis admission.
- [x] Exercise the new intake on the original July19 background without M/H/optimizer/native execution; compare all70 corresponding retained arrays with historical intake.
- [x] Process both prepared July20/21 cases as `PENDING_NATIVE_INPUT`; no new-date native NPZ or analysis is invented.
- [x] Review with Green/Red; resolve receipt-ID, wrong-fixture and immutable-input coverage findings. See the packet reports and validation record.
- [ ] Connect an actual lineage-bound native state/forcing at either new valid date. The existing source/archive request remains outstanding; no repeated question or global absence claim.
- [ ] Execute the first ready date's baseline→analysis→accepted-point final audit. One ready date can proceed without waiting for the other.
- [ ] Execute the other available date and compare BT, costs/gradient, T/Q, saturation/hydrometeors and the defined water/heat measures. Retain no-cloud, stagnation and quality-failure outcomes.

The user-owned management assessment stays **79/100**. A consumer, tests and a same-date intake replay are not new-date analysis results. [Packet report](pr406_native_case_consumer_2026-10-11/COORDINATOR_REPORT.md).
