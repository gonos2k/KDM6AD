# Synthetic full-runtime C3 ice nucleation witness

The [replay](replay.py) takes the exact two-column, three-level **synthetic** state from PR #504's paired ice-chain test, reverses it into WRF vertical order, and runs the public `_kdm6_pure()` for `dt=1` with an explicit `NCCN=1e8`, `pii=1`, `p=80 kPa` and `xland=None` (the default maritime mask). Unlike PR #505's component replay, this call includes runtime's pre-sedimentation BRS update, CCN path and **automatic** main/ice `mstep` selection. The selected counts are `[1,1]` for both loops. It evaluates the legacy raw and opt-in normalized first-ice handoffs separately. No private host, C++, Fortran or RTTOV executable is called; scientific status is **INCONCLUSIVE**.

A scoped, single-thread Python observer invokes the original `ice_nucleation_torch()` exactly once and retains the **actual C3 producer arguments and outputs**. The unobserved full runtime is run separately and every final `State` field matches at the raw-bit level. The existing stage trace and PR #504 ice-chain capture connect the producer to the post-sedimentation state and the cold rate records. The 43 source paths are checked against a **co-versioned SHA-256 manifest**, which is a checkout consistency check rather than an independent trust root.

## Actual first-column target-deficit branch

| Selected top-level operand | Value |
| --- | ---: |
| Post-freeze NI entering C3 | `26.20400517796132` |
| Cooper target (N_d) | `104.52621617538789` |
| Target deficit | `78.32221099742657` |
| Raw mass nucleation rate | `2.050470559358255e-10` |
| Half-saturation supply candidate | about `0.00149257809058` |
| Remaining-supersaturation candidate | about `0.00298509378318` |
| Applied `pinud`, `ninud` | `2.050470559358255e-10`, `78.32221099742657` |
| C3 saturation-exhaustion flag `ifsat` | false |

The outer cold/supersaturation and inner target-deficit gates are active. The raw deficit mass rate is **strictly below both supply caps**. A separate binary32 scalar calculation reconstructs the source's constant particle mass `Minud=2.0943949699536724e-12`; producer output, cold rate, and limited cold rate words agree in this fixture. Other selected input regimes directly exercise the half-supply cap, remaining-supply cap, outer-inactive, **target-equal** and target-exceeded cases. These **isolated C3 inputs** are logical producer contrasts, not automatically reachable full thermodynamic profiles. They also retain the distinction that `ifsat` can be true with the inner target gate off, but is false when the outer gate is off.

At fixed actual C3 inputs on the uncapped target-deficit branch, (NI+\Delta t\,ninud=N_d); the isolated JVP and centered FD of that number output are both zero for an NI perturbation. The mass rate keeps a nonzero NI tangent, `-2.6179937124420904e-12` per unit raw NI. This **does not** make the entire runtime NI or QI sensitivity zero: C3 also feeds deposition, group limits and subsequent state updates.

## Full public runtime result and selected derivatives

| First synthetic column, top-first | Legacy raw handoff | Normalized first handoff |
| --- | --- | --- |
| Post-sedimentation QI | `0, 0, 0` | about `7.963e-8, 6.002e-8, 4.002e-8` |
| Final QI | about `2.082e-10, 1.627e-10, 1.480e-10` | about `8.065e-8, 6.080e-8, 4.062e-8` |
| Final NI | about `104.526` at all levels | about `104.524–104.525` at all levels |

The normalized/legacy final QI ratios are about **387, 374 and 274** from top to bottom even though NI is close. These are separate physical maps, not trace-on/off differences.

QI-only and NI-only one-hot perturbations at the first column's middle **fixture level** are run through the **full f64 public runtime** in both handoff modes. Baseline and ±`1e-4` retain the same captured stage masks, C3 strict deficit-minimum gate and subcycle topology. With the stage trace, ice-chain capture **and scoped C3 producer observer** enabled, JVP and VJP words match the unobserved run; JVP also agrees with central FD on the reported scaled numerical output vector `(QI*1e8, NI, QV*1e3, TH)`:

| Handoff | Direction | Maximum absolute FD–JVP on scaled vector |
| --- | --- | ---: |
| Legacy | QI only | `2.956e-10` |
| Legacy | NI only | `1.006e-10` |
| Normalized | QI only | `1.033e-10` |
| Normalized | NI only | `2.728e-10` |

These numbers are **fixture diagnostics**, not a general derivative tolerance or physically unit-bearing BT response. The captured masks do not enumerate every internal slope/min/clip branch. At `dt=1`, the runtime topology is fixed in these perturbations; topology changes require separate one-sided checks.

The replay now retains each selected input's baseline value, absolute and relative direction, actual ± endpoint and the **signed unscaled JVP, FD and error for every field, column and WRF level**. It also records the numerical factors used by the preceding packed-vector check (`QI*1e8`, `NI`, `QV*1e3`, `TH`). For a relative increase of initial NI at the first column's middle fixture level, the same output level gives:

| Handoff | Final QI JVP, unscaled | Final NI JVP, raw kernel coordinate |
| --- | ---: | ---: |
| Legacy | `-4.63411610585e-11` | `-2.53481348370e-4` |
| Normalized | `+4.60406780875e-10` | `+5.37310055030e-4` |

The opposite signs are results of two distinct forward rules at this one synthetic state. They do not establish which physical rule should be adopted. The [separate weak-supersaturation replay](../ice_nucleation_supply_2026-10-31/README.md) tests a strict supply cap in the full public runtime.

An f32-input replay is classified as **mixed precision**: QI is float32 after sedimentation but float64 after D2–D4, and final QI/NI are float64. It cannot certify an operational f32 C++/Fortran calculation or its branch bits.

```bash
python3 -m harness.evidence.ice_nucleation_runtime_2026-10-31.replay
python3 -m unittest discover -s harness/evidence/ice_nucleation_runtime_2026-10-31 -v
python3 -O -m unittest discover -s harness/evidence/ice_nucleation_runtime_2026-10-31 -v
```

The retained evidence does not establish QNICE's physical unit, named host-process attribution, a private native run, RTTOV cost, forecast impact or analysis acceptance. It isolates one strongly supersaturated synthetic runtime branch and several direct C3 counterexamples. Real native evidence must connect the same producer operands and applied amounts to the executed host build before a physical conclusion is made.
