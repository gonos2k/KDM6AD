---
title: "A New Double-Moment Microphysics Parameterization for Application in Cloud and Climate Models. Part I: Description"
page_kind: paper
zotero_key: LDHPT85H
year: "2005"
doi: "10.1175/jas3446.1"
section: "KDM/WDM 계열 핵심 미세물리"
paper_use: "미세물리 설계공간 또는 비교 문헌"
aliases:
  - "A New Double-Moment Microphysics Parameterization for Application in Cloud and Climate Models. Part I: Description"
  - "Morrison 2005"
  - "LDHPT85H"
---
# A New Double-Moment Microphysics Parameterization for Application in Cloud and Climate Models. Part I: Description

## 이 페이지의 역할

이 페이지는 Morrison 2005 논문을 일반 초록 수준으로 요약하지 않고, [[KDM6]], [[KDM6AD]], [[KDM6 Literature Genealogy]], [[KDM6AD Literature Claim Map]] 안에서 어떤 학술적 결절점으로 쓰이는지를 정리한다. 목표는 논문 작성용 카드가 아니라, KDM6AD 연구의 과학사·수학·구현·자료동화 계보에서 이 논문이 담당하는 역할을 분명히 하는 것이다.

**핵심 판정:** double-moment bulk microphysics가 단순한 “상태변수 추가”가 아니라 size spectrum의 자유도를 늘려 cloud/climate model의 aerosol-cloud-precipitation 연결을 바꾸는 방법임을 체계화한 기준점이다.

## 기본 서지와 근거 상태

- Zotero key: `LDHPT85H`
- 연도: `2005`
- 저자: Morrison, H.; Curry, J. A.; Khvorostyanov, V. I.
- DOI/URL: `10.1175/jas3446.1`
- 컬렉션 섹션: `KDM/WDM 계열 핵심 미세물리`
- 컬렉션 내 역할: 미세물리 설계공간 또는 비교 문헌
- 근거 상태: PDF 원문 및 추출 텍스트 확보 (`99330` chars extracted). 원문 기반으로 구조를 정리했다.

## 학술적 가치

- single-moment scheme의 q-only closure가 평균입자 크기와 수농도를 분리하지 못하는 문제를 드러내고, q와 N을 동시에 예측하는 문법을 대기모델 물리 패키지 안에 정착시킨다.
- KDM6AD에서 q와 N의 동시 미분을 주장하려면, 이 논문은 “왜 number concentration이 prognostic state가 되어야 하는가”를 설명하는 선행 근거가 된다.
- 기후모델 문맥의 bulk scheme이라 WRF/KIM mesoscale scheme과 완전히 같지는 않지만, 모멘트 기반 미세물리의 언어를 공유한다.

이 논문의 학술적 가치는 “KDM6AD에 인용할 수 있다”는 수준이 아니라, KDM6AD가 어떤 기존 물리 operator를 미분가능한 계산 대상으로 삼는지 설명하게 해 주는 데 있다. 따라서 이 페이지에서는 논문의 결론을 KDM6AD 성능 주장으로 바로 옮기지 않고, operator, closure, state variable, validation regime 중 어느 부분에 연결되는지를 분리한다.

## 계보적 위치

- Kessler/Lin류 단일모멘트 계보에서 double-moment 계보로 넘어가는 다리 역할을 한다.
- WDM6의 cloud/rain number 및 CCN prognostic 확장과 직접적인 사상은 다르지만, KDM6AD의 state-space 확장 정당화에 들어간다.
- LIMA, CAM double-moment, aerosol-aware schemes가 이 문제의식을 이어받는다.

섹션 계보 요약: Lin/WSM식 단일모멘트 ice microphysics에서 WDM6의 double-moment warm-rain 및 CCN prognostic state로 이동하고, 이후 WDM7·graupel density·KIM host 통합으로 확장되는 흐름이다.

이 위치 때문에 Morrison 2005은/는 [[KDM6 Literature Genealogy]]에서 단순 참고문헌이 아니라 선행 가정, 비교 계보, 구현 방법론, 또는 관측 응용 중 하나의 노드로 다루어야 한다. 특히 KDM6AD를 설명할 때는 “새 물리 scheme”이라는 표현보다 “기존 KDM/WDM 및 관련 bulk microphysics 계보의 discrete operator를 AD 가능한 표면으로 노출한다”는 해석이 더 정확하다.

## 방법론과 모형 구조

- hydrometeor mass와 number moment를 함께 다루어 mean size와 process rate를 분리한다.
- autoconversion, accretion, deposition, freezing 등 bulk source를 PSD moment의 함수로 닫는다.
- aerosol-cloud interaction은 단일 q budget으로는 설명하기 어려운 민감도 축을 제공한다.

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

- M0=N, M3~q의 관계에서 lambda(q,N)가 정해지고, process rate P(q,N,T,rv) 역시 lambda를 통해 간접 의존한다.
- KDM6AD의 JVP에서 delta q와 delta N은 같은 source term에 서로 다른 경로로 진입하므로, q-only scheme보다 tangent structure가 풍부하다.
- limiter와 saturation branch가 들어가는 순간 formal smoothness는 piecewise-smooth로 낮아진다.

원문/매니페스트에서 확인한 수학적 읽기 단서:
- 원문 추출의 수식/기술 단서는 해당 논문을 process-rate closure 또는 model-coupling 문헌으로 읽게 한다.

KDM6AD wiki에서 이 논문을 수학적으로 사용할 때의 기본 원칙은 다음과 같다.

- 모든 derivative는 먼저 discrete operator derivative로 쓴다. 즉 연속 방정식의 미분이 아니라 실제 구현된 `F_micro`의 미분이다.
- PSD closure, moment choice, particle density, fall-speed relation, CCN activation, cloud fraction, observation operator 중 무엇이 derivative의 조건부 가정인지 명시한다.
- branch crossing, saturation adjustment, positivity limiter, hydrometeor category activation 같은 구간에서는 미분가능성을 전역 smooth가 아니라 piecewise 또는 regime-local로 해석한다.

## KDM6AD와 직접 연결되는 지점

- KDM6AD가 “미분가능한 WDM/KDM 계열 구현”임을 설명할 때 double-moment state의 과학적 필요성을 제공한다.
- VJP 관점에서는 precipitation error가 number concentration과 mass moment 중 어느 축으로 되돌아가는지 해석하는 근거가 된다.
- 단, 이 논문은 KDM6AD 구현 논문이 아니므로 libtorch/Fortran ABI 자체의 근거로 쓰면 안 된다.

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

- double-moment microphysics는 q-only scheme보다 PSD 자유도를 더 많이 가진다.
- KDM6AD에서 q와 N을 함께 미분하는 것은 물리적으로 의미 있는 sensitivity family다.

추가로 이 논문은 다음 수준의 주장에만 안전하게 사용한다.

- `KDM/WDM 계열 핵심 미세물리` 축에서 KDM6AD의 학술적 위치를 설명하는 근거.
- KDM6AD가 다루는 discrete microphysics operator의 물리적 또는 방법론적 배경.
- 후속 연구 질문을 만드는 계보적 연결.

## 이 논문만으로는 정당화하기 어려운 주장

- KDM6의 구체적 코드 상수와 branch를 검증해 주지는 않는다.
- cloud/climate model 문맥이므로 convective storm 또는 KIM host parity 결과와 직접 등치하면 안 된다.

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

| 축 | Morrison 2005에서 확인할 내용 | KDM6AD에서 남는 의미 |
| --- | --- | --- |
| 직접 조상성 | WSM/WDM/KDM 계열의 상태변수와 process closure가 어떻게 현재 KDM6AD의 forward target이 되는지 확인한다. | mp37 KDM6와 mp137 KDM6AD의 parity는 단순 numerical regression이 아니라 이 계보의 물리 의미를 보존하는 시험이다. |
| moment 구조 | mass mixing ratio q만 볼 것인지, cloud/rain number와 CCN까지 state로 둘 것인지가 핵심이다. | JVP/VJP에서 q, Nc, Nr, NCCN perturbation을 분리해 해석해야 한다. |
| 진단량 | reflectivity, graupel density, precipitation rate 같은 값은 prognostic state와 diagnostic의 경계에 놓인다. | 진단량을 ABI state로 승격하지 않으면 gradient target이 아니라 forward diagnostic으로 남는다. |
| 검증 계보 | 개발 논문과 평가 논문을 분리해야 한다. 개발은 state/closure를, 평가는 적용 regime을 설명한다. | KDM6AD 검증도 forward parity, gradient check, observation-space utility를 분리해야 한다. |

이 매트릭스의 목적은 Morrison 2005을/를 단순히 “관련 논문”으로 묶지 않고, KDM6AD의 물리 계보에서 어떤 추상화 수준에 놓이는지 고정하는 것이다. 같은 bulk microphysics 문헌이라도 하나는 직접 조상, 하나는 대안 closure, 하나는 구현 방법론, 하나는 관측연산자 계보일 수 있다. 이 구분이 없으면 KDM6AD 설명은 문헌 목록은 길지만 과학적 주장은 흐린 상태가 된다.

## KDM6AD 연산자 대응

KDM/WDM 계열을 KDM6AD operator로 옮기면 `y=(q_v,q_c,q_r,q_i,q_s,q_g,N_c,N_r,N_CCN,T,...)`와 같은 상태에서 `F_micro(y)`가 한 timestep tendency 또는 updated state를 만든다. 여기서 scientific claim은 “새 물리”가 아니라 “이산화된 기존 물리 연산자의 AD-compatible representation”이다.

Morrison 2005을/를 KDM6AD 코드와 연결할 때는 다음 대응을 확인한다.

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

이 분해는 실제 코드의 정확한 call graph가 아니라 학술적 독해를 위한 operator decomposition이다. 중요한 점은 KDM6AD가 미분하는 대상이 “구름물리 일반”이 아니라 특정 closure와 branch를 가진 discrete KDM6 계열 연산자라는 사실이다. 따라서 Morrison 2005의 가치는 KDM6AD의 모든 주장을 보증하는 데 있지 않고, 이 discrete operator가 어떤 계보적 선택 위에 서 있는지 밝히는 데 있다.

## 적대적 검토 포인트

- 논문이 제안한 scheme과 현재 KDM6AD 코드가 같은 version인지 확인하지 않고 동일시하면 안 된다.
- case-study 성능을 AD gradient correctness로 대체하면 안 된다.
- diagnostic output을 AD control/state처럼 서술하면 ABI와 논문 claim이 어긋난다.
- CCN sensitivity는 local activation derivative와 storm-scale coupled response를 분리해야 한다.

이 적대적 검토는 논문의 가치를 낮추려는 것이 아니다. 오히려 학술적 가치를 보존하려면 어떤 주장까지 안전하고 어디서부터 과장인지 분리해야 한다. KDM6AD 위키에서는 이 분리를 페이지마다 남겨, 나중에 신규 논문을 작성하거나 발표자료를 만들 때 문헌의 계보적 의미와 코드의 실제 성취를 혼동하지 않도록 한다.

## 연결된 논문 페이지

- [[paper-6P3B5EDZ|Lim 2010]] - Development of an Effective Double-Moment Cloud Microphysics Scheme with Prognost…
- [[paper-7JDU3L3I|Morrison 2008]] - A New Two-Moment Bulk Stratiform Cloud Microphysics Scheme in the Community Atmos…
- [[paper-Q7L5Z453|Morrison 2008]] - A New Two-Moment Bulk Stratiform Cloud Microphysics Scheme in the Community Atmos…
- [[paper-S98KNIGB|Vié 2016]] - LIMA (v1.0): A quasi two-moment microphysical scheme driven by a multimodal popul…
- [[paper-FPPAYJ7D|Seifert 2005]] - A two-moment cloud microphysics parameterization for mixed-phase clouds. Part 1: …

## 연결된 개념 페이지

- [[KDM6 Literature Genealogy]], [[KDM6AD Mathematical Microphysics Operators]], [[KDM6AD Forward Parity]], [[Bulk Microphysics Design Space]]
- [[KDM6]]
- [[KDM6AD]]

## 읽기 우선순위

1. 먼저 이 페이지의 “계보적 위치”와 “수학적·물리적 구조”를 읽어 KDM6AD와 연결되는 축을 잡는다.
2. 그 다음 연결된 논문 페이지를 따라 선행/후속 문헌을 확인한다.
3. 마지막으로 [[KDM6AD Literature Claim Map]]에서 이 논문으로 정당화 가능한 주장과 불가능한 주장을 대조한다.
