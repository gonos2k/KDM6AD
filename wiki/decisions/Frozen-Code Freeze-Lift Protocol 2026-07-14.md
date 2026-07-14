---
title: Frozen-Code Freeze-Lift Protocol 2026-07-14
type: decision
date_modified: 2026-07-14
---
# Frozen-Code Freeze-Lift Protocol 2026-07-14

## Decision

The operational dylib code that governs mp37↔mp137 f32 bitwise parity —
`libtorch/bridge/kdm6_c_api.{cpp,h}`, the Fortran ISO_C shim, `libtorch/src/**`,
and the headers — is **frozen**. A change is made only under an **explicit,
scoped owner freeze-lift** issued before any implementation, and is merged only
after an **owner host-parity gate**.

## A valid freeze-lift names all four

1. **Baseline** — an explicit commit (e.g. `origin/main@<sha>`).
2. **Allowed files** — the exact edit set; nothing else is touched.
3. **Prohibited areas** — physics, constants, dtype, operation order, the ABI
   function signatures, the v2 struct/framing (additive-only; v1 byte-frozen).
4. **Verification gates** — stated up front: Linux + macOS port-CI, hooks-OFF
   dylib load, C/Fortran ABI smoke, and the **owner-host mp37↔mp137 short strict
   bitwise parity** as the merge gate (optionally a 12h MPI np4 campaign).

## Working rules

- Work on a branch; never commit frozen-code changes direct to `main`.
- Keep the PR head stable once its gates pass — a new SHA resets them.
- The assistant does **not** merge to `main` and does **not** run the host-parity
  gate; those are owner-only.
- Verification gates and scope come first; implementation second.

## Why

Public CI cannot reproduce the mp37↔mp137 host bitwise parity — only the owner
host can. An unscoped edit risks silently breaking that parity, which is the
project's paramount invariant. This discipline was used for PR1-A, PR2, and PR3
(all merged) — see [[KDM6AD C ABI Hardening]] and
[[abi-v2-hardening-roadmap-2026-07-14]].

## Standing frozen item

**PR1-B** — removal of the default `KMP_DUPLICATE_LIB_OK=TRUE` injected by the
bridge constructor — remains **FROZEN**. It requires a scoped freeze-lift AND is
gated on a source-free OpenMP dependency diagnostic first (launch the host with
`KMP_DUPLICATE_LIB_OK=FALSE`; the constructor's `setenv(..., overwrite=0)`
preserves the external FALSE). GO only if the host FALSE-mode run + mp37↔mp137
strict parity pass; split into PR1-B1 (diagnostics/docs) and PR1-B2 (the actual
`setenv` removal).

> [!note] Reusable protocol
> This is filed as a dated decision, but the four-part freeze-lift structure is a
> reusable rule for **any** future frozen-code work. If it is applied again,
> consider promoting it to a Heuristic via `/kg-elicit`.
