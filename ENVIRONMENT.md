# ENVIRONMENT — reproducibility notes

Bitwise parity depends on the math library and floating-point behavior of the toolchain, so
the exact environment matters. Below is the **reference environment** on which the current
`mp37 ↔ mp137` STRICT BITWISE parity was produced. Other versions may work but are not
guaranteed to reproduce bit-for-bit.

**C++ unit-test status on this reference toolchain: `ctest` is green (16/16).** The operational
**float32** derivative handle (`kdm6_step_c` value_only=0) is a mechanics/diagnostics path whose
VJP/JVP may be non-finite at inactive-ice corners (f32 underflow that propagates to graph-connected
inputs — which fields exactly is toolchain-dependent); `test_c_abi` asserts only the packed-ABI
mechanics, not f32 finiteness. Reliable fully-finite fp64 adjoints come from `kdm6_step_ad_c`.
(History: earlier `coordinator` aborts were stale unit tests — a pre-§53q Picons invariant and two
`SlopeOutputs` initializers missing appended fields — and the f32 `c_abi` corner-set assertion was
tightened to the actual contract; all since fixed.)

## Reference environment (verified 2026-07-04)

| Component | Version | Notes |
|-----------|---------|-------|
| OS / arch | macOS 26.5.1 / arm64 (Apple Silicon) | Darwin 25.5.0 |
| C++ compiler | Homebrew clang 22.1.4 | C++17 |
| Fortran compiler | GNU Fortran (Homebrew GCC) 15.2.0 | ISO_C bridge + host build |
| CMake | 3.24.4 | |
| Python | 3.9.10 (miniforge) | oracle + harness |
| PyTorch / libtorch | 2.8.0 | `find_package(Torch)` uses the Python torch install |
| Open MPI | 5.0.9 | host `-np ≥ 2` runs |
| netCDF4 (python) | 1.7.2 | strict-bitwise NetCDF comparison |

## Why these are pinned

- **libm parity**: the float32 operational path reproduces gfortran bit-for-bit because Apple
  `libSystem_m` matches `libgfortran`'s math library (IEEE-754 does not mandate correctly-rounded
  `exp/log/pow`; torch's vectorized Sleef differs at the last bit). A different libm may break
  the f32 bitwise match — this is the single most sensitive dependency. See
  `docs/KDM6AD_differentiable_mathematics.md` §7.1.
- **FP-contract**: both mp modules compile with `-ffp-contract=off`; the two-rounding accumulate
  (`ops::fma_acc`) mirrors that. A `fast` contraction setting changes results.
- **Threading**: the ABI forces single-thread determinism by calling the runtime setters
  directly — `at::set_num_threads(1)`, `at::set_num_interop_threads(1)`, `omp_set_num_threads(1)`
  — so the effective libtorch/OpenMP thread count is **1 regardless of the environment**. It
  also seeds `OMP_NUM_THREADS=1` etc. with `setenv(..., overwrite=0)`, which only avoids
  clobbering an externally-set env var; it does **not** let an external value raise the actual
  runtime thread count (the direct setters win).
- **PyTorch**: the f64 autograd path (VJP/JVP/HVP) uses torch-native ops; a major torch version
  change can shift autograd internals (though the adjoint-identity tests are tolerance-based at
  rel<1e-12 and should hold across minor versions).
- **MPI transport**: host `-np ≥ 2` runs are numerics-identical across transports; the shared-memory
  (vader) BTL completed the 12h np4 gate. (An earlier `--mca btl self,tcp` attempt died at ~3h23m
  as downstream fallout of a since-fixed numerics NaN, not a transport limitation.)

## Not pinned / out of scope

- The WRF/KIM-meso host tree (not in this repo; see README → Full host integration).
- GPU: the port is CPU/float32 for parity; no CUDA/Metal path is claimed here.
