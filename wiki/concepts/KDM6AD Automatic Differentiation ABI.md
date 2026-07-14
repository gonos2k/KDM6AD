---
title: KDM6AD Automatic Differentiation ABI
type: concept
date_modified: 2026-07-14
---
# KDM6AD Automatic Differentiation ABI

## Why This Matters

The AD surface defines how external DA or sensitivity workflows can use [[KDM6AD]] without confusing the operational WRF runtime path with graph-building differentiation calls.

## Current Status

- Operational mp137 calls `kdm6_step` with `value_only=1`, so it does not retain a graph.
- AD calls use packed fp64 state and forcing buffers through `kdm6_step_ad_c`.
- VJP and JVP are exposed through handles via `kdm6_handle_vjp_c` and `kdm6_handle_jvp_c`.
- The packed state field order is `th,qv,qc,qr,qi,qs,qg,nccn,nc,ni,nr,bg`.
- The 2026-06-10 presentation described C-ABI VJP/JVP as not yet implemented. That is historical only. Current June 25 code and targeted tests show the fp64 C/Fortran handle path exists.

## Rationale

Separating operational forward from AD handle calls keeps WRF execution deterministic and simpler while still providing differentiability for DA workflows. It also lets the project keep the operational ABI at f32 for mp37 parity while using fp64 packed buffers for DA-oriented derivatives.

## Boundaries

- `diag_rhog` is forward-only and excluded from the packed AD ABI.
- Diagnostics used for WRF output parity may not automatically have derivative semantics.
- The WRF mp137 operational runtime remains value-only even though the separate AD ABI exists.
- A complete DA system still needs dynamics, observation operators, covariance models, checkpointing, and minimization outside this microphysics ABI.

## ABI hardening (2026-07-14)

- `kdm6_step_ad_c`, `kdm6_handle_vjp_c`, and `kdm6_handle_jvp_c` are 3 of the **exactly 9** exported symbols after the [[KDM6AD C ABI Hardening]] (`abi-v2-hardened`, export surface 1342 → 9).
- A stable additive **ABI v2** (`kdm6_step_v2_c`, options struct framed by `struct_size`/`abi_version`) now carries inputs so the signature never changes again; v1 stays byte-frozen and v1↔v2 are bitwise-equivalent.
- The AD (fp64) buffers stay `double` by design; only the operational state/forcing ABI went native f32 for mp37 parity — unchanged by the hardening.

## Update (2026-07-04): VJP/JVP/HVP 메커니즘 정식화

`docs/KDM6AD_differentiable_mathematics.md`(→ [[kdm6ad-differentiable-mathematics-2026-07-04]])가 ABI의
미분 메커니즘을 코드 근거로 확정:

- **VJP(수반)**: 스칼라 $s=\langle F(x),u\rangle$(state_dot로 seed $u$ 주입)를 입력 리프에 대해 역전파 →
  $\nabla_x s=J^\top u$. `torch::autograd::grad`, `retain_graph=true`로 한 핸들에 여러 관측 수반 반복 적용
  (`runtime.cpp:611`, `kdm6_handle_vjp_c`).
- **JVP(순방향)**: 커스텀 autograd Function에 forward-mode 규칙이 없어 `torch.func` 불가 → **Pearlmutter
  이중-VJP**: 더미 $u=0$으로 $w=J^\top u$(u에 선형), $Jv=\nabla_u\langle w,v\rangle$. 역방향 2패스
  (`runtime.cpp:639`, `kdm6_handle_jvp_c`).
- **HVP**: 전용 함수 없음. `create_graph=true`의 grad-of-grad로 스칼라 손실의 헤시안-벡터 곱 제공
  (`GraphOptions.create_graph`). 커스텀 Function backward가 이중-미분 가능해야 성립(테스트로 실증).
- **커스텀 libm autograd Function 5종**(exp/log/pow×2/gamma): f32 forward는 gfortran 비트정합(libm),
  backward는 해석적 torch-native. `use_custom_autograd` 3중 게이트(GradMode·!InferenceMode·requires_grad).
- **핸들 수명**: `kdm6_handle_close_c`가 그래프 해제 후 wrapper까지 delete(재사용=UB); value-only 스텝은
  null 핸들 → VJP 시 `KDM6_ERR_NULL_POINTER`.

정확성: 수반 항등식 $\langle Jv,u\rangle=\langle v,J^\top u\rangle$ rel<$10^{-12}$(양변 역방향, FD 무관).
**현재 리프는 12개 상태장뿐** — 물리 파라미터는 `make_parameters(0)`로 상수(비학습).

## Evidence

- [[kdm6ad-differentiable-mathematics-2026-07-04]]
- [[kdm6-vs-kdm6ad-code-comparison-2026-06-25]]
- [[kdm6ad-20260610-presentation-adversarial-review]]
