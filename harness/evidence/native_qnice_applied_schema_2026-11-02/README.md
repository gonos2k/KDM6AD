# Synthetic applied-NI capture schema and replay

The [versioned replay](replay.py) serializes **one column** of detached `IceNumberAppliedLedger` records from the public Python `ice_substep_advection_torch()` in f32 or f64 raw words. It also records the synthetic normalized number speed and reconstructs the stored fall rate from that input. It requires an independently supplied case/call/column identity, top-first vertical order, positive `dtcld`, integer mstep and a complete ordered substep inventory. It refuses missing or extra fields, wrong dtype/width, nonfinite values, broken state/fall continuity and altered state, cap, projection, candidate or fall-accumulator words. The [sample](sample_arrival_cap.json) has SHA-256 `90f001b330e966021aa4402ff5ecb6ff913bfbbdb99ad12abdfce8aebf773014`.

The replay keeps three different results visible:

| Synthetic case | State update replay | `dz` weighted column change | Interface mismatch | Closure residual |
| --- | --- | ---: | ---: | ---: |
| Two layers, incoming cap inactive | raw-bit equal | `0` | `0` | `0` |
| Two layers, incoming cap active | raw-bit equal | `−6` | `+6` | `0` |
| Three layers, top floor projection | raw-bit equal | `−13` | `+20, 0` | `0` |

In the capped two-layer sample, top NI `10` has a **scheduled pre-floor debit** of `8` and ends at `2`; the lower layer receives only `2` because arrival is capped by the **updated** top reservoir. The replay residual is zero, yet the column changes by `−6`. Thus replay agreement is distinct from transfer consistency. In the three-layer example, top scheduled debit is `20` but its floor correction is `+10`, so the realized top loss is `10`; bottom applied out is `3` in weighted units, and `13 = 3 + 20 − 10`. A separate f32 test starts the fall accumulator at `2^24`: the fall rate and candidate amount are `1` while the rounded accumulator difference is `0`. At `dtcld=2`, fall rate `2` and candidate amount `4` are kept separate. Candidate, scheduled debit, realized loss and accumulator delta have distinct names.

The source-order state replay checks top `clamp(before−out,0)` and interior `clamp((before−out)+in,0)` in the recorded dtype. For f32, scalar `dtcld` is rounded to the tensor dtype before fall-amount multiplication; signed-zero projection words are retained, while the top incoming record must be positive zero. The aggregate diagnostics use exact rational sums of the **already rounded stored words**, which removes only additional aggregation rounding. `state_replay_max_abs_residual` is zero for an accepted raw-bit replay; `closure_residual_dz` separately reports the aggregate arithmetic residual. The weighted `NI×dz` measure is a **kernel numerical-coordinate diagnostic**, not certified physical particle number.

This synthetic packet reconstructs the fall rate and candidates from the supplied synthetic normalized speed, NI, geometry and timestep, then checks the saved fall accumulator. It does not independently attest an executed native C++ instruction stream: the Python producer and serializer share the declared input values. A future native schema must capture those operands and actual call/build/DSO identity for all 39 levels and executed substeps; it must not relabel this synthetic packet as native evidence. See the [native capture contract](../../../docs/NATIVE_QNICE_APPLIED_CAPTURE_CONTRACT_20261102.md). `scientific_status: SYNTHETIC_ONLY`; no native host or RTTOV execution occurred.

```bash
python -m harness.evidence.native_qnice_applied_schema_2026-11-02.replay \
  harness/evidence/native_qnice_applied_schema_2026-11-02/sample_arrival_cap.json \
  --sha256 90f001b330e966021aa4402ff5ecb6ff913bfbbdb99ad12abdfce8aebf773014 \
  --case-id two_layer_arrival_cap --call synthetic:1 --column 0 \
  --levels 2 --substeps 1
python -m unittest discover -s harness/evidence/native_qnice_applied_schema_2026-11-02 -v
```
