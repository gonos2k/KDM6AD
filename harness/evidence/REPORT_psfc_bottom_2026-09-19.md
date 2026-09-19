# Native-model bottom-pressure assumption comparison

## Question and fixed contract

Compare the retained P8W bottom with PSFC from the **same local 5 km model**,
without replacing the native model pressure coordinate in production. This is
one deliberately separate observation-operator boundary experiment at column
45577 (j=194, i=181), retaining all 39 mass-level pressures and atmospheric values,
39 unchanged upper interfaces, centre-anchor viewing geometry, surface inputs,
observations, sigma=1 K, Huber delta=1, zero bias and QC.

The stored PSFC is float32 `100888.234375 Pa`; promoting this stored value to
float64 and dividing by 100 yields `1008.88234375 hPa`. The retained P8W bottom is
`1008.8232416207046 hPa`, a difference of `5.9102129295351915 Pa`. The bottom full
level remains `1005.8479309082031 hPa`, strictly inside both choices of boundary.
Stored precision is preserved; promotion does not restore information lost before
NetCDF storage. No external model/reanalysis profile or additional upper data is used.

For each fixed bottom choice b, the measured quantity is
`g_p(b) = K(z0; b) v_p`, where `v_p` is the retained process profile tangent.
KDM forcing, full-level conversion and the profile values are unchanged, so the
two existing process directions can be reused with one baseline direct/K call.
The Huber seed is recomputed from the new BT before `dJ/dalpha = seed dot g_p`.
This is a finite comparison between two prescribed boundary definitions, not
`dJ/dPSFC`, a new independent process finite-difference check, or a pressure JVP.

## Interpretation limits

The lowest pressure interval grows from 5.9665355345 to 6.0256376638 hPa
(about 0.99056%) while its T/Q/cloud samples stay fixed. This deliberately changes
the radiative column boundary; it is not a new hydrostatically adjusted model state.

The original P8W evidence remains the baseline and is not overwritten. A smaller
cost in this comparison would not select the physically correct boundary or
establish forecast skill. The model top, coefficient background gases, cloud
representation and all other operator assumptions stay fixed.

BT text rounding and K-text rounding are separate from internal RTTOV accuracy.
A difference exceeding text spacing is resolvable in the serialized outputs; it
does not by itself bound upstream numerical or physical error. Native input
identity and unchanged QC are checked separately from derivative agreement.

Exact pixel navigation, upper/gas assumptions, representative process coverage,
particle-number units/nonzero applied transport and timestep convergence remain
open. This experiment measures only the selected bottom-boundary assumption.

## Measured result

The [public numerical summary](psfc_bottom_comparison_2026-09-19.json) includes all
16 raw BT tokens, observation values, quality/masks, Huber seeds, channel tangents,
six profile-field contributions and file hashes. Preflight independently checked
all 44 copied files: only the final numeric line of `p_half.txt` changed. All 39
full pressures, 39 upper interfaces and the other 21 input files are unchanged.
Strict interleaving passes. The two process alpha-zero baselines are byte-identical.

Exactly **one** additional RTTOV direct/K call was executed. Direct and K outputs
agree exactly in BT and quality. The same seven channels remain usable;
WV063/WV069 retain quality 32768. There is no silent channel-set change.

| Quantity | P8W baseline | PSFC bottom |
| --- | ---: | ---: |
| J | 20.511083910530242 | 20.51118789168064 |
| Deposition dJ/dalpha | -0.013383672296319402 | -0.013383655674129262 |
| Riming dJ/dalpha | -1.3201112415040182e-5 | -1.3201138806864955e-5 |

Signed changes divided by the absolute baseline derivative are **+0.000124198%**
for deposition and **-0.000199921%** for riming. Maximum absolute channel-derivative
relative changes are **0.000455158%** and **0.000335358%**, respectively. Each cost
uses its own Huber seed; the IR133 seed changes with its new BT.

| Usable channel | PSFC minus P8W BT (K, Decimal from raw strings) |
| --- | ---: |
| WV073 | -0.000000018 |
| IR087 | +0.000057859 |
| IR096 | +0.000032690 |
| IR105 | +0.000043425 |
| IR112 | +0.000021588 |
| IR123 | +0.000012299 |
| IR133 | +0.000001562 |

Both endpoint text spacings are 1e-9 K for these channels. Assuming nearest
rounding, each value has at most half a spacing of text error, giving a BT
difference contribution of at most **1e-9 K**. Every listed change exceeds that
bound; WV073 is the weakest at 18 spacings. This is a direct difference between
boundary assumptions, not a central difference divided by a process epsilon.
No global bound for printed K contraction error or total RTTOV error has been
established. Small reported derivative changes remain conditional on that limit.

The local live wrapper used Python 3.10.11 / NumPy 2.2.6 / PyTorch 2.13.0;
this retained runtime is distinct from the unchanged Python 3.12 CI policy.
No production physics, ABI, grid writer, QC, tolerance or CI setting was changed.
This closes the selected bottom-assumption **measurement**, not the choice of a
universal surface boundary, all-column sensitivity, or upper/gas assumptions.

A separate Python 3.12 arithmetic check of the public JSON verifies the seven
Decimal BT differences, unchanged QC, Huber seed/cost, both scalar derivative
contractions and 32 channel field sums. These checks are not another live RTTOV
call. Green/Red review checks the retained raw input/output contract separately.
Graphify structural refresh and manual KG synthesis record the changed evidence;
no full oracle/native suite is claimed for this documentation/data-only change.
