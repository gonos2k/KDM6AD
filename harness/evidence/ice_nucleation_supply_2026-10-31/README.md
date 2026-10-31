# Coherent weak ice supersaturation in the public runtime

The [replay](replay.py) extends PR #506's synthetic two-column state without changing its hydrometeors or initial numbers. It runs with **dt=1 s** and sets `T=263.15 K`, `p=80 kPa`, `pii=(p/100 kPa)^(Rd/Cpd)`, `TH=T/pii`, and moist density from the ideal-gas relation using the same qv, Rd and Rv. It obtains `qs_ice` and `qs_water` from the project's thermodynamics and sets **qv = qs_ice + offset**. Thus ice supersaturation and ice relative humidity are generated together by the full public runtime; neither C3 input is assigned independently. This is an idealized thermodynamically consistent **f64** family, not an observed native atmosphere or a certified host density/number-unit contract.

At `263.15 K, 80 kPa`, `qs_ice=0.0020148438188448653`. For the weak `offset=1e-10`, qv is `0.0020148439188448653` and the actual C3 ice RH is `1.0000000496316386`. The full runtime includes BRS preparation, NCCN, automatic one-step `[1,1]` main/ice topology, and the legacy raw first-ice handoff. The replay captures the **actual** C3 arguments and output via PR #506's scoped observer, checks all final State words against an unobserved run, and follows producer rates through the cold and limited-cold records. C3 consumes saturation/RH staged at **microphysics entry**; the later cold-rate state's temperature can differ slightly after D2–D4. The replay verifies the staged input relation at that owning boundary.

| Actual first-column top-level candidate | Weak offset `1e-10` | Strong offset `5e-10` |
| --- | ---: | ---: |
| Raw number-deficit mass rate | `1.5373343406e-10` | `1.5373343410e-10` |
| Half ice-supersaturation rate | **`5.0000000017e-11`** | `2.5000000009e-10` |
| Remaining ice-supersaturation rate | `6.0061112490e-9` | `6.4061004133e-9` |
| Strict minimum | **half supply** | **number deficit** |
| Final QI | `5.0002008544e-11` | `1.5373544263e-10` |
| Final NI | `52.12559656` | `104.52591683` |

The weak case is a **realized supply-limited C3 branch in the full public runtime**, with strict positive margins to both other candidates. It does not refill NI to the Cooper target. The strong case refills most of the deficit. The C3 saturation-exhaustion flag `ifsat` is true in both because the preceding rain evaporation rate is negative and large relative to the tiny positive ice supersaturation. This can suppress downstream deposition; final state differences are not attributed to C3 alone.

Under ordinary subfreezing default-control conditions, the source gives a conditional reason a **strict remaining-supply minimum may be unreachable**: `qs_water>=qs_ice`, and warm rain condensation is capped at half the water supersaturation rate while evaporation has `prevp<=0`. For positive ice supersaturation, `prevp<=max(0,water_supsat/(2dt))<=ice_supsat/(2dt)`, hence `supice=ice_supsat/dt-prevp>=ice_supsat/(2dt)`. The replay checks the ingredients and a strict inequality on these selected runtime states. This is a source-based inference for the named regime, not a global proof across arbitrary controls, pathological temperatures or rounding ties. Direct producer inputs from PR #506 can select the remaining-supply cap but do not prove full-runtime reachability.

A one-hot qv direction at the first column's middle WRF level uses `dqv/dparameter=1e-10`, with moist density recomputed from qv at fixed p and T. At `h=0.01`, the actual qv endpoints differ by `±1e-12`; all **captured** stage masks, subcycle counts and C3 half-cap margins remain on the same side. The trace does not enumerate every internal slope/min/clip branch. Full-runtime f64 JVP/VJP are bit-identical with the observer on/off. On the scaled numerical vector `(QI*1e8, NI, QV*1e3, TH)`, maximum central FD–JVP difference is `1.0092298e-7` and relative L2 difference is `3.99581e-9`. The unscaled middle-level JVPs include `dQI=5.0e-11` and `dNI=25.25719925` per unit direction. Every field/column/level's signed JVP and FD is printed in JSON; these are fixture diagnostics, not a general scientific tolerance.

An **exact ice-saturation** boundary contrast runs initial offsets `-1e-12`, `0`, `+1e-12`. The actual C3 outer gate is false, false, true, respectively. The full-runtime final NI also changes through other branches, so the one-sided results must not be assigned to C3 alone; no central derivative is asserted at equality.

Near this `qs_ice`, one binary32 qv ULP is `2.3283064365e-10`, larger than the weak offset `1e-10`. The f64 supply branch therefore does **not** certify the existence or bit pattern of an operational f32 host branch. There are no new host, C++, Fortran or RTTOV calls. QNICE units, applied native budgets and observation cost remain **INCONCLUSIVE**.

```bash
python3 -m harness.evidence.ice_nucleation_supply_2026-10-31.replay
python3 -m unittest discover -s harness/evidence/ice_nucleation_supply_2026-10-31 -v
python3 -O -m unittest discover -s harness/evidence/ice_nucleation_supply_2026-10-31 -v
```

The new replay checks its sources against a bundled manifest and calls the PR #506 parent source checks first. Neither co-versioned manifest independently authenticates an arbitrary changed checkout or a private executable.
