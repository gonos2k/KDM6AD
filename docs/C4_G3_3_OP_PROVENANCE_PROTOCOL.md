# C4 Gate B G3.3-M — op-level first-divergence instrumentation protocol (proof-grade)

**Branch**: `analysis/c4-g3.3-op-provenance` · diagnostic-only, compile-time OFF, **no production change**.
**Review status**: two owner adversarial reviews incorporated (2026-07-19). Confirmation-bias defenses
(d186f00) approved; this revision closes the remaining arithmetic-model, record-completeness, and
provenance-independence gaps. **Approved to start now**: typed/versioned schema + reference parser +
independent expectation generator + synthetic corruption tests + RAII context skeleton. **After this
doc is in**: the C++/Fortran numerical-path instrumentation. **Never** before a PASS + owner
adjudication: any production physics / existing checker change.

**Purpose**: close Gate B G3.3 by *mechanism provenance* — replacing the withdrawn absolute-ULP and
fixture-wide-relative envelopes (see [`C4_G3_3_FIRST_DIVERGENCE.md`](C4_G3_3_FIRST_DIVERGENCE.md)).

---

## 0. Method — find first, classify second

Do **not** pre-assume the first cross-tree divergence is at `falk`. The C++ chain re-runs
`preamble → ProgB → slope` after each main substep, regenerating `work1_qr`/`workn_qr`; `falk` *inputs*
can already differ from an earlier re-slope. The comparator LOCATES the first divergence over the full
recorded space (canonical total order, §7), THEN classifies it as *shared* or *conservative-only*. If
it predates sedimentation (`outer_pre_sed`, `work1`/`mstep` already differ) → **INCONCLUSIVE**, never
FAIL; widen upstream.

---

## 1. Snapshots (whole B×K, every value)

```
outer_pre_sed        qr nr qv th   rho delz
  substep_pre_n      qr nr  work1_qr workn_qr  mstep(native) mstepmax gate  rho delz
    <per-k op ladders — §3>
  substep_post_n     qr nr qs qg brs
  reslope_input_n / reslope_output_n     work1_qr workn_qr + regenerated fall-speed inputs
outer_post_sed       qr nr qv th
outer_post_micro     qr nr qv th
```
`qv`/`th` are absent from `SubstepAdvectionState`, so they are captured only at the outer boundary;
`outer_pre_sed.{qv,th} == outer_post_sed.{qv,th}` is a checked sed-invariant (violation = instrumentation bug).

---

## 2. Typed, native-precision dump — never pre-round

A dedicated typed writer records each value at NATIVE width — the existing `.to(kFloat32)` helper is
NOT reused (it destroys f64 last-bit differences that round to the same f32 → false "input bitwise").

```
real32 → uint32   real64 → uint64   int32 → int32   logical → uint8
```

**mstep is an integer-VALUED float tensor** (clamped, then used as divisor + gate), NOT an int type.
Storing only `int32(2)` hides `2.0` vs `2.0000002`. Record:
```
mstep_native_dtype  mstep_native_bits(u32/u64)  mstep_decoded_i32  mstep_exact_integer(u8)  gate(u8)
```
`mstepmax` is NOT dumped (owner adjudication): it is `max_b(mstep_b)`, so the comparator
derives it offline from the `mstep_native` bits (`g33_dump.derive_mstepmax`). Dumping it
would have required naming `int /*mstepmax*/`, an unnamed production parameter — a
production edit for a value that is not independent of evidence already recorded, and a
producer reporting both an operand and a summary OF that operand attests to its own
arithmetic. For the same reason, every producer-emitted verdict here (`mstep_decoded_i32`,
`mstep_exact_integer`, `gate_exact_01`, `active_mask`, `*_floor_active`) is a DEBUGGING
AID: acceptance authority is `g33_derived.py`, which recomputes each from the raw bits and
cross-checks the producer's version — a disagreement means the producer's arithmetic is
not what its evidence claims, and the run is invalid before any cross-tree comparison.
Acceptance: recomputed `exact_integer==true`, recomputed `decoded_i32` in range,
`mstep_native_bits` equal *within each backend* (a repeated-read self-consistency
check), NOT across trees. C++ mstep_native is f64 and Fortran mstep_native is i32
(different dtypes, different bit widths): the CROSS-tree comparison is on the
DECODED semantic fields (`mstep_decoded_i32` and the gate law `n <= mstep`), never
on the raw native bits. Comparing f64 bits against i32 bits would be a category
error dressed as strict-bitwise.

---

### Units contract (owner meteorological review §1.1) — pinned from the host source

Raw-bit parity needs no units; any CONSERVATION claim does. These are cited from
the host source, not asserted from memory:

| variable | meaning | units | column measure |
|---|---|---|---|
| `qr` | rain-water mixing ratio | kg kg⁻¹ | ρ Δz qr |
| `nr` | rain number **MIXING RATIO** — host `Registry.EM_COMMON:122`: `qnr_gc … "rain num concentration" "# kg-1"` | # kg⁻¹ | **ρ Δz nr** |
| `fallsum` / `bottom_fall_*` | bottom-cell fall-rate density | kg m⁻³ s⁻¹ | — |
| `surface_mul1` | `fallsum·Δz(kts)/denr` | m s⁻¹ liquid-equivalent | — |
| `rain_increment` (rainncv) | `fallsum·Δz(kts)/denr·dtcld·1000.` (`module_mp_kdm6_cons.F:1504`) | mm per step | — |

Consequence, stated so it cannot be blurred later: `nr` is a mixing ratio, so
the physically complete column-number measure is **ρ Δz nr**. The conservative
number rung transports ΔN with the Δz ratio ONLY — faithful to the corrected
Fortran reference, which is exactly what G3.3-M compares — and therefore
"Fortran-faithful" and "physically conserving column number" are DIFFERENT
claims. G3.3-M makes only the first. Any conservation statement must use the
ρΔz measure and belongs to the oracle water/number-budget diagnostics, never to
this gate. The same separation bounds the verdict itself: a G3.3-M PASS
establishes that the observed Fortran↔C++ difference did not ORIGINATE in
conservative-only arithmetic but in a mechanism common to both variants — it
says nothing about which variant is meteorologically more correct; that
question is answered afterwards with column water, precipitation, hydrometeor
profiles and BT/obs-cost, not here.

## 3. Exact per-rung op ladders — pinned to the code (raw/safe, top vs interior, mass vs number)

The "ρΔz conversion" is a concept; the gate records the **operational expression**. Verified against
`sedimentation.cpp` / `sedimentation_conservative.cpp` at HEAD. `dend_safe=clamp(dend,qcrmin)`,
`delz_safe=clamp(delz,qcrmin)`; record `dend_raw dend_safe dend_floor_active delz_raw delz_safe delz_floor_active`.
Every record carries `cell_role ∈ {TOP, INTERIOR, BOTTOM}`; the comparator rejects a record whose op
template does not match its `cell_role`.

**Shared rung (all templates): `falk`** — but note the NUMBER falk omits the `dend` factor.
```
QR_FALK  falk_qr = (dend_raw · q · work1_qr / mstep_safe · gate) → f32     [mass]
NR_FALK  falk_nr = (        nr · workn_qr / mstep_safe · gate) → f32       [number — NO dend]
```

**Op templates (four mass + four number families):**

`conservative_mass_top` / `conservative_mass_interior` (`sedimentation_conservative.cpp:72-88`)
```
QR_OUTFLOW  dq_out = min(falk_qr · dtcld / dend_safe, q)                     cap_active(u8)  source_reservoir=q
QR_INFLOW   (INTERIOR only) dq_in = prev_out · (dend_safe_src · delz_RAW_src) / (dend_safe_dst · delz_SAFE_dst)
            src_metric = dend_safe[k-1]·delz_raw[k-1]   dst_metric = dend_safe[k]·delz_safe[k]
QR_UPDATE   TOP: q_post = q − dq_out          INTERIOR: q_post = q − dq_out + dq_in     (NO clamp)
```
`conservative_number_*` (`:93-103`)
```
NR_OUTFLOW  dn_out = min(falk_nr · dtcld, nr)                    [NO /dend]
NR_INFLOW   (INTERIOR) dn_in = prev_out_nr · delz_RAW_src / delz_SAFE_dst      [Δz only, NO density]
NR_UPDATE   TOP: nr − dn_out    INTERIOR: nr − dn_out + dn_in     (NO clamp)
```
`legacy_mass_top` (`sedimentation.cpp:106`) — **no dqr_k, no inflow; direct clamp**
```
QR_UPDATE   q_post = max(q − falk_qr · dtcld / dend_safe, 0)
```
`legacy_mass_interior` (`:135-164`)
```
QR_OUTFLOW  dqr_k    = min(falk_qr · dtcld / dend_safe, q)                    cap_active(u8)
QR_INFLOW   dqr_above = min(stored_falk_prev · delz_RAW_src / delz_SAFE_dst · dtcld / dend_safe_dst, q[k-1])
            inflow_cap_active(u8)  source_reservoir=q[k-1]
QR_UPDATE   q_post = max(q − dqr_k + dqr_above, 0)     clamp_active(u8)
```
`legacy_number_*` — number uses `fma_acc(nr, falk_nr, dtcld, −1) → clamp(…,0)` at top
(`:109-111`), and the `min(falk_nr·dtcld, nr)` / `min(falk_nr_prev·Δz-ratio·dtcld, nr[k-1])` interior
form (`:136/:151-152`); recorded as its own template.

Each `*_INFLOW`/`*_UPDATE` stores the intermediate rungs (`prev_out`/`stored_falk_prev`,
`src_metric`, `dst_metric`, `inflow_numerator`, `inflow_pre_cap`, `inflow_cap_active`, `inflow_final`,
`q_before`, `q_minus_out`, `q_plus_in_preclamp`, `clamp_active`, `q_post`).

---

## 4. Fall accumulator + surface-diagnostic ladder (P1-12)

The final G3.3 diff includes `rain_increment`; the state-update ladder alone can't trace it. Legacy
adds the raw stored `falk` to the accumulator; conservative adds the actual capped-outflow rate. Record:
```
fall_before  fall_increment  fall_after
bottom_fall  delz_bottom  surface_mul1  surface_mul_dt  rain_increment  snow_increment  graupel_increment
```
so `qr seed → rain_increment` is shown as an actual op path, not mere cell-set inclusion.

---

## 5. Signature-neutral, macro-local, shadow-only instrumentation

- **No signature change** — the trailing `loop` arg is rejected (would change the mangled symbol + the
  function-pointer type `sedimentation_chain` dispatches on). Context is a macro-local `thread_local
  G33DumpContext {outer_loop_1based, case_id, pair_id, algorithm}` set by RAII (`ScopedG33DumpContext`).
- **Shadow ladder** — the active expression stays verbatim; the ladder is recomputed into
  diagnostic-only variables that never feed state (C++ compiler re-association / Fortran REAL temporary
  rounding would otherwise change the observed target).
- **Dedicated macro/env** — `KDM6_G33_OP_DUMP` at compile time; independent of the shared
  `KDM6_SUBSTEP_DUMP` (which also drives coordinator/cold/melt-freeze hooks). The run
  environment is ALL-OR-NOTHING: none of the variables set means diagnostics are off, any
  subset means the run is misconfigured and the producer says so. A half-configured run —
  `DUMP_DIR` and `CASE_ID` exported, `PAIR_ID` forgotten — otherwise produces no evidence
  and still exits 0, which is indistinguishable from "diagnostics off".

  Do not export these by hand; `harness/g33_run_env.py` derives all of them from one
  schedule and seals what they point at, so the declaration the producer checks itself
  against and the expectation the comparator uses afterwards cannot drift apart:

  | variable | meaning |
  |---|---|
  | `KDM6_G33_DUMP_DIR` | where containers are written |
  | `KDM6_G33_CASE_ID`, `KDM6_G33_PAIR_ID` | case/pair identity, echoed into every header |
  | `KDM6_G33_RUN_UUID` | ties all containers to one run |
  | `KDM6_G33_PRODUCER_COMMIT` | resolved from git HEAD |
  | `KDM6_G33_BINARY_SHA256` | digest of the dylib the run loads, hashed from the file |
  | `KDM6_G33_COLUMN_LAYOUT_ID`, `KDM6_G33_COLUMN_MAP` | declared Fortran(i,j)↔C++ flat-B map (§7c) |
  | `KDM6_G33_OP_SEQ_MAP` | each container's declared op_seq window (§7, P0-2) |
  | `KDM6_G33_SCHEMA_DIR` | sealed per-container expected record streams |
  | `KDM6_G33_SCHEMA_SHA256` | their digests, delivered by a channel an edit of the files does not reach |

  The last pair is why the descriptor check is not a self-attestation: a producer that
  hashes the file it just read and reports the result agrees with itself no matter what
  that file contains.

  The binary digest is bound the same way (P0-5): `dladdr` on a symbol with internal
  linkage in the instrumented TU asks the dynamic linker which artifact it actually
  mapped that code from — a measurement, where the sealed digest is a claim about a file
  on disk. The overlay hashes the resolved artifact, refuses on mismatch, and records
  `resolved_binary_path`/`resolved_binary_sha256` in every header; the reader
  independently requires the resolved digest to equal the sealed one, so a writer that
  never resolved anything cannot fabricate agreement. Scope stated honestly: the file at
  the resolved path is hashed at first dump use, so a swap after load is outside this
  check — the A/B/C runs (§10) execute freshly built artifacts where that window is not
  live.
- **C++ via overlay too (P0-8)** — instrument `sedimentation*.cpp` on a **temporary diagnostic source
  overlay**, not the canonical tree, so the public production source is byte-unchanged and A vs B/C
  separate cleanly (mirrors the Fortran overlay, §6).

### 5a. Shadow-fidelity gate (P1-10)
The shadow ladder is only trusted if, at every active cell:
```
shadow_falk_stored_f32 bits == actual falk_stored_f32 bits
```
AND an independent Python/scalar evaluator, from the raw recorded inputs, reproduces the actual output
exactly: `actual == shadow == offline`. Any mismatch → that rung is unusable → **INCONCLUSIVE**.

---

### Static verification is a tripwire, not evidence

Nine consecutive review rounds bypassed source-text certification of runtime properties
(slicing spellings, rank-changing calls, dtype relabels, unknown operands, allowed-name
collisions, multi-argument `.to()`, comments parsed as syntax — each fix opened the next
hole one layer down). The static checks' load-bearing role is therefore limited to what
source text CAN establish: (1) the canonical base SHA pin, (2) macro-OFF textual identity,
(3) macro-ON in-order superset plus the mutation tripwire. Tensor runtime shape, runtime
dtype, arithmetic equivalence, and non-mutation through aliases are NOT certifiable from
source text and must never be cited from it. That authority lives at runtime: the sealed
per-container expected-descriptor stream (§7) that `rec()` consumes record-by-record with
the tensor in hand, the producer-side shape guard, and the comparator recomputation of
every derived flag (`g33_derived.py`). Non-invasiveness is established only by the 3-way
A/B/C run (§10).

### Fixture policy: density/metric floors are not a normal branch (owner review §6)

The general NaN/UNORDERED policy is right for dead-branch microphysics
intermediates, but rho and delz are not intermediates: in a real column both are
finite and strictly positive, so `dend_floor_active`/`delz_floor_active` MUST be
zero. A fixture is therefore one of two kinds, declared, not inferred:

    real_atmosphere:        all rho,delz finite and > 0; floor counts == 0;
                            NaN/Inf in rho/delz => INVALID RUN (not INCONCLUSIVE);
                            a density/metric floor as the first divergence is an
                            invalid input/mapping, not a rounding finding.
    synthetic_floor_stress: floor activation allowed; results are a branch-
                            coverage stress test and are NOT used for the
                            representative G3.3-M science verdict.

The self-check fixture below is real_atmosphere (floors inactive by construction).

### §5a executed: shadow == actual == offline (self-check)

`selfcheck_build.sh` links the overlay TUs into a standalone driver (their
objects replace the canonical archive members, so dladdr resolves the artifact
that actually contains the instrumented code) and `g33_selfcheck.py` runs one
FRESH PROCESS per algorithm on a deterministic branch-covering fixture
(mstep {1,2,2} gates a column off at n=2; a 20x work1 column makes the entry
cap bind; floors inactive per the real-atmosphere policy). Verified from the
EVIDENCE alone — never the driver's fixture, so a driver bug cannot vacuously
agree with itself: exact sealed container set; per-record shadow_falk_f32 ==
falk_f32; a NumPy recomputation from the dumped operands reproducing every
FALK rung bit-for-bit (72 rungs per algorithm); and the producer cross-checks
(gate law, mstep range, floor semantics) on real data. The standing mutation kill is ENFORCED by
`selfcheck_gate.sh` (a committed gate, not a transcript loop): it rebuilds the
shadow mutant from the committed overlay every run — a fake mutant cannot be
handed in — and requires real=PASS and mutant=FAIL *for the right reason* (a
fidelity mismatch, never a SKIP, crash or configuration error). The mutant dies
exactly at the first rung where the gate matters (n=2, the mstep=1 column,
falk_precast). Measured green for legacy AND conservative.

## 6. Canonical Fortran + C++ via temporary build overlay (P0-8, P0-10)

The private Fortran reference permits only its pinned edits; a diagnostic `#ifdef` still changes the
canonical file SHA and would pollute the Gate A source pin. So BOTH the Fortran dumps AND the C++ sed
dumps live on **temporary diagnostic overlays** (throw-away source copies patched immediately before the
diagnostic build), never the canonical/public tree. Final checks: canonical Fortran + C++ source SHA
**before == after**, and `build_c4_evidence.py` Gate A scope **PASS**.

---

### Build-level gate: compile smoke + macro-off object equivalence

`harness/g33_overlay/compile_smoke.sh` (flags parsed from the real kdm6_c
flags.make, so it cannot drift from what ships): every overlay TU must compile
with the macro ON, and with the macro OFF its object must equal the canonical
object byte-for-byte — directly, or via the line-shift proof (the g33 blocks
occupy source lines even when compiled out, and TORCH_CHECK materializes
`__LINE__` as an integer immediate; compiling the canonical text in the
overlay's blank-line layout isolates that one difference). Measured:
sedimentation is directly object-identical; runtime and coordinator differ
ONLY by `__LINE__`. This is a build-level gate — run-level non-invasiveness is
still §10's A/B/C alone.

## 7. Dump container + INDEPENDENT expectation + attestation

### 7a. Container (versioned, self-verifying) — one per (case, backend)
```
HEADER  magic="KDG33OP" format_version producer_commit binary_sha256 case_id pair_id
        backend algorithm B K column_layout_id record_count_expected(informational)
        column_index_map[B]{B_index, fortran_i, fortran_j, cpp_flat_index}
        fortran_k_index cpp_k_index canonical_k_index
        run_uuid process_id owner_thread_id
RECORD* seq_no outer_loop chain n cell_role species op_id stage field dtype shape payload_size payload
FOOTER  record_count_actual payload_sha256 COMPLETE
```
Write `.tmp → flush/close → verify → atomic rename`.

### 7b. Independent expectation manifest (P0-5) — completeness is NOT writer self-reported
A **separate** generator derives, from the fixture + the known substep/re-slope schedule, the exact
expected record-key set `(case,pair,backend,outer_loop,chain,n,cell_role,species,op_id,field,dtype,shape,op_seq_id)`.
The comparator requires `observed_keys == independently_expected_keys`; the header's
`record_count_expected` is informational only. The generator MUST encode the conditional schedule
(C++ main re-slope after every main substep, **ice re-slope only when `n < mstepmax_ice`**).

### 7c. Column & K identity (P0-6) — declared, then anchor-verified
`B` must mean the same physical column in Fortran and C++. The `column_index_map` DECLARES the
Fortran `(i,j)` ↔ C++ flat-B correspondence from the source contracts (not inferred from "better-fitting"
data); K orientation likewise DECLARED top-first from the source contracts. A nondegenerate anchor
(`outer_pre_sed.qr`) then VERIFIES the declaration. If the data is too uniform to verify → **INCONCLUSIVE**.

### 7d. External attestation (P0-7) — provenance not self-reported
The harness independently computes, before the run, a `run_attestation.json`:
```
public_source_commit  diagnostic_patch_sha256  canonical_fortran_base_sha256  fortran_overlay_sha256
cpp_overlay_sha256  diagnostic_dylib_sha256  gateb_exe_sha256  fixture_sha256  env_config_sha256
```
The comparator reads a container ONLY if its header values agree with `run_attestation.json`. The
running binary is never asked to self-attest.

### 7e. Writer crash/stale/concurrency contract (P1-13)
Header carries `run_uuid, process_id, owner_thread_id`; records carry monotone `seq_no`. The writer
fails (never overwrites) if the final file exists; fails on a pre-existing `.tmp` (stale); fails if two
writers in one process open the same `(case,backend)`; fails on a regressed/duplicate `seq_no`; and
writes the `COMPLETE` footer ONLY via an explicit `finalize()` — never from `atexit`/destructor (which
may not run on STOP/exception/abort).

### 7f. Fail-closed comparator rejects
missing/extra/duplicate key vs the independent manifest · stale case/pair/run id · attestation mismatch
· dtype/shape mismatch · absent COMPLETE footer · payload-size/`payload_sha256` mismatch · orientation
unverifiable · NaN/Inf in an active+finite-required cell (§8c) · degenerate container (no active target
cell, or qr & nr K-uniform, or all falk & q_post zero).

---

## 8. Verdict — tri-state, evidence-graded

### 8a. Canonical total order (P2-14)
`outer_loop → chain(main before ice) → n → phase(outer_pre, substep_pre, falk_inputs, falk_rungs,
outflow, inflow, update, substep_post, reslope_input, reslope_output, outer_post_sed, outer_post_micro)
→ species → cell_role → canonical_k → canonical_column → field`. Each record carries a canonical
`op_seq_id`; the same LOGICAL op gets the same id even where C++ and Fortran source order differ.

### 8b. PASS / FAIL / INCONCLUSIVE (P1-9)
**PASS (inherited shared mechanism).** *Within each pair*: `outer_pre_sed` + pre-op inputs bitwise;
mstep/branch signature bitwise (Fortran==C++ *within the pair*); the first cross-tree difference is the
**same shared expression family at the same local rounding law/rung**; every conservative-only op is
strictly *after* that pair's first divergence; shadow-fidelity holds (§5a); and the final rain-family
divergence (incl. `rain_increment`, §4) is causal-set-included from the seed. *Between variants*: the
first-divergence **op_id/class is identical** and the variant state difference is **traceable to the
already-approved conservative interface-transfer trajectory** (not merely "magnitude only").

**FAIL (conservative-specific mechanism).** The conservative pair's first cross-tree difference is at a
conservative-only rung: `dq_in` / the ρΔz `src_metric`·`dst_metric` conversion / the no-clamp update /
a conservative-only branch.

**INCONCLUSIVE.** Divergence predates sedimentation · `work1`/`mstep` differ at substep entry · first
difference at an undumped stage · missing/duplicate records or unverifiable orientation · shadow-fidelity
fails.

### 8c. Active-mask-aware NaN/degeneracy (P1-11)
KDM6 evaluates raw divide/sqrt in dead branches then masks. Each record carries `active_mask, gate_mask,
cap_active, finite_required_mask`. NaN/Inf in an active + finite-required cell → FAIL; in an
inactive/dead branch → recorded but excluded from the verdict. Degeneracy is judged container-wide
(§7f), not per-record (a gate-all-1, cap-all-0, or inactive-species-all-0 record is legitimate).

---

## 9. Checker — additive, evidence-graded (P2-15)

New `harness/gateb_g33m_check.py` (the existing ULP gate is UNTOUCHED until a PASS + adjudication):
```json
{ "gate":"G3.3-M", "version":1, "verdict":"PASS|FAIL|INCONCLUSIVE",
  "evidence_strength":"STRONG|PARTIAL",
  "first_divergence":{"outer_loop":0,"chain":"main","n":0,"op_id":"","species":"","column":0,"k":0},
  "shadow_fidelity":true, "preop_inputs_bitwise":true,
  "branch_signature_equal_within_pair":true, "conservative_only_op_precedes_seed":false,
  "causal_propagation":{"qr":true,"nr":true,"qv":"not-yet-traced","th":"not-yet-traced","rain_increment":true},
  "noninvasiveness":{}, "completeness":{} }
```
If `qv`/`th` are confirmed only by the coarse outer snapshot, mark `evidence_strength: PARTIAL` and the
respective `causal_propagation` entries `not-yet-traced`; the first-divergence gate may PASS while
propagation coverage remains separate.

---

## 10. Non-invasiveness — 3-way, section-aware (P0-8)

For each backend × fixture, three configs: **A** macro undefined, **B** defined/env-unset, **C**
defined/dumping. Require strict-bitwise `A==B==C` outputs across `{legacy F, legacy C++, cons F, cons
C++} × {closure3-C3.3, species-iso}`. For the dylib: try full-SHA equality vs the committed production
dylib first; a mismatch is NOT immediately a physics failure (an `#ifdef` line-shift can move Mach-O
UUID / debug metadata) — fall back to comparing exported symbols, install-name, `.text`/`.rodata`
section hashes, disassembled production functions, and the C-ABI + C++ symbol sets, plus A/B/C outputs.
Because C++ is instrumented on an overlay (§6), the canonical build is unchanged and the full-SHA gate
is expected to hold; the environment it depends on (compiler/linker version, build path, CMake cache
hash, Torch build hash, deployment target, timestamp policy) is pinned in the attestation.

---

## 11. Implementation order (owner-revised, 20 steps)

```
1  protocol exact-ladder amendment                     ← THIS commit
2  canonical schema specification
3  Python-only container parser/writer reference
4  independent expectation-manifest generator
5  corrupt/missing/duplicate/stale/orientation synthetic tests
6  C++ internal diagnostic writer + RAII context (overlay)
7  C++ legacy qr/nr shadow ladder
8  shadow-fidelity self-check
9  C++ conservative qr/nr ladder
10 A/B/C non-invasiveness
11 Fortran temporary-overlay legacy
12 Fortran temporary-overlay conservative
13 four fresh-process cases
14 G3.3-M comparison
15 conditional expansion to qv/th/surface path
16 diagnostic code removal from production branch
17 preserve immutable diagnostic commit/patch hashes
18 production SHA · symbols · Gate A · full C3 re-verify
19 owner adjudication
20 final C4 manifest
```

**Cleared to start now**: steps 2–5 (typed/versioned schema, reference parser, independent expectation
generator, synthetic corruption tests) + the step-6 RAII skeleton — all pure harness, no frozen-code
touch. **After this doc lands**: steps 7+ (the actual sed op-ladder instrumentation on overlays). First
instrumentation scope is `qr/nr` + re-slope + outer boundary; widen to other species / upstream only on
INCONCLUSIVE.

> Doc-status note: any pre-C4-S1 narrative (the earlier 3-commit / Gate-D-residual-pending report) is a
> historical snapshot, not current status — which lives in
> `FREEZE_LIFT_CONSERVATIVE_INTERFACE_V1.md` §Current-status and `docs/c4_evidence_manifest.json`.
