# Host integration — wiring `host_fortran/` into a WRF/KIM-meso tree

The Layer-3 Fortran files in `host_fortran/` are the KDM6/KDM6AD microphysics
integration source. They build into a full **KIM-meso/WRF host tree** (the foreign
host model, not bundled here). This doc records the exact wiring so the bundled
`.F` files can be dropped into a host and produce `wrf.exe` with selectable
`mp_physics=37` (KDM6 Fortran) / `mp_physics=137` (KDM6AD libtorch port).

## Files (drop into `<WRF>/phys/`)
| File | Role |
|---|---|
| `module_mp_kdm6.F` | KDM6 mp37 reference scheme (incl. the diag_rhog gate+snap, commit eb1c823) |
| `module_mp_kdm6ad.F` | KDM6AD mp137 wrapper — calls the C++ ABI; computes re_*/diag_rhog/REFL_10CM diagnostics |
| `kdm6_iso_c.F` | ISO_C_BINDING interface declaring `kdm6_step_c` etc. (Fortran ↔ C++ ABI) |
| `module_microphysics_driver.F` | dispatches mp37 vs mp137 |

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
The C++ side must be compiled with `-ffp-contract=off` (it is, via CMakeLists) and the
Fortran mp modules likewise (`configure.wrf` per-file rule) for bitwise parity.

### 2. Module dependency — `phys/Makefile` (+ `main/depend.common`)
```make
module_mp_kdm6ad.o: module_mp_kdm6.o kdm6_iso_c.o    # kdm6ad reuses effectRad_kdm6/refl10cm_kdm6 from kdm6
```

### 3. Scheme registration — `Registry/Registry.EM`
`mp_physics==137` must be registered as the KDM6AD scheme (state arrays identical to
the mp37 KDM6 package: moist/scalar/nc/ni/nccn/bg + diag_rhog/RHOPO3D, re_*, REFL_10CM).

## Build & run
```sh
cd <WRF> && ./compile -j 4 em_b_wave          # → main/wrf.exe (links libkdm6_c.dylib + libtorch)
# touch phys/module_mp_kdm6*.F if only .F changed; no clean unless Registry changed.
```
Then run with `harness/run_ss_case.py` (set `mp_physics` via `--mp 37|137`) on an SS real case.

## Source note
The `host_fortran/` files here were copied from the archived tracked KDM6AD tree at
commit `eb1c823`.
The generated `.f90`/`.mod`/`.o` are build artifacts — not bundled; the host regenerates
them (`.F` is preprocessed by `cpp` on capital-`.F`).

## Verified result
With this wiring, SS step-1 `mp_physics=37` ↔ `137` is **254/254 strict f32 bitwise**
(253 BITWISE-MATCH + Times non-numeric; RHO_ICE 0 diffs), C++ ctest 16/16.
