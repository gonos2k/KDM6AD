# Native snap-A ice-number rewrite: conditional local replay and AD

This packet extends the [same-call 39-level native ledger](../native_qnice_39_applied_2026-11-03/README.md)
without running the host again. It reads that packet's immutable raw capture
SHA-256 `27b89eb5b38b88174f55188be7d724cd74df8e6577c034a044581c78b3dff3bf`
and the pinned executed C++ coordinator source. The public Python oracle's
`_limit_number_for_lamda()` from the current checkout is evaluated at the
**captured snap-A inputs**. Its source, f32 constant implementation, and
constants definitions are retained in [source_snapshots](source_snapshots/)
with fixed hashes. The actual compiled C++ lineage is the parent packet's
separately pinned source and build receipt; the current Python oracle is a
regression target, not a claim that those Python bytes were compiled in WRF.
All results are local to that selected producer map; upstream sedimentation,
later C3/C4/C5, host time integration and RTTOV are outside this derivative.

```bash
python harness/evidence/native_qnice_snap_a_ad_2026-11-03/replay.py
python -m unittest discover -s harness/evidence/native_qnice_snap_a_ad_2026-11-03 -v
python -O -m unittest discover -s harness/evidence/native_qnice_snap_a_ad_2026-11-03 -v
```

The CLI ends with `NATIVE_QNICE_SNAP_A_LOCAL_AD_REPLAY_PASSED`. The saved
[results.json](results.json) retains level-specific inputs, outputs, branch
margins, represented finite-difference endpoints, JVP, VJP, and signal size.
Its numerical finite-difference diagnostics are checked within explicit
bounds rather than as cross-platform raw bits.

## Source-order baseline

The actual call's forcing density and snap-A QI/NI are binary64 working
values. The ice-number constant PIDNI was formed in f32 and widened:
`1570.79638671875` (`0x44c4597c` as f32). The exponent uses the f32 value
of `1/3`, widened to `0.3333333432674408`. The active gate is
`QI >= 1e-14` and `NI >= 0`; the ratio and QI×density floors are `1e-30`.
The lower and upper slope bounds are 9080 and 1.82e6. The source uses
`exp(log(ratio) × f32(1/3))`, then `<=` for the lower bound and `>=` for the
upper. On the selected lower branch, it stores source-order
`DEN × QI × pow(9080,3) / PIDNI`.

The independent scalar rendition and the public Torch oracle reproduce the
**NI outputs of all 39 native levels as f64 raw bits**. The captured gates and
auxiliary `lambda_raw` diagnostics imply the same lower/upper branch winners
as the source and oracle at all 39 levels. The limiter's winner flags were
not themselves captured. The six changing levels are:

| Native level | NI before | NI after | Lower slope selected |
| ---: | ---: | ---: | :---: |
| 25 | 0 | 0.0000033864200867247893 | yes |
| 20 | 0.0017688861416626483 | 22.098723072163416 | yes |
| 19 | 0 | 20.469069918980324 | yes |
| 18 | 0 | 15.796100824316364 | yes |
| 17 | 0 | 8.31364022014741 | yes |
| 16 | 0 | 0.7932710418717757 | yes |

Their **recorded** `Σ NI·DELZ` stage difference is `+49027.35812796282`
in the unresolved numerical NI coordinate. This is a before/after snap-A
change, not a physical particle creation or conservation judgment.

## Conditional derivative contract

For a fixed active lower-bound branch with `QI`, `DEN` positive, the local
map is `N_out = C×QI×DEN`, where `C = pow(9080,3)/PIDNI`. Thus relative QI
and relative DEN seeds each give a JVP equal to `N_out`. The replay compares
this independent analytic relation to the oracle's JVP, a weighted VJP,
JVP/VJP transpose product, and centered differences at h=`1e-3`, `1e-4`,
`1e-5`. It uses the **represented plus/minus input gap** per level and checks
strict QI and lambda margins, the ratio/floor selections, and nonzero gaps at
every endpoint. The scalar lambda is compared within a `1e-12` relative
bound to allow platform libm differences; captured output NI words remain
bit-exact comparison targets. At h=`1e-5`, the largest absolute
finite-difference minus JVP residual was approximately `1.81e-10` in the
recorded NI coordinate; the weighted transpose difference was
`3.55e-15` in this run.

Five changed levels (25, 19, 18, 17, 16) have incoming NI **exactly zero**.
They are on the `NI >= 0` gate boundary, and a symmetric NI perturbation
would cross it. Their QI and density directional checks hold NI fixed at
zero; **no two-sided NI derivative is claimed for these five levels**.
Level 20 has positive NI and remains on the lower-slope branch under the
tested symmetric NI direction. Its direct NI JVP, VJP component and centered
differences are zero within the recorded calculation.

This is a synthetic-direction local test at **actual captured native
operands**, using the f64 Python oracle. It does not certify an operational
f32 derivative, a full host/RTTOV JVP or VJP, the physical QNICE number
basis, or a unique derivative at gate and slope ties. The parent packet's
`scientific_status: INCONCLUSIVE` and `physical_unit_status: INCONCLUSIVE`
remain in force.
