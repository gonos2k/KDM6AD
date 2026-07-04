---
title: Differentiable Bulk Microphysics Research Gap
instance_of: Concept
page_kind: concept-page
epistemic_status: inferred
confidence: medium
date_created: 2026-06-25
date_modified: 2026-06-25
provenance:
  sources:
    - wiki/sources/kdm6-microphysics-zotero-survey-2026-06-25.md
    - wiki/queries/kdm6ad-differentiable-microphysics-zotero-kg-2026-06-25.md
relations:
  - predicate: derived_from
    target: "[[kdm6-microphysics-zotero-survey-2026-06-25]]"
    rationale: "The survey establishes the microphysics side of the gap."
  - predicate: about
    target: "[[KDM6AD Automatic Differentiation ABI]]"
    rationale: "The gap is addressed through KDM6AD's differentiable ABI."
---
# Differentiable Bulk Microphysics Research Gap

## Definition

The differentiable bulk microphysics research gap is the missing bridge between mature WRF/KIM bulk microphysics schemes and automatic-differentiation-ready implementations that preserve forward behavior while exposing interpretable VJP/JVP sensitivities.

## Why It Matters

Bulk microphysics literature shows large sensitivity to number concentration, CCN, particle density, riming, fall velocity, spectral-shape assumptions, sedimentation choices, melting efficiency, and partial cloudiness. Traditional evaluations diagnose these sensitivities through controlled experiments. A differentiable implementation can make local sensitivity and calibration workflows more direct, but only if the AD surface is explicitly tied to a parity-validated physical scheme.

## Current Understanding

- The surveyed KDM/WDM literature establishes forward scientific importance but does not itself provide an AD interface.
- [[KDM6AD]] already separates operational forward execution from an fp64 handle-based AD ABI.
- The strongest manuscript contribution is therefore implementation methodology plus derivative auditability, not a new microphysics parameterization.
- Derivative interpretation remains conditional around nonsmooth adjustments, category thresholds, clipping, lookup tables, diagnostic-only fields, and sedimentation corrections.
- The related query note tracks external AD/differentiable-programming references that should be combined with this microphysics survey before manuscript drafting.

## Manuscript Positioning

The paper can be positioned as: "A parity-preserving differentiable port of a KDM/WDM-family six-class bulk microphysics scheme for sensitivity and DA-oriented workflows." The literature review should first show why the microphysics controls matter, then show that previous KDM/WDM work evaluates forward behavior but lacks a differentiable ABI, then argue that [[KDM6AD]] fills that implementation gap while preserving [[KDM6AD Forward Parity]].

## Evidence

- [[kdm6-microphysics-zotero-survey-2026-06-25]]
- [[kdm6ad-differentiable-microphysics-zotero-kg-2026-06-25]]
- [[KDM6AD Automatic Differentiation ABI]]
- [[KDM6AD Forward Parity]]
