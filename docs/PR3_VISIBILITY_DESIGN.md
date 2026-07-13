# PR3 — Symbol visibility / SOVERSION / export allowlist (design + test plan only)

**Status:** DESIGN ONLY. No build/link config is changed until the owner grants
an explicit, scoped freeze-lift (same discipline as PR1-A / PR2, see
`[[pr1a-thread-fence-merge-gate]]`). This document is the parallel preparation:
the measured problem, the mechanism, the export allowlist, the cross-platform
plan, and the verification matrix — so implementation is a mechanical follow-up
once the freeze is lifted.

Baseline: `origin/main@e33a6c3` (PR2 merged — stable C ABI v2 is in place).

## 1. The measured problem

`libkdm6_c.dylib` currently exports **almost its entire internal C++ world**,
not just its C ABI. Measured on the built dylib (`nm -gU`, arm64 Release-class):

| Exported symbols | Count |
|---|---:|
| **Total external defined** | **1342** |
| Intended C ABI (`kdm6_*_c`) | **9** |
| Leaked `kdm6::` internal C++ | 166 |
| Leaked `at:: / c10:: / torch:: / std::` | 1222 |

→ **~99.3 % of the exported surface is unintended internal leakage.**

Why this is a real problem, not cosmetics:

* **ODR / symbol collision.** The host (`wrf.exe` / KIM-meso) links *both*
  `libkdm6_c` *and* its own copy of libtorch. Two default-visible copies of the
  same `at::`/`c10::` symbols in one process is an ODR violation the dynamic
  linker resolves by interposition — the classic source of the flaky-NaN /
  divergence class this project already fights (the thread-fence and FP-env
  fences exist for exactly this reason). A hidden internal surface removes a
  whole category of interposition risk.
* **Accidental API.** Every exported `kdm6::` internal is a symbol a downstream
  consumer *can* link against and then depend on, freezing our internals as
  de-facto API. The contract is the 9 `kdm6_*_c` functions and nothing else.
* **Load time / binary size.** 1342 export-table entries and their dynamic
  relocations are pure overhead for a library whose contract is 9 functions.

## 2. Goals / non-goals

**Goals**

* Export **exactly** the 9 `kdm6_*_c` C ABI symbols; localize everything else.
* Add `SOVERSION` / `VERSION` so the ABI major (currently **2**, from PR2) is
  encoded in the soname / install-name and a consumer links against a versioned
  library.
* A CI gate that **asserts** the exported surface is the 9-symbol allowlist and
  that zero `kdm6::` / `torch::` symbols leak.

**Non-goals (explicitly out of scope for PR3)**

* **No numerical / signature / behavior change.** PR3 changes *packaging only*.
  The 9 symbols keep their exact signatures and byte results; the v1↔v2 bitwise
  test and the oracle↔C++ parity are unchanged and remain the guard.
* **No host migration**, no CMake package/`find_package` export (the install
  stays the plain file-copy of §CMakeLists — see `[[HOST_INTEGRATION]]`).
* **No `KMP_DUPLICATE_LIB_OK` change** — that is PR1-B and stays FROZEN.

## 3. The exported allowlist (the entire public surface)

Exactly these 9 symbols (measured present in the PR2 dylib):

```
kdm6_step_c                 # v1 forward (frozen)
kdm6_step_ad_c              # fp64 AD forward
kdm6_step_v2_c              # v2 options-struct forward (PR2)
kdm6_get_abi_version_c      # PR2
kdm6_step_v2_args_size_c    # PR2 layout guard helper
kdm6_handle_vjp_c
kdm6_handle_jvp_c
kdm6_handle_close_c
kdm6_handle_closep_c
```

The host's private ISO_C shim (`kdm6_iso_c.F`) references only this set, so
hiding the `kdm6::` / torch internals cannot break the host link (verified: the
host declares `kdm6_step_c` etc. and links nothing by internal name).

## 4. Mechanism (defense in depth)

Two independent layers, because neither alone is sufficient given that the
static `kdm6` core is linked into the shared `kdm6_c` (§4.3):

### 4.1 Compiler visibility (primary, portable)

Hide by default, opt the 9 back in via an attribute:

```cmake
# applied to BOTH the shared bridge AND the static core it absorbs
set_target_properties(kdm6   PROPERTIES CXX_VISIBILITY_PRESET hidden
                                         VISIBILITY_INLINES_HIDDEN ON)
set_target_properties(kdm6_c PROPERTIES C_VISIBILITY_PRESET   hidden
                                         CXX_VISIBILITY_PRESET hidden
                                         VISIBILITY_INLINES_HIDDEN ON)
```

```c
/* kdm6_c_api.h — additive export macro, NO signature change */
#if defined(_WIN32)
#  define KDM6_C_API __declspec(dllexport)
#else
#  define KDM6_C_API __attribute__((visibility("default")))
#endif

KDM6_C_API int kdm6_step_c(/* … unchanged … */);
/* … the other 8, each prefixed with KDM6_C_API … */
```

The macro is purely additive to the declarations; it changes no parameter,
type, or order. A consumer that includes the header still sees the identical
9 prototypes.

### 4.2 Linker allowlist (robust backstop, platform-specific)

Compiler visibility depends on every object being compiled with the hidden
preset. To be robust even against a stray default-visible object (e.g. a torch
inline that ignores the preset), pin the export set at link time:

* **macOS** — `-Wl,-exported_symbols_list,<path>/kdm6_c.exports`, where the file
  lists the 9 mangled C symbols (leading underscore):
  ```
  _kdm6_step_c
  _kdm6_step_ad_c
  _kdm6_step_v2_c
  _kdm6_get_abi_version_c
  _kdm6_step_v2_args_size_c
  _kdm6_handle_vjp_c
  _kdm6_handle_jvp_c
  _kdm6_handle_close_c
  _kdm6_handle_closep_c
  ```
  Everything not listed becomes a local symbol; the dylib exports exactly 9.
* **Linux** — `-Wl,--version-script,<path>/kdm6_c.map`:
  ```
  KDM6_2 {
    global:
      kdm6_step_c; kdm6_step_ad_c; kdm6_step_v2_c;
      kdm6_get_abi_version_c; kdm6_step_v2_args_size_c;
      kdm6_handle_vjp_c; kdm6_handle_jvp_c;
      kdm6_handle_close_c; kdm6_handle_closep_c;
    local:
      *;
  };
  ```
  `local: *` localizes all internals; the version node also stamps the soname
  version. Wire both via `target_link_options(kdm6_c PRIVATE …)` guarded by
  `APPLE` / `UNIX AND NOT APPLE`.

The linker allowlist is the **load-bearing** mechanism (it is what the CI gate
measures); the compiler visibility is defense in depth and shrinks the binary.

### 4.3 Why the static core needs the same treatment

`kdm6` is a separate `STATIC` target linked `PUBLIC` into `kdm6_c`. Its objects
are compiled under *its own* target's visibility preset, so today they carry
default visibility and are re-exported when absorbed into the dylib (this is the
source of the 166 leaked `kdm6::` symbols). PR3 therefore sets the hidden preset
on **both** targets. The test executables that link `kdm6` STATIC *directly*
(not through the dylib export table) are unaffected — hidden visibility governs
the dynamic export table, not static linking, so their asserts still resolve
every `kdm6::` symbol.

## 5. SOVERSION / VERSION

```cmake
set_target_properties(kdm6_c PROPERTIES
    VERSION   2.0.0     # ABI major.minor.patch (major tracks KDM6_ABI_VERSION)
    SOVERSION 2)        # soname major (Linux) / compatibility version (macOS)
```

* **Linux** → `libkdm6_c.so.2` with soname `libkdm6_c.so.2`; consumers link the
  major-versioned soname, so a future incompatible v3 dylib will not be picked
  up silently.
* **macOS** → sets `compatibility_version`/`current_version` and the versioned
  `install_name`. The host Makefile links `libkdm6_c.dylib` (the dev symlink);
  the versioned install_name is recorded for release provenance.

Major `2` matches `KDM6_ABI_VERSION` from PR2, so the soname and the runtime
`kdm6_get_abi_version_c()` agree.

## 6. Freeze / scope boundaries

* **Signatures + behavior of all 9 symbols: FROZEN.** PR3 changes only the
  export table, the soname, and a header export macro — never a parameter, a
  type, an order, or a numerical path.
* **Physics / src / dtype / op-order: FROZEN.** No `src/*.cpp` change. The v1↔v2
  bitwise test and oracle parity are the guard.
* **v1 byte-frozen; v2 bitwise-equivalent to v1** — unchanged from PR2.
* **Allowed files for the eventual freeze-lift (the scope to authorize):**
  * `libtorch/CMakeLists.txt` — visibility presets, `SOVERSION`/`VERSION`,
    `target_link_options` for the version scripts.
  * `libtorch/bridge/kdm6_c_api.h` — add the `KDM6_C_API` export macro to the 9
    declarations (additive only).
  * `libtorch/bridge/kdm6_c.exports` + `libtorch/bridge/kdm6_c.map` — **new**
    linker allowlist files.
  * `.github/workflows/ci.yml` — add the exported-symbol assertion gate.
  * `libtorch/tests/*` — a symbol-surface test/assertion if done in-tree.
* **NOT touched:** `kdm6_c_api.cpp` (no body change), `kdm6_iso_c.f90` /
  `kdm6_iso_c.F` (the 9 names are unchanged, so the shim needs no edit),
  `src/*`, any physics. **PR1-B (`KMP_DUPLICATE_LIB_OK`) stays FROZEN.**

## 7. Verification / test matrix

The load-bearing new check is a **measured symbol-surface assertion**, scripted
in CI (mirrors the PR1-A "seam-absent strings" gate):

* **Exported set == allowlist.** After a shipped (`KDM6_ENABLE_TEST_HOOKS=OFF`)
  Release build: `nm -gU libkdm6_c.dylib` (macOS) / `nm -D --defined-only
  libkdm6_c.so.2` (Linux) yields **exactly the 9** `kdm6_*_c` symbols.
* **Zero internal leakage.** The same listing contains **no** `kdm6::` and
  **no** `at::/c10::/torch::/std::` symbol (grep count == 0). Pins the 1342→9
  reduction and fails if a future edit re-widens the surface.
* **Cross-platform parity.** Both the macOS `exported_symbols_list` path and the
  Linux `--version-script` path independently produce the 9-symbol surface.
* **SOVERSION present.** Linux: `objdump -p libkdm6_c.so.2 | grep SONAME` ==
  `libkdm6_c.so.2`. macOS: `otool -L` / `otool -D` shows the versioned
  install_name.
* **Behavior unchanged (the freeze guard).** Full CTest incl. `c_abi`
  (v1↔v2 bitwise, the PR2 struct_size + genuine-contract tests) and the
  oracle↔C++ parity all still pass — the dylib's numbers are byte-identical to
  `e33a6c3`.
* **Host link smoke.** The dylib still `dlopen`s in a fresh process and resolves
  `kdm6_step_c` (and the other 8); an internal symbol like
  `kdm6::warm_phase` is now **absent** from the export table (positive proof the
  allowlist bit).
* **Fortran smoke unchanged.** `test_fortran_smoke` (the 9 names are unchanged)
  still links and passes, including the PR2 layout/size guards.

## 8. Risks / subtleties (measured, not assumed)

* **exported_symbols_list drift.** A symbol in the list that the build does not
  define is a macOS linker warning; the CI gate's "== 9" assertion catches a
  list that drifts out of sync with the header in either direction.
* **torch weak/inline template symbols.** `VISIBILITY_INLINES_HIDDEN` plus the
  version-script `local: *` localizes the 1222 `at::/std::` leaks; the CI gate
  is the proof they are gone, since header-only inline instantiations are the
  easiest to accidentally re-export.
* **Test targets vs the dylib.** Test executables link `kdm6` STATIC directly,
  so hidden dynamic visibility does not hide symbols from them; verified by the
  full CTest still passing. Only `test_c_abi` / `test_fortran_smoke` go through
  the `kdm6_c` shared target, and they use only the 9 default-visible symbols.
* **Host `install_name` on macOS.** Adding `VERSION`/`SOVERSION` changes the
  recorded install_name; confirm the host Makefile's link line
  (`$(LIB_LOCAL)`) still resolves the dev `libkdm6_c.dylib` symlink so the WRF
  build is unaffected (owner host-parity gate covers this).

## 9. Sequencing

1. PR2 merged (`e33a6c3`) — done.
2. **Owner freeze-lift for PR3**, scoped to §6's allowed files.
3. Implement from this design (visibility presets, export macro, `.exports` +
   `.map`, `SOVERSION`, CI symbol-surface gate), under the same
   freeze-lift-then-verify discipline.
4. Owner host-parity gate (clean OFF rebuild, macOS load smoke, short
   mp37↔mp137 parity, dylib links into the real WRF/KIM-meso build with the new
   install_name) → merge PR3.
5. PR1-B (`KMP_DUPLICATE_LIB_OK` removal) remains FROZEN — a separate decision.
