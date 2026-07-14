---
title: WRF KIM-meso Host
type: entity
date_modified: 2026-07-14
---
# WRF KIM-meso Host

## Key Facts

- The host tree lives under `host/KIM-meso_v1.0/`.
- It dispatches [[KDM6]] as `mp_physics=37` and [[KDM6AD]] as `mp_physics=137`.
- The microphysics driver supplies the same WRF state surface to both schemes.

## Connections

- Owns the runtime integration surface for [[KDM6]] and [[KDM6AD]].
- Loads the self-built `libkdm6_c.dylib` for the [[KDM6AD]] mp137 path.
- Provides the SS real-case run artifacts used by [[KDM6AD Forward Parity]] evidence.

## From [[kdm6-vs-kdm6ad-code-comparison-2026-06-25]]

- Existing final SS run artifacts for mp37 and mp137 both exited 0 and completed WRF successfully.

## Runtime linkage (2026-07-14)

- The host `wrf.exe` lives at `host/KIM-meso_v1.0/main/wrf.exe` (in-repo, gitignored; ~2187 Fortran files); other locations symlink to it.
- Its rpath resolves `@rpath/libkdm6_c.dylib` to **`libtorch/install/lib/libkdm6_c.dylib`** (the in-repo install), NOT the sibling `/Users/yhlee/KDM6AD` copy.
- mp137 links the C ABI surface hardened in [[KDM6AD C ABI Hardening]]; because v1 is byte-frozen, the `abi-v2-hardened` dylib is a drop-in re-install (no `wrf.exe` relink).

> [!warning] Tension — documented parity is at the pre-hardening dylib
> The 12h strict-bitwise parity in [[KDM6AD Forward Parity]] was verified against the **2026-07-04 pre-PR3** installed dylib, not the `abi-v2-hardened` build. Re-installing the `a53503e` dylib into `libtorch/install/` and re-running parity is pending. See [[abi-v2-hardened baseline 2026-07-14]].

## Run directories / cases (2026-07-14)

Three run configurations under `host/` are easily confused — full map in
`docs/HOST_RUN_LAYOUT.md`. Resolve any doubt with `ncdump -h <wrfinput> | grep ':DX'`.

| Dir | Case | Resolution | Role |
|---|---|---|---|
| `host/lc05_da_run/` | [[LC05 5km SS Case]] | **5 km** (234×282) | **the real-time DA target** |
| `host/KIM-meso_v1.0/run/` | ideal experiment | 100 km (`ideal_case 7`, 41×81) | previous experiment |
| `…/run/wrfinput_d01.37` | old 1 km experiment | 1 km (100×100) | previous experiment |

- `main/` holds the shared `wrf.exe`/`ideal.exe`/`real.exe`; the run dirs symlink to it.
- The 5 km case data lives OUTSIDE the repo at
  `/Users/yhlee/KDM6AD+/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS/`;
  `lc05_da_run/` symlinks into it.

> [!warning] Do not run the ideal scripts for the real case
> `run_parity.sh` / `run_kdm6ad.sh` in `KIM-meso_v1.0/run/` invoke `ideal.exe`
> and `rm -f wrfinput_d01` first. For the 5 km case run `wrf.exe` directly on the
> existing `wrfinput`. See [[host-run-dir-confusion-2026-07-14]].

