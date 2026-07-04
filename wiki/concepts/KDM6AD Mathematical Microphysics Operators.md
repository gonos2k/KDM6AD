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
