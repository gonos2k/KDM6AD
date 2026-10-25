---
title: Overview
type: meta
date_modified: 2026-10-25
---
# Overview

[[sources/native-domain-ko7-bounded-case-2026-10-25]] records the completed
65,988-column offline KO7 case: one global baseline cost/gradient and three
actual bounded T/Q proposals. Derivative gates pass, but all proposals lose
fixed observation support and are rejected. The accepted input and final BT
remain baseline; this is neither convergence nor a host/forecast cycle.

[[sources/native-ko7-restricted-confirmation-2026-10-25]] records one later
post-hoc alpha=1 control-space projection on the same scene. Its actual
129-block forward/direct-RTTOV confirmation preserves the original 381,528
support and lowers the fixed objective by 0.0760%. This is a restricted local
cost acceptance, not held-out validation, forecast skill or a native host/RK
cycle; physical water/energy/number closure and legacy number units remain
unresolved.

[[sources/native-block22-saved-response-2026-10-25]] is a saved-data-only
analysis of the original B512 block22 target `(i=167,j=50,k=18)`. Its fixed
sinusoidal baseline probe JVP is not the candidate descent direction. A
separate baseline-K projection against the actual finite RTTOV profile change
is compared with saved BT endpoints; the large residual is a bounded
nonlinearity diagnostic, not process causality or a local FD/forecast claim.

[[sources/native-ice-factorial-2026-10-23]] completes the one-column ice-only
factorial and prepares the full native-grid endpoint packet. At that preparation
stage, no regional KDM execution was claimed; later four-arm execution is
separately recorded in [[sources/native-domain-ice-factorial-2026-10-23]]. Physical
kernel closure and operational map selection are distinct from these comparisons.

[[sources/native-ice-boundary-2026-10-23]] fixes diagnostic summation and
attributes the same-call QI sedimentation loss to measured internal
departure/arrival gaps. It preserves the legacy physical map and local
derivative results; physical water closure remains unresolved.

[[sources/same-call-water-budget-2026-10-22]] adds an isolated fp64 accounting
result: one native-column legacy call loses water with zero surface export.
The dominant loss is localized to sedimentation, separate from cleanup,
forward parity and the accepted local derivative evidence; closure remains open.

[[sources/pr418-nine-channel-closeout-2026-10-12]] fixes the internal AMI L1B research execution closeout at PR417 evidence plus explicit9 support. Added WV063/WV069 real H returned flags32768; this input is not eligible for9-channel analysis. Completed7 functionality and bounded experiments remain closed; strict convergence, other dates and actual observed temporal fit remain separate.

This vault tracks project knowledge for KDM6AD-k: a standalone KDM6AD working tree that compares the original [[KDM6]] Fortran microphysics scheme with the [[KDM6AD]] libtorch-based differentiable port inside the [[WRF KIM-meso Host]].

The main theme is [[KDM6AD Forward Parity]]. mp37 calls the Fortran `module_mp_kdm6.F`; mp137 enters a Fortran wrapper, stages WRF arrays through `kdm6_iso_c.F`, and calls the C++ libtorch port. As of 2026-07-04 the two paths agree STRICT BITWISE across all 254 variables at every frame through a full 12-hour × MPI(np4) integration (2160 steps) — the campaign goal. The interim "12h in progress / mp137 MPI-runtime crash" note is superseded: that crash was an upstream numerics NaN from a transposed/OOB read in `flow_dep_bdy_qnn` (`share/module_bc.F`), root-caused and fixed (see [[module-bc-flow-dep-bdy-qnn-oob-2026-07-03]]); the last physics seed was §53x. Earlier "step-1 gate" / "irreducible §48 floor" framings are also superseded. See [[kdm6ad-differentiable-mathematics-2026-07-04]].

The second theme is [[KDM6AD Automatic Differentiation ABI]]. Operational mp137 is forward-only (`value_only=1`), while AD workflows use packed fp64 state and forcing buffers through handle-based VJP/JVP calls. As of 2026-07-14 this C ABI was hardened and sealed as tag `abi-v2-hardened` (`a53503e`): thread fail-closed, stable additive ABI v2, and hidden visibility cutting the export surface to exactly 9 symbols — packaging only, numbers unchanged ([[KDM6AD C ABI Hardening]]). The documented 12h parity was verified against the pre-hardening installed dylib and is not yet re-run at that baseline ([[abi-v2-hardened baseline 2026-07-14]]).

The literature theme is [[Bulk Microphysics Design Space]]. The Zotero survey of KDM/WDM-related papers shows that number concentrations, CCN, moment closure, graupel/riming properties, sedimentation, partial cloudiness, and ice-category design are the main scientific axes that should guide [[KDM6AD]] derivative experiments.

The paper-level literature layer is split into [[papers/_index|42 individual paper pages]]: use [[KDM6 Literature Genealogy]] for the KDM/WDM lineage and [[KDM6AD Literature Claim Map]] to connect manuscript claims to specific papers.

The manuscript theme spans storytelling ([[kdm6ad-code-story-literature-review-2026-06-25]]) and math ([[kdm6plus-collection-mathematical-deep-ingest-2026-06-25]], [[KDM6AD Mathematical Microphysics Operators]], [[KDM6AD Differentiability Audit]]): explain KDM6AD as a parity-preserving differentiable surface for an existing KDM/WDM scheme, with the online host path and the fp64 DA path separated, and cover PSD-moment/tendency/VJP-JVP relations and diagnostic-boundary caveats before derivative claims.

The June 10 presentation ([[kdm6ad-20260610-presentation-adversarial-review]]) is historical story context but stale on ABI status (it predates the now-implemented, now-hardened C-ABI VJP/JVP).

Open questions center on boundaries: `diag_rhog` is excluded from the packed AD ABI because it is a diagnostic with no meaningful derivative (no longer because it is a parity floor — it is now bitwise), diagnostics used for WRF parity may not all have derivative semantics, mp137 remains slower than mp37 in observed run timing (still unquantified), and the [[Differentiable Bulk Microphysics Research Gap]] still needs full-text literature verification before manuscript drafting. The dtype-conditional "operational-raw / DA-clamped" numerics idiom that reconciles Fortran's raw operational math with autograd-safe clamped forms — used ~25× and now the port's load-bearing technique — is captured in [[Operational-Raw vs DA-Clamped Dual Path]].

## October10 internal research update

PR397 provided a completed native rank/launcher, valid saved input and actual
single-column KDM–all-sky RTTOV T/Q analysis with preserved states/gradient.
The outer Python harness exit120 remains separately recorded. The user-reviewed
management basis is56/75 (74.7%), reflecting those actual results rather than
the number of PRs. [[sources/pr398-local-balance-and-sensitivity-2026-10-10]]
tracks bounded same-objective and saved-host sensitivity follow-ups. Precise
pixel UTC, footprint, flux closure and held-out event validation remain open;
normal native completion does not establish them.

## Spatial representativeness follow-up

The subsequent [[sources/pr398-spatial-representativeness-2026-10-10]] diagnostic
reads fixed native/AMI/VIIRS patches. It finds an all-clear native3×3, consistent
raw liquid phase in103 VIIRS samples and a4.78K observed IR105 range. Nine QA
bytes conflict with the advertised range. These descriptive samples do not
establish common footprint or independent-case validation; no new forecast
or optimization was run.

## Initialization Note (historical)
This is an Obsidian-ready vault. The formal kg schema pin was not created because the global schema files were not available in the expected local skill directories.

## Jul19 multi-time local analysis

[[sources/pr414-jul19-ten-minute-local-window-2026-10-12]] records three real AMI
scenes jointly fitted along61×20s held-forcing local transitions from the normal
05:55:40 native state. All-slot audit and checkpoint returned, strict convergence
remains unmet. This extends temporal calculation coverage on Jul19, not full
host cycling, independent-date or forecast-skill evidence.

## Three-slot bounded follow-up

[[sources/pr415-three-slot-bounded-finish-2026-10-12]] records a single same-problem
eight-budget numerical check. Gradient/cost decrease, but sampled BT stays
constant and strict convergence remains unmet. A narrowed hourly archive audit
now confirms normal historical four-rank completion, without certifying old
executable/input bytes or substituting it into the current experiment.

## Historical hourly-state evidence

[[sources/pr416-hourly-native-column-2026-10-12]] records real selected05/06/07
native weather arrays with evolving cloud/thermodynamics/metrics/winds. It is
a distinct historical host diagnostic, not a temporal BT validation or an
interpolated replacement for the fixed-forcing three-slot experiment.

## Historical hourly radiance response

[[sources/pr417-hourly-rttov-response-2026-10-12]] completes two actual06/07
forwardH calls, showing nonzero joint state/auxiliary-input response. It is
separate from the fixed-forcing window and does not establish temporal fit,
individual mechanism or a required new full-host model.
