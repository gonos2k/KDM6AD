# PROJECT KNOWLEDGE BASE

Generated: 2026-06-25
Commit: unavailable at this root
Branch: unavailable at this root
Scope: KDM6/KDM6AD only; this is not a general WRF/KIM-meso guide.

## Canonical Worktree

The canonical project root is `/Users/yhlee/KDM6AD-k`.

Do not use `/Users/yhlee/KDM6AD/KDM6AD-k` for new work. That nested path may
still appear in older Codex session metadata or shell `PWD`, but it is not the
current KDM6AD-k worktree. When in doubt, run commands with explicit
`workdir=/Users/yhlee/KDM6AD-k` and verify `pwd` before editing.

## Public repo vs full host tree

This root serves two contexts; keep their paths straight:

- **Public repo** (published at github.com/gonos2k/KDM6AD): the differentiable
  **port and tooling** only — `oracle/`, `libtorch/`, `harness/`, `docs/`, `wiki/`.
  The WRF/KIM-meso host tree (`host/`) and the isolated integration Fortran
  (`host_fortran/`) are **excluded via `.gitignore`** and are NOT in the public repo.
- **Full host tree** (this local worktree only): additionally has `host/KIM-meso_v1.0/`
  and `host_fortran/`. Host-path tasks below apply here, not in a fresh public clone.

When working from a public clone, treat any `host/…` or `host_fortran/…` path below as
"present only in the full host tree"; the port itself (`libtorch/`, `oracle/`, `harness/`)
is self-contained and its `ctest`/`pytest` run from the repo alone.

## Overview

`KDM6AD-k` is a KDM6 microphysics parity stack: Python f64 oracle,
C++ libtorch f32/AD mirror, Fortran ISO_C bridge, and — in the full host tree — a
KIM-meso/WRF host where `mp_physics=37` is KDM6 and `mp_physics=137` is KDM6AD.

The load-bearing invariant is strict parity: mp37 vs mp137 raw-bit identical for all
numeric common variables (only the non-numeric `Times` differs). As of **2026-07-04**
this holds through a **full 12-hour (2160-step) SS real-case integration under MPI(np4)**
— all 254 output variables bit-identical at every output frame (the campaign goal; see
`wiki/concepts/KDM6AD Forward Parity.md`). Earlier milestones were SS step-1 and 10-step.

## Structure

```text
KDM6AD-k/
├── oracle/                  # Python f64 reference and pytest oracle        [public]
├── libtorch/                # C++ mirror, C ABI, ISO_C bridge, ctest suite  [public]
├── host_fortran/            # isolated KDM6/KDM6AD Fortran sources     [PRIVATE, gitignored]
├── host/KIM-meso_v1.0/      # runnable host; only KDM6/KDM6AD in scope [PRIVATE, gitignored]
├── harness/                 # SS/parity comparators and dump analysis      [public]
├── docs/HOST_INTEGRATION.md # host wiring contract
├── wiki/                    # Obsidian KG notes
└── graphify-out/            # Graphify structural graph
```

Generated or foreign areas are not source for normal KDM6AD work:
`libtorch/build/`, `libtorch/install/`, `*.o`, `*.mod`, generated `*.f90`,
`graphify-out/cache/`, run output directories, and broad WRF vendor subtrees.

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| KDM6 Fortran reference | `host/KIM-meso_v1.0/phys/module_mp_kdm6.F` | mp37 source of forward parity |
| KDM6AD host wrapper | `host/KIM-meso_v1.0/phys/module_mp_kdm6ad.F` | calls C++ ABI and mirrors diagnostics |
| Host dispatch | `host/KIM-meso_v1.0/phys/module_microphysics_driver.F` | `KDM6SCHEME` vs `KDM6ADSCHEME` branch |
| C ABI | `libtorch/bridge/kdm6_c_api.cpp` | `kdm6_step_c`, `kdm6_step_ad_c`, handle VJP/JVP |
| Fortran ABI shim | `libtorch/bridge/kdm6_iso_c.f90` and `host_fortran/kdm6_iso_c.F` | ISO_C binding surface |
| C++ runtime | `libtorch/src/runtime.cpp`, `libtorch/src/coordinator.cpp` | state update and post-step coupling |
| Python oracle | `oracle/kdm6/runtime.py`, `oracle/kdm6/coordinator.py` | f64 reference and AD checks |
| Host build wiring | `host/KIM-meso_v1.0/apply_kdm6ad_config.sh`, `phys/Makefile` | re-inject link flags and build hook |
| SS parity | `harness/strict_bitwise_nc.py`, host SS case runner | final raw-bit gate |

## Code Map

| Symbol | Type | Location | Role |
| --- | --- | --- | --- |
| `kdm6ad` | Fortran subroutine | `module_mp_kdm6ad.F` | mp137 wrapper into C++ ABI |
| `module_mp_kdm6` | Fortran module | `module_mp_kdm6.F` | mp37 forward reference |
| `kdm6_step_c` | C ABI | `libtorch/bridge/kdm6_c_api.cpp` | operational f32 forward path |
| `kdm6_step_ad_c` | C ABI | `libtorch/bridge/kdm6_c_api.cpp` | fp64 DA forward/handle path |
| `kdm6_handle_vjp_c` / `kdm6_handle_jvp_c` | C ABI | `libtorch/bridge/kdm6_c_api.cpp` | reverse/forward AD products |
| `kdm6::kdm6_step` | C++ runtime | `libtorch/src/runtime.cpp` | main C++ step implementation |
| `_kdm6_pure` / `kdm6_step` | Python oracle | `oracle/kdm6/runtime.py` | reference forward and handle logic |

## Conventions

- Preserve `mp_physics=37` as Fortran KDM6 and `mp_physics=137` as KDM6AD.
- Strict parity is raw-bit equality, not tolerance equality.
- Keep `-ffp-contract=off` on both C++ and Fortran KDM6 paths.
- Test targets must keep assertions live; do not let `NDEBUG` erase checks.
- After every host `./configure`, run `./apply_kdm6ad_config.sh` before compile.
- The host build hook is build-if-missing for `libtorch/install`; remove or rebuild
  that install tree when C++ source changes must be picked up by `./compile`.
- SS parity baseline is single-process and single-threaded (`mpirun -np 1`,
  `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `OMP_THREAD_LIMIT=1`).
- `history_interval` replacement must be exact-key; do not rewrite
  `history_interval_s`.
- `diag_rhog`, `re_*`, and `REFL_10CM` are forward diagnostics; do not silently
  add them to the packed AD ABI.

## Anti-Patterns

- Do not treat the bundled host as a general WRF refactor target.
- Do not edit generated `.f90`, `.o`, or `.mod` files as the source of truth.
- Do not hand-maintain `configure.wrf` changes that belong in
  `apply_kdm6ad_config.sh`.
- Do not accept approximate parity unless the user explicitly changes the gate.
- Do not insert `.item()`, `detach`, `no_grad`, or scalar extraction in AD paths
  unless the surrounding code already marks the block value-only.
- Do not broaden `AGENTS.md` coverage to all host/vendor directories without a
  KDM6/KDM6AD reason.

## Commands

```bash
# Host build, including C++ port via phys/Makefile hook
cd /Users/yhlee/KDM6AD-k/host/KIM-meso_v1.0
./configure
./apply_kdm6ad_config.sh
./compile -j 4 em_real

# C++ port-only iteration
cd /Users/yhlee/KDM6AD-k/libtorch && mkdir -p build && cd build
cmake .. -DCMAKE_PREFIX_PATH="$(python3 -c 'import torch,os;print(os.path.dirname(torch.__file__))')" \
         -DCMAKE_INSTALL_PREFIX=../install -DCMAKE_CXX_FLAGS=-DKDM6_SUBSTEP_DUMP
cmake --build . -j4 && cmake --install . && ctest

# Python oracle
cd /Users/yhlee/KDM6AD-k/oracle && python3 -m pytest
```

## Knowledge Graph

This project has a derived graph at `graphify-out/` and an Obsidian vault at
`wiki/`. For codebase questions, first run `graphify query "<question>"` when
`graphify-out/graph.json` exists. Use `graphify path`, `graphify explain`, and
`graphify affected` for relationships, concepts, and impact checks.

Use `wiki/index.md`, `wiki/hot.md`, and `wiki/overview.md` for orientation.
Raw source files remain authoritative. Dirty graph files are expected after
updates and are not a reason to skip Graphify.

After modifying code or AGENTS files, run `graphify update .`. Keep raw
code-tree reports outside the Obsidian vault under `graphify-out/`; do not
mirror `GRAPH_REPORT.md` into `wiki/`. The wiki should keep synthesized KG
notes, indexes, logs, and generated Canvas views rather than raw code-tree dumps.
