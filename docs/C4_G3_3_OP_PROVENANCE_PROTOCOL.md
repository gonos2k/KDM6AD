# C4 Gate B G3.3-M — op-level first-divergence instrumentation protocol

**Branch**: `analysis/c4-g3.3-op-provenance` · diagnostic-only, compile-time OFF, **no production change**.
**Purpose**: close Gate B G3.3 by *mechanism provenance* (not the withdrawn absolute-ULP envelope,
nor the withdrawn fixture-wide relative envelope — see [`C4_G3_3_FIRST_DIVERGENCE.md`](C4_G3_3_FIRST_DIVERGENCE.md)).
This document pins the exact instrumentation BEFORE any code is touched, so the change to
frozen-adjacent physics is reviewable and provably non-invasive.

## The question G3.3-M answers

For **both** cross-tree pairs — legacy (Fortran `kdm6` id 37 ↔ C++ `physics_variant=0` id 137) and
conservative (Fortran `kdm6_cons` id 237 ↔ C++ conservative id 337) — at the divergence cell
(**closure3-C3.3, j=2, k=3**, and the `nr`/`qv` cells carrying the 1.76×/2.56× ratios), record per
sub-cycle and per sedimentation operation the raw f32 bits of the Fortran and C++ result, and find
the **first operation where they diverge**.

**PASS-by-mechanism** iff, for both pairs:
1. the first cross-tree divergence occurs at the **same shared operation** (the `falk` fall-flux
   compute — identical idiom in both algorithms), on the **same branch/mstep signature**, and
2. the conservative pair differs ONLY in the input **magnitude** entering that shared op (larger `qr`
   because rain mass is not deleted at interfaces), with **no conservative-only operation or branch**
   at or before the first divergence.

**FAIL** iff the conservative pair's first divergence is at a conservative-only op — specifically the
ρΔz interface transfer `dq_in` (`sedimentation_conservative.cpp:84-86`, no legacy analogue) or the
absence of the positivity `clamp(...,0)` — i.e. the variant *introduces* a new cross-tree divergence
rather than amplifying an inherited one.

## Mapped landscape (file:line anchors)

Active Gate B driver: `host/gateb_cons_parity/gateb_driver.f90` (+ `.exe`, `Makefile`, `run_gateb.sh`,
produces `gateb_diffs.txt`). Fixtures at `:81-108`; dt=300 dispatch (`loops=3`) at `:143-150`; spec
indices qr=14, nr=21, qv=12, th=1. Checker `harness/gateb_g3_check.py` computes max-ULP per field/cell
(`:40-45`, `:116-117`) and **explicitly defers** first-divergence-stage + mstep/branch signature to a
per-subcycle host dump (`:18-21`, `:90-94`) — exactly this protocol.

Sedimentation sub-cycle structure (3 levels: outer dt-subcycle `loops` → per-species `mstep` fall
loop → vertical k sweep):

| | Fortran | C++ |
|---|---|---|
| outer `do loop=1,loops` | cons.F `:958`; legacy kdm6.F `:934` | runtime.cpp `:441` |
| rain `mstep` loop | cons.F `:1213-1307`; legacy `:1189-…` | coordinator.cpp `sedimentation_chain` `:2657` |
| per-cell ops (legacy) | kdm6.F top `:1197/:1204`, interior `:1234-1237` (`max(…,0)` clamp) | sedimentation.cpp `substep_advection_torch` `:90-114` (top), `:122-164` (interior) |
| per-cell ops (conservative) | cons.F `:1219-1222` (top), `:1266-1269` (interior ρΔz) | sedimentation_conservative.cpp `substep_advection_conservative` `:72-88` |

The shared op is `falk = (dend·q·work1/mstep·gate)→f32` (legacy sedimentation.cpp `:90/:122`,
conservative `:72`; Fortran cons.F `:1219`, kdm6.F `:1197`). The conservative-only op is the ρΔz
inflow `dq_in = prev_out·(dend[k-1]·delz[k-1])/(dend[k]·delz[k])` (sedimentation_conservative.cpp
`:84-86`; cons.F `:1268-1269`); the legacy analogue is `dqr_above = min(stored_falk·delz-ratio·…)`
+ positivity clamp (sedimentation.cpp `:149-164`; kdm6.F `:1234-1237`).

## Existing hooks to extend (NOT rebuild from scratch)

`KDM6_SUBSTEP_DUMP` (compile-time macro + env output-dir): mirrored big-endian raw-uint32 f32 format.
- C++ helper `kdm6_dump_field_be` / `kdm6_dump_state_substep` — coordinator.cpp `:33-63`; per-subcycle
  addressable via the `kdm6_substep_call` counter + env `KDM6_DUMP_CALL` (coordinator.cpp `:671-679`;
  `kdm62d_one_step` runs once per outer subcycle, runtime.cpp `:551`).
- Fortran helper + activation — module_mp_kdm6.F `:361-375` (env `KDM6_SUBSTEP_DUMP`, `KDM6_DUMP_STEP`),
  but dump sites are **hard-gated `if (… .and. loop .eq. 1)`** (first subcycle only) and fire at
  microphysics **stage boundaries**, not inside the sed loop.
- Consumer: `harness/compare_substep_stage.py` (strict uint32 cell-aligned compare, no tolerance).

## Instrumentation (all under `#ifdef KDM6_SUBSTEP_DUMP` — zero effect when undefined)

Per sedimentation call, for `qr`, `nr`, `qv`-coupling and the mass species, dump these four op-stage
tensors as `(B,K)` big-endian uint32, one file per `(pair, loop, n)`:

1. `sed_falk`   — the fall-flux `falk` immediately after the `→f32` cast (shared op).
2. `sed_capout` — the entry-capped outflow (`dq_out` conservative / `dqr_k` legacy) after the `min`.
3. `sed_inflow` — the interior inflow (`dq_in` conservative ρΔz / `dqr_above` legacy stored-falk).
4. `sed_qpost`  — the cell state after the update (with/without clamp).

### C++ (build with `-DKDM6_SUBSTEP_DUMP`)
- Add a per-call collector to `substep_advection_torch` (sedimentation.cpp) and
  `substep_advection_conservative` (sedimentation_conservative.cpp): push the per-k op tensors into
  `std::vector`s, `torch::stack` at the end, and write via `kdm6_dump_field_be` to
  `cpp_sed_<algo>_L<loop>_n<n>.bin`. `n` is already a parameter; **thread `loop`** from
  runtime.cpp `:441` → `sedimentation_chain` (coordinator.cpp `:2588/:2657`) → the substep fn
  signature (diagnostic-only extra arg, default -1).
- Guard every dump site with `if (std::getenv("KDM6_SUBSTEP_DUMP"))` so a defined-but-unset build is
  still inert.

### Fortran (build the gateb driver with `-DKDM6_SUBSTEP_DUMP`)
- In cons.F `:1213-1307` and kdm6.F `:1189-…`, add `#ifdef KDM6_SUBSTEP_DUMP` writes of the same four
  op values for the target column at each `(loop, n, k)` to `fort_sed_<algo>_L<loop>_n<n>.bin`,
  **relaxing the `loop .eq. 1` gate** to fire every `loop`. `access='stream'` unformatted, same
  big-endian uint32 via `transfer(x, int32)` + byte-swap (reuse the existing dump idiom).

## Build → run → analyze

1. Build a **diagnostic dylib**: `KDM6_ENABLE_TEST_HOOKS=OFF` + `-DKDM6_SUBSTEP_DUMP` (separate
   install prefix; the production dylib SHA in the manifest is unchanged). Gate on `wrf.exe`/lib
   producing the symbol, not on the compile exit code.
2. Build the gateb driver with `-DKDM6_SUBSTEP_DUMP` against that dylib.
3. Run the four cases (`closure3-C3.3`, `species-iso`, and their `LEG` twins) with
   `KDM6_SUBSTEP_DUMP=<dir>`; each emits `fort_sed_*` and `cpp_sed_*` per `(loop, n)`.
4. Extend `compare_substep_stage.py` (or a small `compare_sed_ops.py`) to walk `(loop, n, k, op)` in
   order and report, per pair, the FIRST `(loop, n, k, op)` where the Fortran and C++ uint32 differ,
   plus the branch/mstep signature at that point.
5. Adjudicate against the PASS/FAIL criterion above. On PASS-by-mechanism, replace the absolute-ULP
   envelope with the G3.3-M mechanism gate in `gateb_g3_check.py`; record the op-provenance table in
   `C4_G3_3_FIRST_DIVERGENCE.md` and the manifest.

## Non-invasiveness guarantees

- Every code change is inside `#ifdef KDM6_SUBSTEP_DUMP`; the default production build (macro
  undefined) is byte-for-byte unchanged — re-verified by rebuilding the production dylib and
  re-pinning its SHA against the manifest.
- No numerical/logic change: dumps read state, never write it. The threaded `loop` arg is diagnostic
  metadata with a default that is never used off the dump path.
- Fortran reference modules are touched ONLY in `#ifdef` dump blocks (no reference-semantics change),
  consistent with the owner-approved "diagnostic-only, compile-time OFF" instrumentation exception.
