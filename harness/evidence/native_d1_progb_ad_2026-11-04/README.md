# Same-call native post-D1 ProgB density reclamp and local derivatives

This packet extends the [D1 melt-to-state record](../native_d1_melt_state_ad_2026-11-04/README.md)
on native column `(203,149)` in the same 20 s mp137 call
(`runtime_call=one_step_call=2`, 39 levels, `b_zero=27945`). A value-only
capture flag surrounds only the post-D1 `rebuild_aux` call. Inside the
executed `progb_param_torch`, it records the actual QG/BRS operands, gate,
f64 denominator, raw ratio, `[100,900]` limit, returned density and BRS,
and the selected lookup segment and velocity coefficients. It separately
records the coordinator's merged ProgB outputs. The 8,892-row capture
preserves all 7,917 parent rows in order, dtype, and raw word; 25 new fields
over 39 levels add 975 rows.

```bash
python harness/evidence/native_d1_progb_ad_2026-11-04/replay.py
python -m unittest discover -s harness/evidence/native_d1_progb_ad_2026-11-04 -v
PYTHONOPTIMIZE=1 python -O -m unittest discover -s harness/evidence/native_d1_progb_ad_2026-11-04 -v
```

The replay pins the capture, source snapshots, capture blocks,
build/run/session receipts, and the parent replay. Removing the new
value-only blocks from `coordinator.cpp` and `progb.cpp` restores their
parent bytes. The host executable and input checkpoint are unchanged.
The isolated DSO's capture-off and capture-on full endpoint SHA-256 both
equal the parent variant's
`225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070`.
Private executable, DSO, object, and full checkpoint bytes are represented
by published hashes and run records; this public packet does not rebuild
those historical objects independently.

## Executed postmelt density and BRS calculation

The scalar replay checks every **direct ProgB field** against the captured
raw f64 or Boolean word at all 39 levels. It checks the merged BRS at all
levels and the merged `rhox` where ProgB is active. It also joins the direct ProgB QG/BRS inputs
to the parent's D1 output words and joins the returned BRS through the
coordinator merge to the actual re-slope store. The selected f64 path uses

```text
active       = QG > qcrmin OR BRS > BRS_MIN
denominator  = max(BRS, BRS_MIN)
ratio_raw    = QG / denominator
rhox         = clamp(ratio_raw, 100, 900)      (active branch)
BRS_returned = QG / rhox                     (active branch)
```

Inactive cells have a separate retention path. The parent `preamble`
merges persistent ProgB diagnostics for inactive cells, while `bg`/BRS
follows its own keep semantics. This packet checks the active density
merge directly and records inactive merged values; it does not derive the
history of the retained diagnostics. A test capture with an inactive
merged-`rhox` word changed and its SHA recomputed can pass the selected
arithmetic checks. The ordinary CLI still pins the entire original
capture by SHA-256. The archived runner's inherited “D1 QI capture”
docstring is historical wording; its schema and recorded capture inventory
identify this ProgB run.

| Native level 16 | Captured value |
| --- | ---: |
| Post-D1 QG | `4.1812234388383836e-5` |
| Post-D1 BRS | `4.646212004038053e-8` |
| Raw QG/BRS ratio | `899.9209324078314` |
| Upper limit minus raw ratio | `0.07906759216859882` |
| Selected `rhox` | `899.9209324078314` |
| Returned and stored BRS | `4.646212004038053e-8` |
| Table segment | `800–900`, indices `7,8` |

Eight levels take an active interior ratio and 31 are inactive in this
call; no level selects the lower or upper density cap at baseline. The
captured `avtg` and `bvtg` interpolation results also replay in raw f64
bits. Baseline equality of BRS before and after re-slope is an observed
value relation. Its local derivative is checked below for the selected
interior branch; it is not inferred from equality alone.

## D1-to-ProgB conditional local derivatives

The differentiable replay composes the parent D1 snow/graupel producer and
state-store function with the postmelt f64 ProgB density, BRS, `avtg`, and
`bvtg` calculations. Independent source-derived tangents are compared
with Torch JVP, a mixed-output weighted VJP contraction, and central
differences using the represented input endpoints. Scalar source-order
calculations independently match both finite-difference endpoints in raw
f64 bits. Tested local endpoints retain D1 gates/caps and the ProgB active,
interior-ratio, and `800–900` table branches.

| D1-entry direction | Postmelt `rhox` JVP | Re-slope BRS JVP | `avtg` JVP |
| --- | ---: | ---: | ---: |
| Relative QG16 | `+1163.0564367765057` | `0` | `+89.21573315225235` |
| Relative `rhox`16 | `−263.1355043686744` | `+1.358545284434261e-8` | `−20.18459826911231` |
| Relative QV16 | `+8.901666689274184e-18` | `−2.5627159771234586e-12` | `+6.828290484008454e-19` |
| Absolute T16, 1 K | `+3.6461226759267057e-14` | `−8.914889997487062e-9` | `+2.796867782249863e-15` |

QV and T change D1 QG and BRS together, leaving their ratio's computed
first-order signal near floating-point resolution; the BRS responses remain
nonzero. Those near-zero density/table signals are not treated as resolved
physical effects. The QG and `rhox` directions have clear interior signals.

The earlier QG relative half-step `h=1e-4` is deliberately **excluded**
from local central-difference acceptance. Its negative endpoint has raw
ratio `899.8046267641537`, while the positive endpoint has raw ratio
`900.0372380515089` and selected density `900`. The conditional positive
crossing is `6.798259282050436e-5`. The crossing secant and each endpoint's
branch are reported separately in [results.json](results.json); for the
selected density the cross-branch secant is about `976.866`, versus the
interior JVP `1163.056`. Local QG and `rhox` checks use `h=1e-5,1e-6,1e-7`
with both endpoints inside the cap. Synthetic checks also exercise the
100/800/900 boundaries and the strict active gate; they are distinct from
the observed native call.

## Limits

The result concerns the selected f64, one-call, active interior branch.
Upstream slopes, intercepts, density, pressure, other state and forcing,
geometry, and the substep schedule remain fixed. A Torch re-expression is
used for local JVP/VJP; the executed C++ path supplies baseline values,
not a perturbed native AD call. This packet does not certify the operational
f32 raw-divisor and clamp path, inactive persistent-PR derivatives, the
rest of ProgB's gamma/slope outputs, later BRS limits, a whole-host or
RTTOV tangent, or QNICE's historical physical unit. The stored result is
SHA-pinned; each new computation is checked against independent formulas
and branch/numerical criteria rather than every saved reduction bit.

`scientific_status: INCONCLUSIVE`; `physical_unit_status: INCONCLUSIVE`.

The [isolated C++ graph packet](../native_d1_progb_cpp_ad_2026-11-04/README.md)
subsequently executes the captured D1-entry conditional map with the
same static C++ archive linked into the native variant and checks C++
autograd JVP/VJP. This packet's own derivatives remain the documented
Torch re-expression, and neither packet establishes whole-host AD.
