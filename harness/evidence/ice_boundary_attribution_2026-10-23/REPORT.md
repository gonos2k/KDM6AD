# Native ice boundary follow-up — 2026-10-23

Base: `0b42e83c3283a67e77fa391f0a8a15b3b5998dda` (#434 merge on
`feat/mp137-applied-finish-ad`, separate from main).

## Results

1. **Portable reduction fixed.** Diagnostic ledger v2 uses fixed binary64
   products and `math.fsum` for every species/total aggregate. Exact-rational
   and saved-case tests replace dependence on BLAS summation order. Historical
   #432/#434 artifacts remain unchanged; the additive migration JSON records
   each altered aggregate in ULPs. The same-call total balance remains identical.
2. **Actual first-ice handoff captured.** Runtime-normalized velocity inputs,
   main-to-ice raw handoff, `mstep_i=1`, and all 39 applied ice updates are now
   recorded inside the executed C++ legacy path. No physical expression was
   replaced. All trace indices are top-first.
3. **QI loss attributed.** Internal source departures exceed receiver arrivals
   at five capped interfaces. Their summed defect exactly accounts for the
   QI sedimentation loss with zero bottom export. The separate smaller
   microphysics residual from #434 is not assigned to this mechanism.
4. **Value/AD noninterference passed.** Control, instrumented-off and
   instrumented-on kernel values and selected JVP/VJP are bit-identical. The
   same holds through the existing cleanup/applied finish, whose values match
   #433 exactly. This does not add a full-host or new FD certificate.

## Native call and measured quantities

Same request as #434: SHA-256
`4867805f5318f1ad28b05101ffc583d50000309ed80b81c4379fb9c9e77082e2`,
one native column `(156,21)`, 39 mass levels, dt=20 s, XLAND=2,
ncmin_land=ncmin_sea=10, Legacy variant 0, volume-coordinate kernel operands.
No external model/reanalysis, WRF integration or RTTOV call was used.

| Quantity | Value |
| --- | ---: |
| Ice substep count | 1 |
| Maximum initial `vt_i/DELZ`, s-1 | 0.0004357655468327452 |
| Maximum raw handoff `vt_i`, m/s | 0.30616369170890134 |
| QI sedimentation change, kg/m2 | -0.0012979597722250025 |
| QI summed internal interface defect, kg/m2 | 0.0012979597722250025 |
| QI bottom export, kg/m2 | 0 |
| QI identity residual, kg/m2 | 0 |
| NI kernel-coordinate change, #/m2 | -620092374.2268972 |
| NI internal interface defect, #/m2 | 620092374.2268972 |

The five capped interfaces (native one-based, upper→lower) are 26→25,
25→24, 24→23, 23→22 and 22→21. The corresponding water defects are
`4.918148303300733e-10`, `7.486148257946275e-4`,
`4.523234964308445e-4`, `8.162498599015731e-5` and
`1.5395972194542773e-5 kg/m2`. Tiny signed differences at other interfaces
are numerical summation-scale terms, retained in the raw data.

The trace confirms the raw handoff and post-update-reservoir cap together in
this executed legacy call. It does not quantify isolated counterfactual effects
of changing only one of them. The water budget is still physically unclosed;
this PR fixes its diagnostic replay and explains the dominant measured loss.

Unit caveat: raw `vt_i` has speed units, so expressions consuming it as a
normalized rate are not dimensionally consistent. Traced attempted transfers
and stored-falk field suffixes describe consumer/code coordinates, not certified
physical flux units. The table's departure/arrival gaps use actual applied
changes in nominal state QI units weighted by DEN×DELZ. Stored-bottom export is
a code-equivalent diagnostic; it is not certified as a physical flux by this
trace. Actual and reported bottom values happen to be zero in this case.

## Evidence and scope

- `applied_change_ledger_v2.json`, `same_call_deterministic_reduction_v2.json`
  and `reduction_ulp_changes.json`: additive fixed-arithmetic replays of the
  original #431/#434 arrays, not new model or observation experiments.
- `../ice_boundary_trace_2026-10-23/`: executed internal trace, strict source-
  equation replay, copied-source/build provenance and byte-level controls.
- `native39_ad_noninterference.json` and `ad_products/*.npz`: three fresh-
  process graph-recording comparisons with fixed mixed direction/cotangents.
  Kernel products: 468 values, 468 JVP values, 468 state and 156 forcing VJP.
  Applied-finish products: 195 values, 195 JVP values, 468 state and 156 forcing
  VJP. Seeds and raw products are public; all three modes use identical seeds.
- `forensic_c_build_manifest.json`: same original C ABI object/export list and
  Torch libraries linked against the private instrumented archive. No install.
- `actual_file_build_receipt.json`: a separate read of the actual local source
  snapshots, generated overlays, object members, archive and linked library.
  It verifies that only two of 14 object members changed (archive symbol-index
  metadata is separate), all other objects match, and generated source hashes
  equal the executed-source snapshots. Public analysis regenerates source pins;
  this receipt records the private build-file checks. Neither is a formal proof
  of compiler correctness.

The final extended AD comparison uses three forward/graph recordings. An
earlier private kernel-only comparison also used three recordings before
adding the explicit applied-finish checks; its outputs are not mixed into
the published comparison. The CLI trace and its off control are distinct
value-only calls. No old whole-domain DA process was resumed.

NI is interpreted as a volume-coordinate KDM operand only; the legacy host
payload basis remains unknown/not migrated. The accepted two-step tendency
carry, research number boundary and local KDM–RTTOV AD milestones remain
complete in their declared scopes. Physical conservation, new forecast skill,
pixel-time collocation, the earlier raw-NCCN stress/whole-pressure limitations,
and full host/RK adjoints are not certified here.

## Local validation

- Full Harness: **2,642 passed, 59 skipped, 309 deselected**.
- Focused ledger, trace/parser and public product replay: **64 passed**.
- Existing native finish/prep tests plus AD noninterference tests:
  **39 passed** (overlaps the focused product tests above).
- Undefined-name lint and `git diff --check`: passed.
- Final focused replay with the CI versions (Python 3.12, NumPy 2.4.6,
  pytest 9.1.1, netCDF4 1.7.4): **64 passed**.
- Green checked numerical/source consistency; Red checked counterexamples,
  source/request binding, top/bottom distinctions and unit/attribution limits.

The initial Linux CI run exposed two test-only assumptions: Python 3.12's
builtin float `sum` no longer supplied the naive-addition witness, and a hash
test tried to read the historical producer's absolute workspace path. The
witness now spells out sequential additions; public replay resolves the
source via its pinned repository-relative path. Exact Fraction/fsum and hash
assertions remain unchanged. No measured array, physical operator or tolerance
was altered for these corrections.

No operational C++/Fortran source or ABI was modified. The actual private
instrumented compile/run and derivative comparison are separately attributed;
ordinary public Harness CI replays their artifacts and validates the helpers.
