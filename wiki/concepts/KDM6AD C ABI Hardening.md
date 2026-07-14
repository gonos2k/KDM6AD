---
title: KDM6AD C ABI Hardening
type: concept
date_modified: 2026-07-14
---
# KDM6AD C ABI Hardening

## Why This Matters

`libkdm6_c` is the single binary contract between the Fortran [[WRF KIM-meso Host]]
(mp137) and the libtorch [[KDM6AD]] port. Because that contract must stay
bitwise-deterministic to preserve [[KDM6AD Forward Parity]], its packaging and
error behavior were hardened without touching the numerics. The result is the
`abi-v2-hardened` baseline (`a53503e`).

## The four hardening axes

1. **Thread-determinism fail-closed** — bitwise determinism requires libtorch/
   OpenMP pinned to 1 intra-op + 1 inter-op thread. If it cannot be pinned, the
   call is **refused** with `KDM6_ERR_THREAD_CONFIG = -7` before any tensor is
   created (handle NULL, outputs untouched) — never a silent multi-threaded run.
   The test seam that exercises this path is compiled out of shipped builds
   (`KDM6_ENABLE_TEST_HOOKS=OFF`).
2. **Stable additive ABI v2** — `kdm6_step_v2_c` takes an options struct framed
   by `struct_size` + `abi_version`, so future inputs are appended without
   changing the function signature. v1 `kdm6_step_c` is byte-frozen; v1 and v2
   share the same physics core and are **bitwise-equivalent**. `struct_size` is
   read first and bounds every subsequent read (no read past `min(struct_size,
   sizeof)`).
3. **Symbol visibility + export allowlist** — hidden visibility on both the
   static core and the shared bridge, plus a linker allowlist (macOS
   `-exported_symbols_list` / Linux `--version-script`), reduces the export
   surface **1342 → exactly 9** C ABI functions. This removes ODR/interposition
   risk against the host's own libtorch and stops internal `kdm6::` symbols from
   becoming accidental API.
4. **`SOVERSION 2` / versioned library** — the soname/install-name encode ABI
   major `2` (== `KDM6_ABI_VERSION`), so a consumer links a versioned library
   and a future incompatible v3 is not picked up silently. The host keeps linking
   the unversioned dev symlink and loads the versioned library at runtime.

## The 9-symbol public surface

`kdm6_step_c`, `kdm6_step_ad_c`, `kdm6_step_v2_c`, `kdm6_get_abi_version_c`,
`kdm6_step_v2_args_size_c`, `kdm6_handle_vjp_c`, `kdm6_handle_jvp_c`,
`kdm6_handle_close_c`, `kdm6_handle_closep_c`. The
[[KDM6AD Automatic Differentiation ABI]] (`kdm6_step_ad_c` + the handle VJP/JVP
calls) is a subset of this surface.

## Rationale

Packaging/visibility changes carry real risk (an interposed libtorch symbol can
cause exactly the flaky-NaN class this project fights), so they were staged as
additive, verified changes with the export surface asserted by a CI gate and the
numbers held bitwise-identical to the pre-hardening tree.

## Boundaries

- Packaging only — no change to physics, dtype, operation order, or the frozen
  ABI signatures. [[KDM6AD Forward Parity]] numbers are unchanged by definition.
- Governed by the [[Frozen-Code Freeze-Lift Protocol 2026-07-14]].
- The removal of the default `KMP_DUPLICATE_LIB_OK=TRUE` (PR1-B) is **not** part
  of this baseline — it remains frozen pending a host OpenMP diagnostic.

Provenance: [[abi-v2-hardening-roadmap-2026-07-14]].
