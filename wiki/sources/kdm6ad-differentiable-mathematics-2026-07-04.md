---
title: KDM6AD 미분가능 미시물리 수학·공학 보고서 (2026-07-04)
type: source
date_modified: 2026-07-04
provenance:
  sources:
    - docs/KDM6AD_differentiable_mathematics.md (프로젝트 저장소, Codex 적대검토 2회 반영)
    - docs/KDM6AD_differentiable_mathematics.humanized.md (한국어 산문 윤문본, 기술 span 동일)
---
# KDM6AD 미분가능 미시물리 수학·공학 보고서

`docs/KDM6AD_differentiable_mathematics.md`의 요약. [[KDM6AD]] 미분가능 이식본의 수학적 정식화와
자동미분(AD) 공학을 실제 코드(`파일:줄`) 근거로 서술한 783줄 기술 보고서. Codex 적대검토 2회로
표현을 코드와 정합시킴.

## 핵심 takeaway
1. **이중 경로 설계**: 하나의 연산자 코드가 dtype에 따라 두 대상이 됨 — 작동 f32(NoGradGuard, libm으로
   gfortran 비트정합, 조각적 상수 계단) vs DA f64(autograd 그래프, 조각적 매끄러운 사상). 분기는
   `.item()`이 아니라 `scalar_type()` 구조 검사라 그래프 무절단. → [[Operational-Raw vs DA-Clamped Dual Path]]
2. **합성 사상 정식화**: 한 스텝 $F=\prod G$, $G=K\circ R\circ S$(침강·재기울기·미시물리 1패스), $K$는
   19개 부연산자 좌→우 합성. 야코비안은 역순 곱. → [[KDM6AD Mathematical Microphysics Operators]]
3. **점프 vs 꺾임 판별식**: $\text{where}(cond,A,B)$는 경계에서 $A=B$면 연속(꺾임), $A\neq B$면 불연속(점프).
   균질동결·재분류·cleanup·완전증발은 유한량을 옮기는 **점프**(kink 아님). autograd는 활성 분기의 한쪽
   편도함수만 반환하고 점프의 subgradient는 만들지 않음. → [[KDM6AD Differentiability Audit]] 정정 근거
4. **AD 3종 메커니즘**: VJP = $\nabla_x\langle F(x),u\rangle=J^\top u$(state_dot seed); JVP = Pearlmutter
   이중-VJP(커스텀 Function에 forward 규칙 없어 역방향 2패스); HVP = create_graph 이중-역전파.
   수반 항등식 $\langle Jv,u\rangle=\langle v,J^\top u\rangle$가 rel<$10^{-12}$로 검증. → [[KDM6AD Automatic Differentiation ABI]]
5. **AD-safe 유한수반**: "해석적 유한 ≠ autograd 유한"($t\sqrt t$의 $0\cdot\infty$). 5개 libm 커스텀 autograd
   Function(exp/log/pow×2/gamma) + clamp·where-마스크 유한경계 idiom.

## 검증(보고서 §9)
수반 항등식·마스크 수반 rel<$10^{-12}$, JVP/VJP 중심차분 게이트 rel<$10^{-5}/10^{-6}$, 이중-역전파
준비성, 합성 클라우드(RTTOV) 경로 — 모두 fp64 DA 경로 대상(f32 작동 비트정합과는 별개 검증).

관련: [[KDM6AD Forward Parity]], [[KDM6AD]], [[WRF KIM-meso Host]]
