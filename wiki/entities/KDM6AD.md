---
title: KDM6AD
type: entity
date_modified: 2026-06-25
---
# KDM6AD

## Key Facts

- KDM6AD is the mp137 differentiable-port integration for KDM6AD-k.
- The WRF-facing Fortran entry point is `host/KIM-meso_v1.0/phys/module_mp_kdm6ad.F`.
- The operational host path is a wrapper over `kdm6_iso_c.F` and `libtorch/bridge/kdm6_c_api.cpp`.
- The core forward physics is implemented in libtorch C++ under `libtorch/src/`.
- Automatic differentiation is exposed through handle-based VJP/JVP ABI calls, not through the WRF mp137 runtime path.

## Connections

- Mirrors [[KDM6]] for forward physics parity.
- Runs inside [[WRF KIM-meso Host]] as `mp_physics=137`.
- Implements [[KDM6AD Automatic Differentiation ABI]].
- Must preserve [[KDM6AD Forward Parity]] for operational trust.
- Paper-level evidence is split across [[papers/_index]], [[KDM6 Literature Genealogy]], and [[KDM6AD Literature Claim Map]].

## From [[kdm6-vs-kdm6ad-code-comparison-2026-06-25]]

- The mp137 WRF runtime path passes `value_only=1` and `param_grad_flags=0`, so it is forward-only.
- `diag_rhog`, `REFL_10CM`, and `re_*` are reconciled around the wrapper/C++ boundary for parity with mp37.
- `diag_rhog` is not part of the packed AD ABI.

## From [[kdm6-microphysics-zotero-survey-2026-06-25]]

- The strongest manuscript positioning is a parity-preserving differentiable implementation of a KDM/WDM-family bulk microphysics scheme, not a new physical parameterization.
- Scientifically meaningful derivative experiments should target known sensitive axes from the literature: number concentrations, CCN, graupel/riming properties, sedimentation, partial cloudiness, melting, and size-distribution closure.
- Derivative interpretation must distinguish prognostic state sensitivities from diagnostic-only outputs such as reflectivity and effective radius.

## From [[kdm6ad-code-story-literature-review-2026-06-25]]

- The current explanation story should be organized as: mature KDM/WDM physics lineage, strict mp37/mp137 parity, separated operational and DA ABI surfaces, then literature-motivated derivative axes.
- The operational mp137 path should be described as value-only f32 host integration; the differentiable contribution is the separate packed fp64 VJP/JVP ABI.
- The safest paper claim is implementation methodology plus derivative auditability for an established scheme family.

## From [[kdm6plus-collection-mathematical-deep-ingest-2026-06-25]]

- KDM6AD should be described as a differentiable operator `F_KDM6(y, x, theta)` with explicit JVP/VJP products, not as a vague "AD version" of a scheme.
- The paper should derive or state PSD moment relations, especially `lambda ~ (N/q)^(1/3)`, because they connect number concentration perturbations to fall-speed and reflectivity sensitivities.
- The manuscript needs a [[KDM6AD Differentiability Audit]]: smooth processes, thresholded processes, saturation adjustment, sedimentation artifacts, and forward-only diagnostics require separate derivative claims.
- Data-assimilation claims should distinguish the microphysics tangent/adjoint block from observation operators such as radar reflectivity.

## From [[kdm6ad-20260610-presentation-adversarial-review]]

- The presentation is a useful historical/story source for the "one physics, five representations" architecture: Fortran reference, PyTorch oracle, C++ mirror, C ABI, and Fortran wrapper.
- Slide 6 is stale as a current-status claim: it says C-ABI VJP/JVP was not implemented, while the current code exposes the fp64 packed AD ABI and the targeted C++/Fortran ABI tests pass.
- The presentation should motivate the paper narrative, but the mathematical claims should come from the code notes, differentiability audit, and KDM6+ literature ingest.

## From [[KDM6AD Literature Claim Map]]

- KDM6AD should be argued through claim-to-paper links, not through one monolithic literature page.
- The main claim clusters are KDM/WDM lineage, PSD and number-concentration sensitivity, graupel/riming sensitivity, AD/VJP/JVP implementation, DA observation-operator boundaries, and differentiability audit.
- Each claim cluster points to individual paper pages such as [[paper-6P3B5EDZ]], [[paper-D629MKTV]], [[paper-E6KDCS3V]], [[paper-HSCSIXWK]], [[paper-DMKR59F5]], and [[paper-BTZY27UZ]].
