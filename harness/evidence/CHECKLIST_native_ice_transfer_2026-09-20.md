# PR231 follow-up: existing conservative substep

- [x] Capture actual mixed-precision work/state/fall operands on the same
  column and native grid; never infer coefficients from rounded offer.
- [x] Retain prior raw capture and history bytes in one additional mp37 run.
- [x] Reproduce native number stores with source-ordered mixed arithmetic.
- [x] Execute existing legacy/conservative Python and C++ kernels on those
  operands, distinguishing promoted f64 and mixed-f32 local evaluations.
- [x] Verify actual entry-capped paired transfers, nonnegative output and
  declared mass/number measures; retain f32 residuals instead of hiding them.
- [x] Fixed-metric differentiated inventory and explicit synthetic empty-donor,
  unequal-dz, carried-substep and nonzero bottom-export checks.
- [x] Final Green/Red review and Graphify refresh (8 pre-existing graph edge
  metadata warnings retained; full graph coverage is not claimed).
- [ ] **P1 OPEN — operational legacy transfer defect.** No default was changed.
- [ ] Physical number basis, full conservative native/ABI trajectory, actual
  nonzero surface export, other species and time-step convergence.
- [ ] Independent radiation accuracy; liquid observation approval remains 0/9.
