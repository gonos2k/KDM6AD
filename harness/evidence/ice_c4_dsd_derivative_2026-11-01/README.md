# Branch-interior ice saturation derivative replay

This [offline replay](replay.py) extends the [C4/DSD forward packet](../ice_c4_dsd_boundary_2026-11-01/README.md). Its two full-runtime reference states have initial `qv−qs_ice = -1e-12` and `+1e-12` at 263.15 K and 80 kPa. Exact saturation remains a separate value and branch case; this replay does not assign it a unique full-runtime derivative. The setup is a synthetic f64 public oracle, not a native host or RTTOV run.

At the first column's top WRF level, qv has direction `1e-12` per unit dimensionless parameter. The forward family recomputes moist density from qv at each point. With parameter step `0.01`, each represented one-sided qv change is `9.999813477268304e-15`, compared with nominal `1e-14`. The replay reports both the nominal-step central difference and the secant rescaled by the **represented** plus-minus width. It records each selected output's JVP, difference, signed error, signal and local binary64 spacing.

The actual C3/C4 observers return the original graph tensors. For QI, NI, QV and TH at the selected output level, the observer-on and observer-off JVPs and primal values must match by raw bits. Baseline and both difference endpoints must retain the checked full trace signature, subcycle counts, C3/C4 top-level branch and final DSD masks. The QI secant must agree with its JVP to relative `1e-6` on both sides; the above-saturation NI response has a relative `1e-8` check. These are diagnostic checks for this fixture, not a general scientific tolerance. The below-saturation NI direction is about `-4e-12` while the represented output change is only about 22 binary64 spacings; QV's below-saturation difference is zero at stored precision. Those components are reported without a relative acceptance claim.

The exact-saturation DSD check feeds the **recorded pre-limiter QI, NI and density** to the real `apply_dsd_number_limiters_torch()` and reproduces the recorded NI output. Its strict `ice_too_large`/final-number-gate branch returns `8.15540970156244`. Under fixed density and selected slope bound, a relative QI seed gives a relative NI output tangent of **1**, while the direct incoming NI tangent and adjoint are **0**. The replay compares the helper's JVP, VJP, independent source coefficient and branch-preserving differences, checking the actual ice masks at all four difference endpoints. This isolated stage derivative does not supply a full-runtime derivative at exact ice saturation.

The retained [39-level native column](../interior_profile_jvp_2026-10-31/native_column.npz) is also checked at native one-based levels 21 and 23. Reconstructed ice saturation places level 21 below and level 23 above saturation. This is a **saved checkpoint preflight only**. It has no same-call C3/C4 operands, subcycle selection, limited rate, final DSD stage, or executed host build binding. A native follow-up must capture those together at one call before assigning an executed branch to either level. Raw QNICE units also remain uncertified.

```bash
python3 -m harness.evidence.ice_c4_dsd_derivative_2026-11-01.replay
python3 -m unittest discover -s harness/evidence/ice_c4_dsd_derivative_2026-11-01 -v
python3 -O -m unittest discover -s harness/evidence/ice_c4_dsd_derivative_2026-11-01 -v
```

The source manifest checks code bytes in this checkout and inherits the parent packet's source checks. The native fixture has its own pinned SHA-256. These co-versioned pins establish internal consistency, not independent authentication of private executable or omitted checkpoint bytes. The result remains **`scientific_status: INCONCLUSIVE`**; operating f32 branch parity, physical QNICE and number budgets, and observation cost effects are separate checks.
