# KDM6AD Project Instructions

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

Preserve raw-bit parity between mp37 and mp137 for numeric common outputs.
Historical campaign results and their source/build attribution belong in
`wiki/concepts/KDM6AD Forward Parity.md`; do not treat them as verification
of a changed executable or host configuration.

## Differentiability Validation Goal

The validation target is differentiable KDM microphysics, including sensitivities
between hydrometeor processes, through the GK2A–RTTOV assimilation chain.
Prioritize JVP/VJP correctness, independent directional differences, branch and
numerical diagnostics, declared units and applied-process budgets. Distinguish
state-to-state sensitivity, named process attribution and sensitivity of BT/cost.
Forecast skill and unattended host cycling are separate objectives, not completion
gates for this validation task. Keep first-order RTTOV K validation separate from
unverified higher-order derivatives or parameter identifiability claims.

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

## Theory Before Patching

Actively use small sub-agent teams to reduce token usage. Delegate bounded,
non-overlapping tasks, reuse completed agents and existing evidence, and return
concise findings instead of duplicating the main agent's investigation.

Organize sub-agent work into Green and Red teams. Both teams use
`gpt-5.6-luna` with reasoning effort `high` by default. Apply this setting when
spawning or restarting agents unless the user explicitly requests otherwise.
Before ending a work session, have the Green and Red sub-agent teams review
the final changes and evidence: Green checks consistency and demonstrated
coverage; Red looks for counterexamples, missing paths and unsupported claims.
Resolve actionable findings and record any remaining limitations before the
final session report.

Keep at most seven team agents active at once across the session, including
follow-up reviews. Reuse completed agents and queue remaining work within this
limit; the user's instruction forbids eight or more active team agents.

Think mathematically and numerically before implementing or reviewing a change.
First derive the intended map, its domain, invariants and derivative contract;
then examine how the executed precision and operation order affect values,
JVPs and VJPs. Validate with independent expectations or directional differences,
and distinguish real-arithmetic identities from floating-point behavior.

Check consistency from all four perspectives below. Prioritize a coherent
mathematical and physical contract over a local symptom fix.

- **Mathematical:** identify the variables, units, measure, assumptions and full
  quantity being computed. Derive the relevant identity or budget before changing
  its implementation. Distinguish a diagnostic component from the full residual,
  and fix both applied arrival and departure in a transfer counterfactual.
- **Engineering:** trace the contract from producer through every consumer,
  runner, fixture and report. Share record validation and pairing where the data
  have the same meaning, and make initialization versus stored-data reads explicit.
  Verify actual call boundaries as well as isolated helper functions.
- **Numerical analysis:** check the executed precision, operation order, independent
  caps, rounding, underflow/subnormals and zero denominators. Real-arithmetic
  identities do not imply floating-point bit equality. Use explicit counterexamples
  and independently computed expectations at the relevant boundaries.
- **Meteorological:** trace host and kernel mass/number/volume conventions and
  the species actually connected to observations. Check admissible moment pairs,
  initialization and forcing assumptions. Separate numerical parity, physical
  budgets, mock observation tests and measured forecast performance.

Then choose the smallest change that satisfies that contract end to end. Do not
silence a contradiction by widening tolerances, dropping operands or weakening
assertions. If the physical contract is unresolved, state the conditional result
and open measurement; preserve operational f32 parity and the AD contract.

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

Always use the `graphify` skill for every code-improvement task, including
bug fixes, refactoring and verification changes. Apply this requirement to
both the main agent and team agents; an explicit user invocation is not needed.
Before editing, reuse the existing graph to inspect relevant dependencies and
producer-to-consumer paths, then verify findings against authoritative source.
After editing, refresh the affected graph and check the changed relationships.
Prefer cached queries and incremental updates to avoid duplicate extraction.
Use the skill's semantic update when documentation changes need extraction;
a code-only `graphify update .` does not refresh documentation semantics.
If Graphify is unavailable or incomplete, record the limitation explicitly and
continue source-based checks without claiming graph coverage.

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
