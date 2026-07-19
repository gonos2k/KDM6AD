# C4 Gate B G3.3-M — op-level first-divergence instrumentation protocol (hardened)

**Branch**: `analysis/c4-g3.3-op-provenance` · diagnostic-only, compile-time OFF, **no production change**.
**Status**: conditionally approved (owner adversarial review 2026-07-19). This revision hardens the
protocol against **confirmation bias** and **instrumentation-induced false pass** BEFORE any code is
written. Supersedes the first draft's implicit "falk is the cause" framing.
**Purpose**: close Gate B G3.3 by *mechanism provenance* — replacing the withdrawn absolute-ULP
envelope and the withdrawn fixture-wide relative envelope (see
[`C4_G3_3_FIRST_DIVERGENCE.md`](C4_G3_3_FIRST_DIVERGENCE.md)) — WITHOUT touching production physics or
the existing checker until the evidence is in hand.

---

## 0. The question — find first, classify second (P0-1)

The gate does **NOT** assume the first cross-tree divergence is at `falk`. The C++ sedimentation chain
re-runs `preamble → ProgB → slope` after each main substep, regenerating `work1_qr`/`workn_qr`; the
`falk` *inputs* can therefore already differ from an earlier re-slope. A real causal order may be:

```
subcycle-1 q_post divergence → re-slope input divergence → vt/work1 divergence → subcycle-2 falk divergence
```

so `falk` could be a downstream *carrier*, not the seed. The protocol therefore:

1. **Locates the first cross-tree divergence** over the full recorded space (below), THEN
2. **Classifies** it as a *shared* operation (present identically in both algorithms) or a
   *conservative-only* operation.

If the first divergence is **before sedimentation** (`outer_pre_sed` already differs, or `work1`/`mstep`
already differ at substep entry), the verdict is **INCONCLUSIVE — divergence predates sedimentation**,
never FAIL, and the instrumentation must widen upstream.

---

## 1. Snapshots required (P0-1, P1-8)

For each outer sub-cycle and each main/ice substep `n`, both backends dump, in order:

```
outer_pre_sed        qr nr qv th   + rho delz               (whole B×K)
  substep_pre_n      qr nr  work1_qr workn_qr  mstep_col mstepmax gate  rho delz
    <sed op ladders per k — §3>
  substep_post_n     qr nr  (+ qs qg brs)
  reslope_input_n    the fields fed to preamble/ProgB/slope
  reslope_output_n   work1_qr workn_qr (+ the regenerated fall-speed inputs)
outer_post_sed       qr nr qv th
outer_post_micro     qr nr qv th
```

- **`qv`/`th` are NOT in `SubstepAdvectionState`** (only `qr nr qs qg brs`), so they are captured **only
  at the outer-loop boundary**. Sedimentation must leave `qv`/`th` invariant, so
  `outer_pre_sed.{qv,th} == outer_post_sed.{qv,th}` is itself a checked invariant (a violation is an
  instrumentation/logic bug, not a physics finding).
- Every snapshot records the **whole `(B,K)`** field, not just the final-max cell (P0-5).

---

## 2. Typed, native-precision dump — never pre-round (P0-2)

The existing `kdm6_dump_field_be` casts every tensor `.to(torch::kFloat32)` before writing. That
**destroys native-precision differences**: two backends whose `work1` differ in the last f64 bit but
round to the same f32 would look "input-bitwise" — a false pass. G3.3-M uses a **typed writer** that
records each value at its NATIVE width:

```
real32  → uint32 raw bits          real64 → uint64 raw bits
int32   → int32                    logical → uint8
```

Minimum per-op fields (mass species, per k):

```
q_entry_f32   dend_f32   delz_f32   work1_native_f64   mstep_i32   gate_u8
falk_precast_native_f64    falk_stored_f32
```

and, where feasible, the **arithmetic ladder** so the rounding rung of the first divergence is visible:

```
mul_dend_q → mul_work1 → div_mstep → mul_gate → falk_precast(native) → falk_f32(stored)
```

---

## 3. Per-rung op ladders — pin the exact operation (P0-1, P1-9)

Recording only `inflow` + `q_post` cannot say WHICH op diverged. Both paths dump the full rung set:

**Conservative** (`sedimentation_conservative.cpp:72-88`, cons.F `:1219-1269`):
```
falk_f32
dq_out = min(falk*dtcld/dend_safe, q)          cap_active(u8)  source_reservoir=q
prev_out(from k-1)   src_metric=dend[k-1]*delz[k-1]   dst_metric=dend[k]*delz[k]
prev_out*src_metric  → /dst_metric = dq_in
q_before  q_minus_out=q-dq_out  q_plus_in = q_minus_out+dq_in   (NO clamp)   q_post
```

**Legacy** (`sedimentation.cpp:90-164`, kdm6.F `:1197-1237`):
```
falk_f32   (stored falk_prev carried into the interior inflow)
dqr_k   = min(falk*dtcld/dend_safe, q)          cap_active(u8)
inflow numerator: stored_falk_prev * delz_src / delz_dst * dt / rho_dst
dqr_above = min(inflow_numerator, q[k-1])       inflow_cap_active(u8)  source_reservoir=q[k-1]
q_before  q_minus_out=q-dqr_k  q_plus_in=q_minus_out+dqr_above  clamp_active(u8)  q_post=max(...,0)
```

The **shared** rung is `falk` (identical idiom). The **conservative-only** rungs are the ρΔz
`dq_in` metric conversion and the missing positivity clamp. A FAIL requires the first cross-tree
difference to fall on a conservative-only rung with proof-grade rung isolation — not an aggregate
`inflow`/`q_post` diff.

---

## 4. Signature-neutral, macro-local instrumentation (P0-3, P0-4, P1-7)

### 4a. No signature change (P0-3)
The proposed trailing `loop` arg is **rejected**: a default arg is source-level only; the mangled
symbol and the exact function-pointer type used by `sedimentation_chain` to select legacy vs
conservative would change, so the macro-OFF binary would differ from the committed one — breaking the
"production SHA unchanged" contract. Instead, carry the sub-cycle/case/pair context in a **macro-local
thread-local** set by RAII, so public/internal signatures are byte-identical when the macro is off:

```cpp
#ifdef KDM6_G33_OP_DUMP
struct G33DumpContext { int outer_loop_1based; const char* case_id;
                        const char* pair_id;  const char* algorithm; };
thread_local G33DumpContext* g_g33_context = nullptr;         // set/cleared by ScopedG33DumpContext (RAII)
#endif
```

Every `#ifdef KDM6_G33_OP_DUMP` block vanishes entirely from the preprocessor output when undefined.

### 4b. Shadow ladder — never re-associate the active expression (P0-4)
Splitting `falk`/`dq_in` into temporaries can change compiler evaluation / tensor dispatch (C++) or add
a REAL storage-rounding point (Fortran), i.e. **change the observed target**. The active expression
stays verbatim; the ladder is recomputed in **diagnostic-only** variables that never feed state:

```cpp
auto falk = /* ORIGINAL EXPRESSION, unchanged */;
#ifdef KDM6_G33_OP_DUMP
if (g_g33_context) { auto d1 = dend*q; auto d2 = d1*work1; /* … */ g33_dump(...); }  // NOT used in state
#endif
```

Fortran keeps the original assignment, then recomputes the same ladder into diagnostic-only variables.
Correctness that the shadow did not perturb state is proven by the 3-way gate (§7).

### 4c. Dedicated macro + env (P1-7)
Do **not** reuse `KDM6_SUBSTEP_DUMP` (it also drives coordinator/cold/melt-freeze forensic hooks and
their static counters/IO). Use an independent macro + env:

```
macro:  KDM6_G33_OP_DUMP
env:    KDM6_G33_DUMP_DIR   KDM6_G33_CASE_ID   KDM6_G33_PAIR_ID
```

---

## 5. Fortran via temporary build overlay — canonical SHA untouched (P0-10)

The private Fortran reference permits exactly the pinned edits; even a diagnostic `#ifdef` changes the
canonical file SHA and would pollute the Gate A source pin. So the Fortran dump is added on a
**temporary diagnostic copy**, never the canonical source:

```
canonical host phys/*.F       — UNCHANGED (SHA before == after)
diagnostic overlay copy       — #ifdef KDM6_G33_OP_DUMP dumps added
diagnostic build dir          — separate; builds the gateb driver against the diagnostic dylib
```

Equivalently, apply a patch to a throw-away source tree immediately before the diagnostic build. Final
checks: **canonical Fortran SHA before == after**, and `build_c4_evidence.py` **Gate A scope PASS**.

---

## 6. Dump format — one versioned, self-verifying container per (case, backend) (format §)

Loose per-`(loop,n)` binaries are replaced by a single container so the comparator can prove
completeness. **K orientation is fixed once** from the `outer_pre_sed.qr` anchor (top-first) and applied
to every record — never auto-optimized per file.

```
HEADER   magic="KDG33OP"  format_version  producer_commit  binary_sha256
         case_id  pair_id  backend(fortran|cpp)  algorithm(legacy|conservative)
         B  K  canonical_k_order  record_count_expected
RECORD*  outer_loop_1based  chain(main|ice)  n_1based  species  stage  field
         dtype  shape  payload_size  payload
FOOTER   record_count_actual  payload_sha256  COMPLETE
```

Write `.tmp → flush/close → verify → atomic rename`. The comparator is **fail-closed** and rejects:
missing/extra/duplicate record · stale case/pair id · producer-SHA mismatch · dtype/shape mismatch ·
absent COMPLETE footer · payload-size error · orientation ambiguity · unexpected NaN/Inf · degenerate
evidence (all-zero or K-uniform).

---

## 7. 3-way non-invasiveness gate — SHA alone is insufficient

Comparing only the production dylib SHA is not enough: instrumentation can change register allocation
or temporary materialization. For **each backend × each fixture** run three builds/configs:

```
A  macro undefined
B  macro defined, env unset
C  macro defined, env set + dump fires
```

and require **strict bitwise** `A_output == B_output == C_output` for:

```
{legacy Fortran, legacy C++, conservative Fortran, conservative C++} × {closure3-C3.3, species-iso}
```

Additionally, the macro-undefined rebuilt dylib SHA **must equal** the committed production binary SHA.
Any inequality → the instrumentation is invasive → fix before trusting any dump.

---

## 8. Verdict is tri-state — PASS / FAIL / INCONCLUSIVE

Never promote INCONCLUSIVE to PASS.

**PASS — inherited shared mechanism.** For EACH pair internally: `outer_pre_sed` inputs bitwise;
mstep/branch signature bitwise (Fortran==C++ *within the pair*); pre-op inputs bitwise; the first
cross-tree difference is the **same arithmetic rung of the shared `falk` op**; any conservative-only op
occurs strictly *after*; and the final rain-family divergence is causal-set-included from that seed.
BETWEEN variants: the first-divergence **operation class is identical** and the only difference is the
**intended state magnitude**.

**FAIL — conservative-specific mechanism.** The conservative pair's first cross-tree difference is at a
conservative-only rung: `dq_in` / ρΔz metric conversion / the no-clamp update / a conservative-only
branch.

**INCONCLUSIVE — widen instrumentation.** `outer_pre_sed` already differs · `work1`/`mstep` already
differ at substep entry · the first difference is at a stage not yet dumped · missing/duplicate records
or orientation ambiguity · the shadow ladder fails to reproduce the real stored `falk`.

### mstep/branch comparison scope (P0-6)
Legacy and conservative have intentionally different physical states, so `mstep` **may legitimately
differ between variants** — that is not a defect. Required equality is **within each pair only**
(Fortran mstep/branch == C++ mstep/branch for legacy; likewise for conservative). Between variants,
compare only whether the first-divergence **operation class** is the same shared mechanism. Do NOT
implement "all four runs' mstep equal" — it would false-FAIL a normal conservative trajectory.

---

## 9. Checker — additive, never overwrite the existing gate

Do not edit `gateb_g3_check.py` or any production/checker gate until G3.3-M PASSes AND owner
adjudication is recorded. Add a **new** `harness/gateb_g33m_check.py` emitting:

```json
{ "gate": "G3.3-M", "version": 1, "verdict": "PASS | FAIL | INCONCLUSIVE",
  "pairs": { "legacy": { "first_divergence": {} },
             "conservative": { "first_divergence": {} } },
  "noninvasiveness": {}, "completeness": {} }
```

The existing absolute-ULP result is retained as a historical diagnostic
(`G3.3-ULP: failed, superseded as unsuitable`; `G3.3-M: operative gate`). The formal gate replacement
is documented only after a PASS + owner sign-off.

---

## 10. Implementation order (owner-specified)

```
1.  docs(c4-g3.3): harden op-provenance protocol            ← THIS commit
2.  typed/versioned dump schema + synthetic parser tests
3.  dedicated macro + signature-neutral diagnostic context (RAII)
4.  outer_pre_sed / re-slope snapshots
5.  C++ legacy qr/nr shadow ladder                          ← first code instrumentation
6.  C++ conservative qr/nr shadow ladder
7.  A/B/C non-invasiveness
8.  temporary-overlay Fortran legacy instrumentation
9.  temporary-overlay Fortran conservative instrumentation
10. fresh process × four cases
11. fail-closed G3.3-M comparator
12. causal-propagation report
13. remove diagnostic code entirely
14. re-verify production SHA · Gate A · full C3
15. final C4 manifest
```

**First instrumentation is scoped to `qr/nr` + re-slope + outer boundary.** Widen to other species /
upstream processes ONLY if that yields INCONCLUSIVE.

---

## 11. Non-invasiveness guarantees (summary)

- All code inside `#ifdef KDM6_G33_OP_DUMP`; macro-off preprocessor output is byte-identical → the
  production dylib SHA is re-pinned equal to the committed one (§7).
- No public/internal signature change (§4a); no active-expression re-association (§4b); the shadow
  ladder never feeds state.
- Canonical Fortran reference untouched — diagnostic overlay only (§5); Gate A scope re-verified PASS.
- Verdict is fail-closed and tri-state (§8); the existing gate/checker is untouched until a PASS +
  owner adjudication (§9).

> Doc-status note: any pre-C4-S1 narrative (the earlier 3-commit / Gate-D-residual-pending report) is a
> **historical snapshot**, not current status. Current status lives in
> `FREEZE_LIFT_CONSERVATIVE_INTERFACE_V1.md` §Current-status and `docs/c4_evidence_manifest.json`.
