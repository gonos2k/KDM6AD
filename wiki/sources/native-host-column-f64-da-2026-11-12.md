---
title: Host-selected column f64 DA activation sensitivity
type: source
date: 2026-11-12
---

# Host-selected column f64 DA activation sensitivity

The [packet](../../harness/evidence/native_host_column_f64_da_2026-11-12/README.md) exactly widens all 624 saved f32 input words of [[native-host-column-f32-2026-11-11]] and runs the installed Legacy `kdm6_step_ad_c` on the B=1 column. The f64 map differs from the operational f32 map: 101/468 baseline f64 outputs, when rounded to f32, differ from the f32 output words. Its TH16 activation predicates cross at adjacent f64 words `4074005089907cc6`→`4074005089907cc7`, separate from the [[native-host-column-f32-boundary-2026-11-12|f32 transition]].

At strict interior points 0.01 K to either side, the selected activation masks remain fixed over three central-difference scales. The fraction-one side has NC16 JVP/VJP projection zero and identical NC16 endpoint words, so its nonzero response is unresolved. The fraction-below-one side has NC16 JVP about −7.8821467×10⁸ and a smallest-step independent central-difference relative residual about 2.86×10⁻⁹. A separate isolated f64 `torch::minimum` experiment observes `(0.5,0.5)` operand weights at a rate-cap tie, distinct from the whole-column tangent. These are state-sensitivity and operator observations, not named-process budgets, a perturbed WRF host adjoint or GK2A–RTTOV cost sensitivity. Scientific and physical-unit statuses remain `INCONCLUSIVE`.
