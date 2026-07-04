---
title: KDM6+ Collection Mathematical Deep Ingest
instance_of: Source
page_kind: source-page
date_ingested: 2026-06-25
epistemic_status: observed/inferred
provenance:
  zotero_collection: KDM6+ / ZABGLNPX
  zotero_items: 42
  pdf_fulltext_items: 35
  no_pdf_items: 7
  staging_dir: .omo/kg-ingest-kdm6plus-20260625/staging
  fulltext_manifest: .omo/kg-ingest-kdm6plus-20260625/kdm6plus_collection_fulltext_manifest.json
  prior_sources:
    - wiki/sources/kdm6-microphysics-zotero-survey-2026-06-25.md
    - wiki/sources/kdm6ad-code-story-literature-review-2026-06-25.md
    - wiki/sources/kdm6ad-kdm6plus-literature-set-2026-06-25.md
---
# KDM6+ Collection Mathematical Deep Ingest

## Scope

This page ingests the current Zotero `KDM6+` collection after narrowing it to KDM6/KDM6AD-relevant references only. The collection now contains 42 top-level Zotero items. Thirty-five have attached PDFs and seven remain metadata-only. The purpose of this ingest is not another shallow bibliography. It extracts the mathematical and numerical structure that should drive a KDM6AD manuscript: particle-size distributions, moment closures, process-rate nonlinearities, sedimentation operators, graupel-density state variables, and VJP/JVP use in sensitivity and data assimilation.

The central thesis is:

> [[KDM6AD]] should be framed as a differentiable operator for an established KDM/WDM-family bulk microphysics map, not as a new physical scheme. The paper must specify the mathematical map being differentiated and identify where that map is smooth, piecewise smooth, diagnostic-only, or numerically fragile.

## Collection Result

- Ingested Zotero collection: `KDM6+` (`ZABGLNPX`)
- Staged abstract/metadata export: `.omo/kg-ingest-kdm6plus-20260625/staging` with 42 markdown source files.
- PDF text extraction manifest: `.omo/kg-ingest-kdm6plus-20260625/kdm6plus_collection_fulltext_manifest.json`.
- PDF coverage: 35/42.
- Metadata-only / full text still needed: `FPPAYJ7D`, `PR3T9Z88`, `R5RMW5GG`, `WC9TJWPA`, `LCVBT38U`, `DFJTS2Q8`, `WGYGYPHD`.

## Mathematical Object

KDM6AD should be written as a time-step map

```text
y_{n+1} = F_KDM6(y_n, x_n, theta; Delta t, Delta z, rho, p, T, masks)
```

where a practical KDM6AD state vector is close to

```text
y = (theta, qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg)
```

and the host also carries diagnostic fields such as radar reflectivity, effective radii, precipitation accumulators, and `diag_rhog`. The literature says that the scientifically important sensitivities are not arbitrary. They concentrate in:

- mass mixing ratios `q_x`;
- number concentrations `N_x`;
- CCN/aerosol activation variables;
- hydrometeor particle-size distribution parameters;
- graupel/riming density or particle-property variables such as `bg`;
- sedimentation and size sorting;
- cloud fraction or subgrid condensate variability;
- radar/reflectivity observation operators.

The differentiable interface is therefore a Jacobian problem:

```text
J_y      = dF_KDM6 / dy
J_theta  = dF_KDM6 / dtheta
J_x      = dF_KDM6 / dx
```

Forward-mode products are JVPs:

```text
delta y_{n+1} = J_y delta y_n + J_theta delta theta + J_x delta x_n
```

Reverse-mode products are VJPs:

```text
lambda_n      = J_y^T lambda_{n+1}
lambda_theta += J_theta^T lambda_{n+1}
```

This is the correct language for the paper: KDM6AD exposes derivatives of the implemented time-step map. It does not automatically make every diagnostic or thresholded branch physically differentiable.

## Bulk PSD and Moment Mathematics

Most of the KDM/WDM-relevant papers use the standard bulk assumption that a hydrometeor category `x` has a particle-size distribution approximated by a generalized gamma/exponential form:

```text
n_x(D) = N0_x D^{mu_x} exp(-lambda_x D)
```

The kth diameter moment is

```text
M_k = integral_0^infty D^k n_x(D) dD
    = N0_x Gamma(mu_x + k + 1) / lambda_x^{mu_x+k+1}.
```

If `q_x` is a mass mixing ratio and `N_x` is a number mixing ratio, the usual spherical mass relation gives, up to density and air-density conventions,

```text
q_x ~ (pi rho_x / 6 rho_air) M_3
N_x ~ M_0 / rho_air
lambda_x = [ pi rho_x N_x Gamma(mu_x+4)
             / (6 q_x Gamma(mu_x+1)) ]^{1/3}.
```

This formula is manuscript-critical. It shows why a two-moment scheme is not just "more variables." Predicting `q_x` and `N_x` changes `lambda_x`, and any process depending on powers of `D` receives a nonlinear sensitivity through `lambda_x`. In AD terms, the derivative of a process rate `P(lambda(q,N), q, N)` contains both direct and PSD-induced terms:

```text
dP = P_q dq + P_N dN + P_lambda (lambda_q dq + lambda_N dN).
```

Milbrandt and Yau Part I (`UTM4WM2T`, DOI `10.1175/JAS3534.1`) is the clearest PSD-shape reference. It emphasizes the three-parameter gamma spectrum and the role of the shape parameter `mu`/`alpha` in size sorting and instantaneous growth rates. Part II (`4NU3SNG7`, DOI `10.1175/JAS3535.1`) extends this to a third moment, radar reflectivity, so that the shape parameter can become prognostic rather than fixed. For KDM6AD, this means reflectivity is not a passive output: mathematically, reflectivity is a high-order PSD moment.

Radar reflectivity can be sketched as

```text
Z_x ~ integral D^6 n_x(D) dD
    = N0_x Gamma(mu_x+7) / lambda_x^{mu_x+7}.
```

Therefore small perturbations in `lambda_x` or `N0_x` can produce much larger changes in `Z` than in mass. A KDM6AD manuscript must not claim reflectivity derivatives unless the packed AD ABI actually includes the reflectivity operator. At present, `REFL_10CM` is a forward diagnostic boundary in the host path.

## Process-Rate Nonlinearity

The collection repeatedly shows that microphysical tendencies are sums of nonlinear source and sink terms:

```text
dq_x/dt = sum_i P_{i -> x} - sum_j P_{x -> j} - d(V_q q_x)/dz + mixing/advection
dN_x/dt = sum_i S^N_{i -> x} - sum_j S^N_{x -> j} - d(V_N N_x)/dz + mixing/advection.
```

Examples include autoconversion, accretion, collection, freezing, melting, deposition, sublimation, breakup, riming, and sedimentation. In an AD implementation this is important because each term has different smoothness:

- polynomial/power-law rates are locally differentiable away from zero;
- thresholded rates such as `max(qc-qcrit,0)` are piecewise differentiable but have nondifferentiable kinks;
- saturation adjustment often includes clipping, iteration, or regime switches;
- lookup or category-change logic creates derivative discontinuities;
- sedimentation limiters and positivity fixes can zero out or distort sensitivities.

Pincus and Klein (`S2R9LH3S`, DOI `10.1029/2000JD900504`) gives the cleanest mathematical warning. If a process rate behaves like `R(q)=q^n`, then using a grid-mean condensate in place of the subgrid distribution gives

```text
R(mean(q)) != mean(R(q)).
```

For a cloud fraction `C` with in-cloud condensate `q_c/C`, a process of order `n` scales like

```text
P_grid = C P(q_c/C) ~ C^(1-n) q_c^n.
```

Thus for `n>1`, partial cloudiness amplifies conversion/accretion tendencies relative to a homogeneous gridbox. Kim et al. (`YKPE6B2X`, DOI `10.1029/2018JD029519`) gives the operational version: in-cloud values are obtained by dividing grid-mean hydrometeor mixing ratios by cloud fraction, which enhances accretion/autoconversion and reduces some evaporation/sublimation effects. For KDM6AD, cloud fraction is therefore an AD-sensitive structural variable, not an implementation detail.

## WDM6/KDM6 Lineage

Lim and Hong (`6P3B5EDZ`, DOI `10.1175/2009MWR2968.1`) defines the WDM6 move beyond WSM6: water vapor, cloud water, rain, cloud ice, snow, and graupel remain the six water species, but cloud and rain number concentrations plus prognostic CCN become active variables. Hong et al. (`H3KYIIM9`, DOI `10.1155/2010/707253`) evaluates this WDM6 formulation in WRF and ties the improvement in precipitating convection to a wider range of cloud/rain number concentrations. These two papers are the lineage anchor for KDM6AD.

The paper should make the variable connection explicit:

```text
WSM6-like mass state:      (qv, qc, qr, qi, qs, qg)
WDM6/KDM6 extended state: (qv, qc, qr, qi, qs, qg, Nc, Nr, Nccn, ...)
KDM6AD AD state:          (theta, qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg)
```

The new KDM6AD contribution is that this extended state can be treated as a differentiable map with forward parity to the legacy KDM6 implementation.

## Graupel Density and Particle Properties

Park et al. (`D629MKTV`, DOI `10.5194/gmd-17-7199-2024`) is central because it modifies WDM6 by predicting graupel density. The mathematical meaning is that graupel is no longer fully described by a fixed category with static mass-diameter and velocity-diameter coefficients. Instead, density modifies relations of the type

```text
m_g(D) = a_g D^{b_g}
V_g(D) = alpha_g D^{beta_g} (rho_0/rho_air)^gamma
rho_g(D) ~ 6 m_g(D) / (pi D^3).
```

When density changes, fall speed changes; when fall speed changes, sedimentation changes; when sedimentation changes, vertical graupel distribution and surface precipitation change. In KDM6AD, `bg`/`BG` should therefore be presented as a physically meaningful sensitivity axis. A derivative like

```text
d precipitation_surface / d bg
```

is not a generic gradient; it is a graupel sedimentation and riming-property sensitivity.

Morrison and Milbrandt P3 (`DKMG7MT6`, DOI `10.1175/JAS-D-14-0065.1`) generalizes the same idea. Ice particles are represented by evolving bulk properties rather than fixed categories. The relevant state variables include ice mass, number, rime mass, and rime volume/density. This supports a broader claim: KDM6AD is aligned with the literature trend from fixed categories to differentiable particle-property continua.

## Sedimentation and Numerical Consistency

Mansell (`WMBSU2NB`, DOI `10.1175/2010JAS3341.1`) is the main cautionary paper. In multimoment schemes, different moments often sediment with different weighted fall velocities. For a PSD,

```text
V_k = integral V(D) D^k n(D) dD / integral D^k n(D) dD.
```

With `V(D)=aD^b`, this becomes approximately

```text
V_k = a Gamma(mu+k+b+1) / Gamma(mu+k+1) lambda^{-b}.
```

Mass and number can therefore move at different effective velocities:

```text
dq/dt = -d(V_3 q)/dz
dN/dt = -d(V_0 N)/dz.
```

This permits physical size sorting but can also create numerical artifacts, including artificial reflectivity growth. For KDM6AD this is a major derivative-validity issue: AD can faithfully differentiate an artifact. The manuscript should include a "differentiability audit" separating:

- differentiable physics response;
- differentiable numerical artifact;
- nonsmooth limiter/positivity response;
- diagnostic-only response.

## AD and Sensitivity Literature

Hieronymus et al. (`HSCSIXWK`, DOI `10.1029/2021MS002849`) directly supports KDM6AD: AD can identify magnitude and timing of cloud microphysics sensitivity over many uncertain parameters. The parameters they highlight, such as hydrometeor diameter/fall velocity, CCN activation, and heterogeneous freezing, overlap the KDM/WDM design axes above.

Baumgartner et al. (`E6KDCS3V`, DOI `10.5194/gmd-12-5197-2019`) frames AD as a way to provide derivatives of cloud schemes to machine accuracy. The relevant mathematical distinction is:

```text
finite difference: [F(theta + eps e_i) - F(theta)] / eps
AD tangent:        J_theta e_i
AD adjoint:        J_theta^T lambda
```

Finite differences are simple but scale with the number of parameters and are contaminated by step-size and nonsmoothness. VJP/JVP products scale with the chosen tangent/adjoint workflow and can be used inside optimization or DA.

For KDM6AD, the verification identities should be explicit:

```text
JVP check:  F(y + eps v) - F(y) ~ eps Jv
VJP check:  <Jv, w> = <v, J^T w>
```

These are stronger than "gradients exist." They establish that the handle ABI returns mathematically consistent products for the implemented map.

## Data Assimilation Operator View

For DA, the cost function can be written

```text
J(x0, theta) =
  1/2 ||x0 - xb||_{B^{-1}}^2
  + 1/2 sum_k ||H_k(M_{0:k}(x0, theta)) - y_k||_{R_k^{-1}}^2.
```

The gradient requires adjoints of dynamics, microphysics, and observation operators:

```text
grad_x0 J =
  B^{-1}(x0-xb)
  + M'_{0:k}^T H'_k^T R_k^{-1} (H_k(M_{0:k}) - y_k).
```

KDM6AD contributes the microphysics block inside `M'` or `M'^T`. Radar reflectivity DA references (`BTZY27UZ`, `DMKR59F5`) show why this matters: reflectivity assimilation is sensitive to hydrometeor distributions, humidity, and precipitation structure. But reflectivity is a sixth-moment diagnostic and often involves nonlinear transforms, thresholds, attenuation/scattering assumptions, and hydrometeor category mappings. The paper should state clearly whether reflectivity is differentiated inside KDM6AD or only recomputed as a forward diagnostic for parity.

## ML and Fortran/PyTorch Coupling

SuperdropNet/ICON (`K6KQNP7S`, DOI `10.5194/gmd-17-4017-2024`) and FTorch (`4N5KCMYS`, DOI `10.21105/joss.07602`) support the implementation approach. They do not replace the physics argument, but they support a practical software claim: legacy Fortran atmosphere models can be coupled to modern ML/differentiable components without rewriting the host.

For KDM6AD this justifies the architecture:

```text
Fortran host arrays
  -> ISO_C staging
  -> C/C++ libtorch mirror
  -> value-only forward path for WRF parity
  -> separate fp64 AD handle path for JVP/VJP
```

This is distinct from Python-in-the-loop training. The online KIM/WRF path should remain deterministic and forward-only.

## Literature Ledger by Mathematical Role

### KDM/WDM lineage and Korean evaluation

| Key | DOI | Mathematical / manuscript role |
| --- | --- | --- |
| `6P3B5EDZ` | `10.1175/2009MWR2968.1` | WDM6 origin: `q` plus `Nc`, `Nr`, `Nccn`; variable PSD through number concentration. |
| `H3KYIIM9` | `10.1155/2010/707253` | WDM6 WRF evaluation; number concentration range explains precipitation changes. |
| `D629MKTV` | `10.5194/gmd-17-7199-2024` | Graupel density prediction; `bg`/density affects mass-diameter and fall-speed laws. |
| `5T4INXZ3` | `10.5194/gmd-15-4529-2022` | ICE-POP WRF scheme comparison; evaluation context for Korean winter storms. |
| `Y8G9YXWQ` | `10.3390/rs13193860` | WDM7/Korean convection; WDM-family evaluation and mixed-phase revisions. |
| `DFJTS2Q8` | `10.1007/s13143-018-0028-9` | KIM system context; metadata-only, verify full text before detailed citation. |

### PSD moments, closure, and sedimentation

| Key | DOI | Mathematical / manuscript role |
| --- | --- | --- |
| `UTM4WM2T` | `10.1175/JAS3534.1` | Gamma PSD `N(D)=N0 D^alpha exp(-lambda D)`; shape parameter controls sorting and growth. |
| `4NU3SNG7` | `10.1175/JAS3535.1` | Three-moment closure with reflectivity moment; high-order moment sensitivity. |
| `WMBSU2NB` | `10.1175/2010JAS3341.1` | Sedimentation/advection consistency; AD can differentiate artificial reflectivity growth. |
| `DKMG7MT6` | `10.1175/JAS-D-14-0065.1` | P3 Part I; prognostic ice particle properties and rime density. |
| `R5RMW5GG` | `10.1175/JAS-D-14-0066.1` | P3 Part II; metadata-only in current library. |
| `WC9TJWPA` | `10.1175/JAS-D-15-0204.1` | P3 Part III; metadata-only in current library. |
| `LCVBT38U` | `10.1175/MWR2810.1` | Particle-parameter uncertainty; metadata-only in current library. |

### Aerosol, CCN, and cloud fraction

| Key | DOI | Mathematical / manuscript role |
| --- | --- | --- |
| `S98KNIGB` | `10.5194/gmd-9-567-2016` | Aerosol/CCN/IFN driven quasi-two-moment scheme; activation and nucleation sensitivity. |
| `RXNFS727` | `10.1175/JAS-D-12-0264.1` | Aerosol effects on storm microphysics; CCN/graupel/electrification coupling. |
| `W5UHJDNL` | `10.1175/2009JAS2965.1` | Two-moment electrification; number and graupel density affect charging. |
| `S2R9LH3S` | `10.1029/2000JD900504` | Subgrid variability bias `mean(R(q)) != R(mean(q))`. |
| `YUBAXLI6` | `10.1175/JAS-D-17-0234.1` | Partial cloudiness concept for bulk microphysics. |
| `YKPE6B2X` | `10.1029/2018JD029519` | Cloud fraction scaling in WSM5-style microphysics; accretion/autoconversion response. |

### Differentiability, AD, and DA

| Key | DOI | Mathematical / manuscript role |
| --- | --- | --- |
| `HSCSIXWK` | `10.1029/2021MS002849` | AD for cloud microphysics sensitivity; supports KDM6AD VJP/JVP motivation. |
| `E6KDCS3V` | `10.5194/gmd-12-5197-2019` | AD for cloud schemes with CoDiPack; machine-accurate derivative framing. |
| `4ZRTINZD` | `10.48550/arxiv.2208.13825` | Differentiable programming for Earth-system modeling; broad methodological frame. |
| `H6I7RBDT` | `10.5194/egusphere-2025-6266` | Differentiable atmospheric model; broader AD model ecosystem. |
| `CNEVCLQJ` | `10.48550/arxiv.2605.24544` | JAX single-column model; differentiable SCM comparison. |
| `ZGBTAJKZ` | `10.48550/arxiv.2403.02215` | Joint parameter/parameterization inference; KDM6AD parameter-gradient use case. |
| `BTZY27UZ` | `10.5194/nhess-19-907-2019` | Cloud radar reflectivity assimilation; observation-operator motivation. |
| `DMKR59F5` |  | WRFDA-4DVAR radar reflectivity TL/AD context; no DOI in current Zotero metadata. |

### Fortran/PyTorch and ML parameterization coupling

| Key | DOI | Mathematical / manuscript role |
| --- | --- | --- |
| `K6KQNP7S` | `10.5194/gmd-17-4017-2024` | Stable coupling of ML microphysics with ICON; supports staged host coupling narrative. |
| `4N5KCMYS` | `10.21105/joss.07602` | Fortran/PyTorch coupling; supports C/ISO_C/libtorch integration claims. |
| `M9XUQ75C` | `10.48550/arxiv.2505.04358` | Equation discovery / automatic tuning; future parameterization-inference story. |
| `JSEKWT8Q` | `10.48550/arxiv.2304.08063` | Cloud-cover equation discovery; data-driven parameterization contrast. |

## What The KDM6AD Paper Should Derive Explicitly

### 1. The differentiated state and outputs

The paper should list the AD-packed state in order and distinguish it from forward diagnostics:

```text
AD state:        theta, qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg
Forward-only:    diag_rhog, REFL_10CM, re_cloud, re_ice, re_snow, accumulators
```

This prevents ambiguity about whether radar reflectivity and effective radius are differentiated or merely parity-preserved.

### 2. PSD closure derivatives

At least one appendix should derive how `lambda` changes with `q` and `N`. For the simplified two-moment relation

```text
lambda = C (N/q)^{1/3}
```

the logarithmic derivatives are

```text
d log(lambda) = (1/3) d log(N) - (1/3) d log(q).
```

Any fall-speed or reflectivity expression containing `lambda^{-b}` or `lambda^{-(mu+7)}` then has amplified sensitivity:

```text
d log(V_k) = -b d log(lambda)
d log(Z)   = -(mu+7) d log(lambda) + d log(N0).
```

This is the mathematical bridge from WDM6 number concentrations to KDM6AD gradients.

### 3. Sedimentation dot-product tests

For every JVP/VJP implementation claim, the paper should include a dot-product test:

```text
random v, w:
  abs( dot(Jv, w) - dot(v, J^T w) ) / scale < tolerance.
```

Run it separately for:

- warm rain only;
- mixed phase without sedimentation;
- sedimentation enabled;
- graupel density enabled;
- threshold-heavy cases near cloud/no-cloud and freezing/melting boundaries.

### 4. Nonsmoothness audit

The paper should not hide nondifferentiabilities. It should classify process terms:

| Class | Example | AD interpretation |
| --- | --- | --- |
| Smooth | gamma moment, power-law fall speed away from zero | standard local derivative |
| Piecewise smooth | autoconversion threshold, positivity limiter | one-sided or branch-local derivative |
| Iterative / adjustment | saturation adjustment, melting/freezing constraints | derivative of algorithm, not closed-form physics |
| Diagnostic-only | `REFL_10CM`, `re_*`, `diag_rhog` in host path | forward parity unless explicitly included in AD ABI |
| Numerical artifact risk | moment-inconsistent sedimentation | derivative may expose artifact |

## Manuscript-Level Claims Supported

- WDM6/KDM6 relevance: prognostic number concentrations and CCN make the scheme a meaningful target for sensitivity analysis.
- Forward parity requirement: without mp37/mp137 parity, derivatives would apply to a different scheme.
- Mathematical novelty: KDM6AD supplies VJP/JVP access to a legacy bulk microphysics map with physically interpretable state variables.
- Scientific sensitivity axes: `Nc`, `Nr`, `Nccn`, PSD closure, graupel density, sedimentation, and cloud fraction.
- DA extension: KDM6AD can supply the microphysics tangent/adjoint block, but reflectivity/effective-radius observation operators must be treated explicitly.

## Claims To Avoid

- Do not state that every KDM6 diagnostic is differentiable in the current ABI.
- Do not state that AD solves physical nonsmoothness from clipping or thresholding.
- Do not state that metadata-only P3/KIM papers have been full-text verified.
- Do not claim that online WRF mp137 is training or optimizing; it is the value-only forward path.

## Links

- [[KDM6]]
- [[KDM6AD]]
- [[KDM6AD Mathematical Microphysics Operators]]
- [[KDM6AD Differentiability Audit]]
- [[KDM6AD Automatic Differentiation ABI]]
- [[KDM6AD Forward Parity]]
- [[Bulk Microphysics Design Space]]
- [[Differentiable Bulk Microphysics Research Gap]]
