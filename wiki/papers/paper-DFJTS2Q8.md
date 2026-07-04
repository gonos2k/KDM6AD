---
title: "The Korean Integrated Model (KIM) System for Global Weather Forecasting"
page_kind: paper
zotero_key: DFJTS2Q8
year: "2018"
doi: "10.1007/s13143-018-0028-9"
section: "원문 보강 필요"
paper_use: "미세물리 설계공간 또는 비교 문헌"
aliases:
  - "The Korean Integrated Model (KIM) System for Global Weather Forecasting"
  - "Hong 2018"
  - "DFJTS2Q8"
---
# The Korean Integrated Model (KIM) System for Global Weather Forecasting

## 이 페이지의 역할

이 페이지는 Hong 2018 논문을 일반 초록 수준으로 요약하지 않고, [[KDM6]], [[KDM6AD]], [[KDM6 Literature Genealogy]], [[KDM6AD Literature Claim Map]] 안에서 어떤 학술적 결절점으로 쓰이는지를 정리한다. 목표는 논문 작성용 카드가 아니라, KDM6AD 연구의 과학사·수학·구현·자료동화 계보에서 이 논문이 담당하는 역할을 분명히 하는 것이다.

**핵심 판정:** KIM system paper는 KDM6AD가 실제로 접속하려는 KIM/Korea operational modeling 생태계의 host-level 배경을 제공한다.

## 기본 서지와 근거 상태

- Zotero key: `DFJTS2Q8`
- 연도: `2018`
- 저자: Hong, Song-You; Kwon, Young Cheol; Kim, Tae-Hun; Kim, Jung-Eun Esther; Choi, Suk-Jin; Kwon, In-Hyuk; Kim, Junghan; Lee, Eun-Hee; Park, Rae-Seol; Kim, Dong-Il
- DOI/URL: `10.1007/s13143-018-0028-9`
- 컬렉션 섹션: `원문 보강 필요`
- 컬렉션 내 역할: 미세물리 설계공간 또는 비교 문헌
- 근거 상태: 원문 PDF 미확보. Springer 공개 Abstract 기준: https://link.springer.com/article/10.1007/s13143-018-0028-9

## 학술적 가치

- KDM6AD가 독립 라이브러리 장난이 아니라 KIM-meso/WRF host와 operational NWP physics package에 접속되는 연구임을 설명한다.
- KIM의 nonhydrostatic cubed-sphere dynamical core, physics package, hybrid 4DEnVar context는 microphysics AD가 어디에 들어갈 수 있는지 큰 그림을 준다.
- 자료동화 확장을 말할 때 KIM이 이미 advanced DA framework를 갖는다는 계보적 연결을 제공한다.

이 논문의 학술적 가치는 “KDM6AD에 인용할 수 있다”는 수준이 아니라, KDM6AD가 어떤 기존 물리 operator를 미분가능한 계산 대상으로 삼는지 설명하게 해 주는 데 있다. 따라서 이 페이지에서는 논문의 결론을 KDM6AD 성능 주장으로 바로 옮기지 않고, operator, closure, state variable, validation regime 중 어느 부분에 연결되는지를 분리한다.

## 계보적 위치

- Korean NWP model development 계보에서 WSM/WDM/KDM microphysics가 들어갈 host context를 설명한다.
- partial cloudiness, KDM/WDM microphysics, 4DEnVar DA와 연결된다.
- KDM6AD는 이 host ecosystem 안에서 microphysics operator의 differentiable replacement/parallel path로 위치한다.

섹션 계보 요약: 불완전 근거 문헌은 확정 주장보다 “보강해야 할 계보 연결”로 취급한다. 특히 Seifert-Beheng two-moment, P3, KIM, WSM7 hail은 KDM6AD 설명에서 연결성이 크다.

이 위치 때문에 Hong 2018은/는 [[KDM6 Literature Genealogy]]에서 단순 참고문헌이 아니라 선행 가정, 비교 계보, 구현 방법론, 또는 관측 응용 중 하나의 노드로 다루어야 한다. 특히 KDM6AD를 설명할 때는 “새 물리 scheme”이라는 표현보다 “기존 KDM/WDM 및 관련 bulk microphysics 계보의 discrete operator를 AD 가능한 표면으로 노출한다”는 해석이 더 정확하다.

## 방법론과 모형 구조

- KIM global model system의 dynamical core, physics parameterization package, DA framework, performance evolution을 소개한다.
- 12-km global forecast framework와 operational deployment strategy를 설명한다.
- KMA operational model replacement context를 제공한다.

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

- host model 전체는 M = DYN ∘ PHYS ∘ DA initialization으로 볼 수 있고, KDM6AD는 PHYS 안의 microphysics block derivative를 제공한다.
- hybrid 4DEnVar는 full adjoint-free/ensemble covariance elements를 갖지만, process-level derivatives는 future hybrid DA에 추가 정보를 줄 수 있다.
- KDM6AD가 host dynamics derivative를 제공하는 것은 아니므로 chain 범위를 분명히 해야 한다.

원문/매니페스트에서 확인한 수학적 읽기 단서:
- 매니페스트에 별도 math snippet이 없다. 페이지의 수학 해석은 제목, 섹션, 확보된 초록/원문 구조와 KDM6AD operator 관점에서 작성했다.

KDM6AD wiki에서 이 논문을 수학적으로 사용할 때의 기본 원칙은 다음과 같다.

- 모든 derivative는 먼저 discrete operator derivative로 쓴다. 즉 연속 방정식의 미분이 아니라 실제 구현된 `F_micro`의 미분이다.
- PSD closure, moment choice, particle density, fall-speed relation, CCN activation, cloud fraction, observation operator 중 무엇이 derivative의 조건부 가정인지 명시한다.
- branch crossing, saturation adjustment, positivity limiter, hydrometeor category activation 같은 구간에서는 미분가능성을 전역 smooth가 아니라 piecewise 또는 regime-local로 해석한다.

## KDM6AD와 직접 연결되는 지점

- KDM6AD의 practical relevance와 자료동화 확장 스토리를 host-level로 고정한다.
- KIM 4DEnVar와 KDM6AD VJP/JVP를 연결할 때는 “가능한 접점”으로 조심스럽게 표현해야 한다.
- 원문 미확보 상태라 세부 성능수치는 사용하지 않는다.

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

- KDM6AD는 KIM/Korea NWP physics ecosystem과 연결될 때 학술·실용적 의미가 커진다.
- microphysics AD는 full NWP/DA system 안의 한 block으로 위치해야 한다.

추가로 이 논문은 다음 수준의 주장에만 안전하게 사용한다.

- `원문 보강 필요` 축에서 KDM6AD의 학술적 위치를 설명하는 근거.
- KDM6AD가 다루는 discrete microphysics operator의 물리적 또는 방법론적 배경.
- 후속 연구 질문을 만드는 계보적 연결.

## 이 논문만으로는 정당화하기 어려운 주장

- KIM system paper는 KDM6AD 구현 논문이 아니다.
- global KIM과 현재 KDM6AD-k의 bundled host 범위가 다를 수 있다.

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

| 축 | Hong 2018에서 확인할 내용 | KDM6AD에서 남는 의미 |
| --- | --- | --- |
| 근거 등급 | PDF 원문이 없으므로 공개 초록, 출판사 summary, DOI metadata, 확립된 계보만 사용한다. | 세부 수치·그림·case conclusion은 원문 확보 전까지 claim으로 쓰지 않는다. |
| 계보 필요성 | 원문이 없어도 Seifert-Beheng, P3, KIM, WSM7 같은 결절점은 KDM6AD 계보에서 빠질 수 없다. | 보수적 연결과 보강 필요성을 함께 기록한다. |
| 수학 축 | moment closure, particle property, DA host context 같은 구조적 함의만 정리한다. | KDM6AD의 derivative claim은 가능한 경로 수준으로 제한한다. |
| 후속 작업 | Zotero 원문 확보 후 계수, 실험 설계, 결과, 그림 해석을 추가한다. | 현재 페이지는 연구지도이자 감사 로그다. |

이 매트릭스의 목적은 Hong 2018을/를 단순히 “관련 논문”으로 묶지 않고, KDM6AD의 물리 계보에서 어떤 추상화 수준에 놓이는지 고정하는 것이다. 같은 bulk microphysics 문헌이라도 하나는 직접 조상, 하나는 대안 closure, 하나는 구현 방법론, 하나는 관측연산자 계보일 수 있다. 이 구분이 없으면 KDM6AD 설명은 문헌 목록은 길지만 과학적 주장은 흐린 상태가 된다.

## KDM6AD 연산자 대응

이 축의 페이지는 KDM6AD claim의 직접 근거가 아니라 missing-but-relevant genealogy를 보존한다. operator 대응도 “현재 구현됨”이 아니라 “이런 state/parameter/operator가 후속 확장 후보”라는 수준으로 쓴다.

Hong 2018을/를 KDM6AD 코드와 연결할 때는 다음 대응을 확인한다.

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

이 분해는 실제 코드의 정확한 call graph가 아니라 학술적 독해를 위한 operator decomposition이다. 중요한 점은 KDM6AD가 미분하는 대상이 “구름물리 일반”이 아니라 특정 closure와 branch를 가진 discrete KDM6 계열 연산자라는 사실이다. 따라서 Hong 2018의 가치는 KDM6AD의 모든 주장을 보증하는 데 있지 않고, 이 discrete operator가 어떤 계보적 선택 위에 서 있는지 밝히는 데 있다.

## 적대적 검토 포인트

- 원문 없이 세부 계수나 결과 수치를 확정적으로 쓰면 안 된다.
- 공개 초록 문구를 넘어선 해석은 “계보적 추정” 또는 “후속 확인 필요”로 표시해야 한다.
- KDM6AD 구현과의 직접 대응은 코드와 원문이 모두 확인된 후에만 주장한다.
- 이 페이지는 삭제 대상이 아니라 보강 우선순위 목록으로 관리한다.

이 적대적 검토는 논문의 가치를 낮추려는 것이 아니다. 오히려 학술적 가치를 보존하려면 어떤 주장까지 안전하고 어디서부터 과장인지 분리해야 한다. KDM6AD 위키에서는 이 분리를 페이지마다 남겨, 나중에 신규 논문을 작성하거나 발표자료를 만들 때 문헌의 계보적 의미와 코드의 실제 성취를 혼동하지 않도록 한다.

## 연결된 논문 페이지

- [[paper-YUBAXLI6|Hong 2018]] - The Use of Partial Cloudiness in a Bulk Cloud Microphysics Scheme: Concept and 2D…
- [[paper-YKPE6B2X|Bae 2019]] - Effects of Partial Cloudiness in a Cloud Microphysics Scheme on Simulated Precipi…
- [[paper-6P3B5EDZ|Lim 2010]] - Development of an Effective Double-Moment Cloud Microphysics Scheme with Prognost…
- [[paper-DMKR59F5|Wang 2011]] - Radar Reflectivity Assimilation with the updated WRFDA-4DVAR system

## 연결된 개념 페이지

- [[KDM6 Literature Genealogy]], [[Bulk Microphysics Design Space]], [[KDM6AD Literature Claim Map]], [[Differentiable Bulk Microphysics Research Gap]]
- [[KDM6]]
- [[KDM6AD]]

## 읽기 우선순위

1. 먼저 이 페이지의 “계보적 위치”와 “수학적·물리적 구조”를 읽어 KDM6AD와 연결되는 축을 잡는다.
2. 그 다음 연결된 논문 페이지를 따라 선행/후속 문헌을 확인한다.
3. 마지막으로 [[KDM6AD Literature Claim Map]]에서 이 논문으로 정당화 가능한 주장과 불가능한 주장을 대조한다.
