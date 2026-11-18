# Native D1 graupel number-factor input tangents (2026-11-09)

This packet uses the saved `(203,149)` native column, 39 levels, 20-second f64 call and initial QG17/BRS17 relative directions from [#562](../native_d1_graupel_applied_cpp_ad_2026-11-08/README.md). A test-only live hook records the **actual D1 melt call inputs** `qg`, `rslope_g`, `n0go`, `t`, `qcrmin`, `t0c` and returned `gfac_melt` at native level 16. It retains the original C++ runner and all previous full-call stages. The value-only native D1 producer capture from [#553](../native_c2c_pre2_upstream_2026-11-07/README.md) anchors the baseline and joint `h=10^-3` endpoints.

## Executed calculation

The producer sets `warm=(t>t0c)`, `graupel_active=warm && (qg>0)`, then computes `gfac_raw=(rslope_g*n0go)/max(qg,qcrmin)` with **multiplication followed by division**. Its returned `gfac_melt` is `gfac_raw` only where `graupel_active && qg>qcrmin`, otherwise zero. The selected baseline and saved endpoints are checked to remain on the strictly active, unclamped branch before applying the interior derivative formula.

Across the 25 saved cases, the smallest `qg-qcrmin` margin is `5.397643e-5` in the QG numeric coordinate; the smallest `t-t0c` margin is separately `1.530319 K`. The call's QG and temperature are checked against the preexisting D1 consumer QG and entry temperature by raw bits for all 25 values and three JVP directions. These links prevent offsetting input-tangent edits or a changed, still-warm temperature from masquerading as the recorded call.

On the checked interior branch, the tangent is the sum of the slope, `n0go` and QG input terms:

`dg = (n0go/qg)*d(rslope_g) + (rslope_g/qg)*d(n0go) - (rslope_g*n0go/qg^2)*dqg`.

The replay checks this against the live C++ `gfac_melt` JVP in QG-only, BRS-only and joint directions, then connects it to #562's `-A*dg` contribution in `dNR2`. These are algebraic chain-rule terms for one shared graph, not independent process-off effects. Joint-equals-single JVP checks are internal AD consistency; independent high/low value calls and represented f64 input gaps provide separate directional-difference evidence.

At the selected baseline, `qg=5.4038067779247255e-5`, `rslope_g=0.00024344411705125857`, `n0go=4,000,000`, and `gfac_melt=18,020,194.063619033`. The joint initial relative direction gives `dqg=4.515172243280481e-5`, `d(rslope_g)=5.085425713705934e-5`, and measured `d(n0go)=0`. The slope term contributes `+3,764,328.3135`; the QG divisor term contributes `-15,056,844.8130`; their sum matches the C++ `dgfac_melt=-11,292,516.4995` at roundoff. This feeds the earlier `-A*dg=-138.0604253` contribution to `dNR2`.

## Provenance and limits

The isolated test build preserves the private source and input, with a new live-stage hook only. The public packet pins the executed coordinator, C++ runner, build flags, input, archive and executable hashes and raw result. It verifies that all **234** #562 baseline stages, **226** old JVPs per direction, four VJP rows and 24 final-state endpoints remain unchanged. For the three cases with a separate native producer capture, the six inputs and returned factor are compared by raw f64 word and dtype (**21 words**). All **25** selected baseline and finite-difference cases reproduce the source-order factor and its handoff to the D1 consumer by raw bits. Other new stage endpoints are isolated C++ value evaluations without a second native-host capture. The public CI replays the saved evidence and does not rebuild the private archive.

The replay separates previously captured density-cap crossings from local derivative acceptance, checks signal size against output ULPs, and records the weaker branch evidence for extra small-step pairs without independent cap captures. The result remains conditional on this native column, selected layer and f64 branch. It does not establish slope or `n0go` upstream derivatives in general, the capped melt-amount production formula, operational f32 behavior, physical number units/budgets, full host AD or GK2A–RTTOV cost sensitivity. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.

Run `python -m unittest discover -s harness/evidence/native_d1_gfac_upstream_cpp_ad_2026-11-09 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`.
