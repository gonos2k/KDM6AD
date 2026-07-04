---
title: Operational-Raw vs DA-Clamped Dual Path
type: concept
date_modified: 2026-07-04
provenance:
  sources:
    - docs/KDM6AD_differentiable_mathematics.md §1.1, §8 (2026-07-04)
    - fortran-pytorch-port lessons-learned §53n/§53t/§53u/§53x/§60
    - libtorch/src/{warm,cold,coordinator,melt_freeze}.cpp (dtype 분기 사이트)
---
# Operational-Raw vs DA-Clamped Dual Path

[[KDM6AD]] 포트를 지탱하는 핵심 수치 기법. **하나의 연산자 코드가 dtype에 따라 두 다른 수학적 대상**이
되게 하여, 작동(f32) 경로의 Fortran 비트정합과 자료동화(f64) 경로의 유한 수반을 동시에 얻는다.
보고서 §8 기준 포트 전반에서 ~25회 사용.

## 왜 필요한가
Fortran `mp37`은 원시(raw) 나눗셈·제곱근을 쓴다(예: `coeres`의 `sqrt(rslope*rslopeb)`, F:1924). 여기에
무조건 `clamp`를 넣으면:
- **작동 경로**: 미소값에서 결과가 팽창해 **f32 비트정합이 깨진다**(§53u: `coeres` ~6자리 팽창).
- **DA 경로**: 반대로 clamp가 없으면 $d/dx\,\sqrt x=1/(2\sqrt x)\to\infty$ 등 **수반이 발산**한다.

두 요구가 충돌한다. 해법은 **dtype 조건부 분기**다.

## 관용구
```cpp
auto arg = (qr.scalar_type() == torch::kFloat32)
    ? raw_product                                   // 작동: Fortran raw (비트정합)
    : torch::clamp(raw_product, /*min=*/QCRMIN);    // DA: 유한 수반
auto coeres = ... torch::sqrt(arg) ...;
```
- 분기는 **`scalar_type()` 구조 검사**이지 데이터 의존 `.item()`이 아니므로 **autograd 그래프를 끊지 않는다**.
- f32 경로는 `NoGradGuard` 아래라 raw 발산(±Inf/NaN)이 하류 `fmaxnm` 등으로 원본과 동일하게 붕괴한다.
- f64 경로만 clamp/where-마스크로 유한 수반을 보장한다.

대표 사이트: `warm.cpp:293`(coeres sqrt), `coordinator.cpp:1991/2022`(rhox 나눗셈),
`melt_freeze.cpp:137`(우박밀도), `cloud_dsd.cpp:138`(cbrt 상수).

## 원리: 해석적 유한 ≠ autograd 유한
$t\sqrt t=t^{3/2}$는 $t=0$에서 도함수가 유한하지만, autograd는 곱셈규칙 $\sqrt t+t\cdot\frac1{2\sqrt t}$를
적용해 $0\cdot\infty=$NaN을 만든다. 그래서 `clamp(t,1K)`로 sqrt 노드 기울기를 유한화한다. 이것이 이중경로가
DA에서 clamp를 유지하는 근본 이유다.

> [!note] 프레이밍 통합
> [[KDM6AD Differentiability Audit]]가 min/max 클램프를 "균일하게 AD-safe한 piecewise-smooth"로 서술한
> 것은 이 이중경로로 정정된다 — **클램프는 균일하지 않고 dtype 조건부**이며, f32 작동 경로에서는 오히려
> 제거된다.

관련: [[KDM6AD Forward Parity]], [[KDM6AD Differentiability Audit]], [[KDM6AD Automatic Differentiation ABI]],
[[kdm6ad-differentiable-mathematics-2026-07-04]]

> 향후 [[.item() NoGradGuard 규칙]] 등 actionable 트랩을 Heuristic으로 분리할 여지 있음(현재 heuristics 폴더 비어 있음).
