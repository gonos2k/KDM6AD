# Conditional native ice-speed → D1 → snap A/B chain AD

This public replay combines the [ice-speed producer packet](../native_qnice_ice_speed_ad_2026-11-03/README.md)
and the [same-call D1 mass/heat packet](../native_qnice_d1_ad_2026-11-03/README.md).
It makes **no new host, C++, Fortran, or RTTOV call**. Both parent replay
sources, results, capture and execution receipts are checked by SHA-256.
The tested column is native `(164,242)`, 39 levels, one 20 s mp137 call with
`runtime_call=one_step_call=2`, one ice sedimentation substep, and the
experimental `norm_actual` f64 value path.

```bash
python harness/evidence/native_qnice_d1_chain_ad_2026-11-04/replay.py
python -m unittest discover -s harness/evidence/native_qnice_d1_chain_ad_2026-11-04 -v
python -O -m unittest discover -s harness/evidence/native_qnice_d1_chain_ad_2026-11-04 -v
```

The CLI ends with `NATIVE_QNICE_D1_SPEED_CHAIN_AD_REPLAY_PASSED`.
Its [saved result](results.json) is hash-pinned. Every fresh JVP/VJP and
represented-gap difference is judged against a source-derived sparse
expectation, branch audit and numerical bounds; saved reductions are not
required to reproduce bitwise on another Torch/CPU implementation.

## Baseline and selected outputs

The conditional map recomputes ice `work1_qi/workn_qi` from the recorded
QI/NI/density, applies the source-order conservative sedimentation, then
recomputes D1 complete ice melt from its post-sedimentation QI and captured
temperature. It carries D1 QC/QI/NC/NI/T, the recorded inactive homogeneous
mask, snap A, **fixed captured D2–D4 applied amounts**, and snap B to C3
input NI. No level-15 QI constant is injected. With captured speeds the map
matches **13 stage fields × 39 levels in f64 raw bits**. With recomputed
speeds it reproduces the same baseline C3 NI in this environment; the
portable check allows at most `1e−8` absolute difference across the column
and requires selected active speed relative agreement within `1e−12`.

The output vector is `(D1 QC15,QI15,NC15,NI15,T15; C3 NI15,NI16,NI22,NI23)`.
For a **unit relative perturbation at sedimentation entry**, the verified
JVP components are:

| Input direction | D1 QC15 | D1 T15 | C3 NI16 | C3 NI22 | C3 NI23 |
| --- | ---: | ---: | ---: | ---: | ---: |
| QI16 | `+6.10913581735702e−11` | `−2.119551621600676e−8 K` | `+0.354010809709542` | 0 | 0 |
| QI23 | 0 | 0 | 0 | `+57.10582274001688` | `−57.59018034479256` |
| QI16 + QI23 | both contributions above in one JVP | both | both | both | both |

The selected QI15, NI15, NC15 and C3 NI15 JVP components are zero in these
directions. NI→NC at the D1 input was separately checked in the parent packet;
this chain does not introduce a physically admissible upstream NI perturbation
at the zero-NI level 16.

## Why the paths differ

Native 16 has QI>0 and NI=0. Its ice-speed slope is on the lower branch:
the **QI16→speed JVP is zero**, even though QI16 changes the departure
amount. The source-order departure `QI16 × work1_qi16 × dt` and the recorded
density/depth arrival metric carry mass to warm native 15. D1 melts that
incoming QI, leaving QI15 at zero while QC15 rises and T15 falls. Snap A's
QI gate is inactive at 15. The independent sparse expectation also uses
the native-16 snap-A lower rewrite and snap-B interior branch to predict
the `+0.354010809709542` C3 NI16 tangent.

Native 23 has an interior ice-speed slope. Relative QI23 increases the
number-fall speed by `a·workn23`, with `a=float32(1/3)`. Its number
departure response is `a·NI23·workn23·dt`; the captured depth ratio maps
it into NI22, and NI23 loses that amount. This is the speed-producer path
found in the earlier packet. The mixed seed exercises both paths in the
same differentiable map, without claiming that the 23→22 transfer reaches
the warm level 15 in one substep.

At both finite-difference endpoints for `h=1e−3,1e−4,1e−5`, the replay
recomputes all speeds and checks producer, transport-cap, D1 melt, and
snap-A/B branch signatures at levels 15, 16, 22, and 23. It explicitly
keeps the native-15 zero-departure tie and the active 15-level melt gate.
The difference denominator uses each seed's **represented input gap**;
for the mixed seed, the two represented gaps are recorded separately.
The level-15 temperature difference at `h=1e−3` is about 745 output f64
spacings; at `h=1e−5` it is only about 7 spacings. QC/T differences have
an output-ULP bound separate from the curvature-based C3 NI comparison.

## Evidence limits

The QI interface departure/arrival is **reconstructed from captured
consumed speeds and source-order operators**. The earlier native applied
ledger directly recorded NI applied amounts, not a separate QI interface
flux. This packet does not promote reconstructed QI flux to an independently
captured host value.

Density, layer thickness, timing, substep gates, D1-entry T/QC/NC and
`cpm_safe`, snow/graupel melt amounts, homogeneous mask, D2–D4 applied
amounts, other hydrometeors and batch schedule are fixed. The QI16>0,
NI16=0 baseline is not an admitted physical moment pair. These are
**conditional numerical directions** on one f64 native call, not a full
host trajectory or physical particle budget. The next producer work is
QV→cpm and the other melt/freeze rates; operating f32, QNICE units,
host-wide JVP/VJP, and RTTOV sensitivity remain open.

`scientific_status: INCONCLUSIVE` and `physical_unit_status: INCONCLUSIVE`.

The later [active native QI transfer packet](../native_qi_applied_d1_active_2026-11-04/README.md)
directly captures applied QI departure/arrival in another column. This
historical conditional derivative still uses its stated reconstructed QI
interface amount.

A later [QV→cpm packet](../native_qnice_d1_cpm_ad_2026-11-04/README.md)
checks the fixed coefficient's baseline production and its isolated D1
temperature tangent. Other QV-dependent producers remain outside that test.
