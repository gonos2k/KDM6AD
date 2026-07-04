# KDM6AD-k — Standalone, self-contained KDM6AD differentiable-port + WRF host

Single-directory consolidation of the **KDM6AD differentiable microphysics port**
*and* its WRF/KIM-meso Fortran host, copied from the separated source trees so the
whole mp37↔mp137 strict-bitwise pipeline **builds and runs independently** of the
originals. **Originals untouched (copy only).**

Copied 2026-06-24 from the archived KDM6AD source/build trees at git HEAD
`eb1c823` (includes the diag_rhog / RHO_ICE strict-bitwise fix).

**Verified standalone:** SS step-1 `mp_physics=37` ↔ `137` = **254 common, 253
BITWISE-MATCH, 0 DIFFER, Times non-numeric → STRICT BITWISE PASS**, using KDM6AD-k's
own self-built `wrf.exe` + `libkdm6_c.dylib` (no reference back to the original trees).
C++ `ctest` 16/16.

## Layout

```
KDM6AD-k/                                  (~16G:  ~8G WRF host + ~8G C++ build + sources)
├── README.md  /  docs/HOST_INTEGRATION.md
├── oracle/            Layer 1 — Python f64 ground-truth  (copy of kdm6_torch/)
│   └── kdm6/            algorithm definition = parity reference (oracle-first)
├── libtorch/          Layer 2 — C++ libtorch f32 mirror + ISO_C ABI
│   ├── src/  include/kdm6/  bridge/  tests/  CMakeLists.txt
│   ├── build/          ← fresh standalone CMake build
│   └── install/lib/libkdm6_c.dylib       ★ self-built runtime ABI library (ctest 16/16)
├── host/              Layer 3 — full WRF/KIM-meso Fortran host (self-contained, runnable)
│   └── KIM-meso_v1.0/
│       ├── phys/ dyn_em/ frame/ share/ main/ external/ inc/ run/ Registry/ ...   (WRF source+build)
│       ├── configure.wrf      KDM6AD_PREFIX → ../../../libtorch/install (KDM6AD-k's own dylib)
│       ├── compile            ./compile -j 4 em_real  → main/wrf.exe + real.exe
│       ├── main/wrf.exe       ★ self-built executable (rpath → KDM6AD-k dylib + miniforge torch)
│       └── test/ss_real_case_20260619_063620/SS/    SS case: inputs + run_ss_case.py (runs excluded)
├── host_fortran/      the 4 KDM6/KDM6AD .F files in isolation (reference; host/ supersedes for running)
└── harness/           parity scripts (strict_bitwise_nc.py, compare_*.py, run_ss_case.py)
```

Runtime chain: `host/.../main/wrf.exe` → `libtorch/install/lib/libkdm6_c.dylib` → `libtorch`
(miniforge, system-shared). The Python **oracle is not in the runtime** — it is the f64
algorithm definition used for development and parity verification.

## Build (standalone — integrated into the KIM-meso build)

The KIM-meso build now builds the C++ port itself: a single `./compile` produces both
`libkdm6_c.dylib` and `wrf.exe`. Because `./configure` regenerates `configure.wrf` (and the
KDM6AD block is not in `arch/configure.defaults`), re-apply the hook with
`apply_kdm6ad_config.sh` after every `./configure`:

```sh
KROOT=/Users/yhlee/KDM6AD-k
cd "$KROOT/host/KIM-meso_v1.0"

./configure                 # e.g. compiler choice 35, nesting 1
./apply_kdm6ad_config.sh    # re-inject the KDM6AD wiring into the fresh configure.wrf
./compile -j 4 em_real      # SS is a REAL case → em_real (not em_b_wave); builds the C++
                            # port (phys/Makefile hook), then real.exe + wrf.exe
```

How the integration works:
- `phys/Makefile` runs the port's CMake build/install into `$(KDM6AD_PREFIX)`
  (= `<KROOT>/libtorch/install`) as an order-only prerequisite of the KDM6 Fortran objects,
  so the dylib + headers exist before the `wrf.exe` link — no separate manual cmake step.
- `configure.wrf` derives every KDM6AD path from its own location (`$(MAKEFILE_LIST)` idiom),
  so the tree is relocatable and has no dependency on the archived development trees.
- `apply_kdm6ad_config.sh` is idempotent and arch-independent (it transforms whatever
  `configure.wrf` `./configure` produced); `-DKDM6_SUBSTEP_DUMP` (dormant, env-gated on
  `$KDM6_SUBSTEP_DUMP`) and the FP-contract rules are preserved.
- The port rule is **build-if-missing**. To pick up C++ source edits, remove
  `libtorch/install` (or re-run cmake in `libtorch/build`) before `./compile`.

Optional — build/test the C++ port directly (port-only iteration):

```sh
cd "$KROOT/libtorch" && mkdir -p build && cd build
cmake .. -DCMAKE_PREFIX_PATH="$(python3 -c 'import torch,os;print(os.path.dirname(torch.__file__))')" \
         -DCMAKE_INSTALL_PREFIX=../install -DCMAKE_CXX_FLAGS=-DKDM6_SUBSTEP_DUMP
cmake --build . -j4 && cmake --install . && ctest          # ctest 16/16
```

## Run + verify strict bitwise parity (standalone)

```sh
cd "$KROOT/host/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS"
python3 run_ss_case.py --mp 37  --minutes 1 --history 0 --fixed-dt --label v
python3 run_ss_case.py --mp 137 --minutes 1 --history 0 --fixed-dt --label v
A=$(ls -dt runs/mp37_v_*|head -1); B=$(ls -dt runs/mp137_v_*|head -1)
python3 "$KROOT/host/KIM-meso_v1.0/run/strict_bitwise_nc.py" \
        "$A/klfs_lc05_fcst.202507190000" "$B/klfs_lc05_fcst.202507190000" 1
#  → VARIABLES: 254 common, 253 BITWISE-MATCH, 0 DIFFER, Times non-numeric → STRICT BITWISE PASS
```
The SS namelist already has `history_interval_s=20` so the 254-var main history
`klfs_lc05_fcst` writes at the 20s step-1 frame (frame index 1). `--history 0` sets
`history_interval=0`; the `_s=20` supplies the 20s cadence.

### Python oracle (independent of the host)
```sh
cd "$KROOT/oracle" && python3 -m pytest        # algorithm + parity tests (needs torch)
```

## Provenance
- Source: archived KDM6AD source/build trees @ `eb1c823` ("KDM6AD: diag_rhog/RHO_ICE
  bitwise via symmetric output-only diagnostic gate+snap"). Originals untouched.
- Independence wiring (2026-06-24): the port build is integrated into the KIM-meso build via
  the `phys/Makefile` hook; `configure.wrf` KDM6AD paths are derived from its own location
  (relocatable) and re-applied after `./configure` by `apply_kdm6ad_config.sh`; `wrf.exe`
  rpath → `…/KDM6AD-k/libtorch/install/lib`. The SS-case `wrf.exe`/`real.exe` symlinks and
  the `run/` parity/debug scripts were repointed to KDM6AD-k-local targets;
  `kdm6_parity.py` was copied in to `libtorch/tools/`. Only the system miniforge `libtorch`
  is shared (not duplicated). Verified: from-scratch port build via the hook + `ctest` 16/16.
- Excluded by design: other WRF test cases (em_real/em_quarter_ss/…) and all parity `runs/`
  output dirs (the session's ~138G were cleaned before the copy).
- Result reproduced standalone: SS step-1 mp37↔mp137 = 254/254 strict f32 bitwise; C++ ctest 16/16.
