# Native activation upper-boundary TH16/QV16 sweep (2026-11-10)

This packet extends the saved native `(203,149)` column, 39 levels, 20-second f64 call and initial TH16/QV16 directions from [the thermal-input packet](../native_d1_thermal_input_cpp_ad_2026-11-10/README.md). TH is the packed **potential-temperature** state coordinate; physical temperature is `TH*pii` with forcing fixed. The executed C++ physics and coordinator source remain unchanged. A separately built test-only runner mode evaluates the same full `kdm6_fn` map around the activation-fraction upper boundary; the parent's baseline, VJP, QG/BRS and thermal direction results remain separately pinned.

## Boundary and measurements

The selected activation source computes `sw_percent=(qv/max(qs1,qcrmin)-1)*100`, then `activated_fraction=min(1,safe_pow(max(sw_percent/0.48,0),ACTK))`. The mathematical upper threshold is `sw_percent=0.48` percent. The runner brackets it with full-call value evaluations along initial TH16 and QV16 separately, retains each evaluated input's actual f64 word and activation/NC state, and narrows to adjacent representable input values on opposite observed fraction states. It records the f64 `sw_percent` and `activated_fraction` values, `ncact_raw` versus the `NCCN/dt` rate cap, positive-supersaturation gate and NCCN floor separately. The pre-minimum pow value is not directly captured, so a rounded `activated_fraction=1` tie alone does not prove which `minimum` operand supplied the result; an exact representable threshold is not presumed.

Existing native endpoints anchor the broad brackets: TH16 absolute `+0.001 K` keeps the activation fraction at its upper selection while `+0.01 K` leaves it; QV16 relative `-10^-4` keeps the upper selection while `-10^-3` leaves it. New bisection and side-interior points are isolated C++ executions, not new host captures. The runner evaluates strict points on each side and records selected-stage JVP/VJP rows for supersaturation, fraction, activation rate and NC/NCCN before and after activation. Independent one-sided value differences use actually represented input gaps and remain within the same recorded branches at several scales; unresolved output-ULP signals are reported rather than accepted as precise derivatives.

The upper bound can create a **kink** in the selected activation contribution. It does not imply that the total final NC16 tangent is zero on the saturated side: other smooth paths can still respond to TH/QV. The packet compares side-specific total tangents and values before identifying a cap-related difference. Adjacent-f64 endpoint output changes are a numerical continuity diagnostic with finite output resolution, not proof of mathematical continuity or a unique derivative at the tie.

## Observed brackets and side derivatives

The final boundary mode records **190 full-call forwards**: two baseline off/on evaluations, 168 value-only bisection evaluations, four strict-interior AD evaluations and 16 same-side one-sided differences. For each axis, the `sw_percent=0.48` and observed `activated_fraction=1` bisections terminate on the same pair of **adjacent f64 input words** in this call. The latter is an observed-value statement, not an unmeasured pre-minimum pow operand selection.

| Axis | Adjacent initial input words, lower / upper | `sw_percent` lower / upper | Fraction lower / upper | Final NC16 upper−lower |
| --- | --- | ---: | ---: | ---: |
| TH16 | `4073ff3df21f1aca` / `4073ff3df21f1acb` | `0.48000000000010257` / `0.4799999999999027` | `1` / `0.9999999999998784` | `−3.0368566513061523e−5` (**1,019 output ULP**) |
| QV16 | `3f7dfbea42c929bb` / `3f7dfbea42c929bc` | `0.47999999999999154` / `0.48000000000001375` | `0.9999999999999895` / `1` | `+2.682209014892578e−6` (**90 output ULP**) |

The corresponding `ncact_raw − NCCN/dt` values are `0 / −1.5441328287124634e−6` for TH and `−1.341104507446289e−7 / 0` for QV. The TH adjacent `20×Δ(ncact)` is `−3.088265657424927e−5`; the difference from the observed final-NC gap is `+5.140900611877441e−7` in the recorded update order. For QV, `20×Δ(ncact)` and the final-NC gap are equal at stored precision. This is endpoint arithmetic on one shared calculation, not a process-off attribution or a continuity proof.

| Axis and strict side | `D(activated_fraction)` | `D(ncact)` | Total `D(final NC16)` | Same-side NC16 FD scale with relative residual `<10^-6` |
| --- | ---: | ---: | ---: | ---: |
| TH, observed fraction `1` | `0` | `0` | `+6294480.325839229` | `10^-6 K`: `1.54045×10^-7` |
| TH, fraction below `1` | `−7.475034544315362` | `−94972014.54604448` | `−1893149644.5365849` | `10^-7 K`: `1.05262×10^-7` |
| QV, observed fraction `1` | `0` | `0` | `−112.99282024398357` | relative `10^-4`: `2.54880×10^-8` |
| QV, fraction below `1` | `+124.56156041756262` | `+1582435829.960713` | `+31648716486.243755` | relative `10^-8`: `2.85296×10^-7` |

Each side retains every tested scale and its actual represented input gap, branch signature, VJP/JVP dot and output-ULP resolution. The smallest QV fraction-`1` NC16 difference is only **380 output ULP**: its signal-relative FD residual is `0.00226`, while the absolute mismatch is about **0.86 output ULP**. It is not reported as `10^-6` relative agreement. All four sides have at least one larger, resolved same-branch scale meeting that relative criterion. The strict-side output gradients and nearby one-sided differences show different side responses; no single derivative at the cap is certified.

For each nominal one-sided step, the replay recomputes the source-generated endpoint (`TH_base+h` or `QV_base*(1+h)`) in f64, checks its raw input word and actual positive represented gap, and requires distinct endpoint words across scales. This prevents a recorded small-step endpoint from being relabeled as an independent larger-step difference.

Full replay rejects nonfinite saved values and nonfinite derived AD/FD diagnostics before accepting any side result, including side differences at scales that fail the relative-error criterion.

The replay requires both TH16 and QV16 interior records, both strict sides on each axis, four validated AD points and 16 validated one-sided FD endpoints. It derives those call counts from the records it checks and binds them to the saved 190-call ledger. Each bisection summary's terminal lower/upper observations must match the reconstructed trace records field by field, preserving f64 raw bits and value types. Repeated evaluations of the same input across the two predicate traces must also agree on their recorded observations. These checks reject incomplete or internally contradictory rehashed packets without changing the original C++ results.

## Limits

The branch sweep concerns one selected native f64 call and two initial state directions. D1 warm/snow/graupel caps, shared NC limiter, activation gate, `ncact` rate cap and NCCN floor are checked or explicitly identified as unobserved at each reported point. A change in any unrecorded branch limits the derivative conclusion. Operational f32, physical number/mass/volume budgets, whole host AD and GK2A–RTTOV cost sensitivity remain open. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`. Public CI replays the saved private runner result and source hashes rather than rebuilding that private executable.

Run `python -m unittest discover -s harness/evidence/native_activation_upper_boundary_cpp_ad_2026-11-10 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`.
