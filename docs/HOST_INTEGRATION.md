# Host integration — wiring the KDM6/KDM6AD Fortran into a WRF/KIM-meso tree

> **Not in this public repo.** Both the WRF/KIM-meso host tree (`host/`) and the isolated
> integration Fortran (`host_fortran/`) are **excluded via `.gitignore`** — they are part of a
> separately-governed model tree, not published here. This document is the wiring reference for
> a maintainer who **already has** those sources. The KDM6/KDM6AD `.F` integration files
> (`module_mp_kdm6.F`, `module_mp_kdm6ad.F`, `kdm6_iso_c.F`, and the `module_bc.F` /
> `module_microphysics_driver.F` edits) live in that private host tree; the **differentiable
> port itself** (`libtorch/`, `oracle/`, `harness/`) is what this public repo ships.

The KDM6/KDM6AD microphysics integration source builds into a full **KIM-meso/WRF host tree**
(the foreign host model, not bundled here). This doc records the exact wiring so those `.F`
files can be dropped into a host and produce `wrf.exe` with selectable
`mp_physics=37` (KDM6 Fortran) / `mp_physics=137` (KDM6AD libtorch port), and — since C4 —
the conservative-interface-v1 variant pair `mp_physics=237` (corrected Fortran reference) /
`mp_physics=337` (C++ v2 `physics_variant=1`).

## Files (drop into `<WRF>/phys/`)
| File | Role |
|---|---|
| `module_mp_kdm6.F` | KDM6 mp37 reference scheme (incl. the diag_rhog gate+snap, commit eb1c823) — **never modified** |
| `module_mp_kdm6ad.F` | KDM6AD mp137 wrapper — calls the C++ ABI; computes re_*/diag_rhog/REFL_10CM diagnostics — **never modified** |
| `kdm6_iso_c.F` | ISO_C_BINDING interface declaring `kdm6_step_c` etc.; C4 adds the **append-only** v2 mirror (`kdm6_step_v2_args`, `kdm6_step_v2_c`, `kdm6_step_v2_args_size_c`, variant enums) |
| `module_mp_kdm6_cons.F` | **C4** corrected Fortran conservative reference (mp237): byte-identical copy of `module_mp_kdm6.F` except renames + the pinned sedimentation interface-transfer edits (Gate A manifest) |
| `module_mp_kdm6ad_cons.F` | **C4** thin separate wrapper (mp337): calls `kdm6_step_v2_c` with `physics_variant=1`, `value_only=1`; first-call `abi_version` + `struct_size` layout gate (fatal on mismatch — a stale mirror must never silently run legacy) |
| `module_microphysics_driver.F` | dispatches mp37 / mp137 / mp237 / mp337 (additive CASEs only) |

## Build wiring (in the WRF host)

### 1. Link the C++ ABI library — `configure.wrf`
```make
KDM6AD_PREFIX   = <path>/libtorch/install            # KDM6AD-k self-built install
KDM6AD_TORCH_LIB= <miniforge>/lib/python3.9/site-packages/torch/lib
LIB_LOCAL       = $(KDM6AD_PREFIX)/lib/libkdm6_c.dylib \
                  $(KDM6AD_TORCH_LIB)/libtorch.dylib \
                  $(KDM6AD_TORCH_LIB)/libtorch_cpu.dylib \
                  $(KDM6AD_TORCH_LIB)/libc10.dylib
LIB             = ... $(LIB_LOCAL) ...                # ensure LIB_LOCAL is in the final link line
```
> **Versioned library (PR3).** The install ships a `SOVERSION 2` library. The
> real file is `libkdm6_c.2.0.0.dylib` (macOS) / `libkdm6_c.so.2.0.0` (Linux),
> with a soname/compat symlink `libkdm6_c.2.dylib` / `libkdm6_c.so.2` and an
> unversioned dev symlink `libkdm6_c.dylib` / `libkdm6_c.so`. Keep linking the
> unversioned `libkdm6_c.dylib` above — the link resolves through the symlink and
> records the versioned install-name `@rpath/libkdm6_c.2.dylib` (macOS) / soname
> `libkdm6_c.so.2` (Linux), so `wrf.exe` loads the versioned library at runtime
> while the Makefile path is unchanged. Major `2` matches `KDM6_ABI_VERSION`
> (`kdm6_get_abi_version_c()`).

The C++ side must be compiled with `-ffp-contract=off` (it is, via CMakeLists) and the
Fortran mp modules likewise (`configure.wrf` per-file rule) for bitwise parity.

### 2. Module dependency — `phys/Makefile` (+ `main/depend.common`)
```make
module_mp_kdm6ad.o: module_mp_kdm6.o kdm6_iso_c.o    # kdm6ad reuses effectRad_kdm6/refl10cm_kdm6 from kdm6
```

### 3. Scheme registration — `Registry/Registry.EM`
`mp_physics==137` must be registered as the KDM6AD scheme (state arrays identical to
the mp37 KDM6 package: moist/scalar/nc/ni/nccn/bg + diag_rhog/RHOPO3D, re_*, REFL_10CM).

## Conservative-interface variant wiring (C4)

Scheme IDs (collision-scanned against the host Registry + driver; the
`Fortran ID + 100 = C++ ID` rule mirrors 37/137):

| ID | Package | Backend |
|---|---|---|
| 237 | `kdm6consscheme` | corrected Fortran reference (`module_mp_kdm6_cons.F`) |
| 337 | `kdm6adconsscheme` | C++ conservative-interface-v1 (`kdm6_step_v2_c`, `physics_variant=1`) |

- Registry packages use **state arrays byte-identical** to the 37/137 packages.
- `MP_PHYSICS` is written to history output (`rconfig ... irh`), so the scheme ID
  itself records which backend produced a file; the ID→backend map above plus the
  C4 evidence manifest are the sidecar provenance.
- `module_physics_init.F`: both new IDs dispatch to `kdm6init_cons` (additive CASEs).
- `phys/Makefile`: both new objects get the same explicit `-ffp-contract=off`
  strict-IEEE rules as the legacy kdm6 objects; `main/depend.common` adds
  `module_mp_kdm6ad_cons.o: kdm6_iso_c.o module_mp_kdm6_cons.o`.
- `apply_kdm6ad_config.sh` is unchanged: it only restores the `configure.wrf`
  link/compile hook; all cons wiring lives in Registry/Makefiles that survive
  `./configure`, so a rerun preserves the variant wiring (Gate C check).
- **Gate A scope proof**: `harness/check_cons_fortran_scope.py` (public) verifies
  the private `module_mp_kdm6_cons.F` is legacy + renames + EXACTLY the pinned
  manifest edits (`harness/cons_fortran_scope_manifest.json`), that the raw
  ice-velocity handoff blocks are byte-identical, and that the two legacy modules
  match their pinned sha256.
- **Gate B driver**: `<WRF>/test/kdm6_cons_gateb/` (private host) runs the same
  fixture arrays through `kdm6_cons` and `kdm6_step_v2_c(physics_variant=1)` and
  gates f32 raw-bit equality (12 states + rain/snow/graupel increments + rhog)
  plus per-column water closure on both paths.

## Build & run
`em_b_wave` below is only a **generic build-target example**. **The SS real-case parity runs
build `em_real`** (`./compile -j 4 em_real`) — a REAL case must not use the idealized
`em_b_wave` core. Use whichever target matches your case; the KDM6AD hook is target-independent.
```sh
cd <WRF> && ./compile -j 4 em_real            # SS real case → em_real; → main/wrf.exe (links libkdm6_c.dylib + libtorch)
# (idealized/dry toy cases would use em_b_wave etc.)
# touch phys/module_mp_kdm6*.F if only .F changed; no clean unless Registry changed.
```
Then run with `harness/run_ss_case.py` (set `mp_physics` via `--mp 37|137|237|337`) on an
SS real case. The Fortran schemes (37/237) write `fort_*` substep dumps when the env-gated
dump is enabled; the C++ schemes (137/337) write `cpp_*`.

**`KMP_DUPLICATE_LIB_OK` is caller-owned.** Neither the dylib nor the runner forces
it: a parent `UNSET` stays unset, an explicit `TRUE`/`FALSE` is preserved. Set it in
your launch environment only if your process genuinely loads two OpenMP runtimes.
The single-thread fence (`OMP_NUM_THREADS`/`MKL_NUM_THREADS`/`VECLIB_MAXIMUM_THREADS`/
`OMP_THREAD_LIMIT=1`) is still applied. See [PR1B_OPENMP_DIAGNOSTIC](PR1B_OPENMP_DIAGNOSTIC.md).

## Source note
In the full/private host tree (NOT this public repo — see the banner at the top),
the `host_fortran/` files were copied from the archived tracked KDM6AD tree at
commit `eb1c823`.
The generated `.f90`/`.mod`/`.o` are build artifacts — not bundled; the host regenerates
them (`.F` is preprocessed by `cpp` on capital-`.F`).

## Verified result

The operational f32 path is strict-bitwise identical between `mp_physics=37`
(Fortran KDM6) and `137` (KDM6AD port). Verification, most-recent first:

- **Campaign result (2026-07-04): a full 12-hour (2160-step) SS real-case run under
  MPI(np4)** is bit-identical across all **254 output variables at every output frame**
  (253 numeric BITWISE-MATCH + the non-numeric `Times`). Gate:
  `harness/strict_bitwise_nc.py` (uint32/uint64 bit-equality, not tolerance).
- Earlier milestones: SS step-1 254/254 (253 BITWISE-MATCH + Times; RHO_ICE 0 diffs),
  then a 10-step run.

C++ unit suite (`ctest`): **green — 17/17** on the pinned *local* macOS/clang reference toolchain
(ENVIRONMENT.md), and independently on Ubuntu/gcc with `torch==2.8.0` via the repo's `port-ci`
GitHub Actions workflow (which runs on pushes to `main` and on pull requests targeting `main`
that touch `libtorch/`, the workflow, or the ctest-claim docs — branch + path filters; a
side-branch commit is covered once it is opened as a PR to `main`).

Derivative contract (why the f32 handle is not a finiteness guarantee): a handle from
`kdm6_step_c(... value_only=0 ...)` records the operational **float32** graph. Its VJP/JVP is a
mechanics/diagnostics path — correct packed layout and lifecycle, but the f32 backward can
underflow at inactive-ice corners and the NaN propagates to graph-connected inputs (which fields
exactly is f32-rounding/toolchain dependent). For reliable, fully-finite fp64 adjoints/tangents
use `kdm6_step_ad_c` (the DA design default, §0.1.A). `test_c_abi` asserts only the packed-ABI
mechanics, not f32 finiteness — so it stays green while honestly reflecting that contract.

History (all fixed): earlier `coordinator` aborts were **stale unit tests**, *not* production
bugs — a pre-§53q Picons invariant (ni-gate removed to match Fortran mp37, `coordinator.cpp`
§53q) and two `SlopeOutputs` initializers missing the appended `vt2r/vt2s/vt2i` fields; and the
f32 `c_abi` corner-set assertion was tightened from a toolchain-fragile field pin to the actual
mechanics contract. The operational path populates every field, which is why the 12h×np4 bitwise
parity holds.
