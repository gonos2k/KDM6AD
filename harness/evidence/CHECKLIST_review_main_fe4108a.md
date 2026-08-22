# Cycle checklist: the re-review of `main@fe4108a` (PR #156)

Ten items from the review's §15, plus the regression the review did not know
about because CI cannot see it.

## 0. A regression I shipped, found by running the suite

PR #156 had the driver emit `G33R FIXTURE` and I called it additive because a
stream without the record still parses. It was not: a check in
`validate_member_stream` had been WAITING for that record and was dormant only
because no producer emitted one. The driver emits `FIXTURE_ID`
(`boundary_mapping_v1`) and callers pass the module name
(`g33_fixture_boundary_mapping_v1`), so the first comparison refused every
stream -- **47 local test failures**, none visible to CI because the Fortran leg
is local-only.

`canonical_id()` resolves either spelling through the registry, and
`unpinned_reachable()` caught the second half: importing the registry inside the
producer widened what the producer can reach, and a module reachable but pinned
by nothing means a bundle's provenance does not cover the code that decided its
contents.

The lesson is mine and not the tool's. I ran the factorial and analyzer tests
before pushing, not the suite, and "additive" was an argument rather than a
measurement.

## The four immediate corrections

| # | item | status |
|---|---|---|
| 1 | `ncmin_exposure()` applied the scalar rule to Arm L (§4 P0) | **closed** -- algorithm-aware; `lncmin` reports `per_column`, nothing overridden |
| 2 | representativeness bound was `max(B)`, not the four-arm sum (§9) | **closed** -- and reported beside the flag |
| 3 | the window denominator is not an inventory (§10) | **closed** -- renamed `sum_call_start`, with `window_initial`/`window_final` beside it. Measured: 9.427e+09 against a window-initial 4.269e+08, a factor of 22 |
| 4 | exact dry-density relation (§8) | **closed, and the flagged term was the small one** -- see below |

On item 4: exact-vs-approximate differ by a median 9.5e-07 on the real state,
while BOTH differ from the model's own `mu_d`/`d(eta)` by a median 2.3e-03 and
up to 31 %. The canonical route is the default now. None of it moves the
published figure: 1.9169 % canonical, 1.9420 % exact, 1.9422 % approx.

## The science

| # | item | status |
|---|---|---|
| 5 | actual-XFER dual-basis verification (§6) | **closed** -- dry residuals agree with the recovered ones to better than 0.1 %, so the moisture term is an independent measurement. And the moist row is corrected: the recovered 1e-17 is algebraically forced; the honest figure is 5.8e-08, still below f32 epsilon |
| 6 | Arm N_d | **blocked on freeze-lift.** `REQUEST_freeze_lift_arm_nd.md` filed, no grant recorded |
| 7 | flux-weighted and transport-active LC05 statistics (§7) | **closed** -- the published population was 42 % of the transport-active one, and neither correction moves the answer: 1.92 % / 2.02 % / 1.98 % flux-weighted |
| 8 | `B = 1` real-column replay (§13) | **closed** -- `FINDING_real_column_replay_v1.md` |
| 9 | actual MPI one-step Arm L | **not run.** It needs `wrf.exe` rebuilt with the `lncmin` kernel, which is a deployment-shaped act on the operational binary and is the owner's to authorise |
| 10 | trajectory `q/N`, `D_m`, reflectivity, precipitation | **not run** |

## The result item 8 produced

Running the kernel on a real column of the operational case, Arm N leaves
**1.88 %** of the legacy dry defect. The coefficient analysis over the whole
LC05 domain predicted 1.92 % median and 1.98 % flux-weighted -- a closed-form
estimate from a state file and a kernel run on a column of it agree to within a
tenth of a percentage point.

Two hard-coded schema values had to be widened for it, and both forbade the
experiment rather than protecting anything at `B = 1`. That is now the third
time in this campaign a fixed value in the fixture format was the thing standing
between a question and its answer: the column anchor for the moisture gradient,
and `science_role` and the anchor's constancy rule for the real column.
