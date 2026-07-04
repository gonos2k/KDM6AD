---
title: KDM6AD Differentiability Audit
type: concept
date_modified: 2026-06-25
---
# KDM6AD Differentiability Audit

## Definition

A KDM6AD differentiability audit is the set of checks needed before claiming that a microphysics tendency, state variable, or diagnostic has meaningful derivative semantics. It separates "AD can compute a derivative of the implementation" from "the derivative is physically interpretable."

## Audit Classes

| Class | Examples | Interpretation |
| --- | --- | --- |
| Smooth | gamma moments, power-law fall speeds away from zero | JVP/VJP should be stable and physically interpretable. |
| Piecewise smooth | autoconversion threshold, positivity clipping, min/max saturation guards | AD returns a branch-local derivative; kinks require one-sided or regime tests. |
| Iterative/adjustment | saturation adjustment, melting/freezing correction loops | derivative is of the numerical algorithm. |
| Numerical artifact risk | inconsistent moment sedimentation, reflectivity growth from size sorting numerics | derivative may be mathematically correct but physically misleading. |
| Diagnostic-only | `REFL_10CM`, `re_*`, `diag_rhog` in the forward host path | parity outputs unless explicitly included in the packed AD ABI. |

## Required Checks

Use both finite-difference and adjoint consistency checks:

```text
JVP: F(y + eps v) - F(y) ~= eps Jv
VJP: dot(Jv, w) ~= dot(v, J^T w)
```

Run these checks separately for smooth warm-rain cases, mixed-phase cases, sedimentation-on cases, graupel-density cases, and threshold-near cases. Failures near thresholds should be reported as nonsmoothness, not hidden.

## Manuscript Use

This audit supports a precise KDM6AD claim:

> KDM6AD exposes VJP/JVP products for the implemented microphysics map, with documented smooth, piecewise-smooth, diagnostic-only, and numerically fragile regions.

It prevents overclaiming that the online mp137 path differentiates all WRF diagnostics or that AD makes thresholded microphysics physically smooth.

## Source

Derived from [[kdm6plus-collection-mathematical-deep-ingest-2026-06-25]] and connected to [[KDM6AD Automatic Differentiation ABI]].

## Links

- [[KDM6AD]]
- [[KDM6AD Mathematical Microphysics Operators]]
- [[KDM6AD Forward Parity]]
- [[Differentiable Bulk Microphysics Research Gap]]
