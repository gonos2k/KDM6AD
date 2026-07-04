---
title: KDM6AD Differentiable Microphysics Zotero-KG Bridge
date_ingested: 2026-06-25
source_type: research-bridge
tags:
  - kdm6
  - kdm6ad
  - differentiable-microphysics
  - zotero
  - automatic-differentiation
---
# KDM6AD Differentiable Microphysics Zotero-KG Bridge

## Status

Zotero Desktop is reachable through the local API and connector. The local
semantic index exists with 119 documents. No new Zotero items were written in
this step; the candidate add command was run as `--dry-run` only.

Existing Zotero tag exported for KG staging:

- Tag: `kdm6-microphysics-survey`
- Count: 30 items
- Staging folder: `/tmp/zotero-kg-kdm6-microphysics-survey`
- Next ingest command: `$kg-ingest /tmp/zotero-kg-kdm6-microphysics-survey`

Candidate tag for differentiable/AD references:

- Tag: `kdm6ad-differentiable-microphysics`
- Dry-run result: 5 items built, 0 saved

## Code Findings

[[KDM6AD]] is not a source-to-source AD transform of [[KDM6]]. It is a
hand-ported differentiable mirror with two deliberately separated ABI surfaces:

- Operational f32 path: `libtorch/bridge/kdm6_c_api.cpp:kdm6_step_c`
- fp64 DA path: `libtorch/bridge/kdm6_c_api.cpp:kdm6_step_ad_c`
- Reusable derivative handles: `kdm6_handle_vjp_c`, `kdm6_handle_jvp_c`

The separation matters because operational parity and differentiability pull in
opposite directions. The f32 path must preserve mp37 bitwise behavior, while the
DA path needs fp64 gradients and finite behavior at microphysical threshold
corners.

### ABI Boundary

- `kdm6_handle_t` stores the live graph handle plus `im/kme/jme` and graph dtype.
- `kdm6_step_c` stages Fortran float arrays, calls `kdm6::kdm6_step`, copies state
  back, emits forward diagnostics and precipitation increments, then returns
  `NULL` handle when `value_only != 0`.
- `kdm6_step_ad_c` takes packed fp64 state/forcing, enables `requires_grad` only
  when `value_only == 0`, and returns a fp64 handle for VJP/JVP.
- Packed derivative buffers use field-major Fortran `(im,kme,jme)` column-major
  double blocks. This is the correct ABI for Fortran callers and avoids leaking
  internal `(B,K)` tensor layout.

### Host Wrapper

- `module_mp_kdm6ad.F` calls `kdm6_step` with `param_grad_flags=0` and
  `value_only=1` in the operational WRF path.
- `diag_rhog`, `re_cloud/re_ice/re_snow`, `REFL_10CM`, and surface precipitation
  increments are forward diagnostics reconciled in the wrapper; they are not
  part of the packed DA ABI.
- The wrapper closes the handle even in the value-only operational path, making
  NULL close an expected success case.

### Build/Parity Controls

- `phys/Makefile` builds `libkdm6_c.dylib` as an order-only prerequisite before
  KDM6/KDM6AD Fortran objects.
- KDM6 and KDM6AD Fortran objects are compiled with `-ffp-contract=off`; the C++
  side mirrors this because fma contraction changes seed-level parity.
- The host integration must be re-applied after every `./configure` via
  `apply_kdm6ad_config.sh`.

## Research Interpretation

Current literature supports three design conclusions for KDM6AD:

1. **AD is useful for ranking and diagnosing microphysics sensitivity**, but
   microphysics has many thresholds and inactive branches. This matches the
   KDM6AD split between a strict f32 forward path and an fp64 DA path.
2. **Differentiable programming is becoming a route for improving cloud
   parameterizations**, but legacy Fortran models still need explicit
   interop/ABI strategy. KDM6AD's C ABI plus ISO_C layer is therefore a
   practical bridge rather than an implementation detail.
3. **Forward parity is not optional for online host integration.** A
   differentiable microphysics kernel that changes `re_*`, `REFL_10CM`,
   sedimentation increments, or FP environment can diverge through radiation,
   precipitation accumulation, or host dynamics even if the primary prognostic
   outputs match for one step.

## Zotero Add Candidates

Dry-run command:

```bash
python3 /Users/yhlee/.codex/skills/zotero-kg/scripts/zotero_add.py \
  --doi 10.1029/2021MS002849 10.1029/2025MS005341 10.21105/joss.07602 \
  --arxiv 2605.24544 2505.04358 \
  --tag kdm6ad-differentiable-microphysics \
  --dry-run
```

Candidate papers:

1. Hieronymus et al., "Algorithmic Differentiation for Sensitivity Analysis in
   Cloud Microphysics", DOI `10.1029/2021MS002849`.
2. Lamb et al., "Perspectives on Systematic Cloud Microphysics Scheme
   Development With Machine Learning", DOI `10.1029/2025MS005341`.
3. Atkinson et al., "FTorch: a library for coupling PyTorch models to Fortran",
   DOI `10.21105/joss.07602`.
4. Pierzyna, "JAX-SCM v1.0: a modern atmospheric single-column model for
   boundary layer research", arXiv `2605.24544v1`.
5. Grundner et al., "Reduced Cloud Cover Errors in a Hybrid AI-Climate Model
   Through Equation Discovery And Automatic Tuning", arXiv `2505.04358v4`.

## KG Links

- [[KDM6]]
- [[KDM6AD]]
- [[KDM6AD Automatic Differentiation ABI]]
- [[KDM6AD Forward Parity]]
- [[WRF KIM-meso Host]]

## Source URLs

- https://doi.org/10.1029/2021MS002849
- https://doi.org/10.1029/2025MS005341
- https://doi.org/10.21105/joss.07602
- https://arxiv.org/abs/2605.24544
- https://arxiv.org/abs/2505.04358
