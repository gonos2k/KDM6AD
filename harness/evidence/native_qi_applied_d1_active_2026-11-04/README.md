# Same-call native QI applied transfer and active D1 melt

This packet records one 20 s mp137 call on the current native 5 km column
`(i,j)=(203,149)`, rank 0, tile 2, `runtime_call=one_step_call=2`,
`B=32248`, selected `b_zero=27945`, and all 39 levels. The input is the
retained `2025-07-19 00:00:40` model checkpoint used by the preceding
[39-level NI packet](../native_qnice_39_applied_2026-11-03/README.md).
The same copied host executable and a new isolated DSO were used for
capture-off and capture-on. Both full `00:01:00` endpoints have SHA-256
`225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070`,
also the endpoint hash of the earlier selected-column execution.

Run the public offline verifier:

```bash
python harness/evidence/native_qi_applied_d1_active_2026-11-04/replay.py
python -m unittest discover -s harness/evidence/native_qi_applied_d1_active_2026-11-04 -v
python -O -m unittest discover -s harness/evidence/native_qi_applied_d1_active_2026-11-04 -v
```

The CLI ends with `NATIVE_QI_APPLIED_D1_ACTIVE_REPLAY_PASSED`. The 4,485
selected CSV rows bind each stage/field/level to the same runtime, one-step
call and tile. The verifier checks complete inventory/order/dtype, frozen
source and capture hashes, the source-to-parent capture-only C++ diff,
object/build receipts, loaded DSO path, and off/on endpoint equality.
Private executable, DSO, object and full checkpoint bytes are identified by
receipts; public CI does not independently rebuild or rehash them.

## Actual QI interface transfer

The isolated DSO adds 13 QI fields per layer to the earlier native NI
ledger: pre-state QI, computed fall rate, departure attempt, **applied
departure**, **applied arrival from the preceding layer's actual departure**,
post-state QI, fall accumulator before/after, cap/tie indicators and
roundoff diagnostics. It captures only the selected column. The verifier
recomputes all 39 levels in the executed f64 operation order and compares
every captured QI store and amount in raw bits. `fall_qi` is a cumulative
rate diagnostic; its increment is not substituted for applied departure.

At native levels 17→16 in this call:

| Same-call applied amount | Recorded C++ QI coordinate |
| --- | ---: |
| Level 17 actual departure | `1.524431280686188e−10` |
| Level 16 actual arrival after density/depth metric | `1.5404679459033794e−10` |
| Level 16 post-sedimentation QI | `1.5404807243815997e−10` |

The arrival is larger in mixing-ratio coordinates because the source uses
the recorded density and layer-thickness metric. The verifier checks the
previous-actual-departure word and its destination formula separately.
There was no active QI departure reservoir cap in the selected 39 levels.
The exact-sum diagnostic of stored f64 values reports mass-coordinate
`Σ(QI·DEND_safe·DELZ_safe)` change `+2.587185306343287e−21`, maximum
interface transfer difference `3.6187187960401106e−23`, and arithmetic
closure residual `+2.5494162813814027e−21`. The separately reproduced
state words and these exact-sum diagnostics answer different questions;
rounding during individual state stores remains visible in the residual.
[Numerical result](results.json)

## Active D1 in the same call

The native 16-level D1 input is `274.6803185248609 K` and receives the
recorded post-sedimentation QI. The same stage records applied snow melt
`−1.3202611149878743e−4`, graupel melt `−1.2225833390863422e−5`,
and complete ice melt `+1.5404807243815997e−10`. D1 QC changes from
`5.454791826196015e−4` to `5.45479336667674e−4`, and temperature
changes from `274.6803185248609` to `274.6303629975879 K`.
Using the captured applied amounts and `350000/cpm_safe`, the three
separate temperature terms are about `−0.04572158 K` (snow),
`−0.004233893 K` (graupel), and `−5.334794e−8 K` (ice). They are
source-order arithmetic contributions; they do not independently certify
the snow/graupel rate producers.
Across all 39 levels, the verifier independently recomputes the simple
QI/T-gated complete ice melt, QV→`pre_cpm`→`cpm_safe`, and source-order
QC/QI/NC/NI/T stores **using the captured snow/graupel applied amounts**.
It joins the post-sedimentation QI word to the D1 input word. Runtime-entry
QV and D1-entry QV also match in raw bits at all 39 levels; a rehashed
one-ULP mismatch is rejected by a regression test.

The snow and graupel **producer candidates, caps, and perturbation responses**
are not independently replayed here: their internal slope/intercept and
sequentially heated-temperature operands were not captured. Their nonzero
applied amounts are direct same-call observations. A future producer AD
experiment must record those inputs and confirm its branches at perturbed
endpoints. The checkpoint's warm snow/graupel and upper ice values were only
used to **select** this column; the active D1 conclusion uses the captured
call values above.

## Scope

The active path uses experimental `KDM6_ICE_FACTORIAL_MODE=norm_actual`
and the native fp64 value bridge. This packet adds value and applied-amount
evidence, not a derivative result for the new column. The host-side AL,
ALB, QV and QNICE pre-call words were not recaptured for this selected
column; the preserved Fortran trace hook was fixed to the older `(164,242)`
column and was disabled in this run. C++ runtime ingress and stage values
are directly captured. The physical basis of QNICE and a full host/RTTOV
derivative remain unresolved.

`scientific_status: INCONCLUSIVE` and `physical_unit_status: INCONCLUSIVE`.
