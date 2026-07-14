# Release evidence — `abi-v2-hardened`

Sealed baseline for the completed frozen-code hardening roadmap. Rolling back to
this point restores a fully-verified, stable state.

| Field | Value |
|---|---|
| Baseline | `origin/main` @ `a53503e79c83af4e9954ba063f65c9dac742bc3f` |
| Tag | `abi-v2-hardened` (annotated) → `a53503e` |
| ABI version (`kdm6_get_abi_version_c()`) | `2` |
| `SOVERSION` | `2` |
| Exported C ABI symbols | exactly **9** (list below) |
| Numerical contract | v1 byte-frozen; v2 bitwise-equivalent to v1; identical to the pre-PR3 baseline |

## 1. What this baseline contains

| Item | Merge commit | Summary |
|---|---|---|
| PR1-A | `8888be3` | C ABI thread-determinism **fail-closed** — a call is refused (`KDM6_ERR_THREAD_CONFIG = -7`) if libtorch/OpenMP cannot be pinned to 1 intra-op + 1 inter-op thread, before any tensor creation. Test seam gated OFF in shipped builds. |
| P2-1 | `3b53bc6` | Evidence runner decoupled from the test tree (`kdm6/obs/rttov_fixture.py`). |
| PR2 | `e33a6c3` | Stable **additive ABI v2** — `kdm6_step_v2_c` options-struct entry with `struct_size`/`abi_version` framing; v1 `kdm6_step_c` kept byte-frozen; v1↔v2 bitwise-equivalent (shared physics core). |
| PR3 | `16ebe63` | **Hidden visibility + exact 9-symbol export allowlist + `SOVERSION 2`** — export surface reduced 1342 → 9; `kdm6::`/libtorch/`std` internals hidden. |
| PR #6 | `a53503e` | Symbol-surface gate hardened — collects **every** defined external symbol (data/RTTI/vtable/absolute), excludes only the Linux `KDM6_2` version node by name. |

## 2. Frozen contract preserved

No change during the visibility/packaging work to: `kdm6_c_api.cpp` body, the
Fortran ISO_C shim, `libtorch/src/**`, physics constants, tensor dtype, or
operation order. The 9 ABI function signatures and the v2 struct/framing are
unchanged. PR3/PR#6 changed packaging (export table, soname, install-name) and
test tooling only — the numbers are bitwise-identical to the pre-PR3 tree.

## 3. Public evidence (reproducible facts)

### 3.1 Exported C ABI surface — exactly 9

```
kdm6_step_c
kdm6_step_ad_c
kdm6_step_v2_c
kdm6_get_abi_version_c
kdm6_step_v2_args_size_c
kdm6_handle_vjp_c
kdm6_handle_jvp_c
kdm6_handle_close_c
kdm6_handle_closep_c
```

Gate: `python libtorch/tests/check_c_abi_exports.py <lib>` → "OK: exported set ==
the 9 C ABI symbols, zero internal leakage". Zero `kdm6::`/`at::`/`c10::`/
`torch::`/`std::` symbols exported.

### 3.2 macOS (arm64) versioned library

* install-name: `@rpath/libkdm6_c.2.dylib`
* compatibility version 2.0.0, current version 2.0.0
* symlink chain: `libkdm6_c.dylib` → `libkdm6_c.2.dylib` → `libkdm6_c.2.0.0.dylib`
* host links the unversioned dev symlink; loads the versioned library at runtime

### 3.3 Linux (x86-64) versioned library — CI-attested

* SONAME: `libkdm6_c.so.2` (`objdump -p`)
* symlink chain: `libkdm6_c.so` → `libkdm6_c.so.2` → `libkdm6_c.so.2.0.0`

### 3.4 Installed-artifact SHA-256

A macOS dylib embeds a per-link `LC_UUID`, so the shipped-artifact hash is
**build-specific, not bitwise-reproducible across machines**. Record the hash of
the canonical release build:

```sh
shasum -a 256 <install>/lib/libkdm6_c.2.0.0.dylib   # macOS
sha256sum      <install>/lib/libkdm6_c.so.2.0.0      # Linux
```

* Canonical release-build SHA-256 (macOS): `<OWNER-FILL — from the release build>`
* Canonical release-build SHA-256 (Linux): `<OWNER-FILL — from the release build>`
* Reference (non-canonical, macOS arm64, Homebrew clang 22.1.4 / cmake 3.24.4 /
  torch 2.8.0, hooks-OFF Release):
  `c773d6019e00e4068d59891cc18cb4f4929a365b817d0b9f21df702a4f53afe0`

### 3.5 Public CI (both platforms green on `a53503e`)

* **Linux**: hooks-OFF build/install, 16 CTest, seam-absent, export surface == 9,
  SONAME + `.so`→`.so.2`→`.so.2.0.0`, hooks-ON fault-path, oracle↔C++ parity.
* **macOS arm64**: hooks-OFF Release build/install, 16 CTest, arm64 + install-name,
  export surface == 9, fresh-process ctypes load resolving all 9, versioned dylib
  chain, hooks-ON fault-path.

## 4. Owner-host parity (owner-attested)

Public CI does not exercise the WRF/KIM-meso host or the mp37↔mp137 strict
bitwise parity — those are owner-host evidence. Rather than publish the private
host manifest, the release attests the result and publishes a hash of the
retained manifest:

```text
Owner-attested: mp37↔mp137 short strict-bitwise parity at a53503e — PASS.
Detailed host manifest (host tree SHA; clang / gfortran / OpenMPI / netCDF /
Torch versions; case; frames/steps; variable count) retained privately.
Manifest SHA-256: <OWNER-FILL>
Mismatch set:     empty
Hooks: OFF (shipped).   Seam: absent.
```

Fill the manifest hash from the privately-retained host-parity record before
merging PR #7 — no unfilled owner placeholder should remain in the merged doc
(the §3.4 canonical artifact hashes likewise).

## 5. Tag + rollback

The annotated tag `abi-v2-hardened` marks `a53503e` as the sealed baseline.
To return to it after any later experiment (e.g. a PR1-B trial):

```sh
git checkout abi-v2-hardened     # or: git reset --hard a53503e
```

## 6. Open item

**PR1-B — removal of the default `KMP_DUPLICATE_LIB_OK=TRUE`** remains FROZEN.
It requires a scoped owner freeze-lift AND is gated on a source-free OpenMP
dependency diagnostic first (the constructor uses `setenv(..., overwrite=0)`, so
an external `KMP_DUPLICATE_LIB_OK=FALSE` at launch measures the dependency with
no code change). For the freeze/scope boundaries and the freeze-lift-then-verify
sequencing this follows, see [PR3 visibility design](PR3_VISIBILITY_DESIGN.md)
§6 and §9, and [PR2 ABI v2 design](PR2_ABI_V2_DESIGN.md) §8–§9.
