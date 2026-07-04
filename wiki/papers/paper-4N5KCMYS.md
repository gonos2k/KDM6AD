---
title: "FTorch: a library for coupling PyTorch models to Fortran"
page_kind: paper
zotero_key: 4N5KCMYS
year: "2025"
doi: "10.21105/joss.07602"
section: "자동미분·미분가능 구현"
paper_use: "Fortran 모델과 PyTorch/ML 컴포넌트 결합 근거"
aliases:
  - "FTorch: a library for coupling PyTorch models to Fortran"
  - "Atkinson 2025"
  - "4N5KCMYS"
---
# FTorch: a library for coupling PyTorch models to Fortran

## 이 페이지의 역할

이 페이지는 Atkinson 2025 논문을 일반 초록 수준으로 요약하지 않고, [[KDM6]], [[KDM6AD]], [[KDM6 Literature Genealogy]], [[KDM6AD Literature Claim Map]] 안에서 어떤 학술적 결절점으로 쓰이는지를 정리한다. 목표는 논문 작성용 카드가 아니라, KDM6AD 연구의 과학사·수학·구현·자료동화 계보에서 이 논문이 담당하는 역할을 분명히 하는 것이다.

**핵심 판정:** FTorch는 PyTorch 모델을 Fortran 코드에 결합하는 라이브러리로, KDM6AD의 Fortran host와 libtorch/C++ AD surface를 설명할 때 중요한 기술 계보 문헌이다.

## 기본 서지와 근거 상태

- Zotero key: `4N5KCMYS`
- 연도: `2025`
- 저자: Atkinson, Jack; Elafrou, Athena; Kasoar, Elliott; Wallwork, Joseph G.; Meltzer, Thomas; Clifford, Simon; Orchard, Dominic; Edsall, Chris
- DOI/URL: `10.21105/joss.07602`
- 컬렉션 섹션: `자동미분·미분가능 구현`
- 컬렉션 내 역할: Fortran 모델과 PyTorch/ML 컴포넌트 결합 근거
- 근거 상태: PDF 원문 및 추출 텍스트 확보 (`21286` chars extracted). 원문 기반으로 구조를 정리했다.

## 학술적 가치

- KDM6AD가 왜 Fortran ABI, C bridge, libtorch runtime이라는 구조를 갖는지 현대 Fortran-ML coupling 관점에서 위치시킨다.
- legacy atmospheric model과 PyTorch ecosystem을 연결할 때 자료형, memory layout, build/linking, runtime ownership이 핵심임을 보여준다.
- KDM6AD는 neural network coupling이 아니라 physical operator port지만, 기술적으로 같은 경계면 문제를 가진다.

이 논문의 학술적 가치는 “KDM6AD에 인용할 수 있다”는 수준이 아니라, KDM6AD가 어떤 기존 물리 operator를 미분가능한 계산 대상으로 삼는지 설명하게 해 주는 데 있다. 따라서 이 페이지에서는 논문의 결론을 KDM6AD 성능 주장으로 바로 옮기지 않고, operator, closure, state variable, validation regime 중 어느 부분에 연결되는지를 분리한다.

## 계보적 위치

- Fortran legacy model -> C/C++ bridge -> PyTorch/libtorch coupling 계열의 구현 문헌이다.
- SuperdropNet, hybrid AI climate model, JAX-SCM/JCM과 함께 differentiable infrastructure 계보를 만든다.
- KDM6AD의 ISO_C bridge와 C ABI 설명에 직접 연결된다.

섹션 계보 요약: 수동 tangent-linear/adjoint에서 source-transformation AD, operator-overloading AD, differentiable programming, ML-physics coupling, JAX 기반 atmospheric model로 이어지는 구현 계보다.

이 위치 때문에 Atkinson 2025은/는 [[KDM6 Literature Genealogy]]에서 단순 참고문헌이 아니라 선행 가정, 비교 계보, 구현 방법론, 또는 관측 응용 중 하나의 노드로 다루어야 한다. 특히 KDM6AD를 설명할 때는 “새 물리 scheme”이라는 표현보다 “기존 KDM/WDM 및 관련 bulk microphysics 계보의 discrete operator를 AD 가능한 표면으로 노출한다”는 해석이 더 정확하다.

## 방법론과 모형 구조

- Fortran에서 PyTorch model을 호출할 수 있도록 binding, tensor conversion, runtime management를 제공한다.
- compiled model 또는 TorchScript/libtorch 기반 workflow를 다룬다.
- HPC/legacy codebase에서 ML component를 안전하게 호출하는 engineering pattern을 제시한다.

섹션별 문제의식: 이 축은 “미세물리 scheme을 AD에 태울 수 있는가”를 넘어, legacy Fortran/C++/Python/JAX 생태계에서 미분가능 모델을 어떻게 검증하고 계산비용을 통제할지 다룬다.

KDM6AD 관점에서 방법론을 읽을 때는 세 층을 분리한다.

- 물리 계층: 어떤 hydrometeor, aerosol/CCN, ice property, cloud fraction 또는 관측량을 다루는가.
- 수치 계층: source term integration, saturation adjustment, sedimentation, limiter, clipping, lookup 또는 branch가 어떻게 들어가는가.
- 미분 계층: 위 수치 연산이 JVP/VJP에서 smooth, piecewise-smooth, discontinuous, diagnostic-only 중 어디에 놓이는가.

## 수학적·물리적 구조

```text
y_{n+1} = F_micro(y_n, theta)
JVP: delta y_{n+1} = (partial F_micro / partial y) delta y_n
VJP: bar y_n = (partial F_micro / partial y)^T bar y_{n+1}
```
여기서 derivative는 연속 방정식의 이상화 도함수가 아니라, limiter와 branch를 포함한 discrete implementation의 도함수로 읽어야 한다.

- 수학보다는 ABI가 핵심이지만, F_fortran(y) -> G_torch(y) coupling에서 gradient를 보존하려면 tensor ownership과 dtype 변환이 계산그래프를 끊지 않아야 한다.
- KDM6AD에서 f32 forward parity와 fp64 AD path를 분리하면 derivative semantics를 문서화해야 한다.
- VJP/JVP handle은 host language boundary를 넘는 adjoint state의 life-cycle 문제를 만든다.

원문/매니페스트에서 확인한 수학적 읽기 단서:
- 원문 추출에서 AD/adjoint/sensitivity 관련 표현이 확인되어, discrete derivative와 검증 구조를 중심으로 읽는다.
- 원문 추출의 수식/기술 단서는 해당 논문을 process-rate closure 또는 model-coupling 문헌으로 읽게 한다.

KDM6AD wiki에서 이 논문을 수학적으로 사용할 때의 기본 원칙은 다음과 같다.

- 모든 derivative는 먼저 discrete operator derivative로 쓴다. 즉 연속 방정식의 미분이 아니라 실제 구현된 `F_micro`의 미분이다.
- PSD closure, moment choice, particle density, fall-speed relation, CCN activation, cloud fraction, observation operator 중 무엇이 derivative의 조건부 가정인지 명시한다.
- branch crossing, saturation adjustment, positivity limiter, hydrometeor category activation 같은 구간에서는 미분가능성을 전역 smooth가 아니라 piecewise 또는 regime-local로 해석한다.

## KDM6AD와 직접 연결되는 지점

- KDM6AD의 Fortran-C++ bridge를 학술적으로 설명하는 기술 참고문헌이다.
- `.item()`, detach, no_grad 같은 graph-breaking operation을 피해야 하는 이유를 설명할 수 있다.
- 단, FTorch 자체가 KDM6AD 구현에 사용되었다고 쓰려면 코드상 확인이 필요하다.

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

- legacy Fortran atmospheric model과 differentiable PyTorch/libtorch ecosystem의 결합은 독립적인 기술 연구축이다.
- KDM6AD의 ABI 설계는 물리 포팅만큼 학술적 재현성에 중요하다.

추가로 이 논문은 다음 수준의 주장에만 안전하게 사용한다.

- `자동미분·미분가능 구현` 축에서 KDM6AD의 학술적 위치를 설명하는 근거.
- KDM6AD가 다루는 discrete microphysics operator의 물리적 또는 방법론적 배경.
- 후속 연구 질문을 만드는 계보적 연결.

## 이 논문만으로는 정당화하기 어려운 주장

- FTorch는 물리 microphysics 논문이 아니다.
- 라이브러리 기능을 KDM6AD ABI와 동일시하면 안 된다.

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

| 축 | Atkinson 2025에서 확인할 내용 | KDM6AD에서 남는 의미 |
| --- | --- | --- |
| AD 방식 | 수동 TL/adjoint, source transformation, operator overloading, PyTorch/libtorch, JAX-native 구현을 구분한다. | KDM6AD는 libtorch/C++ AD surface와 Fortran ABI를 결합한 legacy-physics block AD로 위치한다. |
| discrete derivative | AD가 주는 것은 실제 코드 경로의 derivative다. | branch, limiter, dtype 변환, graph break가 derivative semantics를 결정한다. |
| 검증 | finite difference, tangent-adjoint consistency, physical sanity, forward parity가 각각 다른 질문에 답한다. | KDM6AD는 raw-bit forward parity와 AD correctness를 분리해서 제시해야 한다. |
| 확장 | parameter inference, equation discovery, hybrid AI, model-wide differentiability로 이어진다. | KDM6AD는 end-to-end model AD가 아니라 microphysics block derivative라는 범위를 지켜야 한다. |

이 매트릭스의 목적은 Atkinson 2025을/를 단순히 “관련 논문”으로 묶지 않고, KDM6AD의 물리 계보에서 어떤 추상화 수준에 놓이는지 고정하는 것이다. 같은 bulk microphysics 문헌이라도 하나는 직접 조상, 하나는 대안 closure, 하나는 구현 방법론, 하나는 관측연산자 계보일 수 있다. 이 구분이 없으면 KDM6AD 설명은 문헌 목록은 길지만 과학적 주장은 흐린 상태가 된다.

## KDM6AD 연산자 대응

AD 문헌에서 KDM6AD는 `F_micro`를 미분가능하게 노출하는 구현 연구다. 핵심은 AD tool 자체가 아니라, 기존 KDM6 forward semantics를 보존하면서 `JVP(F_micro)`와 `VJP(F_micro)`를 host/ABI 경계 밖으로 안전하게 제공하는 것이다.

Atkinson 2025을/를 KDM6AD 코드와 연결할 때는 다음 대응을 확인한다.

- State 대응: 논문에서 의미 있는 prognostic 또는 diagnostic 변수가 KDM6AD의 packed state, host state, diagnostic output 중 어디에 들어가는가.
- Closure 대응: PSD, density, fall-speed, activation, saturation, cloud fraction, category conversion 같은 closure가 fixed constant인지, diagnostic relation인지, differentiable input인지 구분한다.
- Process 대응: 논문이 강조하는 과정이 KDM6AD의 source term, adjustment, sedimentation, post-step coupling 중 어디에 해당하는가.
- Gradient 대응: JVP로 볼 perturbation direction과 VJP로 되돌릴 adjoint seed를 명확히 정한다.
- Evidence 대응: 이 논문으로 뒷받침할 수 있는 것은 물리 계보인지, 구현 방법론인지, DA 응용 가능성인지 분리한다.

## 미분가능 미세물리 관점의 수학적 독해

AD 수학은 `J v`와 `J^T w`의 계산이다. 여기서 J는 연속 모델의 이상화 Jacobian이 아니라 KDM6AD 코드가 실제로 실행한 discrete operator의 Jacobian이다. 따라서 graph-breaking scalar extraction, detach/no_grad, dtype downcast, masked branch는 모두 학술적 claim에 영향을 준다.

KDM6AD의 수학적 설명에서는 다음 표기 규칙을 적용하는 것이 안전하다.

```text
F_micro = L_pos ∘ Pi_sat ∘ S_sed ∘ S_ice ∘ S_warm ∘ S_cond
J_micro = partial F_micro / partial y
JVP(v)  = J_micro v
VJP(w)  = J_micro^T w
```

이 분해는 실제 코드의 정확한 call graph가 아니라 학술적 독해를 위한 operator decomposition이다. 중요한 점은 KDM6AD가 미분하는 대상이 “구름물리 일반”이 아니라 특정 closure와 branch를 가진 discrete KDM6 계열 연산자라는 사실이다. 따라서 Atkinson 2025의 가치는 KDM6AD의 모든 주장을 보증하는 데 있지 않고, 이 discrete operator가 어떤 계보적 선택 위에 서 있는지 밝히는 데 있다.

## 적대적 검토 포인트

- “AD를 썼다”는 사실만으로 gradient가 과학적으로 의미 있다고 주장하면 안 된다.
- forward parity 없이 AD 결과를 제시하면 원래 물리와 다른 operator의 derivative일 수 있다.
- JAX-native model과 legacy Fortran bridge model의 재현성/성능/범위 차이를 지워서는 안 된다.
- parameter inference를 말하려면 해당 parameter가 differentiable input으로 노출되어야 한다.

이 적대적 검토는 논문의 가치를 낮추려는 것이 아니다. 오히려 학술적 가치를 보존하려면 어떤 주장까지 안전하고 어디서부터 과장인지 분리해야 한다. KDM6AD 위키에서는 이 분리를 페이지마다 남겨, 나중에 신규 논문을 작성하거나 발표자료를 만들 때 문헌의 계보적 의미와 코드의 실제 성취를 혼동하지 않도록 한다.

## 연결된 논문 페이지

- [[paper-K6KQNP7S|Arnold 2024]] - Efficient and stable coupling of the SuperdropNet deep-learning-based cloud micro…
- [[paper-E6KDCS3V|Baumgartner 2019]] - Algorithmic differentiation for cloud schemes (IFS Cy43r3) using CoDiPack (v1.8.1)
- [[paper-H6I7RBDT|Davenport 2026]] - JCM v1.0: A Differentiable, Intermediate-Complexity Atmospheric Model
- [[paper-CNEVCLQJ|Pierzyna 2026]] - JAX-SCM v1.0: a modern atmospheric single-column model for boundary layer research

## 연결된 개념 페이지

- [[Differentiable Bulk Microphysics Research Gap]], [[KDM6AD Automatic Differentiation ABI]], [[KDM6AD Differentiability Audit]], [[KDM6AD Literature Claim Map]]
- [[KDM6]]
- [[KDM6AD]]

## 읽기 우선순위

1. 먼저 이 페이지의 “계보적 위치”와 “수학적·물리적 구조”를 읽어 KDM6AD와 연결되는 축을 잡는다.
2. 그 다음 연결된 논문 페이지를 따라 선행/후속 문헌을 확인한다.
3. 마지막으로 [[KDM6AD Literature Claim Map]]에서 이 논문으로 정당화 가능한 주장과 불가능한 주장을 대조한다.
