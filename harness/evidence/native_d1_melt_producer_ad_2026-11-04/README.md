# Same-call active snow/graupel D1 producers and conditional derivatives

This packet extends the [active native QI transfer and D1 record](../native_qi_applied_d1_active_2026-11-04/README.md)
on native column `(203,149)`, level 16, in the same 20 s mp137 call
(`runtime_call=one_step_call=2`, tile 2, `b_zero=27945`). A new isolated DSO
adds selected-column D1 producer inputs and intermediates to the existing
QI/NI applied ledger. The host executable and input checkpoint are reused.
Capture-off and capture-on full endpoints have identical SHA-256
`225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070`,
the prior variant's endpoint hash.

```bash
python harness/evidence/native_d1_melt_producer_ad_2026-11-04/replay.py
python -m unittest discover -s harness/evidence/native_d1_melt_producer_ad_2026-11-04 -v
python -O -m unittest discover -s harness/evidence/native_d1_melt_producer_ad_2026-11-04 -v
```

The CLI ends with `NATIVE_D1_MELT_PRODUCER_AD_REPLAY_PASSED`. The selected
capture has **6,630 rows**: every one of the parent packet's **4,485 rows**
retains its dtype and raw word, and 55 new producer fields are present at
each of 39 levels. The public verifier checks complete call/tile/level and
row-order inventory, source snapshot and capture hashes, a capture-only
`melt_freeze.cpp` overlay, object/build/run receipts and the loaded isolated
DSO path. Private binary and full checkpoint bytes remain represented by
their frozen hashes and run records. The native capture hook operates only
on the value-only call and has no effect on the returned tensors.

## Executed source order and chosen branch

The new rows include the captured snow/graupel state, density,
intercepts, slopes, `work2`, `precg2`, f32-derived parameter words widened
to f64, warm/active gates, and each mass producer's raw rate, 20 s candidate,
reservoir cap and applied amount. The snow amount first changes
`t1 = T + (XLF/cpm)·psmlt_capped`; the graupel raw rate then consumes
**that `t1`**. An independent scalar implementation checks the source-order
intermediates and both rate→amount selections in raw f64 bits at all 39
levels. It checks the applied amounts against the D1 consumer record and
the resulting D1 temperature store. The retained parent replay separately
checks QI applied interface transfer and D1 QC/QI/NC/NI/T stores.

| Native 16 D1 value | Captured f64 value |
| --- | ---: |
| Input T → snow-heated `t1` | `274.6803185248609 → 274.634596943946 K` |
| Snow raw rate → selected 20 s amount | `−6.601305574939371e−6 → −1.3202611149878743e−4` |
| Graupel raw rate → selected 20 s amount | `−6.112916695431711e−7 → −1.2225833390863422e−5` |
| D1 output T | `274.6303629975879 K` |

Both snow and graupel candidates are strictly between their negative
available-mass caps and zero. All tested finite-difference endpoints keep
warm, snow/graupel/ice active and the same raw-rate-winning caps. If the
graupel expression were evaluated at entry T while holding its other
operands fixed, its raw rate would be `−6.302021509184768e−7`, differing
from the executed sequential rate by `+1.8910481375305634e−8`. This is a
controlled arithmetic counterfactual, not another host run.

## Local conditional JVP/VJP and directional differences

The differentiable replay uses the captured mass producer inputs and
source operation order. In the output order
`(snow raw rate, snow candidate, snow applied amount, t1, graupel raw rate,
graupel candidate, graupel applied amount, D1 output T)`, the target level
has the following independent analytic and Torch JVP values:

| Input direction | Snow applied amount | `t1` | Graupel applied amount | D1 output T |
| --- | ---: | ---: | ---: | ---: |
| Unit relative D1-entry QV16 | 0 | `+2.7883757429813735e−4 K` | `−2.306241751629388e−9` | `+3.038600461751968e−4 K` |
| Unit absolute D1-entry T16 (1 K) | `−8.666008166953617e−5` | `+0.969988997697761 K` | `−8.022696118851808e−6` | `+0.9672106810027554 K` |

For the QV direction, snow's rate is fixed within this defined map;
QV changes cpm, then the snow-heated `t1`, then graupel production.
The independent formula uses
`d log(xka)/dT = 1.5/T − 1/(T+120)` and the derivative of
`xka(t1)·(T0−t1)`. For the T direction, both snow and graupel raw rates
respond, including `dt1/dT = 1+(XLF/cpm)·d(psmlt)/dT`.

Torch JVPs agree with these source-derived expressions; weighted VJP
contractions match the corresponding JVP dots. At relative QV half-steps
`0.1,0.01,0.001` and absolute T half-steps `0.1,0.01,0.001 K`, both
endpoints are independently scalar-replayed in raw bits, branch signatures
remain unchanged, and represented-input-gap finite differences have less
than `1e−6` relative error for nonzero selected JVP components. The output
signal and f64 spacing are retained for each step in [results.json](results.json).

## Limits

This is a **local f64 producer derivative at the captured D1 input**.
Density, pressure, QI/NI, intercepts/slopes, `work2`, `precg2`, `rhox`,
other process rates, geometry and the substep schedule are fixed. The
captured parameters are used as actual producer inputs; their initialization
from earlier routines is not differentiated here. The current packet does
not measure perturbed host calls, direct QS/QG/QR post-D1 stores, operating
f32 derivatives, a host-to-RTTOV tangent, or QNICE's historical physical
unit. The earlier QI interface applied amount remains directly captured;
the snow/graupel derivative is conditional on the stated fixed inputs.

The capture also contains `p` and `rhox`, but neither enters the selected
snow/graupel mass-rate and temperature replay. `rhox` affects the separate
`delta_brs`/BRS path in D1. That path, its output and its tangent are outside
this packet. A rehashed test capture with only `rhox` changed can therefore
pass the selected arithmetic checks; the ordinary CLI still pins the entire
original capture by SHA-256. The mutation tests claim rejection only for the
named source-order intermediates, caps, parameters, identity and parent rows.

`scientific_status: INCONCLUSIVE` and `physical_unit_status: INCONCLUSIVE`.
