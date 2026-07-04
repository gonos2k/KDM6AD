---
title: Overview
type: meta
date_modified: 2026-07-02
---
# Overview

This vault tracks project knowledge for KDM6AD-k: a standalone KDM6AD working tree that compares the original [[KDM6]] Fortran microphysics scheme with the [[KDM6AD]] libtorch-based differentiable port inside the [[WRF KIM-meso Host]].

The main theme is [[KDM6AD Forward Parity]]. The mp37 path calls the direct Fortran implementation in `module_mp_kdm6.F`, while the mp137 path enters a Fortran wrapper, stages WRF arrays through `kdm6_iso_c.F`, and calls the C++ libtorch port. As of 2026-07-02 the two paths agree STRICT BITWISE across all 254 output variables at every frame through a 10-step integration at np1 — the earlier "step-1 is the documented gate" framing is superseded, as is the "irreducible §48 graupel-density floor" (fixed via §53r). Longer-window and MPI-parallel gates are still in progress (a 12-hour np4 attempt had mp137 hit an MPI-runtime init crash, not a numerics divergence). See [[kdm6ad-10step-bitwise-achieved-2026-07-02]].

The second theme is [[KDM6AD Automatic Differentiation ABI]]. Operational mp137 is forward-only (`value_only=1`), while AD workflows use packed fp64 state and forcing buffers through handle-based VJP/JVP calls. This separation keeps WRF runtime behavior deterministic while preserving a differentiation surface for DA workflows.

The literature theme is [[Bulk Microphysics Design Space]]. The Zotero survey of KDM/WDM-related papers shows that number concentrations, CCN, moment closure, graupel/riming properties, sedimentation, partial cloudiness, and ice-category design are the main scientific axes that should guide [[KDM6AD]] derivative experiments.

The paper-level literature layer is now split into [[papers/_index|42 individual paper pages]]. Use [[KDM6 Literature Genealogy]] to follow the KDM/WDM lineage and [[KDM6AD Literature Claim Map]] to connect manuscript claims to specific papers. The older source pages remain as collection ledgers and synthesis notes; paper-specific reasoning should live in `wiki/papers/paper-<ZoteroKey>.md`.

The manuscript/storytelling theme is captured in [[kdm6ad-code-story-literature-review-2026-06-25]]: KDM6AD should be explained as a parity-preserving differentiable implementation surface for an existing KDM/WDM-family microphysics scheme, with the online host path and the fp64 DA path deliberately separated.

The June 10 presentation ([[kdm6ad-20260610-presentation-adversarial-review]]) is useful historical/story context (five-representation architecture, precision/parity narrative), but stale on ABI status: it says C-ABI VJP/JVP was unimplemented, whereas the code now exposes `kdm6_step_ad_c`, `kdm6_handle_vjp_c`, and `kdm6_handle_jvp_c` with tests passing.

The mathematical manuscript theme is captured in [[kdm6plus-collection-mathematical-deep-ingest-2026-06-25]], [[KDM6AD Mathematical Microphysics Operators]], and [[KDM6AD Differentiability Audit]]: PSD moment relations, tendency equations, JVP/VJP products, sedimentation consistency checks, and diagnostic-boundary caveats to include before derivative claims.

Open questions center on boundaries: `diag_rhog` is excluded from the packed AD ABI because it is a diagnostic with no meaningful derivative (no longer because it is a parity floor — it is now bitwise), diagnostics used for WRF parity may not all have derivative semantics, mp137 remains slower than mp37 in observed run timing (still unquantified), and the [[Differentiable Bulk Microphysics Research Gap]] still needs full-text literature verification before manuscript drafting. A newly load-bearing technique — the dtype-conditional "operational-raw / DA-clamped" numerics idiom that reconciled Fortran's raw operational math with autograd-safe clamped forms — is used ~25× but has no dedicated page yet.

## Initialization Note
This is an Obsidian-ready vault. The formal kg schema pin was not created because the global schema files were not available in the expected local skill directories.
