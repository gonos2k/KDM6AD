---
title: Bulk Microphysics Design Space
instance_of: Concept
page_kind: concept-page
epistemic_status: inferred
date_created: 2026-06-25
date_modified: 2026-06-25
provenance:
  sources:
    - wiki/sources/kdm6-microphysics-zotero-survey-2026-06-25.md
relations:
  - predicate: derived_from
    target: "[[kdm6-microphysics-zotero-survey-2026-06-25]]"
    rationale: "Summarizes the design axes exposed by the Zotero microphysics survey."
  - predicate: about
    target: "[[KDM6AD Forward Parity]]"
    rationale: "The design axes define what parity and derivative checks must preserve."
---
# Bulk Microphysics Design Space

## Definition

Bulk microphysics design space is the set of structural choices that determine how a scheme maps thermodynamic state, hydrometeor mass, number concentration, particle properties, and subgrid variability into process tendencies and diagnostics.

## Why It Matters

[[KDM6AD]] differentiates an implementation of a KDM/WDM-family scheme. Gradients are only scientifically useful if the differentiated controls correspond to meaningful microphysics axes. The Zotero survey shows that the influential axes are not just scalar tunable constants; they include moment choice, particle-size distribution closure, graupel/riming representation, aerosol and CCN coupling, partial cloudiness, sedimentation consistency, and diagnostic boundaries.

## Current Understanding

- Moment order matters. One-moment, two-moment, and three-moment schemes differ in their ability to represent size sorting, rain evaporation, stratiform precipitation, and reflectivity.
- Number concentration and CCN prediction are central to WDM6/WDM7 behavior and are therefore first-class sensitivity targets for [[KDM6AD]].
- Ice-phase representation is moving from fixed snow/graupel categories toward predicted particle properties, riming density, and multiple free categories.
- Sedimentation/advection choices can create artifacts such as spurious reflectivity growth; differentiating such artifacts is possible but not physically meaningful.
- Partial cloudiness and subgrid condensate variability alter nonlinear process rates and can interact with radiation and convection.
- Diagnostics such as reflectivity and effective radius may be essential for evaluation while remaining outside the packed AD state.

## KDM6AD Implications

[[KDM6AD]] should treat this design space as a derivative-audit checklist. Forward parity with [[KDM6]] is necessary but not sufficient: each derivative experiment should state which design axis is perturbed, whether the path crosses nonsmooth thresholds, and whether the observed sensitivity is prognostic-state sensitivity or diagnostic-postprocessing sensitivity.

## Evidence

- [[kdm6-microphysics-zotero-survey-2026-06-25]]
- [[KDM6AD Automatic Differentiation ABI]]
- [[KDM6AD Forward Parity]]
