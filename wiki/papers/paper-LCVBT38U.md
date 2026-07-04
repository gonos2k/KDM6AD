---
title: "Precipitation Uncertainty Due to Variations in Precipitation Particle Parameters within a Simple Microphysics Scheme"
page_kind: paper
zotero_key: LCVBT38U
year: "2004"
doi: "10.1175/mwr2810.1"
section: "원문 보강 필요"
paper_use: "미세물리 설계공간 또는 비교 문헌"
aliases:
  - "Precipitation Uncertainty Due to Variations in Precipitation Particle Parameters within a Simple Microphysics Scheme"
  - "Gilmore 2004"
  - "LCVBT38U"
---
# Precipitation Uncertainty Due to Variations in Precipitation Particle Parameters within a Simple Microphysics Scheme

## 이 페이지의 역할

이 페이지는 Gilmore 2004 논문을 일반 초록 수준으로 요약하지 않고, [[KDM6]], [[KDM6AD]], [[KDM6 Literature Genealogy]], [[KDM6AD Literature Claim Map]] 안에서 어떤 학술적 결절점으로 쓰이는지를 정리한다. 목표는 논문 작성용 카드가 아니라, KDM6AD 연구의 과학사·수학·구현·자료동화 계보에서 이 논문이 담당하는 역할을 분명히 하는 것이다.

**핵심 판정:** precipitation particle parameter 변화만으로도 convective storm accumulated precipitation uncertainty가 커질 수 있음을 보여주는 microphysics parameter uncertainty의 고전적 증거다.

## 기본 서지와 근거 상태

- Zotero key: `LCVBT38U`
- 연도: `2004`
- 저자: Gilmore, Matthew S.; Straka, Jerry M.; Rasmussen, Erik N.
- DOI/URL: `10.1175/mwr2810.1`
- 컬렉션 섹션: `원문 보강 필요`
- 컬렉션 내 역할: 미세물리 설계공간 또는 비교 문헌
- 근거 상태: 원문 PDF 미확보. AMETSOC/UCAR 공개 초록·메타데이터 기준으로 보수 정리: https://journals.ametsoc.org/view/journals/mwre/132/11/mwr2810.1.xml

## 학술적 가치

- KDM6AD에서 parameter sensitivity와 uncertainty quantification을 논할 때 중요한 배경이다.
- intercept parameter, particle density 같은 “상수”가 forecast outcome을 크게 바꿀 수 있으므로, AD로 이 계수들을 theta로 열어 보는 연구질문을 정당화한다.
- graupel density prediction, P3, riming treatment 문헌의 문제의식을 선행적으로 보여준다.

이 논문의 학술적 가치는 “KDM6AD에 인용할 수 있다”는 수준이 아니라, KDM6AD가 어떤 기존 물리 operator를 미분가능한 계산 대상으로 삼는지 설명하게 해 주는 데 있다. 따라서 이 페이지에서는 논문의 결론을 KDM6AD 성능 주장으로 바로 옮기지 않고, operator, closure, state variable, validation regime 중 어느 부분에 연결되는지를 분리한다.

## 계보적 위치

- Lin/WSM류 simple ice microphysics의 parameter uncertainty를 정면으로 다룬다.
- D629MKTV graupel density prediction과 P3 property prediction은 이 uncertainty를 더 물리적으로 상태화하려는 후속 흐름으로 읽을 수 있다.
- KDM6AD는 이 sensitivity를 자동미분으로 더 체계적으로 측정할 수 있는 도구가 될 수 있다.

섹션 계보 요약: 불완전 근거 문헌은 확정 주장보다 “보강해야 할 계보 연결”로 취급한다. 특히 Seifert-Beheng two-moment, P3, KIM, WSM7 hail은 KDM6AD 설명에서 연결성이 크다.

이 위치 때문에 Gilmore 2004은/는 [[KDM6 Literature Genealogy]]에서 단순 참고문헌이 아니라 선행 가정, 비교 계보, 구현 방법론, 또는 관측 응용 중 하나의 노드로 다루어야 한다. 특히 KDM6AD를 설명할 때는 “새 물리 scheme”이라는 표현보다 “기존 KDM/WDM 및 관련 bulk microphysics 계보의 discrete operator를 AD 가능한 표면으로 노출한다”는 해석이 더 정확하다.

## 방법론과 모형 구조

- simple liquid-ice microphysics scheme에서 particle intercept parameter와 hail/graupel density 등을 바꾸어 deep convective storm simulation의 precipitation sensitivity를 분석한다.
- accumulated precipitation과 storm evolution의 불확실성을 microphysical parameter choice에 연결한다.
- parameter variation experiment가 중심이다.

섹션별 문제의식: 이 축은 현재 Zotero 컬렉션에 원문 PDF가 없거나 제한적으로만 확보된 논문이다. 그래도 KDM6/KDM6AD 계보에서 빠지면 안 되는 결절점이므로, 공개 초록·출판사 메타데이터·제목과 확립된 계보에 기반해 보수적으로 정리한다.

KDM6AD 관점에서 방법론을 읽을 때는 세 층을 분리한다.

- 물리 계층: 어떤 hydrometeor, aerosol/CCN, ice property, cloud fraction 또는 관측량을 다루는가.
- 수치 계층: source term integration, saturation adjustment, sedimentation, limiter, clipping, lookup 또는 branch가 어떻게 들어가는가.
- 미분 계층: 위 수치 연산이 JVP/VJP에서 smooth, piecewise-smooth, discontinuous, diagnostic-only 중 어디에 놓이는가.

## 수학적·물리적 구조

```text
n_x(D) = N0_x D^{mu_x} exp(-lambda_x D)
M_k,x  = integral_0^inf D^k n_x(D) dD
N_x    = M_0,x
q_x    proportional to rho_x M_3,x / rho_air
P_x    = P_x(q, N, T, r_v; theta, closure)
```
이 표기는 논문의 정확한 식을 대체하지 않는다. KDM6AD 문헌망에서 공통 언어로 쓰기 위한 operator-level 표기다.

- PSD intercept N0, density rho, fall-speed coefficient는 P_micro(y;theta)의 theta다.
- AD로 d precipitation / d theta를 얻으려면 theta가 code constant가 아니라 differentiable input으로 노출되어야 한다.
- 현행 KDM6AD가 state derivative만 제공한다면 parameter derivative는 별도 refactor가 필요하다.

원문/매니페스트에서 확인한 수학적 읽기 단서:
- 매니페스트에 별도 math snippet이 없다. 페이지의 수학 해석은 제목, 섹션, 확보된 초록/원문 구조와 KDM6AD operator 관점에서 작성했다.

KDM6AD wiki에서 이 논문을 수학적으로 사용할 때의 기본 원칙은 다음과 같다.

- 모든 derivative는 먼저 discrete operator derivative로 쓴다. 즉 연속 방정식의 미분이 아니라 실제 구현된 `F_micro`의 미분이다.
- PSD closure, moment choice, particle density, fall-speed relation, CCN activation, cloud fraction, observation operator 중 무엇이 derivative의 조건부 가정인지 명시한다.
- branch crossing, saturation adjustment, positivity limiter, hydrometeor category activation 같은 구간에서는 미분가능성을 전역 smooth가 아니라 piecewise 또는 regime-local로 해석한다.

## KDM6AD와 직접 연결되는 지점

- KDM6AD의 parameter-inference future work를 강하게 정당화한다.
- graupel density를 diagnostic/state로 넣는 extension의 과학적 동기를 제공한다.
- 원문 PDF가 현재 컬렉션에 없으므로 세부 수치/그림 인용은 보류한다.

KDM6AD 코드 설명에 연결하면 다음 구조가 된다.

```text
선행 미세물리/AD/DA 문헌
  -> KDM6 또는 비교 bulk scheme의 상태변수와 closure
  -> KDM6AD의 discrete operator F_micro
  -> JVP/VJP 또는 forward parity 검증
  -> 자료동화, sensitivity, parameter inference로의 확장 가능성
```

이 구조를 지키면 논문을 배경문헌으로만 소비하지 않고, 어떤 Jacobian block, 어떤 ABI state, 어떤 관측연산자, 어떤 검증 regime과 연결되는지 명확하게 유지할 수 있다.

## 정당화할 수 있는 주장

- bulk microphysics parameter uncertainty는 precipitation forecast uncertainty의 중요한 원천이다.
- KDM6AD는 이런 parameter sensitivity를 체계적으로 계산할 수 있는 방향으로 확장 가능하다.

추가로 이 논문은 다음 수준의 주장에만 안전하게 사용한다.

- `원문 보강 필요` 축에서 KDM6AD의 학술적 위치를 설명하는 근거.
- KDM6AD가 다루는 discrete microphysics operator의 물리적 또는 방법론적 배경.
- 후속 연구 질문을 만드는 계보적 연결.

## 이 논문만으로는 정당화하기 어려운 주장

- 현재 페이지는 공개 초록/메타데이터 기반 보수 요약이다.
- simple microphysics scheme 결과를 KDM6AD 계수 민감도로 직접 대체하면 안 된다.

특히 다음 표현은 피한다.

- “KDM6AD가 이 논문의 scheme을 그대로 구현한다”는 식의 등치.
- “이 논문의 예측 성능이 곧 KDM6AD의 성능”이라는 식의 대체.
- “AD가 가능하므로 전역적으로 smooth하고 최적화가 안정적”이라는 식의 과장.
- 원문 미확보 항목에서 세부 계수, 그림 수치, case-specific conclusion을 확정적으로 인용하는 방식.

## 계보상 남는 연구 질문

- 이 논문이 다루는 state 또는 parameter 중 현행 KDM6AD ABI에 들어간 것은 무엇이고, diagnostic-only로 남은 것은 무엇인가?
- 해당 closure의 derivative는 branch-stable perturbation에서만 의미가 있는가, 아니면 자료동화 perturbation 크기에서도 쓸 수 있는가?
- observation-space loss를 쓰면 VJP가 어떤 hydrometeor/state/parameter로 되돌아가는가?
- 이 논문의 계보를 따르면 KDM6AD의 다음 확장은 state 추가, parameter inference, observation operator AD, host dynamics coupling 중 어디가 되어야 하는가?

## 계보적 독해 매트릭스

| 축 | Gilmore 2004에서 확인할 내용 | KDM6AD에서 남는 의미 |
| --- | --- | --- |
| 근거 등급 | PDF 원문이 없으므로 공개 초록, 출판사 summary, DOI metadata, 확립된 계보만 사용한다. | 세부 수치·그림·case conclusion은 원문 확보 전까지 claim으로 쓰지 않는다. |
| 계보 필요성 | 원문이 없어도 Seifert-Beheng, P3, KIM, WSM7 같은 결절점은 KDM6AD 계보에서 빠질 수 없다. | 보수적 연결과 보강 필요성을 함께 기록한다. |
| 수학 축 | moment closure, particle property, DA host context 같은 구조적 함의만 정리한다. | KDM6AD의 derivative claim은 가능한 경로 수준으로 제한한다. |
| 후속 작업 | Zotero 원문 확보 후 계수, 실험 설계, 결과, 그림 해석을 추가한다. | 현재 페이지는 연구지도이자 감사 로그다. |

이 매트릭스의 목적은 Gilmore 2004을/를 단순히 “관련 논문”으로 묶지 않고, KDM6AD의 물리 계보에서 어떤 추상화 수준에 놓이는지 고정하는 것이다. 같은 bulk microphysics 문헌이라도 하나는 직접 조상, 하나는 대안 closure, 하나는 구현 방법론, 하나는 관측연산자 계보일 수 있다. 이 구분이 없으면 KDM6AD 설명은 문헌 목록은 길지만 과학적 주장은 흐린 상태가 된다.

## KDM6AD 연산자 대응

이 축의 페이지는 KDM6AD claim의 직접 근거가 아니라 missing-but-relevant genealogy를 보존한다. operator 대응도 “현재 구현됨”이 아니라 “이런 state/parameter/operator가 후속 확장 후보”라는 수준으로 쓴다.

Gilmore 2004을/를 KDM6AD 코드와 연결할 때는 다음 대응을 확인한다.

- State 대응: 논문에서 의미 있는 prognostic 또는 diagnostic 변수가 KDM6AD의 packed state, host state, diagnostic output 중 어디에 들어가는가.
- Closure 대응: PSD, density, fall-speed, activation, saturation, cloud fraction, category conversion 같은 closure가 fixed constant인지, diagnostic relation인지, differentiable input인지 구분한다.
- Process 대응: 논문이 강조하는 과정이 KDM6AD의 source term, adjustment, sedimentation, post-step coupling 중 어디에 해당하는가.
- Gradient 대응: JVP로 볼 perturbation direction과 VJP로 되돌릴 adjoint seed를 명확히 정한다.
- Evidence 대응: 이 논문으로 뒷받침할 수 있는 것은 물리 계보인지, 구현 방법론인지, DA 응용 가능성인지 분리한다.

## 미분가능 미세물리 관점의 수학적 독해

원문 미확보 상태에서는 식 번호나 수치 결과를 확정하지 않는다. 대신 `theta` parameter uncertainty, `(q,N)` moment pair, particle property state, `H(M(x))` observation chain처럼 계보적으로 안전한 수학 구조만 남긴다.

KDM6AD의 수학적 설명에서는 다음 표기 규칙을 적용하는 것이 안전하다.

```text
F_micro = L_pos ∘ Pi_sat ∘ S_sed ∘ S_ice ∘ S_warm ∘ S_cond
J_micro = partial F_micro / partial y
JVP(v)  = J_micro v
VJP(w)  = J_micro^T w
```

이 분해는 실제 코드의 정확한 call graph가 아니라 학술적 독해를 위한 operator decomposition이다. 중요한 점은 KDM6AD가 미분하는 대상이 “구름물리 일반”이 아니라 특정 closure와 branch를 가진 discrete KDM6 계열 연산자라는 사실이다. 따라서 Gilmore 2004의 가치는 KDM6AD의 모든 주장을 보증하는 데 있지 않고, 이 discrete operator가 어떤 계보적 선택 위에 서 있는지 밝히는 데 있다.

## 적대적 검토 포인트

- 원문 없이 세부 계수나 결과 수치를 확정적으로 쓰면 안 된다.
- 공개 초록 문구를 넘어선 해석은 “계보적 추정” 또는 “후속 확인 필요”로 표시해야 한다.
- KDM6AD 구현과의 직접 대응은 코드와 원문이 모두 확인된 후에만 주장한다.
- 이 페이지는 삭제 대상이 아니라 보강 우선순위 목록으로 관리한다.

이 적대적 검토는 논문의 가치를 낮추려는 것이 아니다. 오히려 학술적 가치를 보존하려면 어떤 주장까지 안전하고 어디서부터 과장인지 분리해야 한다. KDM6AD 위키에서는 이 분리를 페이지마다 남겨, 나중에 신규 논문을 작성하거나 발표자료를 만들 때 문헌의 계보적 의미와 코드의 실제 성취를 혼동하지 않도록 한다.

## 연결된 논문 페이지

- [[paper-54NAR859|Lin 2011]] - A New Bulk Microphysical Scheme That Includes Riming Intensity and Temperature-De…
- [[paper-D629MKTV|Lim 2024]] - Introducing graupel density prediction in Weather Research and Forecasting (WRF) …
- [[paper-66SUJCSY|Lin 1983]] - Bulk Parameterization of the Snow Field in a Cloud Model
- [[paper-DKMG7MT6|Milbrandt 2015]] - Parameterization of Cloud Microphysics Based on the Prediction of Bulk Ice Partic…

## 연결된 개념 페이지

- [[KDM6 Literature Genealogy]], [[Bulk Microphysics Design Space]], [[KDM6AD Literature Claim Map]], [[Differentiable Bulk Microphysics Research Gap]]
- [[KDM6]]
- [[KDM6AD]]

## 읽기 우선순위

1. 먼저 이 페이지의 “계보적 위치”와 “수학적·물리적 구조”를 읽어 KDM6AD와 연결되는 축을 잡는다.
2. 그 다음 연결된 논문 페이지를 따라 선행/후속 문헌을 확인한다.
3. 마지막으로 [[KDM6AD Literature Claim Map]]에서 이 논문으로 정당화 가능한 주장과 불가능한 주장을 대조한다.
