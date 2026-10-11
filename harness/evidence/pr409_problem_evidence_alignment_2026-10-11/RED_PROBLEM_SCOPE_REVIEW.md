# Red review: PR409 problem and evidence alignment

## Disposition

The current problem statement separates the AMI-only input policy, the upper
hydrometeor-process goal, the narrower T/Q initial-state experiment, and
engineering execution. No unresolved overclaim found in the final reviewed
draft. Selected process and H∘M/NC evidence stays bounded to its recorded
regimes; the document does not claim that the T/Q capture closes the upper
process goal.

## Source-contract checks

The single-column helper fixes `active_fields=(th,qv)`, normalized-dry mode,
one declared all-sky slot, 20 s local M step, 7/7 valid background channels,
Huber `delta=1`, observation sigma 1 K and zero bias. It sets all four
microphysics-parameter prior sigmas to zero. `make_default_cvt` makes theta
additive and qv multiplicative with `eps=0`; qv control is limited to positive
background cells among bottom-up levels 0–11. The saved PR395 record has 39
active theta and 12 active qv coordinates (51 total); the draft correctly
presents 51 as an upper bound and calls for per-case active counts. Other
initial State fields are fixed in the control map, though their values may
change through M.

The objective is the sum of the standardized-control prior and masked
seven-channel Huber loss. The seven support values are frozen from background
quality, and a trial that flags a retained channel fails instead of shrinking
the support. The 1 K scale and zero bias are identified as exploration
assumptions rather than an independently measured error model. The draft
correctly limits seven residuals to at most seven local observation directions
and does not infer that all 51 controls are determined, locally converged, or
globally unique. It states that the returned result is not necessarily a
balanced host initial field and keeps full host coupling, cycling and forecast
skill separate.

One terminology ambiguity was identified and resolved in the current draft:
`Forcing.rho` (`rho_m`) is fixed, but the normalized-dry KDM path derives
`rho_m/(1+trial_qv)` inside the M map, so that derived dry-number density
retains qv sensitivity. The draft now distinguishes it from the optical
`rho_d` frozen at background. The chain rule for recomputing forcing from trial
state is therefore properly presented as a different problem.

## Claim and evidence bounds

- Initial cloud/NC are not direct controls or retrieved observations in this
  subproblem. H can depend on evolved microphysics through M; that is a
  model-mediated BT path, not direct NC retrieval.
- The NC→BT C5 record is bounded to a fixed-profile optical/BT probe. The
  selected native two-direction report is historical and source/build/variant
  specific. The PR391 state and H∘M checks are limited to their declared
  points, branches and supports; the draft does not generalize them to complete
  process attribution or number conservation.
- PR395 is a returned July19 diagnostic analysis, with unknown L-BFGS
  termination and a final gradient above `tolerance_grad`. PR408 is a synthetic
  H success/checkpoint path, with real KDM/AD/minimizer/audit code but no real
  RTTOV or new-date forecast. The draft keeps these records distinct and does
  not describe either as science acceptance.
- The optional `Δy_M` comparison is explicitly claim-matched and unexecuted; it
  is not a new completion gate. No SVD/Hessian gate or new analysis campaign is
  proposed.
- July20/21 remain pending native input. The draft permits selection of an
  already available valid date before examining residuals, while preserving
  pending records and prohibiting repeated archive searches solely to create
  receipts. It does not request/acquire data or claim new-date results.
- The 78→79 score is consistently described in the central document, rubric
  and observation contract as reviewer-proposed conversation-management
  context, not user-owned scientific acceptance. Historical execution records
  remain unchanged.

The central document's local links resolve, including the README scope link,
source links, evidence packets, PR408 coordinator report, observation contract
and rubric. `git diff --check` passes. The Graphify query returned broad
attribution/capture context but did not establish these experiment details;
source and saved records were checked directly.

No tests, new calculations, forecast/native reads, H/M calls, optimizer calls,
data requests or acquisition were performed for this documentation review.
