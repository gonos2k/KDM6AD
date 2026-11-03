# Ice-speed producer sensitivity at the captured native column

This packet extends the [fixed-speed conditional chain](../native_qnice_sed_snap_chain_2026-11-03/README.md)
at the same recorded `(164,242)` native column. It re-evaluates the ice slope,
`vt_i`, `vtn_i`, and depth-normalized `work1_qi`/`workn_qi` when QI or NI is
perturbed at selected levels. Density, layer depths, the one-substep schedule,
the intervening zero NI rates and homogeneous-freeze mask, and the explicit
native-15 QI splice remain fixed. **No host, C++ or RTTOV execution was added.**

```bash
python harness/evidence/native_qnice_ice_speed_ad_2026-11-03/replay.py
python -m unittest discover -s harness/evidence/native_qnice_ice_speed_ad_2026-11-03 -v
python -O -m unittest discover -s harness/evidence/native_qnice_ice_speed_ad_2026-11-03 -v
```

The CLI ends with `NATIVE_QNICE_ICE_SPEED_AD_REPLAY_PASSED`. [results.json](results.json)
retains source hashes, baseline words, branch margins, actual represented
endpoints, speed and final C3 NI JVPs, independent sparse formulas, VJP
contractions, and finite-difference signals.

## Producer and baseline

The C++ [slope](source_snapshots/build_tree_slope.cpp.txt) and
[density-factor](source_snapshots/build_tree_thermo.cpp.txt) candidate sources
were copied from the isolated private build tree, checked against the public
source bytes, and pinned. The **linked object hashes** are separately
recorded in the PR #524 C++ build receipt. These two facts and the 39-level
consumed speed equality support the source interpretation; the public packet
does not independently recompile the older objects or prove that the copied
source bytes produced them. Their association remains a private build
attestation.
Archived Python [slope](source_snapshots/oracle_slope.py.txt) and
[thermodynamics](source_snapshots/oracle_thermo.py.txt) sources are pinned
separately; the current Python oracle is the differentiable regression target.

The source computes the ice slope from entry QI, NI and DEND with the
f32-derived `PIDNI` and f32 `1/3`, clips its reciprocal to the ice bounds,
then multiplies by `PVTI`/`PVTIN` and
`denfac = sqrt((1/max(DEN,qmin)) × DEN0)`. Finally both speeds are divided
by the safe layer depth. `vt_i` is zeroed for `QI<=0`; `vtn_i` is not.
For this call DEN and DEND have equal words at all 39 levels but remain
different source operands in the replay. The observed parameters are
`PVTI=10840`, `PVTIN=2710`, `PIDNI=1570.79638671875`.

In the source environment used for this packet, the recomputed
`work1_qi` and `workn_qi` matched the **consumed f64 raw words at all 39
levels**, and the dynamic-speed and fixed-speed C3 baseline outputs were
equal. The portable verifier requires each selected active speed to agree
within `1e−12` relative difference and reports the full-column bit count.
It permits small f32-constant/libm differences at inactive levels; a bit
match on every platform is not claimed. The full-column schedule over other
batch columns is held fixed. The selected column's recalculated local
ice-step count remains 1 at every tested endpoint.

## Added speed-producer paths

At native level 21, the entry ice slope is strictly clipped to the lower
lambda bound. The tested relative QI21 and NI21 directions leave its speeds
locally unchanged, so their C3 NI JVPs equal the preceding fixed-speed
result. At level 23 the slope is strictly interior. With density/depth fixed,
both speeds have relative sensitivity
`a(δQI/QI − δNI/NI)`, `a=float32(1/3)` widened to f64.

| Relative entry direction | C3 NI20 | C3 NI21 | C3 NI22 | C3 NI23 |
| --- | ---: | ---: | ---: | ---: |
| QI21, fixed or recomputed speed | +1.0429468145871474 | 0 | 0 | 0 |
| NI21, fixed or recomputed speed | 0 | +0.1358895005804943 | 0 | 0 |
| QI23, fixed speed | 0 | 0 | 0 | 0 |
| **QI23, recomputed speed** | 0 | 0 | **+57.10582274001688** | **−57.59018034479256** |
| NI23, fixed speed | 0 | 0 | +171.31746311439238 | +116547.04977661459 |
| **NI23, recomputed speed** | 0 | 0 | **+114.21164037437548** | **+116604.63995695938** |

Independent sparse formulas predict these numbers: for NI23, multiplying
the actual fixed-speed departure response by `(1−a)` changes the split
between levels 22 and 23. Relative QI23 changes the same departure through
the speed producer by `+a`; it is a new path absent from the fixed-speed
map. This is a conditional response in the recorded numerical NI coordinate,
not an observed host perturbation or physical particle-number sensitivity.

The replay checks source-producer speed JVPs, final C3 NI JVPs, weighted
VJPs and transpose products, and represented-input finite differences at
`h=1e−3`, `1e−4`, `1e−5`. At every endpoint it checks the ice-slope gate,
ratio/floor and reciprocal-slope branches, local step count, conservative
departure caps, and snap-A/B choices on the 20–23 causal support. Native 20
has a fixed zero-NI entry tie; its input is not seeded. Snap B at native 20
has a small positive lower-bound margin which is checked again at endpoints.

For the interior speed producer, the `h=1e−3` centered difference has a
predictable `O(h²)` power-law curvature: the worst scaled final FD–JVP
residual here is about `1.85e−7`. At `h=1e−5`, reduction/representation
effects can dominate; the recorded error is not treated as a monotone
convergence sequence. The verifier uses the represented input gap and a
step-dependent curvature/precision bound, reporting actual signals and
accepted bounds rather than silently loosening a single tolerance.

## Limits

The native-15 QI process remains unresolved and is held at its recorded
snap-A input. D1/homogeneous/D2–D4 NI producer rates are fixed at their
observed zero values; their derivatives are not certified. The current
producer calculation also holds density, geometry, other batch columns,
global substep schedule and other hydrometeor inputs fixed. This packet
does **not** establish a full native host JVP/VJP, operating f32 behavior,
RTTOV sensitivity, a physical QNICE unit, or particle conservation.
`scientific_status: INCONCLUSIVE` and `physical_unit_status: INCONCLUSIVE`
remain.

A later [D1 conditional AD packet](../native_qnice_d1_ad_2026-11-03/README.md)
removes the level-15 QI splice in a new fixed-speed **baseline** chain and
checks local QC/T melt tangents. The fixed-intermediate-producer derivative
scope of this historical packet remains unchanged.
