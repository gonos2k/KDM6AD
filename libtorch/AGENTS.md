# LIBTORCH KDM6AD GUIDE

Scope: C++ KDM6AD mirror, C ABI, ISO_C bridge, tests, and port-only build.

## Overview

`libtorch/` is the operational C++ layer behind `mp_physics=137`. It mirrors the
KDM6 forward path closely enough for f32 strict parity while also exposing handle
based VJP/JVP paths.

## Structure

```text
libtorch/
├── bridge/        # C ABI and Fortran ISO_C shim
├── include/kdm6/  # public C++ structs and module headers
├── src/           # physics implementation and runtime coordinator
├── tests/         # ctest targets
├── tools/         # parity helper copied into the standalone tree
├── build/         # generated
└── install/       # generated ABI install consumed by the host
```

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| Host ABI | `bridge/kdm6_c_api.cpp`, `bridge/kdm6_c_api.h` | error codes, handles, VJP/JVP |
| Fortran bridge | `bridge/kdm6_iso_c.f90` | Fortran-friendly wrappers |
| Runtime step | `src/runtime.cpp`, `include/kdm6/runtime.h` | `kdm6::kdm6_step` |
| Coupling/diagnostics | `src/coordinator.cpp`, `include/kdm6/coordinator.h` | post-update logic |
| Module parity | `src/{warm,cold,satadj,sedimentation,...}.cpp` | mirrors Python/Fortran phases |
| ABI tests | `tests/test_c_abi.cpp` | handle and error-path coverage |
| End-to-end dumps | `tests/test_autograd_endtoend.cpp` | consumed by Python parity tests |

## Conventions

- `kdm6_step_c` is the operational f32 path; keep it bitwise locked to Fortran.
- `kdm6_step_ad_c` is the fp64 DA path; do not fold it into the operational ABI.
- Preserve `ensure_libtorch_singlethread()` and `FpEnvGuard` around ABI entries.
- Keep `-ffp-contract=off`; reassociation/FMA changes are parity bugs unless
  explicitly proven against mp37.
- Test targets deliberately use `-UNDEBUG`; assertions are part of the test gate.
- Keep packed state/forcing layout in sync with `kdm6_c_api.h`,
  `kdm6_iso_c.f90`, and `host_fortran/kdm6_iso_c.F`.

## Anti-Patterns

- Do not use `detach`, scalar extraction, or value-only shortcuts in AD-sensitive
  code without an explicit local contract.
- Do not make tolerance-based changes to satisfy ctest when the issue is a
  forward parity mismatch.
- Do not rely on stale `install/`; rebuild/install before host testing.
- Do not edit `build/` outputs as source.

## Commands

```bash
cd /Users/yhlee/KDM6AD-k/libtorch && mkdir -p build && cd build
cmake .. -DCMAKE_PREFIX_PATH="$(python3 -c 'import torch,os;print(os.path.dirname(torch.__file__))')" \
         -DCMAKE_INSTALL_PREFIX=../install -DCMAKE_CXX_FLAGS=-DKDM6_SUBSTEP_DUMP
cmake --build . -j4
cmake --install .
ctest
```
