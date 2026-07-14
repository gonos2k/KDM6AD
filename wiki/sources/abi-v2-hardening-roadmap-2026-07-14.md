---
title: ABI v2 Hardening Roadmap 2026-07-14
type: source
date_modified: 2026-07-14
provenance:
  sources:
    - docs/RELEASE_ABI_V2_HARDENED.md
    - docs/PR3_VISIBILITY_DESIGN.md
    - docs/PR2_ABI_V2_DESIGN.md
    - "git merges: 8888be3 (PR1-A), e33a6c3 (PR2), 16ebe63 (PR3), a53503e (PR#6)"
    - "git tag: abi-v2-hardened -> a53503e"
---
# ABI v2 Hardening Roadmap 2026-07-14

Summary of the 2026-07-13/14 frozen-code hardening arc on the `libkdm6_c` C ABI
that the [[WRF KIM-meso Host]] mp137 path ([[KDM6AD]]) links. Sealed baseline:
`origin/main@a53503e`, tag `abi-v2-hardened`.

## Key takeaways

1. A 5-part hardening roadmap landed on `main` and was sealed as tag
   `abi-v2-hardened` (@ `a53503e`):
   - **PR1-A** (`8888be3`) — thread-determinism **fail-closed**:
     `KDM6_ERR_THREAD_CONFIG = -7` refuses a call before any tensor creation if
     libtorch/OpenMP cannot be pinned to 1 intra-op + 1 inter-op thread. A
     test-only fault seam is gated OFF in shipped builds (`KDM6_ENABLE_TEST_HOOKS`).
   - **P2-1** (`3b53bc6`) — evidence runner decoupled from the test tree.
   - **PR2** (`e33a6c3`) — **stable additive ABI v2**: `kdm6_step_v2_c` moves all
     inputs into an options struct whose growth is expressed by
     `struct_size`/`abi_version` framing, so the signature never changes again.
     v1 `kdm6_step_c` is kept **byte-frozen**; v1↔v2 are **bitwise-equivalent**
     (shared physics core).
   - **PR3** (`16ebe63`) — **hidden visibility + exact 9-symbol export allowlist
     + `SOVERSION 2`**: the export surface dropped **1342 → 9**; all
     `kdm6::`/libtorch/`std` internals are hidden.
   - **PR#6** (`a53503e`) — the symbol-surface CI gate now collects **every**
     defined external symbol (not just functions), so a leaked data/RTTI/vtable
     symbol is caught too; only the Linux version-node is excluded by name.
2. **Numerics unchanged**: physics / dtype / operation-order / the 9 ABI
   signatures / the v2 struct framing are all frozen; PR3/PR#6 changed packaging
   (export table, soname, install-name) and test tooling only. Bitwise-identical
   to the pre-PR3 tree.
3. The 9 exported C ABI symbols: `kdm6_step_c`, `kdm6_step_ad_c`,
   `kdm6_step_v2_c`, `kdm6_get_abi_version_c`, `kdm6_step_v2_args_size_c`,
   `kdm6_handle_vjp_c`, `kdm6_handle_jvp_c`, `kdm6_handle_close_c`,
   `kdm6_handle_closep_c`.
4. **Versioned library**: macOS `@rpath/libkdm6_c.2.dylib` +
   `.dylib → .2.dylib → .2.0.0.dylib`; Linux SONAME `libkdm6_c.so.2` +
   `.so → .so.2 → .so.2.0.0`. Major `2` == `KDM6_ABI_VERSION`.
5. **Freeze discipline** (governance): the operational dylib code
   (`kdm6_c_api.cpp`, Fortran shim, `libtorch/src/**`, headers) is frozen;
   changes require an explicit **scoped owner freeze-lift** (baseline + allowed
   files + prohibited areas + verification gates) and an **owner host-parity
   merge gate**. See [[Frozen-Code Freeze-Lift Protocol 2026-07-14]].
6. **PR1-B** (removal of the default `KMP_DUPLICATE_LIB_OK=TRUE` in the bridge
   constructor) remains **FROZEN**, gated on a source-free OpenMP dependency
   diagnostic first (the constructor uses `setenv(..., overwrite=0)`, so an
   external `KMP_DUPLICATE_LIB_OK=FALSE` measures the dependency with no code
   change).

## Verification recorded

- Public CI green on both Linux (x86-64) and macOS/arm64: hooks-OFF build/install,
  16 CTest, seam-absent, exported surface == 9, SONAME/install-name + symlink
  chain, hooks-ON fault-path, oracle↔C++ parity.
- Owner-attested host-parity at merge time (private manifest, digest-only).

## Concepts / entities touched

- [[KDM6AD C ABI Hardening]] (concept)
- [[Frozen-Code Freeze-Lift Protocol 2026-07-14]] (decision)
- [[abi-v2-hardened baseline 2026-07-14]] (experience)
- [[KDM6AD Automatic Differentiation ABI]] (updated — the AD ABI is one of the 9
  exported symbols)
- [[WRF KIM-meso Host]] (updated — install-baseline tension)
