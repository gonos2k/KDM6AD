---
title: KDM6 Literature Genealogy
type: concept
date_modified: 2026-06-25
aliases:
  - KDM6 계보
  - KDM/WDM 문헌 계보
---
# KDM6 문헌 계보

이 페이지는 [[KDM6AD]] 관련 논문 42편을 개별 논문 페이지로 분리한 뒤, 그 논문들을 계보 축으로 따라가기 위한 허브이다. 상세 설명은 각 논문 페이지에 둔다. 여기서는 “어느 논문이 어느 주장으로 이어지는가”만 추적한다.

## 1. Bulk Microphysics 기본 계보

초기 bulk scheme은 hydrometeor category별 질량, 수농도, 입자 크기분포, 낙하속도를 제한된 moment로 닫는 방향으로 발전했다.

- [[paper-66SUJCSY|Lin 1983]] - snow field bulk parameterization의 오래된 출발점.
- [[paper-L2BC8MGF|Tao 1989]] - ice-water saturation adjustment 계보.
- [[paper-LDHPT85H|Morrison 2005]] - double-moment cloud/climate model microphysics.
- [[paper-FPPAYJ7D|Seifert 2005 Part 1]] 및 [[paper-PR3T9Z88|Seifert 2005 Part 2]] - mixed-phase two-moment 설계의 보강 축.

이 축은 KDM6AD 원고에서 “미세물리과정은 본질적으로 moment closure의 집합”이라는 설명으로 이어진다.

## 2. PSD Moment와 Multimoment 계보

KDM6AD의 수학 설명에서 가장 중요한 축이다. `q_x`와 `N_x`가 PSD slope와 고차 moment를 어떻게 바꾸는지를 설명한다.

- [[paper-UTM4WM2T|Milbrandt and Yau 2005 Part I]] - gamma PSD shape parameter와 size sorting.
- [[paper-4NU3SNG7|Milbrandt and Yau 2005 Part II]] - three-moment closure와 reflectivity moment.
- [[paper-WMBSU2NB|Mansell 2010]] - moment별 sedimentation/advection 불일치 경고.

이 축은 [[KDM6AD Mathematical Microphysics Operators]]의 핵심 수식으로 연결된다.

```text
n(D) = N0 D^mu exp(-lambda D)
M_k = N0 Gamma(mu+k+1) / lambda^(mu+k+1)
lambda ~ (N/q)^(1/3)
```

## 3. WDM6/KDM 계열 직접 계보

KDM6AD가 직접 이어받는 문헌 축이다. 여기서는 “새 scheme 제안”이 아니라 WDM/KDM 계열의 물리와 forward parity를 보존한 미분가능 구현이라는 주장을 만들어야 한다.

- [[paper-6P3B5EDZ|Lim and Hong 2010]] - prognostic CCN을 포함한 WDM6 개발.
- [[paper-H3KYIIM9|Hong 2010]] - WDM6 precipitating convection 평가.
- [[paper-Y8G9YXWQ|Bae 2021]] - WDM7 revision 및 한반도 대류 평가.
- [[paper-5T4INXZ3|Choi 2022]] - ICE-POP 겨울폭풍 bulk scheme 비교.
- [[paper-D629MKTV|Park 2024]] - WDM6 graupel density prediction.

이 축은 [[KDM6]]와 [[KDM6AD Forward Parity]]로 직접 연결된다.

## 4. Graupel, Riming, Ice Property 계보

KDM6AD의 `bg`, `diag_rhog`, graupel density, riming 민감도를 해석하는 문헌 축이다.

- [[paper-54NAR859|Morrison and Grabowski 2011]] - riming intensity와 temperature-dependent ice characteristics.
- [[paper-DKMG7MT6|Morrison and Milbrandt 2015 Part I]] - P3 particle property prediction.
- [[paper-R5RMW5GG|Morrison and Milbrandt 2015 Part II]] - P3 case study comparison.
- [[paper-WC9TJWPA|Morrison and Milbrandt 2016 Part III]] - multiple free categories.
- [[paper-D629MKTV|Park 2024]] - WDM6 graupel density prediction.

이 축은 KDM6AD의 graupel 관련 derivative claim을 강화하지만, 동시에 [[KDM6AD Differentiability Audit]]에서 diagnostic-only boundary를 분리해야 한다.

## 5. Cloud Fraction, Subgrid Variability, Cloud Cover 계보

격자 평균 미세물리 operator가 실제 구름 내부 과정률을 어떻게 대표하는지 묻는 축이다.

- [[paper-S2R9LH3S|Pincus and Klein 2000]] - unresolved variability와 nonlinear process-rate bias.
- [[paper-YUBAXLI6|Hong 2018]] - partial cloudiness 개념과 2D 결과.
- [[paper-YKPE6B2X|Kim 2019]] - partial cloudiness가 여름 강수 과정에 주는 효과.
- [[paper-JSEKWT8Q|Beucler 2024]] 및 [[paper-M9XUQ75C|Mooers 2025]] - cloud cover equation discovery와 tuning.

이 축은 KDM6AD의 미분이 “구현된 gridbox operator의 미분”이라는 한계를 설명한다.

## 6. AD와 미분가능 대기모델 계보

KDM6AD의 기술적 주장, 즉 VJP/JVP를 제공하는 미분가능 미세물리 표면이라는 주장을 뒷받침한다.

- [[paper-E6KDCS3V|Baumgartner 2019]] - CoDiPack을 이용한 cloud scheme AD.
- [[paper-HSCSIXWK|Hieronymus 2022]] - cloud microphysics sensitivity analysis AD.
- [[paper-4ZRTINZD|Häfner 2023]] - differentiable programming for ESM.
- [[paper-H6I7RBDT|JCM 2026]] 및 [[paper-CNEVCLQJ|JAX-SCM 2026]] - JVP/VJP를 사용하는 미분가능 대기모델 흐름.
- [[paper-K6KQNP7S|SuperdropNet ICON 2024]] 및 [[paper-4N5KCMYS|FTorch 2025]] - Fortran/PyTorch/ML component coupling.

이 축은 [[KDM6AD Automatic Differentiation ABI]]와 [[KDM6AD Literature Claim Map]]으로 이어진다.

## 7. 자료동화와 관측연산자 계보

KDM6AD가 DA 전체를 완성했다는 주장을 막고, “미세물리 tangent/adjoint block을 제공한다”는 정확한 범위를 잡는 축이다.

- [[paper-DMKR59F5|Wang 2011]] - WRFDA-4DVAR radar reflectivity assimilation.
- [[paper-BTZY27UZ|Borderies 2019]] - airborne cloud radar reflectivity assimilation.

이 축은 observation operator `H`, reflectivity moment, hydrometeor control variable, radar scattering assumptions를 KDM6AD microphysics derivative와 분리해 설명하게 한다.

## 연결 허브

- [[papers/_index|KDM6AD 논문 페이지 색인]]
- [[KDM6AD Literature Claim Map]]
- [[KDM6AD Mathematical Microphysics Operators]]
- [[KDM6AD Differentiability Audit]]
- [[KDM6AD Automatic Differentiation ABI]]
