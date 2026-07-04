---
title: KDM6 vs KDM6AD Code Comparison
date_ingested: 2026-06-25
source_type: analysis-note
tags:
  - kdm6
  - kdm6ad
  - wrf
  - automatic-differentiation
---
# KDM6 vs KDM6AD Code Comparison

## Summary

This note captures the 2026-06-25 local code comparison between [[KDM6]] and [[KDM6AD]] in KDM6AD-k. The comparison showed that [[KDM6AD]] is not a direct automatic-differentiated Fortran rewrite of `module_mp_kdm6.F`; it is a Fortran wrapper plus ISO C ABI around a libtorch C++ port that mirrors the [[KDM6]] forward physics and exposes separate AD handles.

## Key Takeaways

1. [[KDM6]] enters WRF as `mp_physics=37` and calls `module_mp_kdm6.F:subroutine kdm6`; [[KDM6AD]] enters as `mp_physics=137` and calls `module_mp_kdm6ad.F:subroutine kdm6ad`.
2. The mp137 host-facing argument surface intentionally mirrors mp37: prognostic fields, number concentrations, graupel volume, precipitation accumulators, radar reflectivity, effective radii, and `diag_rhog` are passed through the same WRF driver layer.
3. [[KDM6AD]] stages WRF arrays into `REAL(c_float)` buffers, calls `kdm6_step` through `kdm6_iso_c.F`, then copies state back into WRF arrays.
4. Operational mp137 uses `value_only=1` and `param_grad_flags=0`, so the WRF runtime path is forward-only. AD functionality lives in `kdm6_step_ad_c`, `kdm6_handle_vjp_c`, and `kdm6_handle_jvp_c`.
5. Forward parity depends on deliberate f32/ordering fixes, strict FP contraction control, and diagnostic reconciliation for `diag_rhog`, `REFL_10CM`, and `re_*`.

## Evidence

- `host/KIM-meso_v1.0/phys/module_microphysics_driver.F` dispatches mp37 to `CALL kdm6` and mp137 to `CALL kdm6ad`.
- `host/KIM-meso_v1.0/phys/module_mp_kdm6.F` is the full Fortran reference implementation, including `kdm62D`, `ProgB_param`, `slope_kdm6`, `refl10cm_kdm6`, and `effectRad_kdm6`.
- `host/KIM-meso_v1.0/phys/module_mp_kdm6ad.F` is a wrapper that stages arrays, calls the C ABI, restores WRF state, and computes or reconciles diagnostics.
- `host/KIM-meso_v1.0/phys/kdm6_iso_c.F` exposes the Fortran-facing ABI for operational forward and fp64 DA forward.
- `libtorch/bridge/kdm6_c_api.cpp` exposes `kdm6_step_c`, `kdm6_step_ad_c`, `kdm6_handle_vjp_c`, `kdm6_handle_jvp_c`, and `kdm6_handle_close_c`.
- `libtorch/src/runtime.cpp` maps WRF state to the C++ coordinator state and implements VJP/JVP handle logic.
- `libtorch/src/coordinator.cpp` mirrors the KDM6 process sequence and contains parity-specific f32/order fixes.

## Verification Snapshot

- `ctest --test-dir libtorch/build --output-on-failure`: 16/16 passed.
- `pytest oracle/tests/test_cpp_parity.py -q`: 1 passed.
- Existing SS step-1 run comparison, `mp37_final_1min_hist0_20260624_194512` vs `mp137_final_1min_hist0_20260624_194620`, passes the documented gate when `strict_bitwise_nc.py` is called with explicit frame index `1`: 254 common variables, 253 numeric bitwise matches, 0 numeric differences, and 1 non-numeric `Times` variable. See [[kdm6ad-final-code-location-verification-2026-06-25]].
- Both existing SS final runs exited with code 0 and ended with `SUCCESS COMPLETE WRF`.

## Open Risks

- The comparison reused existing final SS run artifacts rather than launching a fresh WRF case in the ingest turn.
- mp137 is slower than mp37 in the observed final run timing.
- `diag_rhog` is a forward-only diagnostic and is not included in the packed AD ABI.

## Links

- [[KDM6]]
- [[KDM6AD]]
- [[WRF KIM-meso Host]]
- [[KDM6AD Forward Parity]]
- [[KDM6AD Automatic Differentiation ABI]]
