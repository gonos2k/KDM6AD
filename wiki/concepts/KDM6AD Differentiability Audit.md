---
title: KDM6AD Differentiability Audit
type: concept
date_modified: 2026-09-25
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

## Update (2026-07-04): 점프 vs 꺾임 구분 + 이중경로 정정

> [!warning] Tension — 이 페이지의 "min/max 클램프 = 균일 piecewise-smooth" 프레이밍이 두 가지로 정정됨
> `docs/KDM6AD_differentiable_mathematics.md`(→ [[kdm6ad-differentiable-mathematics-2026-07-04]]) §2.4·§8이
> 다음을 확정한다. **원래 서술(위 표)은 보존하되 아래로 보강**한다.
>
> 1. **점프 ≠ 꺾임**: 스위치 $\text{where}(cond,A,B)$는 경계에서 $A=B$면 연속(꺾임, 한쪽 편도함수 유효),
>    $A\neq B$면 **불연속(점프, 도함수·subgradient 부재)**. 균질동결·재분류(Picons·작은비→구름)·threshold
>    cleanup·완전증발($n_r\!\to\!n_{ccn}$)은 유한량을 옮기는 **점프**이지 kink가 아니다. autograd는 점프에서
>    활성 분기의 한쪽 편도함수만 반환하고, 점프를 관통하는 수학적 subgradient를 만들지 않는다.
> 2. **클램프는 균일하지 않다**: min/max saturation guard는 dtype 조건부다 — f32 작동 경로는 Fortran raw
>    ÷/sqrt를 위해 **클램프를 제거**하고, f64 DA 경로만 유지한다. → [[Operational-Raw vs DA-Clamped Dual Path]].

## Links

- [[KDM6AD]]
- [[Operational-Raw vs DA-Clamped Dual Path]]
- [[kdm6ad-differentiable-mathematics-2026-07-04]]
- [[KDM6AD Mathematical Microphysics Operators]]
- [[KDM6AD Forward Parity]]
- [[Differentiable Bulk Microphysics Research Gap]]

## Update (2026-09-25): S16 freeze-heat replay remains open

The retained v14 four-case capture reports a one-ULP stored-temperature
difference after freeze. Given its identical pre-heat `t` and f64 rates, its
differing `xlf`/`cpm`, and the declared source-order model, an independent replay
reproduces both stored results. Production intermediates were not emitted, so
this establishes sufficiency under that model, not the actual executables'
operation order. The v14 source finding traces the operands to kernel-entry
`xl`/`cpm` values in Fortran and per-subcycle recomputation in C++, but it is a
conditional explanation from a withdrawn artifact, not a decision-grade
current-source conclusion. See [[kdm6ad-s16-freeze-heat-replay-2026-09-25]].

S16 remains OPEN because the v14 result is withdrawn, the retained Fortran
bundles fail the current evidence-tree attestation check, and the archived
legacy module hash differs from the current private host source. The bounded
replay does not certify a current-source host run or close C4 G3.3's separate
legacy ULP envelope.
