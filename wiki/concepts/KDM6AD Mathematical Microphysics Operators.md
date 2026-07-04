---
title: KDM6AD Mathematical Microphysics Operators
type: concept
date_modified: 2026-06-25
---
# KDM6AD Mathematical Microphysics Operators

## Definition

This concept records the mathematical operator view needed to describe [[KDM6AD]] rigorously. The object of differentiation is the implemented bulk microphysics time-step map:

```text
y_{n+1} = F_KDM6(y_n, x_n, theta)
```

where the practical KDM6AD state includes temperature/potential-temperature information, vapor and hydrometeor mixing ratios, number concentrations, CCN, and graupel-density state:

```text
y = (theta, qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg).
```

## PSD Moment Core

Most KDM/WDM-family bulk microphysics assumes a gamma-like particle-size distribution:

```text
n(D) = N0 D^mu exp(-lambda D)
M_k  = integral D^k n(D)dD
     = N0 Gamma(mu+k+1) / lambda^(mu+k+1).
```

Mass and number moments determine the PSD slope:

```text
lambda ~ (N/q)^(1/3).
```

This gives the main derivative bridge:

```text
d log(lambda) = (1/3)d log(N) - (1/3)d log(q).
```

Because fall speed and reflectivity depend on powers of `lambda`, a small number-concentration perturbation can produce a large diagnostic response:

```text
V_k ~ lambda^(-b)
Z   ~ lambda^(-(mu+7)).
```

## Tendency Operator

The generic tendency has the form:

```text
dq_x/dt = sources_x - sinks_x - d(V_q q_x)/dz
dN_x/dt = number_sources_x - number_sinks_x - d(V_N N_x)/dz.
```

For [[KDM6AD]], the important implementation question is whether the C++/libtorch mirror preserves the same branch structure, thresholding, limiter behavior, and diagnostic reconciliation as [[KDM6]].

## Sensitivity Axes

The KDM6+ collection identifies these first-order derivative axes:

- `Nccn`, `Nc`, `Nr`: activation and two-moment PSD control.
- `BG` / graupel density: fall speed, mass-diameter relation, riming/sedimentation.
- PSD shape/intercept/slope: high-order moment and reflectivity sensitivity.
- sedimentation: moment-consistency and size-sorting.
- cloud fraction/subgrid variability: process-rate nonlinear scaling.
- radar reflectivity: high-order diagnostic/observation operator, not automatically part of the AD state.

## Source

Derived from [[kdm6plus-collection-mathematical-deep-ingest-2026-06-25]].

## Links

- [[KDM6]]
- [[KDM6AD]]
- [[Bulk Microphysics Design Space]]
- [[KDM6AD Automatic Differentiation ABI]]
- [[KDM6AD Differentiability Audit]]
- [[Operational-Raw vs DA-Clamped Dual Path]]
- [[kdm6ad-differentiable-mathematics-2026-07-04]]

## Update (2026-07-04): 스텝의 합성-사상 정식화와 야코비안 연쇄

`docs/KDM6AD_differentiable_mathematics.md`(→ [[kdm6ad-differentiable-mathematics-2026-07-04]])가 한 물리
스텝을 명시적 합성 사상으로 확정:

$$F=\prod_{\ell=L}^{1} J_G^{(\ell)},\quad G=K\circ R\circ S,\quad K=L_{19}\cdots L_1.$$

- $S$ 침강 → $R$ 재기울기 → $K$ 미시물리 1패스, 소사이클 $L$회. `cur` 상태가 detach 없이 이어져 입력
  리프→출력이 단일 autograd 그래프.
- $K$는 **19개 부연산자**의 좌→우 합성(순서 기준은 C++ `coordinator.cpp:642-1291`; Python 오라클은 $L_9$
  완전강수증발 배치·Picons $n_i$ 게이트·최종 얼음 limiter에서 갈림).
- warm/cold/D5(연산자 8·10·11)는 **진단적**(rate만 방출) — 야코비안은 보존(12)·state_update(13)이 rate를
  소비할 때만 진입.
- state_update(13)는 수상 8필드 + $b_g$만 비음 클램프($q_v$·$n_{ccn}$·$\theta$는 비클램프).
- **야코비안은 역순 곱**: VJP는 우→좌(reverse), JVP는 좌→우(forward). → [[KDM6AD Automatic Differentiation ABI]].
