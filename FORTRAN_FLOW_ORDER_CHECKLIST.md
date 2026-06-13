# KDM6 Operation-ORDER Checklist (Fortran `module_mp_kdm6.F` ↔ C++ `kdm6_libtorch` ↔ Python `kdm6_torch`)

Audit of the PROCESS-EXECUTION ORDER + per-step STATE-DEPENDENCY (which snapshot each step reads — entry vs
post-melt vs post-freeze vs post-reclass — the axis that governs both forward sequencing and autodiff sensitivity).
`.F`-basis citations (the `.f90` drifts every build). Rebuilt 2026-06-05 for the CURRENT sequential code.

**FP-REGIME NOTE (2026-06-13, IEEE transition)**: the arithmetic contract underneath this ORDER audit changed —
both mp modules now compile with per-file `-ffp-contract=off` (durable rules in `phys/Makefile`, NOT configure.wrf)
and the ports are strict two-rounding (`ops::fma_acc` plain mul+add; addcmul/std::fmaf mirrors removed). Under this
regime "order-exact" means EVERY `+−×÷` rounds individually in `.F` source order: hand-CSE pre-grouping
(`common = rsloped*rslopemu`), division-for-reciprocal substitution, and `pow(x,3)`-for-`(x*x)*x` are ORDER bugs
even when each op is individually rounded (7 such latent deviations found+fixed by the 2026-06-13 sweep; bitwise
gate re-validated 205 vars × 6 frames). Future order audits must check the rounding ORDER axis, not just the
statement-sequence axis.

**Verdict (2026-06-05 FINAL): MACRO phase-order EXACT + the FOUR intra-phase deviations FIXED in code (O1-O4),
unit+parity+WRF green (inert in the warm validation case — safety proven, positive effect needs an active
cold/melt case). Codex-reviewed twice; 2 first-pass defects corrected (O2 was zeroing nr AFTER the cold phase
that reads it — prevp is a RATE so qr/nr not yet reduced — moved to BEFORE cold; O4 mask used the CAPPED pidep
`<=` which over-fires on all over-sublimation — switched to RAW `pidep_raw == −qi/dtcld` matching Fortran's
F:2343 near-dead exact-equality). O1/O3 confirmed correct by Codex.** The four sequential-mutation deviations below were
implemented in BOTH trees (C++ + Python oracle) — O1 D1 t-cooling threaded into pgmlt (cpm added to MeltingInputs/PreambleMf),
O2 complete-rain-evap nr zeroed before `scale_rates_for_conservation`, O3 D2-D4 freeze fed the pre-homog supcol
(`compute_supcol(working1.t)` override), O4 C5 psaut ni-gated by the C4 `ice_complete_sublim` mask. Validated: C++ ctest
15/15, Python 241, C++↔Python parity green, autograd intact (all fixes are differentiable mask/threading, no .item/detach).
Still REQUIRED before stamping FLOW_ORDER_EXACT: the WRF effect-gate (mp137 vs mp37, staging changes can regress in ways
unit tests miss — see the 806× precedent). Original (pre-fix) verdict retained below for the per-deviation analysis.

**Verdict (pre-fix): MACRO phase-order EXACT; FOUR confirmed residual INTRA-phase sequential-mutation deviations.** The Stage-A
re-architecture made `kdm62d_one_step` a SEQUENTIAL in-place chain that threads the working state through
melt → (homog freeze) → re-slope → freeze → re-slope → warm → cold → D5 → conservation → state-update → reclass → satadj,
and `kdm6_fn` runs sedimentation per-substep at the TOP of the sub-cycle. This fixed the macro inter-phase flow and
SUPERSEDES the 2026-05-31 audit (67 steps / 22 MISMATCH) — all 22 of those MACRO mismatches are resolved (melt/freeze
no longer deferred to a parallel state_update; sediment per-substep; homog freeze enabled; D2-D4 caps sequenced via
`qc_post_d2`; Python pcact present). **BUT two FINER-grained intra-phase sequential STATE-mutations remain in
parallel/deferred form (Codex order-audit 2026-06-05, both .F-adjudicated below) — so the flow is NOT bit-exact: do not
claim "FLOW_ORDER_EXACT" outright.** C++ and Python are order-identical to each other; both deviate from Fortran in the
same two intra-phase spots. All citations spot-adjudicated against the real `.F`.

## Per-sub-cycle execution order (the authoritative sequence)

Sub-cycle: Fortran `do loop=1,loops` (F:876 → `enddo` F:3017); ports loop in `runtime.cpp` `kdm6_fn` / `runtime.py`.
"reads" = the state snapshot the step consumes (the autodiff-critical column).

| # | Operation | Fortran `.F` | C++ (`coordinator.cpp` / `runtime.cpp`) | Python mirror | reads | ORDER |
|---|-----------|--------------|------------------------------------------|---------------|-------|-------|
| 0 | nccn entry-prologue clamp [1e8,2e10] (ONCE, before loop) | F:801 `nci(·,3)=min(max(·,1e8),2e10)` | runtime.cpp `clamp_nccn` (pre-loop) | runtime.py | — | ✅ |
| 1 | **SEDIMENT(dtcld)** at substep TOP, per-substep mstep | F:1119 `do n=1,mstepmax` (fall block) | runtime.cpp:319-356 (sediment at loop top) | runtime.py per-substep | current substep | ✅ |
| 2 | rebuild aux on post-fall state (re-slope) | F:1090/1095 ProgB+slope_kdm6 | runtime `rebuild_aux` post-fall | rebuild_aux_torch | post-fall | ✅ |
| 3 | preamble (entry thermo+slope diagnostics) | F:1274 `supcol=t0c-t` region | coordinator F1a `preamble(state_pre)` | preamble_torch | entry | ✅ |
| 4 | **D1 melt** (psmlt/pgmlt/pimlt) INLINE, xlf0 | F:1274-1345 | F1: `melt_freeze_d1` → `apply_melt_freeze_inline` → `working1` | melt_freeze_d1_torch | entry→working1 | ✅ |
| 5 | **homogeneous freeze** (supcol>40: qc→qi) INLINE | F:1410-1420 | F1pre: `apply_homogeneous_freeze_supercold(working1)` → `working1b` | apply_homogeneous_freeze_supercold_torch | working1 | ✅ (was DISABLED pre-re-arch) |
| 6 | rebuild aux (post-melt/homog re-slope) | F:1422-1480 | `rebuild_aux(working1b)` → pre1/aux1 | rebuild_aux_torch | working1b | ✅ |
| 7 | **D2-D4 freeze** (pinuc/pfrzdtc/pfrzdtr) INLINE, SEQUENTIAL caps, xls−xl(T) | F:1442-1511 | `melt_freeze_d2_d4` → `apply_melt_freeze_inline` → `working` | melt_freeze_d2_d4_torch | working1b→working | ✅ |
| 8 | rebuild aux (post-freeze re-slope: n0c/n0i/rslopec from frozen state) | F:1546-1683 | `rebuild_aux(working)` → pre2/aux2 | rebuild_aux_torch | working | ✅ |
| 9 | **warm phase** (B1-B5: praut/pracw/prevp…) | F:1643-1753 | F1b: `warm_phase(working, pre2/aux2)` | warm_phase_torch | working | ✅ |
| 10 | **cold phase** (C1-C6 + Hallett-Mossop + ice nuc/dep) | F:1768-2394 | F1c: `cold_phase(working, pre2/aux2)` | cold_phase_torch | working | ✅ |
| 11 | **D5 enhanced melting** (pseml/pgeml) | F:2270-2293 | F1d: `melt_freeze_d5(cold_out, working)` | melt_freeze_d5_torch | working+cold | ✅ |
| 12 | **conservation limiters** (budget source/factor rescaling, gate t≤t0c) | F:2449-2756 | F1d2: `scale_rates_for_conservation(working reservoirs)` | scale_rates_for_conservation_torch | working | ✅ |
| 13 | **state update** (apply all committed rates to working base) | F:2616/2738 `qci(1)=max(qci(1)±…)` | F1e: `state_update(working, pre_core entry-thermo)` | state_update_torch | working | ✅ |
| 14 | Picons reclass (qi→qs at avedia_i ≥ 200μm) | F:2807-2808 `qci(2)≥qmin & t<t0c & avedia(3)≥200e-6` | F1f: `reclassify_large_ice_to_snow` | reclassify…_torch | post-update | ✅ |
| 15 | rain→cloud reclass (avedia_r ≤ di82=82μm) | F:2883 `avedia(2)≤di82` | F1g: `reclassify_small_rain_to_cloud` | reclassify…_torch | post-Picons | ✅ |
| 16 | **pcact CCN activation + satadj** (ncact/pcact then conden/pcond; complete-evap NC→NCCN) | F:2905/2911 (pcact) → F:2927/2942 (conden/pcond) | F1g+: `apply_satadj_step` (post-reclass) | apply_satadj_step_torch (nccn threaded, Task #74) | post-reclass | ✅ (Python pcact was OMITTED pre-fix) |
| 17 | paired threshold cleanup | F: (tail clamps) | F1h: `apply_threshold_cleanup` | apply_threshold_cleanup_torch | — | ✅ |
| 18 | DSD number limiters (lamda snap + NRMAX/NCMAX) | F: (tail) | F1i: `apply_dsd_number_limiters` | apply_dsd_number_limiters_torch | — | ✅ |
| end | enddo big loops | F:3017 | for-loop end | for-loop end | — | ✅ |

## State-dependency (the autodiff axis)
The decisive property the old design broke and the re-arch fixed: steps 9-13 (warm/cold/D5/conservation/state-update)
read the **WORKING** state (= entry → D1-melt → homog-freeze → D2-D4-freeze applied IN PLACE), with the DSD diagnostics
(n0c/n0i/rslopec/avedia) rebuilt from that post-freeze state (steps 6, 8). So each downstream rate's gradient threads
through the melt/freeze deltas sequentially — NOT from a parallel entry snapshot. The freeze caps are sequential
(D3 `pfrzdtc` caps against the running qc AFTER D2 `pinuc` drew it; `apply_melt_freeze_inline` commits D1→D2-D4 in order).
Steps 14-16 (reclass → satadj) read the post-state-update / post-reclass state, matching Fortran's tail at F:2807-2942.
NOTE: state_update step 13 deliberately uses ENTRY-thermo `pre_core` (xl/cpm/supcol/rhox) — Fortran re-slopes geometry
post-melt/freeze but NOT qs/xl/rh (see project memory `project-kdm6-flow-order-audit` / `rebuild_aux must preserve
ENTRY-staged thermo`); this is a faithful match, not an ordering shortcut.

## Intra-phase order details (finer than the macro steps — completeness sweep)
The sub-cycle has **7 re-slope (`call slope_kdm6`) points** (F:1089, 1194, 1260, 1397, 1592, 2777, 2868); all are mapped:
- F:1089 / F:1194 — per-substep re-slope INSIDE the RSG (`do n=1,mstepmax` F:1119-1206) and ice (`mstepmax_i` F:1211-1270) sediment loops → ports' `sedimentation_chain` per-substep re-slope (step 1; the resolved #9 item).
- F:1260 — pre-melt re-slope → step 3 preamble (entry diagnostics fed to D1).
- F:1397 — post-melt/pre-D2-D4 re-slope → step 6 `rebuild_aux(working1b)`.
- F:1592 — post-D2-D4-freeze re-slope → step 8 `rebuild_aux(working)`.
- **F:2777 / F:2868 — TAIL re-slopes** before the reclass gates: the ports do NOT have a separate macro step; instead the reclass functions RE-DERIVE the slope INTERNALLY on the post-state-update state — `reclassify_large_ice_to_snow` (coordinator.cpp:1418, avedia_i recompute :1451) recomputes `avedia_i` from post-update qi/ni for the ≥200μm gate (F:2807), and `reclassify_small_rain_to_cloud` (coordinator.cpp:1474, avedia_r recompute :1505) recomputes `avedia_r` for the ≤di82 gate (F:2883). So steps 14-15 gate on FRESH post-update avedia, matching the Fortran tail re-slope. ✅

## Residual INTRA-phase order/state deviations — CONFIRMED (Codex order-audit 2026-06-05, .F-adjudicated)
The macro phase order (the 18 steps) is exact, but TWO finer sequential STATE-mutations are still done in parallel/deferred
form. Both are REAL forward+gradient deviations in their active cells (NOT measure-zero); both are C++/Python-consistent.

**(O1) D1 melt — `t` not cooled between snow-melt and graupel-melt (intra-D1 sequencing).** Fortran D1 applies psmlt then
**cools `t` IN PLACE** (F:1290 `t = t + xlf/cpm·psmlt`, psmlt<0) and computes pgmlt from that COOLED `t` (F:1292 `pgmlt =
xka(t)/xlf·(t0c−t)` — sequential), then cools `t` again, then pimlt. The ports compute psmlt/pgmlt/pimlt from the SAME entry
`t` (melt_freeze.cpp:65/87, parallel) and sum the t-update. So in any cell with BOTH snow and graupel melting, the port's
pgmlt magnitude (its `t0c−t` driver and `xka(t)`) is evaluated at the un-cooled entry `t` ⇒ forward + gradient differ.
- Fortran: F:1289-1296 (psmlt → cool t → pgmlt reads cooled t). Port: coordinator.cpp `apply_melt_freeze_inline` sums D1 t-update.
- Active: melting layers with snow AND graupel present. Inert where only one frozen species melts.

**(O2) complete-rain-evap nr-zeroing — moved AFTER the budgets instead of before.** Fortran, when rain fully evaporates in a
step (`prevp == −qrs(1)/dtcld`), moves `nrs→nci(3)` and zeroes `nrs` INLINE (F:1794-1796) BEFORE the conservation budgets,
so the rain-NUMBER budget reservoir `value=max(nrmin,nrs(1))` reads **0** (F:2587 and F:2719). The ports compute a
`rain_complete_evap` mask in warm phase (warm.cpp:281), scale the conservation budgets from the NON-zeroed `state.nr`
(rain-number budgets coordinator.cpp:973/1009), and apply the nr→nccn transfer only later in `state_update` (coordinator.cpp:1143; Python
documents the gap at coordinator.py:1172). So the rain-number budget reservoir/rescale differs in complete-rain-evap cells.
This is NOT a measure-zero fp-tie (correcting the prior framing) — it is a deterministic pre-budget mutation that Fortran's
rain-number budgets read; flagged in the rate audit as #3/#4 flow-order-deferred. Active: cells where rain fully evaporates
in one substep (common at cloud edges / sub-saturated layers).

**(O3) D2-D4 freeze `supcol` reads POST-homogeneous-freeze `t` instead of the pre-homog scalar.** Fortran sets the scalar
`supcol = t0c−t` ONCE at F:1403 (post-D1-melt, PRE-homog) and reuses it UNCHANGED for D2 (F:1485), D3 (F:1512) AND D4
(F:1542) — it is NOT recomputed after the homogeneous freeze warms `t` at F:1417. The ports `rebuild_aux(working1b)` AFTER
the homog freeze, so `pre.supcol` (consumed by melt_freeze_d2_d4, coordinator.cpp:721 / coordinator.py) reflects the
warmer post-homog `t` ⇒ a smaller supcol ⇒ D2-D4 freezing is suppressed in cells where homog fired. Active ONLY in
supcol>40 (T<−40°C) cells that also undergo D2-D4 freezing (deep cold) — localized but a real fidelity deviation.
- Fortran: F:1403 `supcol=t0c-t` (set once) → F:1417 homog warms t → F:1485/1512/1542 reuse the F:1403 supcol.
- Fix: feed D2-D4 the supcol from the PRE-homog state (the F:1403 snapshot), not the rebuilt post-homog one.

**(O4) complete-ice-sublimation `ni` zeroing — deferred past C5 aggregation.** Fortran, when ice fully sublimates
(`pidep == −qci(2)/dtcld`), zeroes `nci(2)` INLINE inside the C4 deposition block (F:2343-2344) BEFORE C5 ice→snow
aggregation (psaut), so C5's gate `nci(2)>0` (F:2396) reads **0** in fully-sublimated cells. The ports compute C5
aggregation from the post-freeze snapshot with non-zeroed `ni` (cold phase reads `working.ni`) and defer the ni→0 zeroing
to state_update (ni_zero_mask coordinator.cpp:1180 / coordinator.py:1192), so C5 can still produce snow aggregates from ice that
Fortran has already zeroed. Active in complete-ice-sublimation cells.
- Fortran: F:2343-2344 (`if pidep==-qci(2)/dtcld: nci(2)=0`) → F:2396 (C5 `nci(2)>0` reads zeroed ni).
- Fix: apply the complete-sublimation ni→0 to the working state before the C5 aggregation rate (both trees).

**Close-out options:** (O1) thread a running `t` through D1 so pgmlt/pimlt read the post-psmlt-cooled `t` (F:1290/1303→1313).
(O2) apply complete-rain-evap nr→nccn zeroing to the working state BEFORE `scale_rates_for_conservation`. (O3) feed D2-D4 the
pre-homog supcol (F:1403). (O4) apply complete-ice-sublimation ni→0 before C5 aggregation. All four are Fortran-fidelity
sequential-mutation fixes (mirror both trees + autograd guards) deferred to a focused session; the checklist now LISTS
them rather than hiding them under a "FLOW_ORDER_EXACT" verdict. Independently confirmed by the Codex order-audit
(4 defects, all .F-line-adjudicated verbatim); Codex's "CHECKED AND COVERED" set re-confirmed the macro order (sediment
per-substep, warm→cold→D5→conservation→state_update, reclass post-update, pcact/satadj last) and C++/Python agreement.

## C++ ↔ Python order parity
Identical phase-call order (coordinator.cpp F1pre-F1i ≡ coordinator.py kdm62d_one_step_torch); homogeneous freeze ENABLED
in both (working1b); per-substep sediment in both runtimes; pcact/ncact + complete-evap NC→NCCN present in both
`apply_satadj_step{,_torch}` (Python via the threaded `nccn` field, Task #74). The three C++/Python order
inconsistencies the 2026-05-31 audit flagged (Python pcact omitted, complete-evap NC→NCCN C++-only, homog-freeze unused)
are all closed.

## Supersedes
This replaces the 2026-05-31 entry-parallel-era audit (67 steps / 36 MATCH / 22 MISMATCH / 9 REVIEW). That audit's root
cause ("compute every phase from state_pre in parallel, apply once") was the design BEFORE the Stage-A sequential
re-architecture; its 22 mismatches are the change-list that re-arch implemented. Full prior analysis is in git history.
Related: `wiki/procedures/fortran-cpp-1to1-parity-tracking.md` (rate/formula 1:1 + coverage), project memory
`project-kdm6-flow-order-audit` (the re-arch record), `project-kdm6-warm-rain-autoconv-timing-gap` (residual = precision).
