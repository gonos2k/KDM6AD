# Freeze-lift authorization — conservative-interface-v1

**Status**: AUTHORIZED (owner, 2026-07-17) · **Branch**: `physics/conservative-interface-v1`
**Checkpoint**: C1/C1b/C2 landed via PR #22 (`main@d8057ab`); C2a/C2a.1/C3 certified via PR #23 (`main@eb3aeb3`, evidence below). Still an EXPERIMENTAL checkpoint — no tag, release, or host promotion before C4–C5.
**Decision basis**: P0-4b attribution + P0-4b.1/b.2 corrected decision package
([`P0-4b_sedimentation_attribution.md`](P0-4b_sedimentation_attribution.md),
[`P0-4b1_interface_sink_prevalence.md`](P0-4b1_interface_sink_prevalence.md); PRs #14–#17).

This is the first scoped lift of the frozen-code discipline since
`abi-v2-hardened@a53503e`. It authorizes exactly one physics change — the
sedimentation **interface transfer** — as a **new, separately selectable
variant**. The legacy path stays byte-identical everywhere and forever.

## What the variant fixes

Legacy NISLFV-PLM re-caps the stored raw interface flux by the source cell's
POST-update reservoir (`dqs(i,k+1) = min(falk·Δz(k+1)/Δz(k)·dtcld/dend, qrs(k+1))`
with `qrs(k+1)` post-update — verbatim in reference Fortran), deleting mass at
internal interfaces whenever the per-substep fall ratio exceeds ½. The
conservative variant hands the lower cell the mass **actually removed** from
the source cell (entry-capped outflow, per-species ρΔz-converted), and the
surface diagnostic reports the actual bottom outflow. Per-column closure
`Wⁿ⁺¹ − Wⁿ + P_actual = O(ε)` becomes an enforced gate. The oracle
counterfactual (`oracle/kdm6/sed_conservative.py`) is the numerical reference.

## Scope — INCLUDED

- Pass the source cell's actual capped removed mass to the cell below
- Inter-layer mass conversion via ρΔz (per species)
- Bottom diagnostic = actual bottom outflow
- Species: `qr`, `qs`, `qg`, `qi`
- Consistent movement of the paired `nr`, `ni`, `brs/bg` bookkeeping
- Corrected Fortran variant (new scheme module)
- Corrected C++/LibTorch variant
- Append-only ABI variant-selection plumbing (below)
- New WRF/KIM scheme identifier, recorded in outputs and manifests

## Scope — EXPLICITLY EXCLUDED

- Any change to legacy mp37/mp137 equations
- Raw ice-velocity handoff (the qi-dominant *pathway* stays as-is — changing
  it here would make conservation-fix and fall-speed effects inseparable)
- `mstep` selection rule
- DSD, fall-speed, or saturation-adjustment changes
- warm/cold/melt/freeze process changes
- P0-4c energy work

## ABI selection contract (append-only, v2)

```c
typedef enum {
    KDM6_PHYSICS_LEGACY = 0,
    KDM6_PHYSICS_CONSERVATIVE_INTERFACE = 1
} kdm6_physics_variant;

/* appended at the end of kdm6_step_v2_args */
uint32_t physics_variant;
```

- Callers with the smaller existing `struct_size` → automatically legacy
- `physics_variant = 0` → legacy; `= 1` → conservative interface variant
- Any other value → `KDM6_ERR_INVALID_ARG` (fail-loud)
- v1 `kdm6_step_c` → permanently legacy
- Exactly 9 exported symbols, ABI major and SOVERSION 2 unchanged

## Acceptance gates

### Legacy invariance (all mandatory)

- v1 results byte-identical
- Existing v2 struct-size callers byte-identical
- New v2 with `physics_variant = 0` byte-identical
- Existing mp37↔mp137 12 h × MPI parity preserved
- 9-symbol export surface preserved
- `abi-v2-hardened@a53503e` tag permanently immovable

### Conservative variant

Per-column `Wⁿ⁺¹ − Wⁿ + P_actual = O(ε)` across:

- single-layer capped/uncapped · variable ρ/Δz · multiple interfaces
- multi-`mstep` · multi-KDM-subcycle · qr/qs/qg/qi isolation
- number/rime (`nr`/`ni`/`brs`) bookkeeping consistency · nonnegativity
- corrected Fortran ↔ corrected C++ parity · 12 h × np4
- surface precipitation closure · smooth-regime VJP/JVP parity

The variant gets its own scheme ID, release evidence, parity report, and tag;
no legacy tag or result is overwritten.

### Science gates before production / default-DA promotion

- LC05 1 h/3 h precipitation impact · independent precipitation validation
- hydrometeor vertical profiles · replay of actual accepted analysis states
- all-sky BT and observation-cost comparison
- conservative oracle ↔ C++ fp64 derivative smooth-regime parity

## C3 certification evidence (final — PASS)

C2a/C2a.1/C3 landed via PR #23 (`main@eb3aeb3`; commits `820c321` C2a
overloads + fail-loud variant validation, `45a1c19` C2a.1 dt<=0-before-variant
validation fix, `af1b90e` C3 libtorch gates, `bb8ce68` oracle cross-check
parity, `4573676` NaN/finiteness parity hardening). Measured on the reference
toolchains (macOS arm64 clang + Ubuntu 24.04 gcc CI):

- **C3.1** non-uniform-metric interface identity (direct substeps, fp64 and
  f32-input): PASS — per-species mass measure ρΔz, number measure Δz-only;
  the rho-only "wrong alternative" demonstrably fails.
- **C3.2** per-column `mstep` gating / closure / batch independence: PASS —
  gated columns exactly unchanged; batch == single-column bitwise;
  permutation-invariant.
- **C3.3** dt=300 multi-subcycle closure `W_out − W_in + P = O(ε)`: PASS —
  kappa64 max 0.30 (gate 8), public v2 f32 kappa32 max 0.336 (gate 8).
  The cap-inactive column's legacy-vs-conservative difference measured
  exactly zero and is pinned BITWISE on both paths (internal fp64:
  `torch::equal` on all 12 state fields + exact rain/snow/graupel
  increments; public v2 f32: `memcmp` of all 12 output buffers + increments
  on a single-column tile). This pin is a measured per-toolchain,
  per-fixture property — not a variant-wide analytical identity claim.
- **C3.4** oracle↔C++ parity
  (`oracle/tests/test_cpp_conservative_interface_parity.py`): PASS —
  direct-substep fp64 BITWISE 330/330 (per-element contract
  `|py − cpp| ≤ 1e-12 + 1e-10·|py|`), controlled f32 BITWISE (max f32
  ULP = 0; the gate is ULP == 0 — any future nonzero ULP must be
  root-caused and allowlisted per toolchain under review); full-step fp64
  worst rel 8.0e-16 (FS64_CAP) / 4.6e-7 (FS64_MULTI, known op-order drift,
  gate 1e-5) across 12 state fields + rain/snow/graupel increments.
- **C3.5** AD gates: PASS — fp64 adjoint identity rel 5.9e-16; repeated
  JVP→JVP→VJP on one handle identical; 3-point central-FD sweep floor
  7.9e-6 (gate 1e-4); public v2 f32 graph gate (finite, nonzero VJP);
  `kdm6_step_ad_c` pinned EXACTLY to Legacy physics (== internal Legacy
  fp64, != Conservative).
- **C3.6** legacy invariance through the pre-PR22 old-signature caller
  fixture: PASS (bitwise vs the options-overload Legacy path).

**Wording note**: in this line of work, "bitwise" refers only to (i) the
direct-substep oracle parity as measured (fp64 330/330, f32 ULP 0) and
(ii) the cap-inactive legacy==conservative pins above. Full-step oracle↔C++
fp64 parity is NOT bitwise (cross-tree op-order drift, gated at 1e-5), and
cap-active columns differ from legacy BY DESIGN.

**CI at PR #23 merge**: Linux port-ci (build + ctest 17/17 + oracle↔C++
parity) and oracle-ci GREEN; the macOS arm64 job was still in flight at
merge time (auto-cancelled by the merge — the authoritative macOS
validation is the main-push run).

**HOLD (unchanged)**: C5 (12 h × MPI certification), P0-4c, and any tag /
release / default-DA / host promotion remain HOLD until their gates are green.

## C4 — corrected Fortran reference variant (branch `physics/conservative-interface-v1-c4`, base `main@48d8c32`)

Scheme IDs (host Registry, collision-scanned): **237** corrected Fortran
reference (`module_mp_kdm6_cons.F`) / **337** C++ conservative v2 wrapper
(`module_mp_kdm6ad_cons.F` → `kdm6_step_v2_c`, `physics_variant=1`,
`value_only=1`, dual first-call layout gate, rc-fatal). Registry packages
use state arrays byte-identical to 37/137; `kdm6_iso_c.F` gained the
**append-only** v2 mirror (proven: zero deleted lines vs the legacy
reference). Legacy mp37/mp137 and the raw ice-velocity handoff are
permanently untouched.

- **Gate A (source scope): PASS.** `harness/check_cons_fortran_scope.py`
  proves `module_mp_kdm6_cons.F` == legacy + whole-word renames + EXACTLY
  the four pinned edits in `harness/cons_fortran_scope_manifest.json`
  (header comment, REAL(4) metric temporaries, sed main chain, sed ice
  chain); both raw ice-velocity handoff blocks byte-identical in both
  modules; legacy sha256 pins match. Evidence:
  [`c4_evidence_manifest.json`](c4_evidence_manifest.json) (public/host
  SHAs, libkdm6_c binary sha256, toolchain, fixture hashes, embedded
  Gate A/B/D logs; `artifacts/` is gitignored so the docs copy is the
  committed one). Contract tests:
  `harness/tests/test_check_cons_fortran_scope.py` (6/6).
- **Gate B (independent column parity driver)** — G1/G2/G3 substitution
  **owner-APPROVED (2026-07-17 adjudication), standalone Gate B only; it
  does NOT relax Gate D or C5 strict-bitwise**. Private host
  `test/kdm6_cons_gateb/` runs identical fixture arrays through the
  corrected Fortran and C++ v2 (variant=1), reusing the C3 closure
  columns + single-layer / species-isolation / mstep-mix regimes, PLUS a
  **legacy-pair control** (mp37 `kdm6` vs variant=0) on the same fixtures.
  Rationale: at 3 KDM sub-cycles the LEGACY pair itself drifts
  Fortran↔C++ on cap-active columns (pre-existing shared sub-cycle
  machinery drift, never exercised by the single-subcycle host, mirrored
  by C3.4 `FS64_MULTI`), so multi-subcycle raw-bit does not isolate
  variant regressions and both sides of the drift are frozen.
  - **G1 (single KDM subcycle, dtcld ≤ DTCLDCR = 120 s): PASS** — 12
    states + mass/number/rime bookkeeping + the three surface increments
    f32 RAW-BIT identical on all fixtures, for BOTH the conservative and
    legacy-control pairs.
  - **G2 (multi-subcycle physical invariants, dt=300): PASS** — per-column
    `W_out − W_in + P_actual = O(ε32)` with measured kappa32 ≤ 0.26 on
    both conservative paths; all hydrometeors/numbers/rime nonnegative;
    `rain_increment` = actual total bottom outflow with snow/graupel
    increments as its defined subsets; no NaN/Inf. (The legacy control
    FAILS closure on cap-active columns — the documented interface
    defect, re-confirmed against real legacy Fortran for the first time.)
  - **G3 (no-new-divergence, `harness/gateb_g3_check.py` on the driver's
    machine-readable diff listing): G3.1 differing-FIELD subset PASS,
    G3.2 differing-CELL-mask subset PASS, G3.4 no non-finite PASS;
    G3.3 ULP-envelope EXCEEDED pre-fix** — cons max ULP 77,852 vs legacy
    envelope 77,312 (closure3, +0.7%) and 2,188 vs 1,164 (species-iso),
    concentrated in the rain family (qr/nr/qv/rain_increment/th).
    Whether this is chaotic same-mechanism amplification or the same
    root cause as the Gate D residual is exactly what the approved
    diagnostic bisection determines; **G3.3 is re-measured after the
    variant-only fix** before Gate B claims the owner's final wording:
    "PASS — single-subcycle raw-bit parity; multi-subcycle closure and
    no-new-divergence certified. Standalone dt=300 raw-bit parity is not
    claimed."
- **Gate C (host compile/registration)**: em_real clean build with both
  new schemes wired (Registry packages select; `kdm6init_cons` dispatch;
  `-ffp-contract=off` explicit rules on both new objects;
  `apply_kdm6ad_config.sh` rerun idempotent — it also now carries
  `-Wno-error=incompatible-pointer-types` for `external/RSL_LITE` under
  Xcode clang 16+, a diagnostic-severity-only flag). 9-symbol export +
  SOVERSION 2 unchanged (installed dylib sha pinned in the manifest).
- **Gate D (SS host short campaign) — measured 2026-07-17**, via
  `harness/run_ss_case.py` (`--mp 37|137|237|337`, `--seconds`, `--np`) +
  `harness/strict_bitwise_nc.py` on the fresh clean build:
  - **legacy 37↔137: FULL PASS** — 1 step and 10 steps np1, every frame,
    all 254 variables STRICT BITWISE (this also re-validates the pending
    INSTALL-BASELINE item: the hardened SOVERSION-2 dylib now backs the
    parity).
  - **cons 237↔337: NOT yet bitwise** — frame 0 bitwise (253/253 numeric);
    post-step frames diverge in QCLOUD/QICE/QSNOW/QVAPOR/REFL_10CM only,
    ~40 cells of 2.57M per field at **1–4 ULP**, all in supercooled
    (235–273 K) **graupel-marginal** cells (median qg≈2.6e-9) at k=15–23.
    Dump-bisection (per-substep + rate dumps, via the guarded
    `harness/compare_rate_dump.py`): divergence is born between the
    `postfreeze` and `poststateupdate` stages; all 12 state fields at
    entry/postmelt/postfreeze are BITWISE, and every rate with an
    ESTABLISHED cross-tree field correspondence is BITWISE (graupel 8;
    warm/number 8 of fort's 10; ncrates' first 13 — the trees' dump
    lists differ beyond that, `--min-fields` opt-in, and the trailing
    dbg_*/aux captures are capture-point artifacts, not rates). The seed
    is an un-dumped qc→qi-family mass rate.
    Prime suspect class: the §35 `rhox` retain-shadow / §20 brs-underflow
    engineering, whose C++ mask was calibrated against LEGACY's
    `max(...,0.)` f32-underflow behavior that the conservative no-clamp
    update changes in graupel-empty cells. **Next bisection rung requires
    paired mass-rate/rhox dumps, i.e. temporary instrumentation of the
    frozen libtorch source → owner freeze-lift decision** (adjudication
    item #2, alongside the Gate-B dt=300 substitution).
  - 1-step np4 smoke: decomposition behaves identically to np1 (same
    residual class; frame 0 bitwise).
  - **No 12 h campaign in C4** (that is C5).

## P0-4c status

HOLD until BOTH: (1) conservative Fortran ↔ C++ forward parity, and
(2) conservative column-water closure green from single-column through
12 h × MPI. Actual analysis-state replay and all-sky BT/obs-cost remain the
production-promotion gates, not implementation preconditions.
