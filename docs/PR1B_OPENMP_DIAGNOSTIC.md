# PR1-B — OpenMP duplicate-runtime diagnostic (`KMP_DUPLICATE_LIB_OK`)

Public-safe summary of the source-free diagnostic that authorized PR1-B: removing
the default `KMP_DUPLICATE_LIB_OK=TRUE` injection so the variable becomes
**caller-owned**. Private host details are kept in a retained canonical-JSON
manifest; only its digest is published.

## Background

Two places used to force `KMP_DUPLICATE_LIB_OK=TRUE`:

- the shipped dylib constructor — `setenv("KMP_DUPLICATE_LIB_OK", "TRUE", 0)`
  (`overwrite=0`, so an explicit external value already wins);
- the SS parity runner `harness/run_ss_case.py`.

`TRUE` suppresses the OpenMP runtime's duplicate-initialization guard. That guard
only matters if **two different** OpenMP runtimes (e.g. LLVM `libomp` + GNU
`libgomp`, or two `libiomp5`/`libomp` installs) are loaded into one process. If a
single consistent runtime is loaded, the default injection is unnecessary and
hides the very condition it is meant to paper over.

## Diagnostic (source-free)

Against the sealed baseline **`abi-v2-hardened` / `a53503e`** — a freshly built
**hooks-OFF, 9-symbol, versioned** `libkdm6_c` — with **no source change**, the
diagnostic loaded that dylib into the real `mpirun → wrf.exe` chain and ran a
2×2 matrix on a short (2 model-minute) real-case parity run:

| | mp37 | mp137 |
|---|---|---|
| `KMP_DUPLICATE_LIB_OK=TRUE` (control) | run | run |
| `KMP_DUPLICATE_LIB_OK=FALSE` (candidate) | run | run |

`FALSE` is the source-free candidate because the constructor's `overwrite=0`
preserves an external `FALSE` (an *unset* value is still turned into `TRUE` by the
current constructor — that is why unset is only a sanity check, not the candidate).

## Result — GO

- **4/4 runs exit 0** (`wrf: SUCCESS COMPLETE WRF`).
- **All-frame strict-bitwise PASS** (every common frame, full variable set):
  `TRUE mp37 ↔ TRUE mp137`, `FALSE mp37 ↔ FALSE mp137`,
  `mp37 TRUE ↔ FALSE`, `mp137 TRUE ↔ FALSE`.
- `TRUE` and `FALSE` are **whole-file byte-identical per scheme** — removing the
  default perturbs no established trajectory.
- **Single consistent OpenMP runtime** (`libomp`, one resolved path) across all
  four runs; no `libiomp5`, no `libgomp`, **no duplicate-runtime abort**.
- Constructor probe: unset→`TRUE`, external `FALSE`→`FALSE`; `FALSE` C ABI and
  Fortran ISO_C_BINDING smokes PASS.

Retained private manifest (canonical JSON, host tree SHA + toolchain versions +
per-run/evidence digests):

```
Manifest SHA-256: 583727745ab85c8bab7217bade6253c21102118fcc37b94451a545b7c0ec8022
```

## Contract after PR1-B

`KMP_DUPLICATE_LIB_OK` is **caller-owned**: neither the dylib nor the runner sets
it. A parent `UNSET` stays unset; an explicit `TRUE`/`FALSE` is preserved verbatim.
The single-thread fence (`OMP_NUM_THREADS`/`MKL`/`VECLIB`/`OMP_THREAD_LIMIT=1`) is
unchanged, as is the thread-determinism fail-closed fence and the FP-env guard.

## Merge caveat (owner-host)

The source-free result establishes that an **explicit `FALSE`** is safe and
trajectory-neutral. It does **not** substitute for verifying the **new default**
after removal — where `UNSET` stays unset (whereas today's binary turns `UNSET`
into `TRUE`). Before merge, the actual post-removal `UNSET` default must pass an
owner-host strict-bitwise parity check (`UNSET mp37↔mp137`, and `UNSET` vs the
sealed `TRUE` trajectory per scheme), plus a single-consistent OpenMP inventory.
