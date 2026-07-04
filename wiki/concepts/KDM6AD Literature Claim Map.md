---
title: KDM6AD Literature Claim Map
type: concept
date_modified: 2026-06-25
aliases:
  - KDM6AD 주장 근거 지도
  - KDM6AD 논문 근거망
---
# KDM6AD 논문 주장-근거 지도

이 페이지는 개별 논문 페이지들을 KDM6AD 원고의 주장 단위로 묶는 허브이다. 긴 문헌 리뷰 본문이 아니라, “어떤 주장을 할 때 어떤 논문 페이지를 따라가야 하는가”를 기록한다.

## 주장 1. KDM6AD는 새 물리 scheme이 아니라 계보가 있는 KDM/WDM 계열 구현 표면이다

사용할 논문 페이지:

- [[paper-6P3B5EDZ|Lim and Hong 2010 WDM6]]
- [[paper-H3KYIIM9|Hong 2010 WDM6 evaluation]]
- [[paper-Y8G9YXWQ|WDM7 revision]]
- [[paper-D629MKTV|WDM6 graupel density]]
- [[paper-5T4INXZ3|ICE-POP bulk scheme comparison]]

원고 문장 방향:

> KDM6AD의 기여는 새로운 parameterization을 추가하는 것이 아니라, WDM/KDM 계열 bulk microphysics의 forward behavior를 보존하면서 미분가능한 계산 표면을 제공하는 것이다.

주의할 점:

- 물리 scheme 성능 주장은 위 논문들의 평가 맥락에 의존한다.
- 현재 코드 검증은 [[KDM6AD Forward Parity]]와 별도로 제시해야 한다.

## 주장 2. 두 moment와 PSD closure 때문에 수농도 gradient는 물리적으로 의미 있다

사용할 논문 페이지:

- [[paper-LDHPT85H|Morrison 2005 double moment]]
- [[paper-UTM4WM2T|Milbrandt and Yau Part I]]
- [[paper-4NU3SNG7|Milbrandt and Yau Part II]]
- [[paper-6P3B5EDZ|WDM6 prognostic CCN]]
- [[paper-S98KNIGB|LIMA aerosol-aware microphysics]]

핵심 수식:

```text
n(D) = N0 D^mu exp(-lambda D)
lambda ~ (N/q)^(1/3)
Z ~ M_6
```

원고 문장 방향:

> `Nccn`, `Nc`, `Nr`에 대한 KDM6AD gradient는 단순한 보조 변수 민감도가 아니라 PSD slope, process rate, sedimentation, reflectivity moment로 이어지는 물리적 민감도이다.

## 주장 3. Graupel density와 riming은 KDM6AD의 중요한 민감도 축이다

사용할 논문 페이지:

- [[paper-D629MKTV|Park 2024 WDM6 graupel density]]
- [[paper-54NAR859|Morrison and Grabowski 2011 riming intensity]]
- [[paper-DKMG7MT6|P3 Part I]]
- [[paper-R5RMW5GG|P3 Part II]]
- [[paper-WC9TJWPA|P3 Part III]]

원고 문장 방향:

> Graupel/riming 변수는 fall speed와 mass-diameter relation을 통해 표면강수와 반사도에 연결되므로, `bg` 또는 graupel density 관련 derivative는 물리적으로 해석 가능한 축이다.

주의할 점:

- `diag_rhog`는 현재 forward diagnostic boundary로 취급한다.
- AD state에 포함된 변수와 host diagnostic을 혼동하지 않는다.

## 주장 4. AD는 미세물리 민감도와 parameter inference에 실용적이다

사용할 논문 페이지:

- [[paper-E6KDCS3V|Baumgartner 2019 CoDiPack cloud scheme AD]]
- [[paper-HSCSIXWK|Hieronymus 2022 cloud microphysics AD sensitivity]]
- [[paper-4ZRTINZD|Differentiable Programming for ESM]]
- [[paper-ZGBTAJKZ|Joint parameter and parameterization inference]]
- [[paper-H6I7RBDT|JCM VJP/JVP]]

검증 문장:

```text
JVP: F(y + eps v) - F(y) ~= eps Jv
VJP: <Jv, u> = <v, J^T u>
```

원고 문장 방향:

> KDM6AD는 hand-coded adjoint를 새로 작성하는 대신, 구현된 KDM6 time-step map의 JVP/VJP product를 제공하여 민감도 분석과 최적화/DA workflow의 미세물리 블록으로 쓸 수 있게 한다.

## 주장 5. 자료동화 확장은 microphysics block과 observation operator를 분리해야 한다

사용할 논문 페이지:

- [[paper-DMKR59F5|WRFDA-4DVAR reflectivity assimilation]]
- [[paper-BTZY27UZ|Airborne cloud radar reflectivity DA]]
- [[paper-4NU3SNG7|Reflectivity as PSD high-order moment]]
- [[paper-WMBSU2NB|Sedimentation/advection artifact warning]]

원고 문장 방향:

> KDM6AD는 DA 전체가 아니라 forecast model 안의 microphysics tangent/adjoint block을 제공한다. Radar reflectivity assimilation에는 별도 `H`와 `H'`가 필요하며, reflectivity는 PSD의 고차 moment이므로 diagnostic boundary를 명확히 해야 한다.

## 주장 6. 미분가능하다는 말은 smooth하다는 뜻이 아니다

사용할 논문 페이지:

- [[paper-L2BC8MGF|Ice-water saturation adjustment]]
- [[paper-WMBSU2NB|Sedimentation/advection consistency]]
- [[paper-S2R9LH3S|Subgrid variability and process rates]]
- [[paper-YUBAXLI6|Partial cloudiness concept]]
- [[paper-YKPE6B2X|Partial cloudiness precipitation effects]]

원고 문장 방향:

> KDM6AD가 제공하는 derivative는 구현된 연산 그래프의 derivative product이다. Saturation adjustment, clipping, hydrometeor threshold, partial cloudiness, sedimentation limiter 주변에서는 derivative audit가 필요하다.

## 연결 허브

- [[papers/_index|KDM6AD 논문 페이지 색인]]
- [[KDM6 Literature Genealogy]]
- [[KDM6AD Automatic Differentiation ABI]]
- [[KDM6AD Differentiability Audit]]
- [[KDM6AD Mathematical Microphysics Operators]]
