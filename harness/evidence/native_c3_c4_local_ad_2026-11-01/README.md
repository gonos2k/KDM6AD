# Native consumed C3/C4 local derivatives

This is a **local f64 replay**, not a host tangent-linear or adjoint run. It reads the PR 511 selected packet only after verifying its exact SHA-256 `ef185f41ef0aca0226c980ee0449c7e8ec4809770c98e46a09acfc113c38a224`, the PR source manifest and executed overlay via its verifier, and this directory's oracle source manifest. The independent packet pin is embedded in the replay; source pins are co-versioned, with commit identity supplying the review anchor. The upstream packet documents the native one-call inputs, historical capture hashes and their limitations.

For native levels 21 and 23, `ice_nucleation_torch` and `dep_sub_torch` consume the captured C3/C4 operands. All C3 and C4 output rates, saturation flags and complete-sublimation flag match saved f64 bits/booleans; the frozen-other-rate QI and NI update matches saved f64 bits. At the baseline, the selected C3 and C4 rates match the saved limited rates. During perturbations the replay **assumes these selected rates continue through the conservation limiter unchanged** and holds every other limited rate, auxiliary variable, slope, forcing and timestep fixed. It varies the common working NI input and C3 NI operand together, feeds C3 pinud and ifsat into C4, then updates QI/NI. This is conditional process sensitivity, not a derivative of the entire upstream or downstream model. NI has the packet's working numerical basis; its physical unit basis is unresolved.

| Level | dQI/dNI | dNI_out/dNI | dC4 pidep/dNI |
| --- | ---: | ---: | ---: |
| 21 | 0 | 1 | 0 |
| 23 | −5.017018556214326e−12 | approximately 0 | 0 |

Level 23 C3 deficit controls its mass and number rates; the direct NI identity cancels the number-rate response. Level 21 C3 is inactive. C3-to-C4 coupling is included, but the C4 ice raw candidate wins at both levels, so its local NI derivative is zero. A separate local direction `dn0i = n0i` holds slopes and the other inputs fixed: d(pidep) is −8.782281178665383e−12 at level 21 and +1.0855819230719068e−8 at level 23, with dQI equal to timestep times that rate. This is a relative intercept direction, not a derived DSD response.

`results.json` records JVP, componentwise VJP, and central differences using the actual represented plus/minus inputs in the denominator. NI steps are 0.1, 1 and 10; the relative n0i step is 1e−4. The replay checks the C3 gates and strictly winning candidate, C4 sign and strictly winning ice candidate, saturation and sublimation flags, and output positivity at the baseline and both perturbations. Tests compare to independent expected local derivatives, including the cancellation, and recompute the saved diagnostics with a bounded scalar-rounding allowance. Branch checks do not establish differentiability beyond these directions or intervals.

A separate [C5 replay](c5_replay.py) evaluates `ice_aggregation_torch` with the packet's working QI/NI, dry density and `supcol`, and a temperature inferred from the captured step-entry T and the source's `T0−supcol` relation. The temperature roundtrip is bit-identical, but the C5 input itself was not captured. Both C5 rate baselines match the **saved limited** `psaut/nsaut` bits; that equality does not independently prove the native pre-limit rates or limiter factor. With all other limited rates frozen and an **assumed locally identity limiter**, the relative working-QI direction gives:

| Level | d(psaut) | d(nsaut) | dQI after update | dNI after update |
| --- | ---: | ---: | ---: | ---: |
| 21 | 0 | 0 | `+8.333908748191352e−8` | 0 |
| 23 | `+1.4043743363389845e−9` | `+1.1465605817527942` | `+6.155909315749441e−7` | `−22.931211635055885` |

The C5 [saved diagnostics](c5_results.json) and tests compare branchwise analytic results, JVP, componentwise VJP and represented central differences at `h=1e−3, 1e−4, 1e−5`. They check the active, temperature, zero/raw/cap, number-cap and output-floor branches at the baseline and both endpoints. These are conditional local oracle derivatives. The **executed conservation-limiter derivative is not established**: the packet lacks its actual full pre-limit rate bundles and sequential scaling decisions. Full private captures, host sources, binaries and inputs are not redistributed; their recorded hashes are attestations, not independent reproduction. This does not establish physical conservation, host/f32 parity, RTTOV sensitivity or forecast skill.

```sh
python3 -m harness.evidence.native_c3_c4_local_ad_2026-11-01.replay
python3 -m harness.evidence.native_c3_c4_local_ad_2026-11-01.c5_replay
python3 -m unittest discover -s harness/evidence/native_c3_c4_local_ad_2026-11-01 -v
python3 -O -m unittest discover -s harness/evidence/native_c3_c4_local_ad_2026-11-01 -v
ruff check harness/evidence/native_c3_c4_local_ad_2026-11-01
```
