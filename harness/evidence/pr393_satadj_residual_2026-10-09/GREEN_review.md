# Green review: local satadj residual denominator

This review resolves the arithmetic portion of the PR393 checklist against
only two public JSON inputs: the PR391 clear-state result and the PR392 applied
partition result. It does not use the archived forecast, its NPZ checkpoint,
native outputs, RTTOV, a KDM6 step, or an optimizer.

## Checklist findings

| Check | Finding |
| --- | --- |
| Input and scope | Reproduced from the two named JSON receipts. Their SHA-256 hashes are recorded in `RESULT.json`; the reader re-hashes them on every run. |
| Thermodynamic constants | Uses `xa`, `xb`, `ttp`, `psat`, `ep2`, `rv`, and `qmin` exactly as rounded in the PR391 result's executed f64 constants. |
| Post-activation state | For each of the four 5 s calls, forms `qv_a=qv_in-a`, `qc_a=qc_in+a`, and `T_a=T_in+(xl/cpm)*a` from the PR392 result's reconstructed `a`. The receipt explicitly labels `a` reconstructed rather than directly captured. |
| Implemented denominator | Replays the requested left-associated expression `Dimpl=1+((((L*L)/(Rv*cp))*qs)/(T*T))`. |
| Exact local derivative | Differentiates the uncapped water saturation map analytically: `dqs/dT=ep2*p/(p-es)^2 * es*(-xa/T+xb*ttp/T^2)`. `L` and `cp` are held fixed at their captured per-call values. |
| Residual prediction and observation | Computes the local linear prediction `gplus/g=1-Dexact/Dimpl`; computes the observed finite ratio from returned qv/T endpoints. It does not equate a finite update with an infinitesimal derivative. |
| Guards and branches | All four derivative points are above the temperature lower clamp and water-branch threshold; `es<0.99p`, `qs>qmin`, `p-es>qmin`, and `qv>qmin`. The condensation/evaporation availability caps are inactive in the reconstructed calls. The sign of `g` selects condensation, evaporation, condensation, evaporation. |
| Activation gate and N1 inventory check | Call 3 has `sw_percent>0` and reconstructed `F=0.022022771`, while captured `NC/(NC+NCCN)=0.668149012`. The recorded activation equation therefore clamps `b` to zero, matching stored reconstructed `b=0`, `ncact=0`, and applied `a=0`. NC/NCCN are captured volume inputs; F, b, and a are reconstructed or derived, not direct measurements. |
| Water and latent budget | Carries forward only the PR392 satadj-stage totals: `a+c=8.056482903087553e-5 kg/kg`, cumulative qv/qc closure `3.1170812458958252e-19 kg/kg`, and latent closure `-8.545523678941025e-14 K`. These are not a complete microphysics or host budget. |
| Higher-order or convergence claims | None. This is a scalar local first-order derivative check plus finite endpoint ratios, not a sixth-order check, timestep convergence result, or optimizer acceptance result. |

Input hashes: PR391 `result.json` is
`a5bf4fb627e51569a033c585ae567adb418126a960e4eadd06e17401d8a3c524`; PR392
`RESULT.json` is
`6c1c22dae68fb71ee9d35a96db644a5ee60877be484a6410886d8fdb345b3494`.

## Recomputed values

For the second 5 s call, the reader obtains
`Dimpl=3.630693760812917`, `Dexact=3.707384080121035`, predicted
`gplus/g=-0.021122772770278`, and observed finite `gplus/g=-0.021023471023997`.
For the third call it obtains `3.630022709880883`, `3.706670897179219`,
`-0.021115071013110`, and `-0.021117159264919`. Both agree with the rounded
published values within `2.65e-10`; the exact comparison and input hashes are
machine-readable in `RESULT.json`.

The comparison uses `g=qv_a-qs(T_a)` and the implemented applied amount
`c=g/Dimpl`. With the captured `L/cp` held fixed, the local endpoint residual
is `gplus ≈ g-c-(dqs/dT)*(L/cp)*c = g-Dexact*c`; dividing by `g` gives
`gplus/g ≈ 1-Dexact/Dimpl`. The observed value instead evaluates saturation at
the captured finite endpoint `(qv_out,T_out)`.

| 5 s call | `g` (kg/kg dry) | `Dimpl` | `Dexact` | Predicted `gplus/g` | Observed finite `gplus/g` | Satadj sign / cap |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | +2.88079107e-4 | 3.603618525 | 3.678602257 | −0.020807899 | −0.024840307 | condensation; available-qv cap inactive |
| 2 | −7.15597339e-6 | 3.630693761 | 3.707384080 | −0.021122773 | −0.021023471 | evaporation; available-qc cap inactive |
| 3 | +1.50443399e-7 | 3.630022710 | 3.706670897 | −0.021115071 | −0.021117159 | condensation; available-qv cap inactive |
| 4 | −3.17693722e-9 | 3.630036819 | 3.706685892 | −0.021115233 | −0.021115180 | evaporation; available-qc cap inactive |

The first call has a much larger supersaturation residual and finite correction:
the predicted ratio is `-0.020807899347651`, while the endpoint ratio is
`-0.024840306748108`. That gap is consistent with using a local derivative for
a finite update and must not be presented as a failed arithmetic reproduction.
The fourth call is close to saturation (`g=-3.17694e-9 kg/kg`), so its ratio
is more sensitive to endpoint rounding.

The narrow N1 check uses the third 5 s call's captured volume inputs
`NC=201355994.628 m⁻³` and `NCCN=100007909.159 m⁻³`. Its reconstructed
`F=0.022022771` gives an unclamped number increment
`(NC+NCCN)F-NC=-194719126.456 m⁻³`. Applying the recorded
`b=min(max((NC+NCCN)F-NC,0),NCCN)` yields `b=0`; this matches the receipt's
reconstructed `b=0` and `a=0` despite the true strict activation gate. This
confirms the inventory-threshold explanation from the existing record and does
not add a new process trace or physics claim.

## Reproduction

From the repository root, run:

```sh
/opt/local/bin/python3 harness/evidence/pr393_satadj_residual_2026-10-09/analyze_residual.py
```

The reader accepts `--clear-result`, `--partition-result`, and `--output` for
other copies of the same public JSON receipt formats. It uses the standard
library only and asserts the published second/third call reconstruction and
the inactive guard/cap conditions. It does not write over any source input.
