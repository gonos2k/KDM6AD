---
title: "Development of an Effective Double-Moment Cloud Microphysics Scheme with Prognostic Cloud Condensation Nuclei (CCN) for Weather and Climate Models"
page_kind: paper
zotero_key: 6P3B5EDZ
year: "2010"
doi: "10.1175/2009mwr2968.1"
section: "KDM/WDM 계열 핵심 미세물리"
paper_use: "KDM/WDM6 계열의 과학적 계보와 forward parity 기준"
aliases:
  - "Development of an Effective Double-Moment Cloud Microphysics Scheme with Prognostic Cloud Condensation Nuclei (CCN) for Weather and Climate Models"
  - "Lim 2010"
  - "6P3B5EDZ"
---
# Development of an Effective Double-Moment Cloud Microphysics Scheme with Prognostic Cloud Condensation Nuclei (CCN) for Weather and Climate Models

## 이 페이지의 역할

이 페이지는 Lim 2010 논문을 일반 초록 수준으로 요약하지 않고, [[KDM6]], [[KDM6AD]], [[KDM6 Literature Genealogy]], [[KDM6AD Literature Claim Map]] 안에서 어떤 학술적 결절점으로 쓰이는지를 정리한다. 목표는 논문 작성용 카드가 아니라, KDM6AD 연구의 과학사·수학·구현·자료동화 계보에서 이 논문이 담당하는 역할을 분명히 하는 것이다.

**핵심 판정:** WDM6의 핵심 출발점으로, WSM6 six-class mass state 위에 cloud/rain number concentration과 prognostic CCN을 결합해 KDM6AD가 실제로 미분해야 할 상태공간을 만든다.

## 기본 서지와 근거 상태

- Zotero key: `6P3B5EDZ`
- 연도: `2010`
- 저자: Lim, Kyo-Sun Sunny; Hong, Song-You
- DOI/URL: `10.1175/2009mwr2968.1`
- 컬렉션 섹션: `KDM/WDM 계열 핵심 미세물리`
- 컬렉션 내 역할: KDM/WDM6 계열의 과학적 계보와 forward parity 기준
- 근거 상태: PDF 원문 및 추출 텍스트 확보 (`127523` chars extracted). 원문 기반으로 구조를 정리했다.

## 학술적 가치

- KDM6AD 문헌망에서 가장 중심적인 물리 계보 문헌이다. KDM6AD가 미분하는 nccn, nc, nr의 과학적 의미가 이 논문에서 직접 출발한다.
- WSM6 대비 WDM6가 단순한 구현 변형이 아니라 CCN-activation과 raindrop size distribution의 자유도를 더한 scheme임을 보여준다.
- 계산비용을 크게 늘리지 않으면서 double-moment 효과를 얻으려는 설계 철학은 KDM6AD의 “host parity 유지 + AD surface 추가” 전략과 잘 맞는다.

이 논문의 학술적 가치는 “KDM6AD에 인용할 수 있다”는 수준이 아니라, KDM6AD가 어떤 기존 물리 operator를 미분가능한 계산 대상으로 삼는지 설명하게 해 주는 데 있다. 따라서 이 페이지에서는 논문의 결론을 KDM6AD 성능 주장으로 바로 옮기지 않고, operator, closure, state variable, validation regime 중 어느 부분에 연결되는지를 분리한다.

## 계보적 위치

- WSM6 -> WDM6 -> WDM7/KDM6/KDM6AD로 이어지는 직접 계보의 원류다.
- Morrison/Seifert류 double-moment 문법을 WRF operational-style bulk scheme으로 가져온 결절점이다.
- 이후 WDM6 평가, WDM7 revision, graupel density 예측 논문이 이 상태공간을 확장한다.

섹션 계보 요약: Lin/WSM식 단일모멘트 ice microphysics에서 WDM6의 double-moment warm-rain 및 CCN prognostic state로 이동하고, 이후 WDM7·graupel density·KIM host 통합으로 확장되는 흐름이다.

이 위치 때문에 Lim 2010은/는 [[KDM6 Literature Genealogy]]에서 단순 참고문헌이 아니라 선행 가정, 비교 계보, 구현 방법론, 또는 관측 응용 중 하나의 노드로 다루어야 한다. 특히 KDM6AD를 설명할 때는 “새 물리 scheme”이라는 표현보다 “기존 KDM/WDM 및 관련 bulk microphysics 계보의 discrete operator를 AD 가능한 표면으로 노출한다”는 해석이 더 정확하다.

## 방법론과 모형 구조

- qv, qc, qi, qs, qr, qg의 mass mixing ratio에 Nc, Nr, NCCN을 더해 warm-rain microphysics의 수농도 의존성을 예측한다.
- CCN activation이 cloud droplet number source로 들어가며, rain number는 autoconversion/accretion/self-collection 계열 과정과 연결된다.
- 이상화 2D thunderstorm testbed를 통해 bright band, light/moderate precipitation bias, convective/stratiform droplet contrast를 평가한다.

섹션별 문제의식: KDM6AD가 미분가능하게 옮기려는 대상은 새 물리 가설이 아니라 WSM/WDM/KDM 계열에서 누적된 bulk microphysics 연산자다. 이 축의 논문은 그 연산자의 상태변수, closure, 진단량, 실험 검증 전통을 제공한다.

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

- 수학적으로 q와 N이 함께 lambda를 정하고, lambda가 collision/accretion/sedimentation 계수와 radar-like 진단량에 들어간다.
- JVP에서 delta NCCN -> delta Nc -> delta autoconversion/accretion -> delta rain/graupel 경로가 핵심이다.
- VJP에서 강수 또는 반사도 손실은 Nr/Nc/NCCN으로 되돌아갈 수 있으므로 q-only adjoint와 다른 해석을 만든다.

원문/매니페스트에서 확인한 수학적 읽기 단서:
- 원문 추출에서 CCN/cloud droplet number 관련 표현이 확인되어, activation과 number concentration sensitivity를 중심으로 읽는다.
- 원문 추출의 수식/기술 단서는 해당 논문을 process-rate closure 또는 model-coupling 문헌으로 읽게 한다.

KDM6AD wiki에서 이 논문을 수학적으로 사용할 때의 기본 원칙은 다음과 같다.

- 모든 derivative는 먼저 discrete operator derivative로 쓴다. 즉 연속 방정식의 미분이 아니라 실제 구현된 `F_micro`의 미분이다.
- PSD closure, moment choice, particle density, fall-speed relation, CCN activation, cloud fraction, observation operator 중 무엇이 derivative의 조건부 가정인지 명시한다.
- branch crossing, saturation adjustment, positivity limiter, hydrometeor category activation 같은 구간에서는 미분가능성을 전역 smooth가 아니라 piecewise 또는 regime-local로 해석한다.

## KDM6AD와 직접 연결되는 지점

- KDM6AD 원고에서 forward parity의 대상 물리를 설명하는 가장 중요한 논문이다.
- 자료동화로 확장할 때 hydrometeor control variable뿐 아니라 CCN-related control/sensitivity를 논할 수 있는 근거가 된다.
- KDM6AD가 새 scheme을 제안했다는 식의 주장은 피하고, WDM6 계열 연산자를 미분가능 표면으로 옮겼다고 써야 한다.

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

- WDM6는 WSM6 mass state에 Nc, Nr, NCCN 예측을 결합한 double-moment 6-class 계열이다.
- KDM6AD의 핵심 gradient는 NCCN/Nc/Nr와 hydrometeor mass 사이의 process coupling에서 나온다.

추가로 이 논문은 다음 수준의 주장에만 안전하게 사용한다.

- `KDM/WDM 계열 핵심 미세물리` 축에서 KDM6AD의 학술적 위치를 설명하는 근거.
- KDM6AD가 다루는 discrete microphysics operator의 물리적 또는 방법론적 배경.
- 후속 연구 질문을 만드는 계보적 연결.

## 이 논문만으로는 정당화하기 어려운 주장

- 정확한 코드 parity, ABI, floating-point 동일성은 이 논문이 아니라 현재 KDM6AD 코드 검증이 담당한다.
- 논문 실험 결과를 KDM6AD의 AD gradient correctness 검증으로 대체할 수 없다.

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

| 축 | Lim 2010에서 확인할 내용 | KDM6AD에서 남는 의미 |
| --- | --- | --- |
| 직접 조상성 | WSM/WDM/KDM 계열의 상태변수와 process closure가 어떻게 현재 KDM6AD의 forward target이 되는지 확인한다. | mp37 KDM6와 mp137 KDM6AD의 parity는 단순 numerical regression이 아니라 이 계보의 물리 의미를 보존하는 시험이다. |
| moment 구조 | mass mixing ratio q만 볼 것인지, cloud/rain number와 CCN까지 state로 둘 것인지가 핵심이다. | JVP/VJP에서 q, Nc, Nr, NCCN perturbation을 분리해 해석해야 한다. |
| 진단량 | reflectivity, graupel density, precipitation rate 같은 값은 prognostic state와 diagnostic의 경계에 놓인다. | 진단량을 ABI state로 승격하지 않으면 gradient target이 아니라 forward diagnostic으로 남는다. |
| 검증 계보 | 개발 논문과 평가 논문을 분리해야 한다. 개발은 state/closure를, 평가는 적용 regime을 설명한다. | KDM6AD 검증도 forward parity, gradient check, observation-space utility를 분리해야 한다. |

이 매트릭스의 목적은 Lim 2010을/를 단순히 “관련 논문”으로 묶지 않고, KDM6AD의 물리 계보에서 어떤 추상화 수준에 놓이는지 고정하는 것이다. 같은 bulk microphysics 문헌이라도 하나는 직접 조상, 하나는 대안 closure, 하나는 구현 방법론, 하나는 관측연산자 계보일 수 있다. 이 구분이 없으면 KDM6AD 설명은 문헌 목록은 길지만 과학적 주장은 흐린 상태가 된다.

## KDM6AD 연산자 대응

KDM/WDM 계열을 KDM6AD operator로 옮기면 `y=(q_v,q_c,q_r,q_i,q_s,q_g,N_c,N_r,N_CCN,T,...)`와 같은 상태에서 `F_micro(y)`가 한 timestep tendency 또는 updated state를 만든다. 여기서 scientific claim은 “새 물리”가 아니라 “이산화된 기존 물리 연산자의 AD-compatible representation”이다.

Lim 2010을/를 KDM6AD 코드와 연결할 때는 다음 대응을 확인한다.

- State 대응: 논문에서 의미 있는 prognostic 또는 diagnostic 변수가 KDM6AD의 packed state, host state, diagnostic output 중 어디에 들어가는가.
- Closure 대응: PSD, density, fall-speed, activation, saturation, cloud fraction, category conversion 같은 closure가 fixed constant인지, diagnostic relation인지, differentiable input인지 구분한다.
- Process 대응: 논문이 강조하는 과정이 KDM6AD의 source term, adjustment, sedimentation, post-step coupling 중 어디에 해당하는가.
- Gradient 대응: JVP로 볼 perturbation direction과 VJP로 되돌릴 adjoint seed를 명확히 정한다.
- Evidence 대응: 이 논문으로 뒷받침할 수 있는 것은 물리 계보인지, 구현 방법론인지, DA 응용 가능성인지 분리한다.

## 미분가능 미세물리 관점의 수학적 독해

이 축의 derivative는 `d lambda / d q`, `d lambda / d N`, activation derivative, autoconversion/accretion derivative, evaporation/freezing/melting derivative, sedimentation flux derivative로 분해해 읽어야 한다. 특히 number concentration이 들어가는 warm-rain path는 q-only scheme의 derivative와 구조적으로 다르다.

KDM6AD의 수학적 설명에서는 다음 표기 규칙을 적용하는 것이 안전하다.

```text
F_micro = L_pos ∘ Pi_sat ∘ S_sed ∘ S_ice ∘ S_warm ∘ S_cond
J_micro = partial F_micro / partial y
JVP(v)  = J_micro v
VJP(w)  = J_micro^T w
```

이 분해는 실제 코드의 정확한 call graph가 아니라 학술적 독해를 위한 operator decomposition이다. 중요한 점은 KDM6AD가 미분하는 대상이 “구름물리 일반”이 아니라 특정 closure와 branch를 가진 discrete KDM6 계열 연산자라는 사실이다. 따라서 Lim 2010의 가치는 KDM6AD의 모든 주장을 보증하는 데 있지 않고, 이 discrete operator가 어떤 계보적 선택 위에 서 있는지 밝히는 데 있다.

## 적대적 검토 포인트

- 논문이 제안한 scheme과 현재 KDM6AD 코드가 같은 version인지 확인하지 않고 동일시하면 안 된다.
- case-study 성능을 AD gradient correctness로 대체하면 안 된다.
- diagnostic output을 AD control/state처럼 서술하면 ABI와 논문 claim이 어긋난다.
- CCN sensitivity는 local activation derivative와 storm-scale coupled response를 분리해야 한다.

이 적대적 검토는 논문의 가치를 낮추려는 것이 아니다. 오히려 학술적 가치를 보존하려면 어떤 주장까지 안전하고 어디서부터 과장인지 분리해야 한다. KDM6AD 위키에서는 이 분리를 페이지마다 남겨, 나중에 신규 논문을 작성하거나 발표자료를 만들 때 문헌의 계보적 의미와 코드의 실제 성취를 혼동하지 않도록 한다.

## 연결된 논문 페이지

- [[paper-H3KYIIM9|Lim 2010]] - Evaluation of the WRF Double‐Moment 6‐Class Microphysics Scheme for Precipitating…
- [[paper-Y8G9YXWQ|Lim 2021]] - Revision of WDM7 Microphysics Scheme and Evaluation for Precipitating Convection …
- [[paper-D629MKTV|Lim 2024]] - Introducing graupel density prediction in Weather Research and Forecasting (WRF) …
- [[paper-LDHPT85H|Morrison 2005]] - A New Double-Moment Microphysics Parameterization for Application in Cloud and Cl…
- [[paper-S98KNIGB|Vié 2016]] - LIMA (v1.0): A quasi two-moment microphysical scheme driven by a multimodal popul…

## 연결된 개념 페이지

- [[KDM6 Literature Genealogy]], [[KDM6AD Mathematical Microphysics Operators]], [[KDM6AD Forward Parity]], [[Bulk Microphysics Design Space]]
- [[KDM6]]
- [[KDM6AD]]

## 읽기 우선순위

1. 먼저 이 페이지의 “계보적 위치”와 “수학적·물리적 구조”를 읽어 KDM6AD와 연결되는 축을 잡는다.
2. 그 다음 연결된 논문 페이지를 따라 선행/후속 문헌을 확인한다.
3. 마지막으로 [[KDM6AD Literature Claim Map]]에서 이 논문으로 정당화 가능한 주장과 불가능한 주장을 대조한다.
