# PR224 warm-liquid candidate: bounded offline gate

This bounded check used the existing local 5 km KDM6 forecast frame at
`2025-07-19 00:00:20` (frame index 1), because the initial `wrfinput_d01`
contains no stored positive cloud-number levels. The source SHA-256 is
`30ee8656cedf57cc827ad041e4ed8084d8bbf5afdbe0a21b28b33564544bca9f`.
The result is conditional forecast-frame evidence, not an initial-state claim.

The corrected policy orders by native warm-liquid cloud-base AGL, then dry
integrated cloud water, with deterministic flat-column tie breaking. A
predeclared serial cap of 32 candidates was recorded before the rate scan. The
earlier exploratory flat-15763 ordering used an erroneous second division of
geopotential by `g` and is excluded from this selection; the corrected replay
uses `(PH+PHB)/g` once and the reader's dry-density measure. The first 24
candidates had zero autoconvective and accretion applied rates. The
first passing candidate was ordinal 25, flat column **35711** (`j=152,i=143`),
with warm-liquid levels `[0,1,2,4,11,12,14]`, cloud base `25.4955361393 m`
AGL, and `xland=1`.

At alpha zero, the existing `warm_limited` trace reports finite nonzero
accretion rates `pracw=5.380425492609302e-08` and
`nracw=364751.48659655335` as maxima over native levels. The mass-rate unit is
`kg kg-1 s-1`; the number-rate field is the oracle's internal number-unit per
second, while the source cloud-number field is reader-declared `kg-1` and its
host/kernel physical reconciliation remains open. The process-to-state path is
the recorded `warm_limited → state_update → picons → satadj → cleanup →
dsd_limiter` sequence. All native levels and all warm-stage rate records are
retained in the graphify artifact.

The nonzero accretion levels are 11 (`T=282.7823961 K`, `p=723.4450 hPa`,
`2257.5255 m AGL`), 12 (`280.2391899 K`, `685.3113 hPa`, `2706.9672 m AGL`),
and 14 (`275.3375886 K`, `604.4490 hPa`, `3730.5639 m AGL`). These are active
rate levels and are not each the low-cloud-base ranking level.

For accretion, value-only and graph alpha-zero primals are exactly equal for
all state fields and tapped rates. Genuine forward JVP and reverse VJP agree
per native level. Independent central FD checks used epsilon `0.03`, `0.1`,
and `1e-4`; maximum rate relative errors were `1.50e-4`, `1.66e-3`, and
`1.67e-9`, respectively. State tangents are nonzero in `qc`, `qr`, and `nc`;
the pure local model-to-profile map has nonzero `HYDRO` and `DEFF` tangents.
At the diagnostic `1e-4` endpoint, the fixed gates pass with rate relative
error `1.6671e-9 <= 1e-6`, state relative error `1.73e-9 <= 1e-4`, fixed
branch masks at all three epsilons, exact alpha-zero primals, and maximum
forward/reverse duality difference below `1.1e-18` across rate, state, and
profile tangents.

For the observed selected rate scaling `r(alpha)=r(0)*exp(alpha)`,
the analytic central difference is `r(0)*sinh(epsilon)/epsilon`. With the
reported FD-relative normalization, its truncation discrepancy is
`1-epsilon/sinh(epsilon)`: `1.4998425149459e-4` at `.03` and
`1.6647242703890e-3` at `.1`, matching the measured rate discrepancies.
This explains those larger-step differences without changing a tolerance;
it is a selected-rate identity, not a model-wide convergence result.

As a selected one-step transfer check, all 39 native levels have zero residual
for `dqc+dqr`, `dqc+20*dpracw`, `dqr-20*dpracw`, and
`dnc+20*dnracw`. This is evidence for the executed accretion state-update
direction at `dt=20 s`; it is not a global budget or a claim that the internal
number units equal the reader's source `kg-1` label.

This establishes an offline active process candidate. This offline artifact
contains no RTTOV or BT/cost validation and required no external atmospheric
data, synthetic forcing, QC adjustment, or production edit. The subsequent
[live comparison](REPORT_native_liquid_accretion_2026-09-19.md) records five
completed endpoints, all excluded from the cost by RTTOV quality. The reader-declared `nc` unit remains conditional
on the unresolved host/kernel physical-unit reconciliation.

The first exploratory ordering was invalid because geopotential was divided by
`g` twice; the corrected `(PH+PHB)/g` ordering was completed before the rate
scan. An earlier local AD/FD probe also broadcast a level-0 gradient and
stripped forward-mode duals; that script was corrected to retain per-component
JVP/VJP before this evidence was accepted. Those intermediate outputs are
excluded. The compact JSON records the policy ordering, update-`dt` evidence,
and SHA-256 hashes for the reader, process boundary, warm kernel, coordinator,
and reproducibility scripts.

The compact public summary is in
`pr224_warm_liquid_candidate_20260919.json`. Full ordered rejections and
all-level warm-rate records are in
`graphify-out/pr224-liquid/rate_scan_cap32_result.json`; AD/FD, primal,
trace, and profile details are in
`graphify-out/pr224-liquid/first_passing_ad_fd.json`.
