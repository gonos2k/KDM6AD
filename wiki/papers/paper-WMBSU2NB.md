---
title: "On Sedimentation and Advection in Multimoment Bulk Microphysics"
page_kind: paper
zotero_key: WMBSU2NB
year: "2010"
doi: "10.1175/2010jas3341.1"
section: "미세물리 설계공간"
paper_use: "침강/이류 수치일관성과 미분 해석 주의점"
aliases:
  - "On Sedimentation and Advection in Multimoment Bulk Microphysics"
  - "Mansell 2010"
  - "WMBSU2NB"
---
# On Sedimentation and Advection in Multimoment Bulk Microphysics

## 이 페이지의 역할

이 페이지는 Mansell 2010 논문을 일반 초록 수준으로 요약하지 않고, [[KDM6]], [[KDM6AD]], [[KDM6 Literature Genealogy]], [[KDM6AD Literature Claim Map]] 안에서 어떤 학술적 결절점으로 쓰이는지를 정리한다. 목표는 논문 작성용 카드가 아니라, KDM6AD 연구의 과학사·수학·구현·자료동화 계보에서 이 논문이 담당하는 역할을 분명히 하는 것이다.

**핵심 판정:** multimoment bulk microphysics에서 sedimentation/advection을 어떻게 처리하느냐가 moment consistency와 size sorting을 좌우함을 보여준다.

## 기본 서지와 근거 상태

- Zotero key: `WMBSU2NB`
- 연도: `2010`
- 저자: Mansell, Edward R.
- DOI/URL: `10.1175/2010jas3341.1`
- 컬렉션 섹션: `미세물리 설계공간`
- 컬렉션 내 역할: 침강/이류 수치일관성과 미분 해석 주의점
- 근거 상태: PDF 원문 및 추출 텍스트 확보 (`55634` chars extracted). 원문 기반으로 구조를 정리했다.

## 학술적 가치

- KDM6AD의 수치미분 가능성에서 sedimentation은 단순 flux divergence가 아니라 moment별 fall-speed와 limiter가 얽힌 핵심 연산자다.
- forward parity가 raw-bit 수준이어야 하는 이유를 설명한다. sedimentation discretization이 조금만 달라도 hydrometeor distribution과 gradient가 바뀐다.
- multimoment scheme의 moment transport 문제를 KDM6AD ABI/loop structure와 연결할 수 있다.

이 논문의 학술적 가치는 “KDM6AD에 인용할 수 있다”는 수준이 아니라, KDM6AD가 어떤 기존 물리 operator를 미분가능한 계산 대상으로 삼는지 설명하게 해 주는 데 있다. 따라서 이 페이지에서는 논문의 결론을 KDM6AD 성능 주장으로 바로 옮기지 않고, operator, closure, state variable, validation regime 중 어느 부분에 연결되는지를 분리한다.

## 계보적 위치

- Milbrandt/Yau multimoment closure를 수치 transport 문제로 확장한다.
- storm electrification/aerosol effects 문헌과 같은 NSSL/Mansell 계열에서 moment transport가 중요한 이유를 보여준다.
- KDM6AD에서는 source-only AD가 아니라 transport-coupled microphysics AD의 필요성을 환기한다.

섹션 계보 요약: single-moment bulk, double/multimoment closure, spectral-shape 진단, sedimentation size sorting, partial cloudiness, P3 ice-property prediction이 서로 다른 설계 철학을 이룬다.

이 위치 때문에 Mansell 2010은/는 [[KDM6 Literature Genealogy]]에서 단순 참고문헌이 아니라 선행 가정, 비교 계보, 구현 방법론, 또는 관측 응용 중 하나의 노드로 다루어야 한다. 특히 KDM6AD를 설명할 때는 “새 물리 scheme”이라는 표현보다 “기존 KDM/WDM 및 관련 bulk microphysics 계보의 discrete operator를 AD 가능한 표면으로 노출한다”는 해석이 더 정확하다.

## 방법론과 모형 구조

- moment별 sedimentation/advection discretization, size sorting, numerical diffusion 문제를 분석한다.
- mass와 number moment가 다른 fall-speed weighting을 가질 때 PSD evolution이 어떻게 달라지는지 본다.
- bulk scheme에서 moment consistency를 유지하는 numerical choices를 다룬다.

섹션별 문제의식: 이 축은 KDM6의 직접 조상이 아닐 수 있지만, bulk microphysics가 어떤 선택지를 버리거나 채택했는지를 보여준다. 논문을 비교축으로 읽어야 KDM6AD가 미분가능하게 만든 연산자의 과학적 의미와 한계가 분명해진다.

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

- sedimentation은 partial_t M_k + partial_z(V_k M_k)=source 형태이며, V_k는 moment-weighted fall speed다.
- JVP는 flux limiter, upwind choice, boundary condition까지 포함해야 실제 code derivative가 된다.
- VJP에서는 precipitation flux loss가 vertical column states로 역전파되며, limiter activation이 non-smooth point를 만든다.

원문/매니페스트에서 확인한 수학적 읽기 단서:
- 원문 추출에서 radar/reflectivity 관련 표현이 확인되어, observation operator와 hydrometeor moment 연결을 중심으로 읽는다.
- 원문 추출의 수식/기술 단서는 해당 논문을 process-rate closure 또는 model-coupling 문헌으로 읽게 한다.

KDM6AD wiki에서 이 논문을 수학적으로 사용할 때의 기본 원칙은 다음과 같다.

- 모든 derivative는 먼저 discrete operator derivative로 쓴다. 즉 연속 방정식의 미분이 아니라 실제 구현된 `F_micro`의 미분이다.
- PSD closure, moment choice, particle density, fall-speed relation, CCN activation, cloud fraction, observation operator 중 무엇이 derivative의 조건부 가정인지 명시한다.
- branch crossing, saturation adjustment, positivity limiter, hydrometeor category activation 같은 구간에서는 미분가능성을 전역 smooth가 아니라 piecewise 또는 regime-local로 해석한다.

## KDM6AD와 직접 연결되는 지점

- KDM6AD에서 sedimentation을 AD graph에 포함했는지, host transport와 분리했는지 문서화해야 한다.
- single-column parity tests에서 sedimentation on/off가 gradient check 설계를 바꾼다.
- 자료동화에서는 surface precipitation loss가 vertical hydrometeor profiles로 어떻게 돌아가는지 설명한다.

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

- bulk microphysics AD에서 sedimentation/advection은 source-term만큼 중요한 미분대상이다.
- moment consistency는 forward skill뿐 아니라 gradient 해석에도 영향을 준다.

추가로 이 논문은 다음 수준의 주장에만 안전하게 사용한다.

- `미세물리 설계공간` 축에서 KDM6AD의 학술적 위치를 설명하는 근거.
- KDM6AD가 다루는 discrete microphysics operator의 물리적 또는 방법론적 배경.
- 후속 연구 질문을 만드는 계보적 연결.

## 이 논문만으로는 정당화하기 어려운 주장

- scheme-specific numerical choices가 KDM6 코드와 다를 수 있다.
- 일반적인 moment transport 원리로 사용하고 세부 구현 등치는 피해야 한다.

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

| 축 | Mansell 2010에서 확인할 내용 | KDM6AD에서 남는 의미 |
| --- | --- | --- |
| 대안 closure | KDM6이 채택하지 않은 single/double/three-moment, P3, partial-cloud, sedimentation 설계를 비교한다. | KDM6AD의 derivative가 어떤 closure에 조건부인지 명시할 수 있다. |
| PSD 가정 | gamma PSD, spectral shape, intercept, density, fall-speed relation이 process rate를 지배한다. | gradient는 “물리의 절대 도함수”가 아니라 “closure-conditioned discrete derivative”다. |
| scale 문제 | grid-mean process rate와 subgrid/cloudy-area process rate가 다를 수 있다. | 자료동화에서 관측 footprint와 모델 operator scale이 어긋나면 VJP 해석이 약해진다. |
| category 문제 | snow/graupel/hail 같은 fixed categories와 property-prediction schemes가 서로 다른 해석 단위를 만든다. | KDM6AD의 adjoint attribution은 category definition에 의존한다. |

이 매트릭스의 목적은 Mansell 2010을/를 단순히 “관련 논문”으로 묶지 않고, KDM6AD의 물리 계보에서 어떤 추상화 수준에 놓이는지 고정하는 것이다. 같은 bulk microphysics 문헌이라도 하나는 직접 조상, 하나는 대안 closure, 하나는 구현 방법론, 하나는 관측연산자 계보일 수 있다. 이 구분이 없으면 KDM6AD 설명은 문헌 목록은 길지만 과학적 주장은 흐린 상태가 된다.

## KDM6AD 연산자 대응

이 축은 KDM6AD의 `F_micro`가 채택한 closure를 상대화한다. 같은 q와 N이라도 shape parameter, density, fall-speed, cloud fraction, ice property state가 다르면 `F_micro`와 `dF_micro/dy`가 달라진다. 따라서 비교문헌은 KDM6AD의 우월성 근거가 아니라 조건부 해석의 경계다.

Mansell 2010을/를 KDM6AD 코드와 연결할 때는 다음 대응을 확인한다.

- State 대응: 논문에서 의미 있는 prognostic 또는 diagnostic 변수가 KDM6AD의 packed state, host state, diagnostic output 중 어디에 들어가는가.
- Closure 대응: PSD, density, fall-speed, activation, saturation, cloud fraction, category conversion 같은 closure가 fixed constant인지, diagnostic relation인지, differentiable input인지 구분한다.
- Process 대응: 논문이 강조하는 과정이 KDM6AD의 source term, adjustment, sedimentation, post-step coupling 중 어디에 해당하는가.
- Gradient 대응: JVP로 볼 perturbation direction과 VJP로 되돌릴 adjoint seed를 명확히 정한다.
- Evidence 대응: 이 논문으로 뒷받침할 수 있는 것은 물리 계보인지, 구현 방법론인지, DA 응용 가능성인지 분리한다.

## 미분가능 미세물리 관점의 수학적 독해

설계공간 논문은 `C_theta: y -> (N0,lambda,mu,rho,v_t,cloud_fraction)` 같은 closure mapping으로 읽을 수 있다. KDM6AD의 Jacobian은 `partial P/partial C * partial C/partial y`를 포함하거나, C가 fixed parameter이면 그 항을 제외한다. 이 차이를 명시하지 않으면 derivative의 물리 의미가 흐려진다.

KDM6AD의 수학적 설명에서는 다음 표기 규칙을 적용하는 것이 안전하다.

```text
F_micro = L_pos ∘ Pi_sat ∘ S_sed ∘ S_ice ∘ S_warm ∘ S_cond
J_micro = partial F_micro / partial y
JVP(v)  = J_micro v
VJP(w)  = J_micro^T w
```

이 분해는 실제 코드의 정확한 call graph가 아니라 학술적 독해를 위한 operator decomposition이다. 중요한 점은 KDM6AD가 미분하는 대상이 “구름물리 일반”이 아니라 특정 closure와 branch를 가진 discrete KDM6 계열 연산자라는 사실이다. 따라서 Mansell 2010의 가치는 KDM6AD의 모든 주장을 보증하는 데 있지 않고, 이 discrete operator가 어떤 계보적 선택 위에 서 있는지 밝히는 데 있다.

## 적대적 검토 포인트

- 비교 scheme의 성공을 KDM6AD 성능 주장으로 가져오면 안 된다.
- closure parameter가 fixed인지 prognostic인지 diagnostic인지 구분해야 한다.
- partial cloudiness나 P3 같은 대안 설계를 KDM6 현행 state에 이미 포함된 것처럼 쓰면 안 된다.
- smooth한 property prediction도 ratio, positivity limiter, category activation에서 비매끄러움을 만들 수 있다.

이 적대적 검토는 논문의 가치를 낮추려는 것이 아니다. 오히려 학술적 가치를 보존하려면 어떤 주장까지 안전하고 어디서부터 과장인지 분리해야 한다. KDM6AD 위키에서는 이 분리를 페이지마다 남겨, 나중에 신규 논문을 작성하거나 발표자료를 만들 때 문헌의 계보적 의미와 코드의 실제 성취를 혼동하지 않도록 한다.

## 연결된 논문 페이지

- [[paper-UTM4WM2T|Milbrandt 2005]] - A Multimoment Bulk Microphysics Parameterization. Part I: Analysis of the Role of…
- [[paper-4NU3SNG7|Milbrandt 2005]] - A Multimoment Bulk Microphysics Parameterization. Part II: A Proposed Three-Momen…
- [[paper-W5UHJDNL|Mansell 2010]] - Simulated Electrification of a Small Thunderstorm with Two-Moment Bulk Microphysi…
- [[paper-E6KDCS3V|Baumgartner 2019]] - Algorithmic differentiation for cloud schemes (IFS Cy43r3) using CoDiPack (v1.8.1)

## 연결된 개념 페이지

- [[Bulk Microphysics Design Space]], [[KDM6 Literature Genealogy]], [[KDM6AD Differentiability Audit]], [[KDM6AD Mathematical Microphysics Operators]]
- [[KDM6]]
- [[KDM6AD]]

## 읽기 우선순위

1. 먼저 이 페이지의 “계보적 위치”와 “수학적·물리적 구조”를 읽어 KDM6AD와 연결되는 축을 잡는다.
2. 그 다음 연결된 논문 페이지를 따라 선행/후속 문헌을 확인한다.
3. 마지막으로 [[KDM6AD Literature Claim Map]]에서 이 논문으로 정당화 가능한 주장과 불가능한 주장을 대조한다.
