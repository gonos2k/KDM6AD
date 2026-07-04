---
title: KDM6AD Code Story and Literature Review
instance_of: Source
page_kind: source-page
date_ingested: 2026-06-25
epistemic_status: inferred
provenance:
  sources:
    - wiki/sources/kdm6-microphysics-zotero-survey-2026-06-25.md
    - wiki/queries/kdm6ad-differentiable-microphysics-zotero-kg-2026-06-25.md
  code_refs:
    - host/KIM-meso_v1.0/phys/module_microphysics_driver.F
    - host/KIM-meso_v1.0/phys/module_mp_kdm6ad.F
    - host/KIM-meso_v1.0/phys/kdm6_iso_c.F
    - libtorch/bridge/kdm6_c_api.cpp
    - libtorch/src/runtime.cpp
    - host/KIM-meso_v1.0/phys/Makefile
---
# KDM6AD Code Story and Literature Review

## Summary

This note turns the current [[KDM6AD]] code configuration into a manuscript-ready story. The core narrative is not "we made a new microphysics scheme." It is:

> [[KDM6AD]] is a parity-preserving differentiable implementation surface for a KDM/WDM-family bulk microphysics scheme. It keeps the operational WRF/KIM path behaviorally aligned with [[KDM6]] while adding a separate fp64 VJP/JVP interface for sensitivity and DA-oriented work.

The literature explains why this is worth doing: KDM/WDM-family microphysics is sensitive to number concentrations, CCN, graupel/riming properties, particle-size distributions, sedimentation, and subgrid/cloudiness treatment. The code explains how this can be done without breaking operational parity: mp137 mirrors the mp37 host interface, stages state into a C ABI, runs a libtorch C++ mirror, computes forward-only diagnostics where the host expects them, and keeps AD behind a separate packed fp64 handle ABI.

## Story Spine

### Act 1: The scientific object is mature, not new

The KDM6AD paper should begin from the WDM/KDM lineage. WDM6 was developed from WSM6 by adding prognostic number concentrations for cloud and rain plus prognostic CCN, which gives flexibility in raindrop size distributions at reasonable cost. WDM6 evaluation work then connects these degrees of freedom to convective structure, bow echoes, spurious rainfall reduction, and East Asian monsoon rainfall. Recent WDM6/WDM7 work pushes the same lineage toward graupel density, mixed-phase terminal velocity, Korean Peninsula convection, and ICE-POP winter-storm evaluation.

Code hook: the current host keeps mp37 [[KDM6]] and mp137 [[KDM6AD]] as separate `CASE` branches. `module_microphysics_driver.F` calls `kdm6` for `KDM6SCHEME` and `kdm6ad` for `KDM6ADSCHEME`, with the same WRF-facing state and diagnostic arguments (`Q*`, `N*`, `BG`, `diag_rhog`, `REFL_10CM`, `re_*`, precipitation accumulators).

Interpretation: the first claim is lineage preservation. KDM6AD is valuable because it differentiates an established family of physics, not because it invents different physics.

### Act 2: The hard problem is preserving forward behavior

The implementation has to satisfy a stronger condition than "runs without crashing." The mp137 wrapper must behave like mp37 at the host boundary. This matters because radiation, radar reflectivity, graupel density, and precipitation accumulators feed later model behavior. A small difference in a diagnostic can become a trajectory difference even if the primary prognostic fields match for a single call.

Code hook: `module_mp_kdm6ad.F` stages WRF arrays into `REAL(c_float)` buffers, calls `kdm6_step` with `param_grad_flags=0` and `value_only=1`, copies output state back, writes `diag_rhog`, and recomputes `re_cloud/re_ice/re_snow` and `REFL_10CM` using the same KDM6 Fortran helper routines. The build keeps `-ffp-contract=off` for both KDM6 and KDM6AD Fortran objects and requires the libtorch port before the Fortran bridge objects link.

Interpretation: parity is the credibility gate. Without parity, any derivative result would be sensitivity of a different scheme.

### Act 3: AD is added as a separate surface, not mixed into the WRF path

The operational path is forward-only: it calls `kdm6_step_c` through ISO_C and returns `NULL` handle when `value_only=1`. The differentiable path is separate: `kdm6_step_ad_c` accepts packed fp64 state/forcing buffers, enables `requires_grad` when `value_only=0`, returns a handle, and exposes VJP/JVP through `kdm6_handle_vjp_c` and `kdm6_handle_jvp_c`.

Code hook: `kdm6_iso_c.F` declares both the f32 operational ABI and the fp64 DA ABI. `kdm6_c_api.cpp` implements packed Fortran-column-major state blocks for the DA buffers, records graph dtype on the handle, and keeps `diag_rhog/RHOPO3D` out of the adjoint packed ABI. `runtime.cpp` uses `torch::NoGradGuard` in value-only mode and constructs a `Handle` only in graph-retaining mode.

Interpretation: the paper should call this an AD-capable ABI, not "the online WRF path is differentiating." That precision prevents overclaiming.

### Act 4: The literature says which gradients are worth showing

Algorithmic differentiation for cloud microphysics has already been shown useful for ranking hundreds of uncertain parameters and identifying timing/magnitude of sensitivities. That result directly supports KDM6AD's handle-based VJP/JVP surface. But KDM6AD should not present gradients generically. It should target axes that the microphysics literature already identifies as meaningful:

- cloud/rain number concentration and CCN;
- graupel density, rime mass/volume, fall velocity, and particle diameter;
- particle-size distribution closure and spectral shape;
- sedimentation/advection consistency;
- partial cloudiness and subgrid condensate variability;
- diagnostic boundaries such as radar reflectivity and effective radius.

Code hook: the packed AD state order `th,qv,qc,qr,qi,qs,qg,nccn,nc,ni,nr,bg` maps directly to these axes. `BG` is especially important because the WDM6 graupel-density literature identifies prognostic graupel density as a recent and scientifically motivated extension.

Interpretation: the strongest results section is not "we can compute gradients." It is "we compute gradients for physically motivated axes while preserving mp37-forward parity."

## Literature-to-Code Map

| Literature point | Best reference anchor | Code explanation hook |
| --- | --- | --- |
| WDM6 extends WSM6 with cloud/rain number concentrations and prognostic CCN. | Lim and Hong 2010, DOI `10.1175/2009MWR2968.1` | `NC`, `NR`, `NN` are first-class wrapper/ABI fields, not hidden diagnostics. |
| WDM6 forward evaluation improves convective and monsoon precipitation behavior relative to WSM6. | Hong et al. 2010, DOI `10.1155/2010/707253` | mp37/mp137 parity should be evaluated at WRF diagnostic outputs, not only state tensors. |
| Prognostic graupel density changes fall velocity, sedimentation, surface graupel, and Korean winter precipitation bias. | Park et al. 2024, DOI `10.5194/gmd-17-7199-2024` | `BG` is included in the state and `diag_rhog` is surfaced as forward diagnostic; graupel density is a story-critical variable. |
| AD can rank cloud microphysics parameter sensitivities across many uncertain parameters. | Hieronymus et al. 2022, DOI `10.1029/2021MS002849` | `kdm6_step_ad_c`, `kdm6_handle_vjp_c`, and `kdm6_handle_jvp_c` provide the VJP/JVP surface needed for such workflows. |
| Cloud microphysics has parametric and structural uncertainty; differentiable programming is a promising systematic-development tool. | Lamb et al. 2026, DOI `10.1029/2025MS005341` | KDM6AD targets the "differentiable framework" gap for a legacy KDM/WDM scheme. |
| Fortran remains central in HPC models while PyTorch/ML tools are attractive for differentiable or hybrid components. | Atkinson et al. 2025 FTorch, DOI `10.21105/joss.07602` | KDM6AD chooses a C/ISO_C ABI rather than requiring the host to become a Python model. |
| Aerosol/CCN and IFN populations strongly shape mixed-phase pathways. | Vié et al. 2016 LIMA, DOI `10.5194/gmd-9-567-2016` | `NN`, `NC`, and land/sea `ncmin` staging are not incidental; they connect gradients to aerosol-aware controls. |
| Ice particle properties can evolve as prognostic bulk properties instead of fixed categories. | Morrison and Milbrandt 2015 P3, DOI `10.1175/JAS-D-14-0065.1` | `BG` and `diag_rhog` should be described as part of the broader particle-property trend. |
| Multimoment sedimentation can create numerical artifacts if moments use inconsistent fall velocities. | Mansell 2010, DOI `10.1175/2010JAS3341.1` | KDM6AD should separate "differentiated numerical response" from "physically meaningful sensitivity." |
| JAX-based models show the broader movement toward differentiable atmospheric modeling. | JAX-SCM 2026 preprint, DOI `10.5194/egusphere-2026-2916`; JCM 2026 preprint, DOI `10.5194/egusphere-2025-6266` | KDM6AD is the legacy-Fortran/HPC variant of the same trend, not a pure-JAX rewrite. |

## Code Storyboard

### Figure 1: Two schemes, one host surface

Draw the WRF/KIM microphysics driver as a fork:

```text
module_microphysics_driver.F
  ├─ CASE KDM6SCHEME    → CALL kdm6    → module_mp_kdm6.F
  └─ CASE KDM6ADSCHEME  → CALL kdm6ad  → module_mp_kdm6ad.F
```

Caption point: both branches receive the same physical state and host diagnostics, so KDM6AD is judged against KDM6 at the host boundary.

### Figure 2: Wrapper as a parity membrane

Draw `module_mp_kdm6ad.F` as the layer that preserves WRF semantics:

```text
WRF arrays
  → REAL(c_float) staging
  → kdm6_iso_c.F
  → kdm6_step_c
  → libtorch C++ physics
  → copy-back state
  → Fortran diagnostics: diag_rhog, re_*, REFL_10CM, precipitation increments
```

Caption point: diagnostics are deliberately computed or reconciled at the wrapper boundary because the host consumes them as forward model outputs.

### Figure 3: Two ABI surfaces

Draw two separate lanes:

```text
Operational lane:
  kdm6_step_c(float*, value_only=1) → state_out + diagnostics + no handle

DA lane:
  kdm6_step_ad_c(double packed state, value_only=0)
    → state_out packed + handle
    → kdm6_handle_vjp_c / kdm6_handle_jvp_c
```

Caption point: the online mp137 path is deterministic and forward-only; derivative products are obtained through a separate fp64 packed ABI.

## Suggested Manuscript Narrative

### Korean draft

기존 KDM/WDM 계열 미세물리과정은 구름 및 강수 입자의 질량뿐 아니라 수농도, CCN, graupel 밀도, 입자 크기 분포, 침강 속도와 같은 변수에 민감하다. 선행 연구는 이러한 선택들이 강수 구조, 반사도, 겨울 강수 편향, aerosol-cloud 상호작용에 영향을 준다는 점을 보여 주었다. 그러나 이 계열의 운영 코드 대부분은 Fortran 기반의 비미분가능한 형태로 유지되어, 다수의 물리 매개변수와 상태 변수에 대한 국소 민감도 또는 자료동화용 선형화 정보를 직접 얻기 어렵다.

KDM6AD는 이 간극을 메우기 위해 KDM6의 운영 forward behavior를 보존하면서 별도의 자동미분 ABI를 제공하는 구조로 설계되었다. WRF/KIM host에서는 `mp_physics=37`이 원본 KDM6을 호출하고, `mp_physics=137`이 KDM6AD wrapper를 호출한다. KDM6AD wrapper는 원본과 같은 host argument surface를 유지한 채 상태 변수를 C ABI로 전달하고, libtorch 기반 C++ mirror에서 미세물리 forward step을 수행한 뒤, WRF가 기대하는 prognostic state와 diagnostic field를 되돌린다.

중요한 설계 선택은 운영 forward 경로와 미분 경로의 분리이다. 운영 경로는 f32 상태와 `value_only=1`로 실행되어 host parity를 우선한다. 반면 DA 경로는 packed fp64 state와 forcing을 사용하고, handle 기반 VJP/JVP를 통해 민감도 계산을 제공한다. 이 분리는 `diag_rhog`, `REFL_10CM`, effective radius와 같은 forward diagnostic의 의미를 보존하면서도, 자료동화 또는 매개변수 민감도 분석에 필요한 미분가능한 표면을 제공한다.

따라서 KDM6AD의 기여는 새로운 미세물리 parameterization이 아니라, 기존 KDM/WDM 계열 물리의 forward parity를 보존한 상태에서 AD 기반 민감도 분석과 향후 DA/ML 연계를 가능하게 하는 구현 방법론이다.

### English draft

KDM6AD is designed as a parity-preserving differentiable implementation surface for a KDM/WDM-family bulk microphysics scheme. The operational host interface remains aligned with the original KDM6 scheme: `mp_physics=37` dispatches to the Fortran KDM6 implementation, while `mp_physics=137` dispatches to a Fortran wrapper that stages the same prognostic and diagnostic fields into a C/ISO_C ABI and calls a libtorch C++ mirror.

The implementation deliberately separates operational execution from derivative evaluation. The online WRF/KIM path uses a value-only f32 ABI to preserve forward behavior and host diagnostics. A separate packed fp64 ABI exposes reusable VJP/JVP handles for sensitivity or data-assimilation workflows. This separation is essential because cloud microphysics sensitivities identified in the literature, including CCN activation, hydrometeor number concentration, graupel density, fall velocity, sedimentation, and particle-size closure, are scientifically meaningful only when differentiated around a forward model that remains faithful to the reference scheme.

## Claims To Make

- KDM6AD is a differentiable implementation surface for an existing KDM/WDM-family scheme.
- Forward parity is a first-order scientific requirement, not only a software regression test.
- The AD ABI is designed for sensitivity/DA workflows through fp64 packed state and VJP/JVP handles.
- The code structure is compatible with legacy WRF/KIM Fortran hosts through C/ISO_C rather than requiring a host rewrite.
- The most important derivative axes are already motivated by microphysics literature: CCN, number concentration, graupel density, sedimentation, and particle-size distribution choices.

## Claims To Avoid

- Do not claim that KDM6AD is a new microphysics scheme.
- Do not claim the online WRF `mp_physics=137` path is itself running differentiable training or DA.
- Do not claim all diagnostics have derivative semantics. `diag_rhog`, `REFL_10CM`, and `re_*` are forward diagnostics at the host boundary.
- Do not claim full physical smoothness. Saturation adjustment, clipping, thresholds, category transitions, and sedimentation gates can create piecewise or nonsmooth derivative behavior.

## Full-Text Priorities Before Paper Draft

1. Lim and Hong 2010 (`10.1175/2009MWR2968.1`) for exact WDM6 prognostic variable formulation.
2. Park et al. 2024 (`10.5194/gmd-17-7199-2024`) for graupel density and `BG` motivation.
3. Hieronymus et al. 2022 (`10.1029/2021MS002849`) for AD sensitivity framing and expected cost/benefit.
4. Lamb et al. 2026 (`10.1029/2025MS005341`) for modern differentiable/ML cloud microphysics framing.
5. Mansell 2010 (`10.1175/2010JAS3341.1`) for sedimentation artifacts and derivative-interpretation caution.

## Source URLs

- https://doi.org/10.1175/2009MWR2968.1
- https://doi.org/10.1155/2010/707253
- https://doi.org/10.5194/gmd-17-7199-2024
- https://doi.org/10.1029/2021MS002849
- https://doi.org/10.1029/2025MS005341
- https://doi.org/10.21105/joss.07602
- https://doi.org/10.5194/gmd-9-567-2016
- https://doi.org/10.1175/JAS-D-14-0065.1
- https://doi.org/10.1175/2010JAS3341.1
- https://doi.org/10.5194/egusphere-2026-2916
- https://doi.org/10.5194/egusphere-2025-6266

## Links

- [[KDM6]]
- [[KDM6AD]]
- [[WRF KIM-meso Host]]
- [[KDM6AD Automatic Differentiation ABI]]
- [[KDM6AD Forward Parity]]
- [[Bulk Microphysics Design Space]]
- [[Differentiable Bulk Microphysics Research Gap]]
- [[kdm6-microphysics-zotero-survey-2026-06-25]]
- [[kdm6ad-differentiable-microphysics-zotero-kg-2026-06-25]]
