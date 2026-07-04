---
title: KDM6AD KDM6+ Literature Set
instance_of: Source
page_kind: source-page
date_ingested: 2026-06-25
epistemic_status: observed
provenance:
  zotero_collection: KDM6+ / ZABGLNPX
  scope_rule: kdm6ad OR kdm6ad-literature OR kdm6-microphysics-survey
---
# KDM6AD KDM6+ Literature Set

## 범위

이 노트는 Zotero 컬렉션 `KDM6+`에 남긴 KDM6/KDM6AD 전용 문헌 세트이다. 방금 `Desktop/Paper`에서 수집한 일반 기상, 예측, 자료동화 논문은 Zotero 라이브러리에는 유지하되 이 컬렉션에서는 제외했다.

- 컬렉션 항목: 42건
- PDF 원문 확보: 35건
- 원문 보강 필요: 7건
- Zotero 필터 태그: `kdm6ad-paper-writing`
- BibTeX export: `wiki/sources/kdm6ad-kdm6plus-literature-2026-06-25.bib`

## 원고 스토리라인

1. KDM6AD는 새로운 미세물리 scheme이 아니라 KDM/WDM 계열 bulk microphysics를 forward parity를 유지하면서 자동미분 가능한 구현 표면으로 재구성한 것이다.
2. 핵심 물리 축은 수농도, CCN, graupel density/BG, 입자 크기분포, 침강/이류 일관성, 부분운량/아격자 변동성이다.
3. 구현 축은 Fortran host를 유지하면서 C/ISO_C와 libtorch를 통해 별도 VJP/JVP 표면을 제공하는 것이다.
4. 확장 축은 microphysics sensitivity, parameter inference, radar/observation DA로 이어진다. 단, 진단장과 threshold/clip/saturation adjustment의 미분 해석은 명확히 제한해야 한다.

## 우선 인용 후보

| Zotero key | Year | DOI | 용도 | 제목 |
| --- | --- | --- | --- | --- |
| `6P3B5EDZ` | 2010 | `10.1175/2009mwr2968.1` | KDM/WDM6 계열의 과학적 계보와 forward parity 기준 | Development of an Effective Double-Moment Cloud Microphysics Scheme with Prognostic Cloud Condensation Nuclei (CCN) for Weather and Climate Models |
| `H3KYIIM9` | 2010 | `10.1155/2010/707253` | KDM/WDM6 계열의 과학적 계보와 forward parity 기준 | Evaluation of the WRF Double‐Moment 6‐Class Microphysics Scheme for Precipitating Convection |
| `D629MKTV` | 2024 | `10.5194/gmd-17-7199-2024` | KDM/WDM6 계열의 과학적 계보와 forward parity 기준 | Introducing graupel density prediction in Weather Research and Forecasting (WRF) double-moment 6-class (WDM6) microphysics and evaluation of the modified scheme during the ICE-POP field campaign |
| `5T4INXZ3` | 2022 | `10.5194/gmd-15-4529-2022` | KDM/WDM6 계열의 과학적 계보와 forward parity 기준 | Simulated microphysical properties of winter storms from bulk-type microphysics schemes and their evaluation in the Weather Research and Forecasting (v4.1.3) model during the ICE-POP 2018 field campaign |
| `Y8G9YXWQ` | 2021 | `10.3390/rs13193860` | 미세물리 설계공간 또는 비교 문헌 | Revision of WDM7 Microphysics Scheme and Evaluation for Precipitating Convection over the Korean Peninsula |
| `HSCSIXWK` | 2022 | `10.1029/2021ms002849` | KDM6AD의 민감도/AD 필요성을 뒷받침하는 직접 근거 | Algorithmic Differentiation for Sensitivity Analysis in Cloud Microphysics |
| `E6KDCS3V` | 2019 | `10.5194/gmd-12-5197-2019` | KDM6AD의 민감도/AD 필요성을 뒷받침하는 직접 근거 | Algorithmic differentiation for cloud schemes (IFS Cy43r3) using CoDiPack (v1.8.1) |
| `4N5KCMYS` | 2025 | `10.21105/joss.07602` | Fortran 모델과 PyTorch/ML 컴포넌트 결합 근거 | FTorch: a library for coupling PyTorch models to Fortran |
| `S98KNIGB` | 2016 | `10.5194/gmd-9-567-2016` | CCN/aerosol 및 수농도 민감도 축 | LIMA (v1.0): A quasi two-moment microphysical scheme driven by a multimodal population of cloud condensation and ice freezing nuclei |
| `WMBSU2NB` | 2010 | `10.1175/2010jas3341.1` | 침강/이류 수치일관성과 미분 해석 주의점 | On Sedimentation and Advection in Multimoment Bulk Microphysics |
| `DKMG7MT6` | 2015 | `10.1175/jas-d-14-0065.1` | 미세물리 설계공간 또는 비교 문헌 | Parameterization of Cloud Microphysics Based on the Prediction of Bulk Ice Particle Properties. Part I: Scheme Description and Idealized Tests |
| `UTM4WM2T` | 2005 | `10.1175/jas3534.1` | 미세물리 설계공간 또는 비교 문헌 | A Multimoment Bulk Microphysics Parameterization. Part I: Analysis of the Role of the Spectral Shape Parameter |
| `4NU3SNG7` | 2005 | `10.1175/jas3535.1` | 미세물리 설계공간 또는 비교 문헌 | A Multimoment Bulk Microphysics Parameterization. Part II: A Proposed Three-Moment Closure and Scheme Description |
| `BTZY27UZ` | 2019 | `10.5194/nhess-19-907-2019` | 자료동화·관측 연계 확장 근거 | Impact of airborne cloud radar reflectivity data assimilation on kilometre-scale numerical weather prediction analyses and forecasts of heavy precipitation events |

## KDM/WDM 계열 핵심 미세물리

| Zotero key | Year | PDF | DOI | 원고 내 역할 | 제목 |
| --- | --- | ---: | --- | --- | --- |
| `LDHPT85H` | 2005 | Y | `10.1175/jas3446.1` | 미세물리 설계공간 또는 비교 문헌 | A New Double-Moment Microphysics Parameterization for Application in Cloud and Climate Models. Part I: Description |
| `6P3B5EDZ` | 2010 | Y | `10.1175/2009mwr2968.1` | KDM/WDM6 계열의 과학적 계보와 forward parity 기준 | Development of an Effective Double-Moment Cloud Microphysics Scheme with Prognostic Cloud Condensation Nuclei (CCN) for Weather and Climate Models |
| `H3KYIIM9` | 2010 | Y | `10.1155/2010/707253` | KDM/WDM6 계열의 과학적 계보와 forward parity 기준 | Evaluation of the WRF Double‐Moment 6‐Class Microphysics Scheme for Precipitating Convection |
| `54NAR859` | 2011 | Y | `10.1175/2010mwr3293.1` | 미세물리 설계공간 또는 비교 문헌 | A New Bulk Microphysical Scheme That Includes Riming Intensity and Temperature-Dependent Ice Characteristics |
| `S98KNIGB` | 2016 | Y | `10.5194/gmd-9-567-2016` | CCN/aerosol 및 수농도 민감도 축 | LIMA (v1.0): A quasi two-moment microphysical scheme driven by a multimodal population of cloud condensation and ice freezing nuclei |
| `Y8G9YXWQ` | 2021 | Y | `10.3390/rs13193860` | 미세물리 설계공간 또는 비교 문헌 | Revision of WDM7 Microphysics Scheme and Evaluation for Precipitating Convection over the Korean Peninsula |
| `5T4INXZ3` | 2022 | Y | `10.5194/gmd-15-4529-2022` | KDM/WDM6 계열의 과학적 계보와 forward parity 기준 | Simulated microphysical properties of winter storms from bulk-type microphysics schemes and their evaluation in the Weather Research and Forecasting (v4.1.3) model during the ICE-POP 2018 field campaign |
| `D629MKTV` | 2024 | Y | `10.5194/gmd-17-7199-2024` | KDM/WDM6 계열의 과학적 계보와 forward parity 기준 | Introducing graupel density prediction in Weather Research and Forecasting (WRF) double-moment 6-class (WDM6) microphysics and evaluation of the modified scheme during the ICE-POP field campaign |

## 미세물리 설계공간

| Zotero key | Year | PDF | DOI | 원고 내 역할 | 제목 |
| --- | --- | ---: | --- | --- | --- |
| `66SUJCSY` | 1983 | Y | `10.1175/1520-0450(1983)022<1065:bpotsf>2.0.co;2` | 미세물리 설계공간 또는 비교 문헌 | Bulk Parameterization of the Snow Field in a Cloud Model |
| `L2BC8MGF` | 1989 | Y | `10.1175/1520-0493(1989)117<0231:aiwsa>2.0.co;2` | 미세물리 설계공간 또는 비교 문헌 | An Ice-Water Saturation Adjustment |
| `S2R9LH3S` | 2000 | Y | `10.1029/2000jd900504` | 격자 평균 과정률과 부분운량/아격자 변동성 이슈 | Unresolved spatial variability and microphysical process rates in large‐scale models |
| `UTM4WM2T` | 2005 | Y | `10.1175/jas3534.1` | 미세물리 설계공간 또는 비교 문헌 | A Multimoment Bulk Microphysics Parameterization. Part I: Analysis of the Role of the Spectral Shape Parameter |
| `4NU3SNG7` | 2005 | Y | `10.1175/jas3535.1` | 미세물리 설계공간 또는 비교 문헌 | A Multimoment Bulk Microphysics Parameterization. Part II: A Proposed Three-Moment Closure and Scheme Description |
| `7JDU3L3I` | 2008 | Y | `10.1175/2008jcli2105.1` | 미세물리 설계공간 또는 비교 문헌 | A New Two-Moment Bulk Stratiform Cloud Microphysics Scheme in the Community Atmosphere Model, Version 3 (CAM3). Part I: Description and Numerical Tests |
| `Q7L5Z453` | 2008 | Y | `10.1175/2008jcli2116.1` | 미세물리 설계공간 또는 비교 문헌 | A New Two-Moment Bulk Stratiform Cloud Microphysics Scheme in the Community Atmosphere Model, Version 3 (CAM3). Part II: Single-Column and Global Results |
| `3FNR6KLT` | 2008 | Y | `10.1175/2008mwr2387.1` | 미세물리 설계공간 또는 비교 문헌 | Explicit Forecasts of Winter Precipitation Using an Improved Bulk Microphysics Scheme. Part II: Implementation of a New Snow Parameterization |
| `VJK3VRCB` | 2009 | Y | `10.1175/2008mwr2556.1` | 미세물리 설계공간 또는 비교 문헌 | Impact of Cloud Microphysics on the Development of Trailing Stratiform Precipitation in a Simulated Squall Line: Comparison of One- and Two-Moment Schemes |
| `WMBSU2NB` | 2010 | Y | `10.1175/2010jas3341.1` | 침강/이류 수치일관성과 미분 해석 주의점 | On Sedimentation and Advection in Multimoment Bulk Microphysics |
| `W5UHJDNL` | 2010 | Y | `10.1175/2009jas2965.1` | 미세물리 설계공간 또는 비교 문헌 | Simulated Electrification of a Small Thunderstorm with Two-Moment Bulk Microphysics |
| `RXNFS727` | 2013 | Y | `10.1175/jas-d-12-0264.1` | CCN/aerosol 및 수농도 민감도 축 | Aerosol Effects on Simulated Storm Electrification and Precipitation in a Two-Moment Bulk Microphysics Model |
| `DKMG7MT6` | 2015 | Y | `10.1175/jas-d-14-0065.1` | 미세물리 설계공간 또는 비교 문헌 | Parameterization of Cloud Microphysics Based on the Prediction of Bulk Ice Particle Properties. Part I: Scheme Description and Idealized Tests |
| `YUBAXLI6` | 2018 | Y | `10.1175/jas-d-17-0234.1` | 격자 평균 과정률과 부분운량/아격자 변동성 이슈 | The Use of Partial Cloudiness in a Bulk Cloud Microphysics Scheme: Concept and 2D Results |
| `YKPE6B2X` | 2019 | Y | `10.1029/2018jd029519` | 격자 평균 과정률과 부분운량/아격자 변동성 이슈 | Effects of Partial Cloudiness in a Cloud Microphysics Scheme on Simulated Precipitation Processes During a Boreal Summer |

## 자동미분·미분가능 구현

| Zotero key | Year | PDF | DOI | 원고 내 역할 | 제목 |
| --- | --- | ---: | --- | --- | --- |
| `E6KDCS3V` | 2019 | Y | `10.5194/gmd-12-5197-2019` | KDM6AD의 민감도/AD 필요성을 뒷받침하는 직접 근거 | Algorithmic differentiation for cloud schemes (IFS Cy43r3) using CoDiPack (v1.8.1) |
| `HSCSIXWK` | 2022 | Y | `10.1029/2021ms002849` | KDM6AD의 민감도/AD 필요성을 뒷받침하는 직접 근거 | Algorithmic Differentiation for Sensitivity Analysis in Cloud Microphysics |
| `4ZRTINZD` | 2023 | Y | `10.48550/arxiv.2208.13825` | 미분가능 대기/지구시스템 모델링 흐름 설명 | Differentiable Programming for Earth System Modeling |
| `JSEKWT8Q` | 2024 | Y | `10.48550/arxiv.2304.08063` | 미세물리 설계공간 또는 비교 문헌 | Data-Driven Equation Discovery of a Cloud Cover Parameterization |
| `K6KQNP7S` | 2024 | Y | `10.5194/gmd-17-4017-2024` | 딥러닝 미세물리 결합 및 안정적 coupling 사례 | Efficient and stable coupling of the SuperdropNet deep-learning-based cloud microphysics (v0.1.0) with the ICON climate and weather model (v2.6.5) |
| `ZGBTAJKZ` | 2024 | Y | `10.48550/arxiv.2403.02215` | 미분가능 대기/지구시스템 모델링 흐름 설명 | Joint Parameter and Parameterization Inference with Uncertainty Quantification through Differentiable Programming |
| `4N5KCMYS` | 2025 | Y | `10.21105/joss.07602` | Fortran 모델과 PyTorch/ML 컴포넌트 결합 근거 | FTorch: a library for coupling PyTorch models to Fortran |
| `M9XUQ75C` | 2025 | Y | `10.48550/arxiv.2505.04358` | 미세물리 설계공간 또는 비교 문헌 | Reduced Cloud Cover Errors in a Hybrid AI-Climate Model Through Equation Discovery And Automatic Tuning |
| `CNEVCLQJ` | 2026 | Y | `10.48550/arxiv.2605.24544` | 미분가능 대기/지구시스템 모델링 흐름 설명 | JAX-SCM v1.0: a modern atmospheric single-column model for boundary layer research |
| `H6I7RBDT` | 2026 | Y | `10.5194/egusphere-2025-6266` | 미분가능 대기/지구시스템 모델링 흐름 설명 | JCM v1.0: A Differentiable, Intermediate-Complexity Atmospheric Model |

## 자료동화·관측 연계

| Zotero key | Year | PDF | DOI | 원고 내 역할 | 제목 |
| --- | --- | ---: | --- | --- | --- |
| `DMKR59F5` | 2011 | Y | `` | 자료동화·관측 연계 확장 근거 | Radar Reflectivity Assimilation with the updated WRFDA-4DVAR system |
| `BTZY27UZ` | 2019 | Y | `10.5194/nhess-19-907-2019` | 자료동화·관측 연계 확장 근거 | Impact of airborne cloud radar reflectivity data assimilation on kilometre-scale numerical weather prediction analyses and forecasts of heavy precipitation events |

## 원문 보강 필요

| Zotero key | Year | PDF | DOI | 원고 내 역할 | 제목 |
| --- | --- | ---: | --- | --- | --- |
| `LCVBT38U` | 2004 | N | `10.1175/mwr2810.1` | 미세물리 설계공간 또는 비교 문헌 | Precipitation Uncertainty Due to Variations in Precipitation Particle Parameters within a Simple Microphysics Scheme |
| `FPPAYJ7D` | 2005 | N | `10.1007/s00703-005-0112-4` | 미세물리 설계공간 또는 비교 문헌 | A two-moment cloud microphysics parameterization for mixed-phase clouds. Part 1: Model description |
| `PR3T9Z88` | 2005 | N | `10.1007/s00703-005-0113-3` | 미세물리 설계공간 또는 비교 문헌 | A two-moment cloud microphysics parameterization for mixed-phase clouds. Part 2: Maritime vs. continental deep convective storms |
| `R5RMW5GG` | 2015 | N | `10.1175/jas-d-14-0066.1` | 미세물리 설계공간 또는 비교 문헌 | Parameterization of Cloud Microphysics Based on the Prediction of Bulk Ice Particle Properties. Part II: Case Study Comparisons with Observations and Other Schemes |
| `WC9TJWPA` | 2016 | N | `10.1175/jas-d-15-0204.1` | 미세물리 설계공간 또는 비교 문헌 | Parameterization of Cloud Microphysics Based on the Prediction of Bulk Ice Particle Properties. Part III: Introduction of Multiple Free Categories |
| `WGYGYPHD` | 2018 | N | `10.1007/s13143-018-0066-3` | 미세물리 설계공간 또는 비교 문헌 | Development of a Single-Moment Cloud Microphysics Scheme with Prognostic Hail for the Weather Research and Forecasting (WRF) Model |
| `DFJTS2Q8` | 2018 | N | `10.1007/s13143-018-0028-9` | 미세물리 설계공간 또는 비교 문헌 | The Korean Integrated Model (KIM) System for Global Weather Forecasting |

## 원문 보강 메모

아래 항목은 Zotero 메타데이터는 있으나 PDF 원문이 없다. 원고에서 세부 주장을 인용하기 전 원문 확보가 필요하다.

- `FPPAYJ7D` `10.1007/s00703-005-0112-4` A two-moment cloud microphysics parameterization for mixed-phase clouds. Part 1: Model description
- `PR3T9Z88` `10.1007/s00703-005-0113-3` A two-moment cloud microphysics parameterization for mixed-phase clouds. Part 2: Maritime vs. continental deep convective storms
- `WGYGYPHD` `10.1007/s13143-018-0066-3` Development of a Single-Moment Cloud Microphysics Scheme with Prognostic Hail for the Weather Research and Forecasting (WRF) Model
- `R5RMW5GG` `10.1175/jas-d-14-0066.1` Parameterization of Cloud Microphysics Based on the Prediction of Bulk Ice Particle Properties. Part II: Case Study Comparisons with Observations and Other Schemes
- `WC9TJWPA` `10.1175/jas-d-15-0204.1` Parameterization of Cloud Microphysics Based on the Prediction of Bulk Ice Particle Properties. Part III: Introduction of Multiple Free Categories
- `LCVBT38U` `10.1175/mwr2810.1` Precipitation Uncertainty Due to Variations in Precipitation Particle Parameters within a Simple Microphysics Scheme
- `DFJTS2Q8` `10.1007/s13143-018-0028-9` The Korean Integrated Model (KIM) System for Global Weather Forecasting

## 링크

- [[KDM6]]
- [[KDM6AD]]
- [[kdm6-microphysics-zotero-survey-2026-06-25]]
- [[kdm6ad-code-story-literature-review-2026-06-25]]
