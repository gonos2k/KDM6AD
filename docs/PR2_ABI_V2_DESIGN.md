# PR2 — Stable C ABI v2 (design + test plan only)

**Status:** DESIGN ONLY. No production ABI code is written until PR1-A is
merged after owner host verification (see `[[pr1a-thread-fence-merge-gate]]`).
This document is the reviewer-approved parallel preparation: the v2 contract,
the options-struct layout, the negative-test matrix, and the freeze policy —
so implementation is a mechanical follow-up once PR1-A lands.

Baseline: `origin/main@d2c0479` (+ PR1-A on branch `pr1a-thread-fail-closed`,
which adds `KDM6_ERR_THREAD_CONFIG = -7`).

## 1. Why v2 (the problem v1 has)

`kdm6_step_c` grew by **appending trailing C parameters** (`xland`,
`ncmin_land/sea`, precip increments, `rhog_out`). Appending arguments to a C
function is **not binary-compatible**: a caller compiled against the old
signature passes an undefined value where the new library reads the new
argument. It works only because the host and the library are always
recompiled together. To become an independently-versioned, stable ABI we stop
extending the function signature and move to an **options struct** whose growth
is expressed by `struct_size`, not by new positional parameters.

## 2. New symbols (additive — v1 stays frozen)

```c
/* Returns the ABI version this library implements. Lets a host detect a
 * library older/newer than it was built against BEFORE calling step_v2. */
int kdm6_get_abi_version_c(void);

#define KDM6_ABI_VERSION 2   /* header value the caller was built against */

/* The single forward entry going forward. All existing AND future inputs
 * live in the struct; the function signature never changes again. */
int kdm6_step_v2_c(const kdm6_step_v2_args* args);
```

* `kdm6_step_c` (v1) is **KEPT and FROZEN** — its exact behavior and byte
  results are preserved. After v2 lands, v1 becomes a thin compatibility
  wrapper that fills a `kdm6_step_v2_args` and calls the shared internal
  implementation, so v1 and v2 are the same physics by construction.
* `kdm6_handle_closep_c` is the recommended close API; `kdm6_handle_close_c`
  stays but is documented deprecated (pointer not nulled → use-after-free
  foot-gun). No signature change to either in PR2.

## 3. The options struct

```c
#include <stdint.h>

typedef struct {
    /* ── ABI framing (MUST be the first two fields, never reordered) ── */
    uint32_t struct_size;    /* sizeof(kdm6_step_v2_args) AS THE CALLER SAW IT */
    uint32_t abi_version;    /* KDM6_ABI_VERSION the caller was built against  */

    /* ── dimensions ── */
    int32_t  im, kme, jme;
    double   dt;

    /* ── control flags ── */
    int32_t  value_only;       /* 0/1 only */
    int32_t  param_grad_flags; /* reserved, must be 0 (as v1) */

    /* ── required inputs: 12 state + 4 forcing (Fortran col-major float*) ── */
    const float *th, *qv, *qc, *qr, *qi, *qs, *qg,
                *nccn, *nc, *ni, *nr, *bg;
    const float *rho, *pii, *p, *delz;

    /* ── required outputs: 12 state (caller-allocated) ── */
    float *th_out, *qv_out, *qc_out, *qr_out, *qi_out, *qs_out, *qg_out,
          *nccn_out, *nc_out, *ni_out, *nr_out, *bg_out;

    /* ── derivative handle (out) ── */
    kdm6_handle_t** handle;

    /* ── OPTIONAL inputs/outputs: NULL ⇒ "not provided" (documented) ── */
    const float *xland;        /* NULL ⇒ maritime */
    double       ncmin_land, ncmin_sea;
    float       *rain_increment, *snow_increment, *graupel_increment; /* NULL ⇒ skip */
    float       *rhog_out;     /* NULL ⇒ skip */

    /* Future fields are APPENDED here; a smaller struct_size means the caller
     * did not supply them and the library treats them as their documented
     * NULL/zero default. */
} kdm6_step_v2_args;
```

Design rules:

* **Fixed-width integers** (`uint32_t`/`int32_t`) so the struct layout does not
  depend on `int`/`long` width across host toolchains.
* **`struct_size` and `abi_version` are the first two fields, never reordered
  or removed** — every version can read them from any pointer.
* **`struct_size` MUST be at offset 0 and read FIRST** (see the framing
  read-order rule in §4): it bounds every subsequent read, so it cannot itself
  depend on any other field being present.
* **Only additive growth**: new fields are appended, never inserted or
  reordered; a field is never repurposed. Removing/reordering a field is a v3,
  not a v2 change.
* **`args == NULL` ⇒ `KDM6_ERR_NULL_POINTER`** (checked before dereferencing
  any field). After the NULL check, `struct_size` at offset 0 is the first —
  and, until validated, the ONLY — field the library may read.

```c
/* the two framing fields the caller MUST always allocate */
#define KDM6_STEP_V2_MIN_SIZE (2u * sizeof(uint32_t))   /* struct_size + abi_version */
```

## 4. `struct_size` / `abi_version` handling

**Framing read-order (crash-safety — Codex):** the caller MUST allocate at
least the two framing fields (`KDM6_STEP_V2_MIN_SIZE` bytes). After the NULL
check the library reads `struct_size` at offset 0 FIRST and immediately
verifies `struct_size >= KDM6_STEP_V2_MIN_SIZE`. If it is smaller, the call is
rejected with `KDM6_ERR_INVALID_ARG` **before `abi_version` (offset 4) is
read** — otherwise a caller that declared a 4-byte struct would have
`abi_version` read past its buffer. `abi_version` (and every later field) is
read ONLY after `struct_size` has bounded the accessible region. The library
accesses at most `min(struct_size, LIB)` bytes, so no version skew ever reads
uninitialized caller memory.

Let `LIB = sizeof(kdm6_step_v2_args)` as the LIBRARY sees it, and `S =
args->struct_size` as the CALLER passed it (already known `>= KDM6_STEP_V2_MIN_SIZE`
by the framing check above).

* `S < offsetof(fields required by this version)` → `KDM6_ERR_INVALID_ARG`
  (the caller's struct is too small to even contain the required inputs).
* `S < LIB` (older caller, newer library) → **accepted**: the library reads
  only the first `S` bytes and treats every field beyond `S` as its documented
  default (optional pointers → NULL, `ncmin_*` → 0). The library MUST NOT read
  past `S`.
* `S == LIB` → normal.
* `S > LIB` (newer caller, older library) → **accepted only if** every field
  the library does not know about is at its default; since the library cannot
  inspect unknown fields, the safe contract is: read only the first `LIB`
  bytes, ignore the tail. (A stricter variant rejects `S > LIB` with
  `KDM6_ERR_INVALID_ARG`; the negative-test matrix pins whichever we choose.)
* `abi_version` major mismatch (caller major ≠ library major) →
  `KDM6_ERR_INVALID_ARG`. Within the same major, `struct_size` governs.

The key invariant: **the library accesses at most `min(S, LIB)` bytes**, so a
version skew never reads uninitialized caller memory.

## 5. Validation precedence (v2)

Extends the v1 precedence (`[[kdm6_c_api.h]]` VALIDATION PRECEDENCE), with the
struct framing checked first:

1. `args == NULL` → `KDM6_ERR_NULL_POINTER`
2. read `struct_size` (offset 0); `struct_size < KDM6_STEP_V2_MIN_SIZE` →
   `KDM6_ERR_INVALID_ARG` (**before** any other field, incl. `abi_version`, is read)
3. read `abi_version`; major mismatch → `KDM6_ERR_INVALID_ARG`
4. `struct_size` too small for the required fields → `KDM6_ERR_INVALID_ARG`
5. dimensions → `KDM6_ERR_INVALID_DIM`
6. `value_only ∈ {0,1}` → `KDM6_ERR_INVALID_ARG`
7. required pointers → `KDM6_ERR_NULL_POINTER`
8. `param_grad_flags != 0` → `KDM6_ERR_NOT_IMPLEMENTED`
9. single-thread fence → `KDM6_ERR_THREAD_CONFIG` (from PR1-A)
10. tensor creation / microphysics

Same fail-closed contract on every error: `*handle == NULL`, no output buffer
written.

## 6. Fortran `bind(C)` interop

`kdm6_iso_c.f90` gains an interoperable derived type mirroring the struct, and
a `kdm6_step_v2` wrapper — the existing `kdm6_step` wrapper is preserved.

```fortran
type, bind(C) :: kdm6_step_v2_args_t
   integer(c_int32_t) :: struct_size
   integer(c_int32_t) :: abi_version
   integer(c_int32_t) :: im, kme, jme
   real(c_double)     :: dt
   integer(c_int32_t) :: value_only
   integer(c_int32_t) :: param_grad_flags
   type(c_ptr)        :: th, qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg
   type(c_ptr)        :: rho, pii, p, delz
   type(c_ptr)        :: th_out, qv_out, qc_out, qr_out, qi_out, qs_out, qg_out
   type(c_ptr)        :: nccn_out, nc_out, ni_out, nr_out, bg_out
   type(c_ptr)        :: handle
   type(c_ptr)        :: xland
   real(c_double)     :: ncmin_land, ncmin_sea
   type(c_ptr)        :: rain_increment, snow_increment, graupel_increment
   type(c_ptr)        :: rhog_out
end type
```

`struct_size` is set with `c_sizeof` on the Fortran side; the field ORDER must
match the C struct exactly. `test_fortran_smoke.f90` gains a size/offset guard
(the Fortran `c_sizeof(args)` must equal the C `sizeof` reported by a new
`kdm6_step_v2_args_size_c()` helper, or a compile-time `static_assert` mirror)
so a layout drift between the C and Fortran structs fails the smoke test.

## 7. Negative-test matrix (to write with the impl)

Through the pure-C `test_c_abi.cpp` consumer (ABI isolation preserved):

* `args == NULL` → `NULL_POINTER`.
* **framing minimum (Codex):** `struct_size ∈ {0, 4}` (below
  `KDM6_STEP_V2_MIN_SIZE`) → `INVALID_ARG`, and `abi_version` is NOT read —
  exercised by putting the args object at the end of a mmap'd page whose next
  page is unmapped (or poisoning bytes 4..7): the call must return the error,
  never fault or depend on the `abi_version` bytes.
* `abi_version` wrong major (with `struct_size >= min`) → `INVALID_ARG`.
* `struct_size` at the framing minimum but below the required-field cutoff →
  `INVALID_ARG`.
* small-but-valid `struct_size` (caller omits the optional tail) → runs, with
  the omitted optionals treated as NULL/zero, result **bitwise-equal** to a v1
  call with those optionals NULL.
* large future `struct_size` (caller struct bigger than the library's) →
  handled per §4, no read past `min(S,LIB)` (exercised with a deliberately
  oversized buffer whose tail is poisoned; the result must not depend on the
  poison).
* every v1 precedence case (dim / value_only / null / param_grad) reproduced
  on v2, in the §5 order.
* thread-fence precedence (needs `KDM6_ENABLE_TEST_HOOKS` from PR1-A):
  `THREAD_CONFIG` only after all arg checks.
* **v1↔v2 bitwise equivalence**: for a battery of inputs (single cell,
  multi-cell asymmetric `(im,kme,jme)`, mixed xland, with/without precip
  outputs), `kdm6_step_c` and `kdm6_step_v2_c` produce **byte-identical** state
  outputs, increments, and (for `value_only=0`) the same VJP/JVP on the handle.
  This is the load-bearing test: it proves v2 is the same physics, just a
  different calling convention.
* handle is `NULL` on every error path; all outputs are sentinel-preserved on
  every refusal (the PR1-A optional-output sentinel pattern).

## 8. Freeze / scope boundaries

* **v1 `kdm6_step_c` signature + behavior: frozen.** v2 is purely additive.
* **Physics/src/dtype/op-order: frozen.** v2 shares the exact internal
  implementation v1 uses — no numerical path change; the v1↔v2 bitwise test is
  the guard.
* **Symbol visibility / `SOVERSION` / export allowlist: NOT in PR2.** Those are
  PR3. PR2 only adds symbols (`kdm6_get_abi_version_c`, `kdm6_step_v2_c`, a size
  helper); PR3 later hides internals and pins the exported set. PR2 must not
  pre-empt PR3's visibility changes (keep `C_VISIBILITY_PRESET` as-is).
* **Host migration: not in PR2.** The host keeps calling v1; a v2 smoke proves
  parity. Switching the host to v2 is a separate, post-merge step.

## 9. Sequencing

1. PR1-A owner host verification + main merge (`[[pr1a-thread-fence-merge-gate]]`).
2. Then implement PR2 from this design (new symbols, struct, Fortran type,
   negative-test matrix, v1↔v2 bitwise test), under the same
   freeze-lift-then-verify discipline.
3. PR3 (visibility / SOVERSION / symbol allowlist) after PR2.
