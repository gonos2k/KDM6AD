---
title: KDM6
type: entity
date_modified: 2026-06-25
---
# KDM6

## Key Facts

- KDM6 is the mp37 Fortran reference microphysics scheme in the WRF/KIM-meso host.
- Its primary implementation is `host/KIM-meso_v1.0/phys/module_mp_kdm6.F`.
- The host driver calls it through `CALL kdm6` when `mp_physics=37`.
- It owns the direct Fortran implementation of the microphysics sequence and helper routines such as `kdm62D`, `ProgB_param`, `slope_kdm6`, `refl10cm_kdm6`, and `effectRad_kdm6`.

## Connections

- Reference target for [[KDM6AD]].
- Runs inside [[WRF KIM-meso Host]].
- Provides diagnostic helper routines reused by the [[KDM6AD]] wrapper for parity.
- Literature lineage is tracked through [[KDM6 Literature Genealogy]] and the 42 paper pages in [[papers/_index]].

## From [[kdm6-vs-kdm6ad-code-comparison-2026-06-25]]

- KDM6's forward output is the comparison baseline for [[KDM6AD Forward Parity]].
- Existing SS artifacts show numeric bitwise parity between mp37 and mp137 at the documented step-1 gate, frame index 1. See [[kdm6ad-final-code-location-verification-2026-06-25]] for the frame-selection clarification.

## From [[kdm6-microphysics-zotero-survey-2026-06-25]]

- KDM6 sits in the WDM/KDM scheme family whose scientific value is tied to prognostic number concentrations, CCN coupling, hydrometeor category design, and particle-property assumptions.
- The literature survey makes KDM6 more than a code baseline: it is the forward physics lineage that a differentiable port must preserve before derivative claims are credible.

## From [[kdm6plus-collection-mathematical-deep-ingest-2026-06-25]]

- KDM6 can be treated mathematically as a bulk microphysics time-step map whose tendencies combine nonlinear source/sink processes with sedimentation.
- Its WDM/KDM lineage is controlled by PSD moments, number concentrations, CCN, graupel/riming assumptions, and cloud-fraction/subgrid choices.
- The strongest KDM6AD paper framing is to differentiate this established KDM6/WDM-family map while preserving its forward behavior.

## From [[KDM6 Literature Genealogy]]

- Direct WDM/KDM lineage anchor pages are [[paper-6P3B5EDZ]], [[paper-H3KYIIM9]], [[paper-Y8G9YXWQ]], [[paper-5T4INXZ3]], and [[paper-D629MKTV]].
- Earlier bulk and multimoment roots are [[paper-LDHPT85H]], [[paper-UTM4WM2T]], [[paper-4NU3SNG7]], and [[paper-WMBSU2NB]].
- Graupel/riming and particle-property extensions are linked through [[paper-54NAR859]], [[paper-DKMG7MT6]], and [[paper-D629MKTV]].
