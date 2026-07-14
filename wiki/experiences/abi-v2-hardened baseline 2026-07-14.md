---
title: abi-v2-hardened baseline 2026-07-14
type: experience
date_modified: 2026-07-14
---
# abi-v2-hardened baseline 2026-07-14

## What happened

The 5-part [[KDM6AD C ABI Hardening]] roadmap was merged to `main` and sealed as
the annotated tag `abi-v2-hardened` → `a53503e`. The tag is a **source/tag
release** (the release identity is the tag, not a shipped binary); a release-
evidence doc (`docs/RELEASE_ABI_V2_HARDENED.md`) records the reproducible public
facts and an owner-attested host-parity result (private manifest, digest-only).

## The install-baseline tension (discovered this session)

> [!warning] Tension — parity is validated at the PRE-hardening dylib, not abi-v2-hardened
> [[KDM6AD Forward Parity]] records mp37↔mp137 STRICT BITWISE parity through a
> 12h × MPI(np4) run. That was verified against an **older** `libkdm6_c.dylib`,
> **not** the `abi-v2-hardened` build:
> - The host `wrf.exe` (`host/KIM-meso_v1.0/main/wrf.exe`, built **2026-07-04**)
>   links `@rpath/libkdm6_c.dylib` (unversioned, compat 0.0.0) and its rpath
>   resolves to **`libtorch/install/lib/libkdm6_c.dylib`**.
> - That installed dylib is the **2026-07-04 pre-PR3 build** (unversioned,
>   ~2.2 MB, 1342-symbol) — the `abi-v2-hardened` versioned/9-symbol dylib
>   (`libkdm6_c.2.0.0.dylib`) has **not** been re-installed there.
>
> So the documented parity predates the hardening. Re-verifying parity at
> `a53503e` is a pending host step.

## Why the re-verification is a drop-in (not a rebuild)

Because v1 `kdm6_step_c` is byte-frozen and `wrf.exe` calls only the 9 C ABI
symbols through the Fortran ISO_C shim (never internal `kdm6::` symbols), the
`a53503e` dylib is drop-in compatible with the existing Jul-4 `wrf.exe`:
`cmake --install` the hardened build into `libtorch/install/` (which creates
`libkdm6_c.2.0.0.dylib` + the `libkdm6_c.dylib` dev symlink), and the unchanged
`wrf.exe` loads it via the dev symlink. No `wrf.exe` relink needed. This is
exactly the host-load path the PR3 host-parity gate validated.

## Notes / gotchas

- The real WRF integration is in-repo at **`host/KIM-meso_v1.0/`** (gitignored,
  ~2187 Fortran files) — not the sibling `/Users/yhlee/KDM6AD` tree (a stale
  separate copy pinned to `eb1c823`, which is a red herring).
- **MPI gotcha** (from [[KDM6AD Forward Parity]]): `mpirun np≥2` needs
  `--mca btl self,tcp`; the Open MPI shared-memory BTL SEGVs flakily with the
  libtorch-loaded ranks. (`run_ss_case.py` uses `-np 1`, so unaffected there.)
- The bridge constructor injects `KMP_DUPLICATE_LIB_OK=TRUE` with
  `overwrite=0` — relevant to the frozen **PR1-B** diagnostic.

Provenance: [[abi-v2-hardening-roadmap-2026-07-14]]; live inspection of
`host/KIM-meso_v1.0/main/wrf.exe` and `libtorch/install/lib`.
