# Same-call native D1 melt producer to mass, number, and BRS stores

This packet extends the [active D1 producer record](../native_d1_melt_producer_ad_2026-11-04/README.md)
at native column `(203,149)`, level 16, in the same 20 s mp137 call
(`runtime_call=one_step_call=2`, `b_zero=27945`, 39 levels). An isolated DSO
adds value-only capture of the separate D1-entry QR/NR/BRS state, `sfac`,
`gfac`, the f64 `rhox` divisor and BRS increment, the actual D1
QS/QG/QR/NR/BRS stores, and the immediately following BRS re-slope. The
7,917-row capture preserves all 6,630 prior rows in order, dtype, and raw
word. Its 1,287 new rows are 33 fields × 39 levels.

```bash
python harness/evidence/native_d1_melt_state_ad_2026-11-04/replay.py
python -m unittest discover -s harness/evidence/native_d1_melt_state_ad_2026-11-04 -v
PYTHONOPTIMIZE=1 python -O -m unittest discover -s harness/evidence/native_d1_melt_state_ad_2026-11-04 -v
```

The verifier pins the full capture, source snapshots, producer blocks,
build/run/session records and the prior producer replay. It checks complete
call, layer, field, dtype and row-order inventory. Stripping the added capture
blocks from `melt_freeze.cpp` and `coordinator.cpp` reproduces the parent
sources byte for byte. The isolated DSO and loaded-library path are recorded;
the copied host executable and input checkpoint are unchanged. Capture-off and
capture-on full endpoint SHA-256 are both
`225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070`,
the preceding variant's endpoint hash. Binary/object bytes and the full host
checkpoint remain private; their hashes and run records are published here.

## Actual source-order D1 state transfer

The scalar replay first checks the newly recorded number factors and BRS
producer, then independently evaluates every store at all 39 levels in f64
source order. It compares each result to the directly captured raw f64 word:

```text
QSout  = QSin + ps
QGout  = (QGin + pg) + pfrzdtr
QR1    = QRin - ps · warm_mask
QR2    = QR1  - pg · warm_mask
QRout  = QR2  - pfrzdtr
NR1    = NRin - sfac · ps
NR2    = NR1  - gfac · pg
NRout  = NR2  - nfrzdtr
BRSout = BRSin + (delta_brs_capped + delta_brs_freeze)
```

Here `ps` and `pg` are the **applied capped amounts**, not the accumulated
`fall` diagnostics or the rates divided by `dtcld`. `sfac` and `gfac` have
their own `q > qcrmin` gates, separate from the positive-mass melt gates.
The D1-entry QR/NR/BRS words are captured before the producer call and
must equal the corresponding consumer input words at all 39 levels. The
three D1-only freeze amounts `pfrzdtr`, `nfrzdtr`, and `delta_brs_freeze`
must each be the raw `+0` word. Rehashed mutations that forge an otherwise
self-consistent BRS input/output/reslope chain or change these fields are
rejected by the replay.
For this f64 call, `delta_brs_capped = pg / max(rhox,100)`, using the
persistent pre-D1 `rhox`. D1's freeze terms are recorded zero. The ordinary
f32 path has a different raw-`rhox` divisor contract and is not inferred
from this f64 result.

| Native 16 store | Before | After |
| --- | ---: | ---: |
| QS | `0.0006696513402210594` | `0.0005376252287222719` |
| QG | `5.4038067779247255e-5` | `4.1812234388383836e-5` |
| QR | `0.0005710986271243108` | `0.0007153505720139617` |
| NR | `908.5097236614018` | `1499.7893838072516` |
| BRS | `6.004757288472314e-8` | `4.646212004038053e-8` |

The captured intermediates are `QR1=0.0007031247386230983`,
`QR2=0.0007153505720139617`, `NR1=1279.4774935144192`, and
`NR2=1499.7893838072516`. In this actual cell, subtracting the summed
snow and graupel number terms once would change `NR2` by one f64 ULP.
The local exact-sum residual in `(QS+QG+QR)` is at most
`6.776263578034403e-21` among the 39 stored cells; this is a numerical
coordinate check, not a column-integrated physical mass budget.

The D1 inline BRS store is separately connected to the following ProgB
re-slope input. In this call the re-slope BRS words equal the inline BRS words
at all 39 levels. The packet does not replay the ProgB producer or later BRS
clamps, so its BRS derivative ends at the inline D1 store.

## Conditional local derivatives

The selected active level has positive snow and graupel and strictly
interior, raw-rate-winning melt caps. The differentiable replay carries the
source-ordered snow and graupel producers through `sfac/gfac`, the sequential
state stores, `rhox→delta_brs_capped`, and D1 temperature. The independent
analytic tangent is compared with Torch JVP, a mixed-output weighted VJP,
and represented-input-gap central differences. Both endpoints independently
match a scalar source-order replay in raw f64 bits and retain the selected
gate/cap/divisor branches.

| Unit input direction at D1 entry | QSout JVP | QRout JVP | NRout JVP | BRSout JVP |
| --- | ---: | ---: | ---: | ---: |
| Relative QV16 | `0` | `+2.3062417516293893e-9` | `+0.04155892392198228` | `−2.5627159771234586e-12` |
| Absolute T16, 1 K | `−8.666008166953618e-5` | `+9.468277778838799e-5` | `+388.06856471664145` | `−8.914889997487062e-9` |
| Relative QS16 | `+0.0006696513402210594` | `0` | `−370.9677698530173` | `0` |
| Relative QG16 | `0` | `0` | `−220.3118902928324` | `0` |
| Relative rhox16 | `0` | `0` | `0` | `+1.3585452844342608e-8` |

QV changes graupel production through `cpm→snow-heated t1`; T changes
both melt producers. QS and QG relative directions change their respective
number factors as `1/QS` and `1/QG` in the chosen interior gates. The
relative `rhox` direction changes only the f64 BRS quotient in this map.
Finite-difference errors and branch signatures are retained in
[results.json](results.json). The largest reported relative FD–JVP error is
`0.010101...` for the `rhox` direction at `h=0.1`, the expected curvature of
`1/rhox`; smaller steps are also checked. The analytic and AD comparisons
are substantially tighter and are not judged by this one large-step error.

## Limits

These are conditional f64 value and local derivative checks for one actual
native call. Density, pressure, QI/NI, snow/graupel slopes and intercepts,
`work2`, `precg2`, incoming QR/NR/BRS, geometry and the substep schedule are
fixed. The packet does not differentiate their upstream producers, run a
perturbed host, certify the operational f32 stores or the later ProgB/BRS
path, establish QNICE's physical unit, or validate whole-host/RTTOV JVP/VJP.
The exact stored results are SHA-pinned; new derivative computations are
checked against independent formulas and stated numerical criteria rather
than demanded to reproduce every saved reduction bit across platforms.

`scientific_status: INCONCLUSIVE`; `physical_unit_status: INCONCLUSIVE`.

The [postmelt ProgB packet](../native_d1_progb_ad_2026-11-04/README.md)
subsequently records the same-call QG/BRS ratio, `[100,900]` density
selection, returned BRS, and selected branch-local derivatives. This
packet's D1 inline-store scope and original results remain unchanged.
