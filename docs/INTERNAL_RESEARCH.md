# Internal first-attempt research path

Use the [checklist](../harness/evidence/CHECKLIST_internal_research_2026-10-07.md)
to separate code integration, physical/data decisions and experiments. No
installation/release/licensing work is a research completion condition here.
The first attempt has no additional calibration/error-statistics data.

## Fixed observation-error assumptions

The existing normalized KMA route still defaults to diagnostic 1 K, zero bias,
Huber delta 1, fixed background optical density and native-center preservation.
Opt in explicitly to caller-fixed channel scales and observation corrections:

```python
# channels are exactly AMI 8..16, in that order; sigma is Kelvin.
# These sample values demonstrate input shape, not a calibrated error model.
sigma = torch.tensor([1., 1., 1.5, 2., .75, 1.25, 2.5, 1.75, 3.],
                     dtype=torch.float64)
# ColumnObs.bias must be full shape like ColumnObs.bt: B×9 or B×16.
co = dataclasses.replace(co, bias=bias_K)
report = run_fulldomain_analysis(
    frame, co, native_grids, case_root,
    normalized_dry=True, observation_coordinate="kma_v3_0",
    channels=tuple(range(8, 17)), huber_delta=1.,
    fixed_obs_errors=True, obs_sigma=sigma,
    obs_error_source="predeclared sensitivity assumption; not calibrated",
    # Keep the other original dt, time, number-floor, geometry/surface controls.
)
```

The correction is added to the observation: `r=(H-(y+bias))/sigma`.
Sigma may be scalar or a nine-element vector; ColumnObs bias follows the same
thermal selection and column routing as y. Inputs are copied for the inner
objective and included in its signature. Nonfinite/nonpositive scales and
invalid dimensions are rejected before a case is prepared; scales below the
existing lower loss denominator floor are also rejected. State-dependent
sigma recalculation during trial evaluation is unsupported by this fixed policy.
Boolean values surviving in scalar/tensor/array or mixed sequence inputs are
rejected before tensor coercion. A caller-created floating array that already
converted a boolean into a number cannot reveal that earlier input type.

The new objective reuses `compute_obs_loss` in both clear and all-sky paths.
Huber delta is dimensionless in the standardized residual. Bias does not alter
model BT, QC support or the existing raw-IR105 regime proxy.

`omb/oma` remain raw mean-absolute K innovations. `omb_corrected/oma_corrected`
use y+bias; `omb_standardized/oma_standardized` divide those residuals by the
same frozen sigma. Saved NPZ includes `obs_sigma_K`, `obs_bias_K` and
`y_bt_corrected`. The report labels the source assumption and keeps calibrated,
scientific and operational observation approval false.

The initial scope is the actual full-domain evaluator/clear/all-sky worker path.
The separate normalized OSSE `ShardSpec` remains its earlier 1 K diagnostic mode.
Existing generic frozen-dual callbacks already support fixed sigma/bias; no new
loss/solver or covariance framework is introduced.

## Evidence and remaining research decisions

[Actual C5 engineering evidence](../harness/evidence/REPORT_fixed_obs_errors_2026-10-07.md)
connects KDM, real RTTOV, the new fixed-error cost and its initial-state VJP.
It is not a calibrated R/bias experiment or an independent meteorological case.
Different costs from different weights are not forecast improvements.

The [data inventory](../harness/evidence/INTERNAL_research_case_inventory_2026-10-07.md)
records why the retained KO case is still nominal-time/product/geometry evidence.
Without new lineage/scan/geometry information, keep that limitation visible.
The existing diagonal CVT prior/control selection (A2) now has an explicit
normalized-research option. Next science items are R1/R2, signed physical budgets, timestep dependence and unused
validation data. Do not reopen closed numerical results to manufacture progress.

## State prior and initial control choices

Pass `background_sigma_overrides={"nc": 0.0}` with a nonempty
`background_error_source` to fix the initial NC control; use a predeclared
positive scale to enable it. This reuses `make_default_cvt`, including its
existing reservoir and qv-level masks. `th` scales are additive Kelvin;
multiplicative-field scales are dimensionless log-control scales. Overrides
must be known state fields with finite nonnegative real scalars. The default
call remains unchanged. The conserving partition forces qc/qi/qs scales to zero
and rejects positive overrides on all mass hydrometeor fields and bg before
preparing an observation case.

The report saves the assumption, overrides and actual nonzero control counts,
and declares `prior_is_calibrated=False`. This only changes the state diagonal
CVT; the four warm-process parameter priors remain unchanged. Zero initial NC
control does not freeze the NC trajectory against changes driven by other states.
See the [actual comparison](../harness/evidence/REPORT_state_prior_controls_2026-10-07.md).

## First public observation collection

The [acquisition checklist](../harness/evidence/CHECKLIST_first_observation_collection_2026-10-07.md)
starts with actual catalogues and small raw subsets, warm-liquid comparison first
and ice/mixed-phase collection in parallel. It distinguishes sensor calibration,
independent cloud/atmosphere observations and new native model–observation pairs.
No prior calibrated sigma/bias is required to start. Preserve 1 K/zero bias as
diagnostic regression and do not fit scientific weights to a metadata shortlist.

Anonymous NASA CMR and ESA MAAP queries locate actual granules. Nine NOAA LA thermal
originals and four raw Anmado soundings were acquired. None is yet a validated
cloud-phase/pixel/native-model pair. The LA product does not repair KO/ELA lineage,
and independent soundings are observations, not substitute model profiles.

The acquired LA020GE files also require an explicit LA ingest bridge: current
`read_ko_slot` and `read_fd_slot` support KO020LC and FD020GE respectively and
reject LA filenames. Header calibration-tuple agreement does not prove SRF
processing identity. Raw SRF/GSICS files, independent LWP correspondence and a
cold-season search remain unacquired/unqueried in this first packet. The
EarthCARE frame start is not the timestamp of its intersection with Korea.

## Numerical artifact acceptance for fixed errors

When evaluating an actual fixed-error normalized KMA report, explicitly call
`evaluate_artifact_gates(report, expected_fixed_obs_errors=True)`. This requires
the matching fixed-mode marker, normalized KMA coordinates, ordered nine-channel
scale/bias metadata, finite raw/corrected/standardized innovations and final audit.
Total objective descent remains required; individual mean-absolute innovation
metrics need not descend under a weighted, bias-corrected Huber objective.

The omitted/False selector preserves the legacy raw O-A <= O-B policy; a report
cannot switch it by its own marker. The historical LC05 stress runner explicitly
selects False. Neither `accepted=True` policy grants scientific/operational
approval. Do not adjust sigma/bias to satisfy a raw innovation gate.
