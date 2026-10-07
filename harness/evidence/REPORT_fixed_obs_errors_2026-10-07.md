# Fixed channel error and observation-bias plumbing — internal first attempt

The explicit `fixed_obs_errors=True` option now passes caller-fixed sigma and
`ColumnObs.bias` consistently through full-domain selection, the frozen cost
closure, clear chunks and all-sky workers. Both opt-in branches reuse
`compute_obs_loss`: `r=(BT_model-(BT_observed+bias))/sigma`, bias added to the
observation. Existing 1 K/zero-bias calls retain their original loss path and
worker payload. No microphysics, ABI, optical/BT formula or physical threshold
was changed.

The user has no additional calibration/error-statistics data: this is the first
attempt. The new inputs are fixed research assumptions, **not estimated R/bias**.
The source label is required; calibrated/physical/observation approval stays false.

## Contract and reporting

- Supported upper route: normalized dry-number, KMA v3.0, AMI 8–16 in that order,
  Huber delta 1, native-grid fixtures, fixed background optical density, no pseudo-RH.
- Sigma: scalar or nine ordered finite channel scales [K], at least the existing
  lower loss denominator floor (1e-12). Values below it are rejected, not silently
  converted. No full covariance or state-dependent trial weighting is introduced.
- Bias: existing full-field ColumnObs correction follows the same column/thermal
  selection and caps as observations. It is copied for the inner objective.
- Frozen weights and correction are in the objective signature. Caller mutations
  after construction cannot change that objective.
- Original `omb/oma` remain raw K mean-absolute innovations. Separate corrected
  and standardized fields use the frozen bias/sigma; NPZ saves the exact correction,
  weights and corrected target. The raw threshold-based regime proxy is unchanged.
- The generic normalized OSSE `ShardSpec` remains its earlier diagnostic path;
  this change extends the actual full-domain clear/all-sky cost/worker path only.

## Executed verification

The [source](FIXED_obs_errors_source_2026-10-07.py),
[receipt](FIXED_obs_errors_result_2026-10-07.json) and
[raw bundle](FIXED_obs_errors_receipts_2026-10-07.zip) identify the actual retained
C5 20-second KDM→RTTOV→cost/VJP calculation. Geometry is modeled, pixel time/product
compatibility unresolved, and the original 7-channel support remains fixed.
The nonuniform vector and nonzero biases were declared before execution solely
for engineering verification; they were not fitted to the residual.

| Policy | Base cost | Initial-QV VJP | Endpoint cost FD | Relative difference |
| --- | ---: | ---: | ---: | ---: |
| Existing 1 K / zero bias | 19.96343179787636 | -7.547582111015558 | -7.547582128815122 | 2.3583e-9 |
| Fixed synthetic sigma/bias | 10.20315994312423 | -4.825293811010819 | -4.825293822667831 | 2.4158e-9 |

The unchanged FD criterion is 1e-5; direction is 0.01 times initial QV and h=1e-4.
Each BASE/plus/minus set retained its own frozen signature and seven-value support.
The signatures differ between the two objectives, as required. This does not
measure every upstream branch or every endpoint quality flag. Cost values across
these different objectives are not a forecast-improvement comparison.

Software verification: 89 focused tests passed / 2 private-asset skips, including
22 new loss/routing/snapshot/report tests. The public-only suite returned
1,644 passed / 93 skipped; skip details remain in the log (including unbuilt C++
assets in this authoring worktree). Counts overlap. One early real run was rejected
because source changed during execution; its failed log is retained. The final
run verified matching start/end hashes and alone supplies the reported results.

## Checklist disposition

[Internal research checklist](CHECKLIST_internal_research_2026-10-07.md): A1/A3
can close for this integration and selected numerical direction. This does not
close physical calibration, B/prior/control choices, true pixel correspondence,
full water/enthalpy budgets, different native grids or independent weather.
The [retained-data inventory](INTERNAL_research_case_inventory_2026-10-07.md)
shows why R2 is still awaiting actual lineage/time/geometry evidence. No external
model/reanalysis input or replacement observation product was acquired.
