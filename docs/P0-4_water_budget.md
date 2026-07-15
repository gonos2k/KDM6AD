# P0-4 — column water budget (ρΔz), semantics and verified bounds

Oracle-side diagnostic (`oracle/kdm6/water_budget.py`) that measures the ρΔz-weighted
column total-water budget of one KDM6 step and closes it by operator decomposition.
No frozen code (dylib/ABI/physics) is touched; the default `kdm6_step` path is
byte-identical (verified by `test_budget_diagnostics_do_not_change_forward_outputs`).

## Definition

Column total water, per column `b`:

    W(x;f) = Σ_k ρ_k · Δz_k · (q_v + q_c + q_r + q_i + q_s + q_g)_k        [kg/m²]

ρΔz is the correct discrete weight in this code (`forcing.rho·forcing.delz`;
coord space `den·delz`). **Not** `forcing.dend` — `_build_coord_forcing` sets
`dend = rho` (air density alone), despite a mis-labeled comment. Number
concentrations (`nc,nr,ni,nccn`) and the graupel-volume proxy `bg`/`brs` are **not**
water and are excluded (`qg` already carries graupel mass).

## Operator-decomposition ledger (self-consistency, not a conservation proof)

Each sub-cycle the driver applies sedimentation then one microphysics pass. The
budget records both:

    W_out − W_in  =  ΔW_sed + ΔW_micro                       (exact, admissible inputs)

with `sed_column_loss = −ΔW_sed` (the **operator-implied net column-water loss**) and

    decomposition_residual = W_out − W_in + sed_column_loss − ΔW_micro  ≈ 0.

**This closing to zero is a ledger self-consistency check** — that no hook or
sub-cycle was missed — **not** an independent physical-conservation proof (the same
pre/post states are measured in each segment and summed, so the identity holds by
construction). For admissible (all-q ≥ 0) inputs the entry nonneg-clamp is a no-op,
so it closes to machine zero: `decomposition_residual = 0.00e+00` (heavy rain,
dt=120) and `max = 0.00e+00` over a 3-sub-cycle dt=300 case. The two *independent*
scientific results are findings 1 and 3 below.

## Verified findings

**1. Microphysics conserves column water to fp64 roundoff.** Across all processes
(activation, autoconversion, accretion, satadj/condensation, reclassification, and
threshold cleanup), `ΔW_micro ≈ 0`:

    max|ΔW_micro| = 7.11e-15 kg/m²   (dt=300, 3 sub-cycles, W ~ 40 kg/m²)

Regression bound (scale-aware, justified by the measurement, never widened to pass):

    |ΔW_micro_b| ≤ 1e-9 + 1e-11·(|W_in| + |W_out|)

**2. Threshold cleanup is a negligible sink at the single-step level.** The cleanup
mass removed — measured at the exact `apply_threshold_cleanup` boundary, per
sub-cycle, ρΔz-weighted per species — is `~0` here (`cleanup_total = 0.00e+00` in
the sampled columns), and it accounts for exactly the (tiny) micro non-conservation:
`ΔW_micro ≈ −cleanup_total`. This refines the deep-review premise
(`kdm6ad-deep-review-2026-07-15`): cleanup *is* a to-nowhere sink (it zeroes
sub-threshold hydrometeor mass + paired number, leaving `qv`/T — no vapor return, no
latent correction), but at single-step scale it is roundoff-small, not a meaningful
bias. Its long-integration accumulation over a full domain remains worth watching.

**3. `sed_column_loss` and the WRF `rain_increment` diagnostic disagree.** The
operator-implied net column-water loss (`sed_column_loss = −ΔW_sed`) differs from the
reported `rain_increment` (WRF RAINNCV convention, the *total* fallout
`fall_qr+fall_qs+fall_qg+fall_qi`) by a non-constant amount:

| case (heavy rain, dt=120) | sed_column_loss (−ΔW_sed) | rain_increment | gap = diag − loss |
|---|---:|---:|---:|
| col0 | 6.8014 | 2.0001 | −4.8012 |
| col1 | 9.0335 | 3.0153 | −6.0181 |

The ratio is not constant, so it is not a unit scale. **Which side is at fault is
unresolved** — candidates: the RAINNCV accumulator under-reporting the bottom-boundary
flux; a clamp/cap or metric loss in the sedimentation state update; a semantic
mismatch between the `fall` accumulator and the state mass measure; or uncapped
bottom-layer flux vs. capped depletion. `sed_column_loss` is the operator-implied
column loss; `rain_increment` is the WRF-facing total-fallout diagnostic; their
measured discrepancy is a finding, not yet an attribution. Characterizing
or reconciling this gap (P0-4b) requires reading the sedimentation substep flux vs.
the bottom-layer accumulation formula — deferred; exposed here rather than hidden by
redefining the surface term.

## Scope (this PR)

Water only. Moist-energy closure is deferred to a follow-up: KDM6 mixes
temperature-dependent `L_v`/`L_s` and per-branch melt/freeze constants, so a single
moist-enthalpy state function cannot be assumed to reproduce every branch heating.

## API

    from kdm6.water_budget import kdm6_step_with_water_budget, column_water_kg_m2
    out_state, budget = kdm6_step_with_water_budget(state, forcing, dt=120.0)
    #  budget: ColumnWaterBudget — every field per-column (B,), detached:
    #    water_in/out, sed_column_loss, micro_dW, surface_precip_diag,
    #    cleanup_by_species/cleanup_total, decomposition_residual,
    #    sed_surface_diag_gap, n_subcycles

All acceptance is per-column `(B,)`; a domain sum could hide opposite-sign column
errors and is never used as a gate.
