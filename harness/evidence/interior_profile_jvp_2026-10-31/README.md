# Interior native profile-builder JVP replay

This packet validates the **profile builder (G)** at one retained checkpoint column, native one-based `(164,242,21)` and RTTOV zero-based row 45. It is an offline source/AD check. It makes no host, KDM or RTTOV calls. The wider scientific status remains **INCONCLUSIVE**.

[`native_column.npz`](native_column.npz) retains one 39-level REAL4 native column, its 40 interfaces, vertical coefficients, `XLAND`, and the fixed reference profile needed to build 66 RTTOV levels. [`native_column.json`](native_column.json) pins the fixture and records the original checkpoint, observation input and case-manifest SHA-256 values. [`export_private.py`](export_private.py) checked those full private inputs before extracting the column. Public replay can hash the retained fixture and exporter, but cannot reopen the omitted 1.2 GB checkpoint or the 383 MB observation input. The checkpoint labels QNICE as `kg-1`; its physical mass basis is **not certified** by that label.

The [replay](replay.py) first runs the PR #499 parent packet verifier, then checks the 519 source files recorded by the original private experiment against the current checkout. It rebuilds the same profile using the actual REAL4 values widened to float64. All 66 rows of retained baseline HYDRO6, HYDRO7, HYDRO_DEFF6 and HYDRO_DEFF7 match **exactly**. At row 45, QI is `8.316413158127034e-8`, raw QNICE is `40.72736740112305`, and AL/ALB-derived dry density is `0.49126261472702026`. The baseline ice content is `4.0855428732116826e-5 g/m3`, diameter `28.705148916281722 µm`, and cloud fraction `0.999999`. Stored snow is zero at this layer; the content and size bounds are strictly interior at the baseline and tested endpoints.

The batch adapter passes `N_raw / rho_d` to the dry-number cloud profile. That bridge converts it back to a volume number with the same density. On this active, no-snow, unclamped branch, the source-form scalar relation is

\[
H=1000\rho_d QI,\qquad D=C(\rho_d QI/N_{raw})^a,\qquad a=\operatorname{float32}(1/3).
\]

The independent tangent is therefore (dH=1000(\rho_d\,dQI+QI\,d\rho_d)) and (dD=aD(dQI/QI+d\rho_d/\rho_d-dN_{raw}/N_{raw})). The replay compares the **actual `profile_jvp()`** with this scalar formula, f64 centered rebuilds at four steps, and an autograd VJP checked against both the formula and JVP inner products. The per-direction values below are derivatives with respect to a dimensionless relative parameter.

| Direction at the selected layer | (dH), g/m³ | (dD), µm |
| --- | ---: | ---: |
| QI increases by its baseline value | `+4.0855428732116826e-5` | `+9.568383257253942` |
| raw QNICE increases by its baseline value | `0` | `-9.56838325725394` |
| QI increases and raw QNICE decreases | `+4.0855428732116826e-5` | `+19.13676651450789` |
| density increases by its baseline value, raw QNICE fixed | `+4.0855428732116826e-5` | `+9.568383257253942` |

All eight differentiated JVP profile fields are zero outside RTTOV row 45, including the 27 fixed upper rows; the thermodynamic fields and liquid optics are zero even at the target. Cloud fraction is a fixed, gated value outside these eight JVP fields; its target value is checked at the baseline and f64 endpoints. The density-only direction checks the optical coordinate conversion but is **not** a standalone physically consistent checkpoint perturbation of AL/ALB.

The retained PR #498 REAL4 plus/minus states are rebuilt from their **actual rounded QI and QNICE values**, and all their stored HYDRO7 and HYDRO_DEFF7 rows match exactly. The realized relative QI direction ranges from `0.9996316742` to `1.0000588672`; raw QNICE ranges from `-1.0003339130` to `-0.9998655918`. Using each realized direction, the content secant and JVP agree exactly at reported precision; the diameter secant minus JVP grows from about `7.8061e-8` to `4.9894e-6 µm` across the four steps, consistent with the independently checked nonlinear scalar secant. This difference is **not** the PR #498 BT FD-minus-K residual.

```sh
python3 -m harness.evidence.interior_profile_jvp_2026-10-31.replay
python3 -m unittest discover -s harness/evidence/interior_profile_jvp_2026-10-31 -v
python3 -O -m unittest discover -s harness/evidence/interior_profile_jvp_2026-10-31 -v
```

The result supports the profile-builder JVP for **QI, raw QNICE, their combination and density at this one native level**, and one weighted autograd VJP at the selected optical row. It does not certify other input directions, levels or output cotangents; identify QNICE's physical basis; certify a host trajectory or a named KDM process; test branch crossings or other columns; run an independent RTTOV VJP; or establish an end-to-end checkpoint-to-BT derivative. The earlier optical K comparison and this J_G comparison remain distinct evidence.
