# KDM6AD — differentiable microphysics port (KDM6 → PyTorch/libtorch)

A differentiable C++/libtorch port of the **KDM6** bulk cloud-microphysics scheme, with a
Fortran ISO_C ABI bridge for coupling into a WRF/KIM-meso host. The port reproduces the
Fortran reference **bit-for-bit on an operational float32 path** and exposes **autograd**
on a float64 data-assimilation path: **VJP and JVP through the C/Fortran ABI**
(`kdm6_handle_vjp_c` / `kdm6_handle_jvp_c`); **HVP** is available only via the C++ autograd
path (`GraphOptions.create_graph` grad-of-grad) and currently has **no dedicated C ABI entry**. See
[`docs/KDM6AD_differentiable_mathematics.md`](docs/KDM6AD_differentiable_mathematics.md) for the
full mathematical and AD-engineering writeup.

> **Scope of this public repository.** This repo contains the **port and its tooling** only:
> `oracle/` (Python f64 reference), `libtorch/` (C++ port + ABI + tests), `harness/` (parity
> scripts), `docs/`, and `wiki/`. The **WRF/KIM-meso Fortran host tree is NOT bundled here**
> (it is a large, separately-governed model tree, excluded via `.gitignore`). To reproduce the
> *host-coupled* bitwise-parity runs you need access to that host tree — see
> [Full host integration](#full-host-integration-requires-the-wrfkim-meso-tree). The
> **port-only build + tests below are fully reproducible from this repo alone.**

## Public-repo quickstart (port-only, no host needed)

Builds the C++ port + ISO_C ABI library and runs the unit / ABI / autograd test suite.
Requires a local **libtorch/PyTorch** install and a C++17 compiler + CMake (see
[ENVIRONMENT.md](ENVIRONMENT.md) for pinned versions).

```sh
KROOT=$(pwd)
cd "$KROOT/libtorch" && mkdir -p build && cd build
cmake .. -DCMAKE_PREFIX_PATH="$(python3 -c 'import torch,os;print(os.path.dirname(torch.__file__))')" \
         -DCMAKE_INSTALL_PREFIX=../install -DCMAKE_CXX_FLAGS=-DKDM6_SUBSTEP_DUMP
cmake --build . -j4 && cmake --install . && ctest --output-on-failure
```

`ctest` covers module-level physics tests, the C ABI (`test_c_abi`), autograd end-to-end,
and the handle VJP/JVP tests (VJP=backward, `⟨Jv,u⟩=⟨v,Jᵀu⟩` adjoint identity to rel<1e-12,
masked-adjoint identity, double-backward readiness, f32 value-vs-graph determinism, shape
rejection, and handle lifecycle guards). If a Fortran compiler is present, an ISO_C smoke
test is added.

### Python oracle (independent f64 reference)
```sh
cd "$KROOT/oracle" && python3 -m pytest      # algorithm + parity + VJP/JVP FD tests (needs torch)
```

## Parity status

- **2026-07-04 — 12-hour × MPI(np4) STRICT BITWISE parity achieved.** Over a full 12-hour
  (2160-step) SS real-case integration, `mp_physics=37` (Fortran KDM6) and `mp_physics=137`
  (this C++ port) agree bit-for-bit across all **254 output variables at every output frame**.
  This is the campaign goal; see `wiki/concepts/KDM6AD Forward Parity.md` and `wiki/log.md`.
- Verification is uint32 bit-equality (not tolerance) via `harness/strict_bitwise_nc.py`;
  a mismatched variable *set* is itself a failure.
- Host-coupled runs use single-threaded determinism (the ABI sets `OMP_NUM_THREADS=1` etc.
  with `setenv(..., overwrite=0)`, so an external `OMP_NUM_THREADS` still overrides it).

## Layout (this repo)

```
oracle/            Python f64 ground-truth (algorithm definition = parity reference)
  kdm6/            per-process microphysics + obs-operator (RTTOV) modules
libtorch/          C++ libtorch f32 mirror + ISO_C ABI
  src/  include/kdm6/  bridge/  tests/  tools/  CMakeLists.txt
harness/           parity scripts (strict_bitwise_nc.py, compare_*.py, run_ss_case.py)
docs/              math/AD writeup, HOST_INTEGRATION.md, research reports
wiki/              knowledge-graph vault (concepts, sources, parity log)
```
Runtime chain (host-coupled): `wrf.exe` → `libkdm6_c.dylib` (this repo) → `libtorch`. The
Python oracle is **not** in the runtime — it is the f64 algorithm definition used for
development and parity verification.

## Full host integration (requires the WRF/KIM-meso tree)

The WRF/KIM-meso host is **not** in this repo. With access to that host tree, the port
drops in via the `phys/Makefile` hook so a single `./compile` builds both `libkdm6_c.dylib`
and `wrf.exe`. Full wiring is documented in
[`docs/HOST_INTEGRATION.md`](docs/HOST_INTEGRATION.md); the SS real-case build target is
`em_real` (toy/dry cases such as `em_b_wave` are used only as generic examples in that doc):

```sh
cd <WRF-KIM-meso>
./configure                 # pick the dmpar gfortran/gcc + OpenMPI build; nesting: basic (1).
                            # (The exact menu number varies by host/WRF version — the KDM6AD
                            #  wiring is menu-independent; apply_kdm6ad_config.sh transforms
                            #  whatever configure.wrf ./configure produced.)
./apply_kdm6ad_config.sh    # re-inject KDM6AD wiring into the fresh configure.wrf (idempotent)
./compile -j 4 em_real      # SS is a REAL case → em_real; builds the C++ port then wrf.exe
```

- `configure.wrf` derives all KDM6AD paths from its own location (relocatable); re-apply
  `apply_kdm6ad_config.sh` after every `./configure`.
- The port rule is **build-if-missing**: to pick up C++ source edits, remove
  `libtorch/install` (or re-run cmake in `libtorch/build`) before `./compile`.
- `-DKDM6_SUBSTEP_DUMP` is compiled in but **dormant** — the per-substep parity dumps only
  activate when the `KDM6_SUBSTEP_DUMP` env dir is set.

## Provenance
Consolidated 2026-06-24 from the archived KDM6AD source trees (originals untouched). The
host WRF/KIM-meso tree, build artifacts, run outputs, and the libtorch binary install are
intentionally excluded from this public repo (`.gitignore`).
