---
title: KDM6AD Automatic Differentiation ABI
type: concept
date_modified: 2026-06-25
---
# KDM6AD Automatic Differentiation ABI

## Why This Matters

The AD surface defines how external DA or sensitivity workflows can use [[KDM6AD]] without confusing the operational WRF runtime path with graph-building differentiation calls.

## Current Status

- Operational mp137 calls `kdm6_step` with `value_only=1`, so it does not retain a graph.
- AD calls use packed fp64 state and forcing buffers through `kdm6_step_ad_c`.
- VJP and JVP are exposed through handles via `kdm6_handle_vjp_c` and `kdm6_handle_jvp_c`.
- The packed state field order is `th,qv,qc,qr,qi,qs,qg,nccn,nc,ni,nr,bg`.
- The 2026-06-10 presentation described C-ABI VJP/JVP as not yet implemented. That is historical only. Current June 25 code and targeted tests show the fp64 C/Fortran handle path exists.

## Rationale

Separating operational forward from AD handle calls keeps WRF execution deterministic and simpler while still providing differentiability for DA workflows. It also lets the project keep the operational ABI at f32 for mp37 parity while using fp64 packed buffers for DA-oriented derivatives.

## Boundaries

- `diag_rhog` is forward-only and excluded from the packed AD ABI.
- Diagnostics used for WRF output parity may not automatically have derivative semantics.
- The WRF mp137 operational runtime remains value-only even though the separate AD ABI exists.
- A complete DA system still needs dynamics, observation operators, covariance models, checkpointing, and minimization outside this microphysics ABI.

## Evidence

- [[kdm6-vs-kdm6ad-code-comparison-2026-06-25]]
- [[kdm6ad-20260610-presentation-adversarial-review]]
