# Same-call water-budget source audit

Reviewed 2026-10-22 for the one-column fp64 same-call budget. This is a
read-only source audit; no model, RTTOV, or saved-case computation was run.

## Budget measure and residual

For the fixed call-entry measure supplied to KDM6, compute

`W = sum_k (DENdry[k] * DELZ[k]) * (QV + QC + QR + QI + QS + QG)[k]`.

The weight has units kg dry air m-2; the summed mixing ratio is kg water per kg
dry air, so `W` is kg water m-2. Use the same captured fp64 `DENdry` and `DELZ`
for the pre- and post-call states. Exclude number fields and `BG` (the graupel
volume-per-mass proxy). The Fortran kernel sets `dend = den` (active source
`module_mp_kdm6.F:867-870`); the existing oracle column measure independently
uses `forcing.rho * forcing.delz` and sums `qv+qc+qr+qi+qs+qg`
(`oracle/kdm6/water_budget.py:36-47`).

The surface diagnostic matching that total-water measure is `rain_increment`
alone. It is returned in mm water-equivalent over the call; numerically,
1 mm water-equivalent = 1 kg m-2. Therefore report

`R = W_after - W_before + rain_increment_mm` (kg m-2).

Do not add `snow_increment` or `graupel_increment` to `rain_increment`: they
are overlapping category diagnostics, not disjoint additions.

## Producer and category semantics

Fortran `fall` has four mass-flux categories at the bottom level KTS: rain
`qrs(:,:,1)`, snow `qrs(:,:,2)`, graupel `qrs(:,:,3)`, and cloud ice
`qci(:,:,2)`. The source forms the total as their sum at
`module_mp_kdm6.F:1461`; snow diagnostic is snow plus ice (`:1462`), and
graupel diagnostic is graupel only (`:1463`). It writes these as:

- `RAINNCV`: all-species total.
- `SNOWNCV`: snow plus ice fallout.
- `GRAUPELNCV`: graupel fallout.

The KDMAD wrapper documents and implements this mapping at
`module_mp_kdm6ad.F:433-463`. Consequently `rain_increment` is not a liquid-rain
only value. If a disjoint rain-only partition is ever needed, it is total minus
the snow/ice and graupel subsets (subject to the same nonnegative/clamp and
rounding behavior); it is unnecessary for the total-water residual.

The source computes terminal-fall factors divided by layer thickness
(`module_mp_kdm6.F:1168-1175`) and then `falk = dend*q*work1/mstep`
(`:1192-1206`, cloud ice `:1284-1300`). The bottom accumulation is
`fallsum * DELZ(KTS) / DENR * dtcld * 1000` (`:1458-1472`), where `DENR` is
`rhowater = 1000 kg m-3` (`share/module_model_constants.F:58`; the host
argument is documented at `module_microphysics_driver.F:370`). This yields mm
water-equivalent. The C++ surface path matches the four-category sum and unit
conversion (`libtorch/src/sedimentation.cpp:310-319`); `runtime.cpp:627-629`
accumulates all sedimentation subcycle increments before returning one
`FnResult` for the call. KTE is swept as the top cell and its flux is passed to
the cells below; the reported surface value is formed at KTS only. There is no
additional top-boundary precipitation term in this diagnostic.

## Interpretation limits

A qi-only residual is not a full-water residual: qi may transfer to snow,
graupel, rain, cloud water, or vapor. The saved evidence
`harness/evidence/FINDING_ice_ledger_out_of_scope_v1.md` explicitly describes
the large qi sedimentation-ledger residual as conversions the qi-only ledger
does not carry. Include all six water species in `W` before inferring loss.

Even the all-species same-call residual is not promised to be zero for every
legacy input. The source-faithful sedimentation update caps inflow using the
above cell's post-update reservoir (`module_mp_kdm6.F:1216-1224` and analogous
species paths). Existing attribution in `docs/P0-4b_sedimentation_attribution.md`
shows the measured diagnostic-minus-state-loss gap is the internal interface
defect (`P-L = B - sum(D) + sum(A)`), with bottom diagnostic gap near zero in
its cited heavy-rain example. That example is not a prediction for this new
call: evaluate the captured one-column arrays, report `R`, and do not label a
nonzero residual an ice-transfer failure without separating the interface
defect and any microphysics/cleanup contribution.

## Provenance

The public worktree was at `5202ea117c1661472b79411e07e854b532367854`.
The source SHA-256 manifest is in `SOURCE_SHA256.txt`. No source file was
modified by this audit.
