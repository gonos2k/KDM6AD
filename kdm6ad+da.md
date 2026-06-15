<!-- ════════════════════════════════════════════════════════════════════════
 SISTER-SESSION COPY — origin: /Users/yhlee/AD-RTTOV/kdm6ad+da.md (자매 세션)
 KDM6AD 저장소 내 교차참조(model-side-rttov-observation-operator.md §4·§8.4·§9)
 해결용 사본. AD-RTTOV/KDM6AD는 자매 세션이므로 필요분은 자유롭게 복사·재동기한다
 (정책 2026-06-13). 두 세션이 같은 DA 설계를 공유하며 코드 디렉토리만 분리 관리.
 Copy taken: 2026-06-13 (origin mtime 2026-06-11).
═════════════════════════════════════════════════════════════════════════ -->

# KDM6AD + 위성자료동화(DA) 설계

## 0. 목적

이 문서는 KDM6AD를 단순한 forward cloud microphysics kernel이 아니라, GK2A AMI 위성 영상과 RTTOV all-sky/cloudy 모의 영상을 이용한 구간 위성자료동화의 미분 가능한 미세물리 연산자로 사용하는 설계를 정리한다.

핵심 목표는 다음이다.

1. KDM6AD 수행 구간에서 구름 위상, hydrometeor 분포, 상전이 과정, 입자 수 농도, cloud-top 구조를 능동적으로 동화한다.
2. GK2A 채널별 관측 영상과 RTTOV 모의 영상 사이의 loss를 정의한다.
3. loss의 adjoint를 RTTOV/K-matrix 또는 cloudy operator VJP를 통해 KDM6AD state와 microphysics controls로 역전파한다.
4. KDM6AD 내부의 PyTorch/libtorch 동적 연산그래프를 명시적으로 제어한다.
5. VJP, JVP, checkpoint/recompute 구조를 갖춘 자료동화용 KDM6AD operator를 설계한다.

중요 전제:

- KDM6AD는 cloud microphysics이므로 맑은 날에는 사실상 작동하지 않거나 no-op에 가깝다.
- 따라서 KDM6AD 기반 DA는 clear-sky T/Q 동화가 아니라 cloud-active / hydrometeor-active / phase-aware all-sky DA로 설계해야 한다.
- clear-sky T/Q 동화는 별도 dynamical/thermodynamic DA 문제이고, KDM6AD 전용 loss/control은 cloud-active gate 뒤에서만 활성화한다.
- DA adjoint forward는 운영 mp137 forward와 분리한다. 운영 forward는 Fortran RWORDSIZE=4 및 C ABI `float*`에 맞춘 native float32 경로이고, DA VJP/JVP 검증 및 4D-Var inner-loop는 별도 fp64 adjoint forward를 기본으로 한다.
- JVP는 현 oracle의 custom autograd Function들이 forward-mode rule을 갖기 전까지 `torch.func.jvp`를 주 경로로 쓰지 않는다. 기본 설계는 VJP 우선, JVP는 double-VJP/linearized adjoint product 또는 FD diagnostic으로 검증한다.

---

## 0.1 구현 전 필수 결정 사항

### A. 운영 f32 forward와 DA fp64 adjoint forward 분리

현재 KDM6AD 운영 C ABI는 `const float*` Fortran 배열을 `torch::kFloat32` leaf/view로 받아 libtorch forward를 수행한다. 이는 mp37/Fortran RWORDSIZE=4와 bitwise parity를 맞추기 위한 운영 경로다. 반면 `test_autograd_endtoend`가 강하게 검증한 gradient 경로는 fp64 `kdm6_fn`이다.

따라서 DA 설계는 두 forward를 구분한다.

```text
Operational forward:
  input dtype  = float32
  purpose      = KIM-meso mp137 forward / bitwise-parity / forecast
  graph        = off by default
  API          = kdm6_step_c(... value_only=1 ...)

DA adjoint forward:
  input dtype  = float64 by default
  purpose      = VJP/JVP, 4D-Var inner-loop, gradient verification
  graph        = local graph / checkpoint recompute
  API          = kdm6_step_ad / kdm6_step_ad_c or Python oracle path
```

C ABI의 `double* u_packed`/`double* grad_out_packed`는 단순 컨테이너가 아니라 DA fp64 adjoint forward와 함께 써야 의미가 있다. 운영 f32 graph에서 만든 VJP를 double buffer에 담아도 gradient 자체는 f32 precision/noise를 갖는다. 4D-Var/Gauss-Newton inner-loop의 기본값은 fp64 adjoint forward로 둔다.

필요 코드 결정:

1. 기존 `kdm6_step_c`는 운영 f32 ABI로 보존한다.
2. DA용 C/C++ entry를 별도로 둔다.
   - 예: `kdm6_step_ad_c(... double* state/forcing ... graph_mode ... active_field_mask ...)`
   - 또는 Python oracle/fp64 tensor path를 1차 DA 구현으로 사용한다.
3. 운영 forward와 DA forward의 값 차이는 별도 parity/consistency artifact로 관리한다.

### B. JVP 주 경로 재정의

현 KDM6AD oracle에는 custom autograd Function 계열이 있고, 이들이 forward/backward만 정의하고 forward-mode `jvp` rule을 갖지 않으면 `torch.func.jvp`는 실패하거나 신뢰할 수 없다. 따라서 JVP 설계의 기본 순서는 다음이다.

```text
1순위: VJP 구현 및 검증
2순위: double-VJP / adjoint product 기반 tangent·Hessian-vector product
3순위: FD-JVP diagnostic
4순위: custom Function별 setup_context + jvp rule 추가 후 torch.func.jvp 활성화
```

`torch.func.jvp`는 장기 목표이며, 현재 문서의 구현 기본값은 아니다. `⟨Jv,u⟩ = ⟨v,Jᵀu⟩` 테스트에서 JVP가 FD이면 FD 오차 한계를 명시하고, double-VJP route가 가능하면 그쪽을 정밀 검증 경로로 둔다.

---

## 1. 현재 코드 기준 수행 경로

### 1.1 Python oracle 경로

주요 파일:

- `/Users/yhlee/KDM6AD/kdm6_torch/kdm6/state.py`
- `/Users/yhlee/KDM6AD/kdm6_torch/kdm6/runtime.py`
- `/Users/yhlee/KDM6AD/kdm6_torch/kdm6/coordinator.py`
- `/Users/yhlee/KDM6AD/kdm6_torch/kdm6/warm.py`
- `/Users/yhlee/KDM6AD/kdm6_torch/kdm6/cold.py`
- `/Users/yhlee/KDM6AD/kdm6_torch/kdm6/melt_freeze.py`
- `/Users/yhlee/KDM6AD/kdm6_torch/kdm6/sedimentation.py`
- `/Users/yhlee/KDM6AD/kdm6_torch/kdm6/satadj.py`

핵심 함수:

```text
kdm6_fn = _kdm6_pure
kdm6_step(...)
```

State fields:

```text
th, qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg
```

Forcing fields:

```text
rho, pii, p, delz
```

내부 tensor layout:

```text
State field shape = (B, K)
B = im * jme
K = kme
```

Fortran-style input layout:

```text
(im, kme, jme)
```

중요 변환:

```text
T = th * pii
th = T / pii
```

### 1.2 C++ libtorch 운영 경로

주요 파일:

- `/Users/yhlee/KDM6AD/kdm6_libtorch/include/kdm6/runtime.h`
- `/Users/yhlee/KDM6AD/kdm6_libtorch/src/runtime.cpp`
- `/Users/yhlee/KDM6AD/kdm6_libtorch/include/kdm6/state.h`
- `/Users/yhlee/KDM6AD/kdm6_libtorch/src/state.cpp`

현재 C++ 구조:

```text
kdm6_fn(state, forcing, params, dt, xland, ncmin_land, ncmin_sea)
  -> state_to_coord
  -> forcing build
  -> xland/sea_mask/ncmin tensor
  -> entry clamp
  -> subcycle loop
       -> sedimentation
       -> reslope/aux
       -> kdm62d_one_step
  -> coord_to_state
  -> FnResult{state_out, rain_increment, snow_increment, graupel_increment}
```

`kdm6_step` 구조:

```text
if value_only:
    torch::NoGradGuard
    kdm6_fn(...)
    handle = nullptr
else:
    kdm6_fn(...)
    handle = Handle(state_in, state_out, forcing, params, dt)
```

`Handle::vjp`/`Handle::jvp`는 **구현 완료**(runtime.cpp:513/541)되어 fp64 경로에서 동작한다 — Pearlmutter JVP + control-subspace mask로 vjp/jvp가 정확한 adjoint pair. `test_c_abi_step_ad_fp64_vjp_finite_and_adjoint`(ctest green)가 finite gradient + adjoint identity ⟨Jv,u⟩==⟨v,Jᵀu⟩를 검증한다. (operational f32 `kdm6_step_c` graph 경로는 f32 backward caveat; parameter-gradient/모델 보정은 G4 future. ※ 과거 "TORCH_CHECK_NOT_IMPLEMENTED stub" 서술은 2026-06-12 구현(commits 662dc85→975fe6c)으로 superseded.)

### 1.3 C ABI / Fortran wrapper 경로

주요 파일:

- `/Users/yhlee/KDM6AD/kdm6_libtorch/bridge/kdm6_c_api.h`
- `/Users/yhlee/KDM6AD/kdm6_libtorch/bridge/kdm6_c_api.cpp`
- `/Users/yhlee/KDM6AD/kdm6_libtorch/bridge/kdm6_iso_c.f90`
- `/Users/yhlee/KDM6AD/KIM-meso_v1.0/phys/module_mp_kdm6ad.F`  ← 편집 대상
- `/Users/yhlee/KDM6AD/KIM-meso_v1.0/phys/module_mp_kdm6ad.F` (.f90 은 cpp 산출물 — 매 compile 마다 .F 에서 재생성되므로 수정은 반드시 .F 에) ← `.F`의 cpp 산출물

주의: KIM-meso wrapper 수정은 `module_mp_kdm6ad.F`에 해야 한다. `module_mp_kdm6ad.f90`은 compile/preprocess 과정에서 `.F`로부터 재생성·덮어쓰기되는 산출물이므로, graph_mode/AD-entry를 `.f90`에 직접 추가하면 다음 빌드에서 소실된다. 반면 `bridge/kdm6_iso_c.f90`은 직접 소스이므로 그대로 편집 대상이다.

C ABI:

```text
kdm6_step_c(..., value_only, ..., handle, ...)
kdm6_handle_vjp_c(handle, u_packed, grad_out_packed)
kdm6_handle_jvp_c(handle, v_packed, tangent_out_packed)
kdm6_handle_close_c(handle)
```

현재 `kdm6_step_c`는 다음 정책을 이미 갖는다.

```text
requires_grad = (value_only == 0)
```

따라서 `value_only=0`이면 Fortran array에서 생성한 State field가 autograd leaf가 된다.

현재 KIM-meso wrapper는 다음처럼 호출한다.

```text
param_grad_flags = 0_c_int
value_only       = 1_c_int
```

즉 운영 forward 경로는 graph를 만들지 않는다. 자료동화 경로는 별도로 `value_only=0` 또는 향후 `graph_mode` API를 사용해야 한다.

---

## 2. DA 관점의 전체 구조

### 2.1 자료동화 window

동화 구간:

```text
t = 0, ..., T
```

모델 trajectory:

```math
x_{t+1} = M_t(x_t, \eta_t, \alpha_t)
```

여기서:

- `x_t`: KDM6AD state
- `M_t`: KDM6AD microphysics step
- `η_t`: weak-constraint state/tendency increment
- `α_t`: process-rate control

관측 operator:

```math
\hat{y}_{t,c,p} = H_{t,c,p}(x_t)
```

- `c`: GK2A AMI channel
- `p`: image pixel
- `H`: RTTOV all-sky/cloudy observation operator 또는 RTTOV K/surrogate 기반 operator

전체 목적함수:

```math
J = J_b + \lambda_{sat} J_{sat} + \lambda_{model} J_{model}
  + \lambda_{phase} J_{phase} + \lambda_{phys} J_{phys}
  + \lambda_{smooth} J_{smooth}
```

KDM6AD 전용 DA에서는 `J_sat`, `J_phase`, `J_phys`가 cloud-active 영역에서만 켜진다.

범위 주석:

- `J_b`와 background/control 공분산 `B`, preconditioning, outer-loop minimizer는 이 문서의 주제가 아니라 외부 DA solver 설계로 deferred한다.
- 이 문서는 KDM6AD operator, cloud/phase loss, RTTOV/KDM6AD adjoint bridge, VJP/JVP/checkpoint 인터페이스를 정의한다.

---

## 3. Cloud-active gate

KDM6AD는 맑은 날 작동하지 않으므로 자료동화 driver는 cloud-active gate를 먼저 평가해야 한다.

### 3.1 모델 cloud activity

```math
q_{hydro} = q_c + q_r + q_i + q_s + q_g
```

조건 예:

```text
model_active = sum(q_hydro) > min_total_hydro
            and fraction(column_sum(q_hydro) > min_column_hydro) > min_cloud_fraction
```

### 3.2 관측 cloud activity

GK2A에서 cloud mask 또는 cloud probability가 있으면:

```text
obs_active = mean(C_obs) > min_cloud_fraction
```

### 3.3 최종 gate

```text
cloud_active = model_active or obs_active
```

정책 (2026-06-11 구현에서 확정 — **VJP-skip 제거**):

```text
cloud_active gate 는 (1) obs-side loss 게이팅(맑은 픽셀에 cloud loss 를
평가하지 않음)과 (2) 진단 집계에만 쓴다. KDM6AD VJP 는 cloud_active 와
무관하게 모든 step 에서 실제로 수행한다.
```

근거 — 3 라운드 적대 검증이 점진적으로 강한 skip 조건을 모두 격파:

1. entry-hydrometeor 휴리스틱 → 과포화 청천이 응결 (hydro=0인데 J≠I).
2. 실측 value-noop → 정확 포화점에서 pcond=0이지만 ∂pcond/∂qv≠0
   (값 고정점 ≠ 항등 Jacobian).
3. value-noop + hydro≡0 + strict 미포화 margin → hydro=0 상태 자체가
   clamp/where kink 경계 위 (예: sediment vt 게이트가 qi=+ε에서 즉시 발화,
   보호 임계 없음) ⇒ 그 점의 AD Jacobian 은 subgradient 이지 항등이 아님.

결론: AD 수준에서 싸게 증명 가능한 J=I skip 조건은 존재하지 않는다.
정확성이 최적화에 우선한다 — clear 영역 비용 절감은 obs-side loss 게이팅
(평가 자체를 생략)으로만 얻는다. 구현: kdm6_torch/kdm6/da_window.py
(`use_cloud_gate`는 진단 전용; clear-sky 윈도 adjoint 가 full-window-graph
gradient 와 kink subgradient 까지 포함해 정확 일치함을 테스트로 고정).

---

## 4. GK2A-RTTOV cloud/phase-aware loss

### 4.1 기본 BT 영상 loss

```math
J_{BT} = \sum_{t,c,p} m_{t,c,p} w_t w_c w_p
\rho_\delta\left(\frac{\hat{BT}_{t,c,p} - BT^{obs}_{t,c,p}}{\sigma_c}\right)
```

권장 penalty:

```text
Huber 또는 Cauchy robust loss
```

단순 MSE는 cloud displacement, cloud-top mismatch, phase mismatch에 취약하므로 초기부터 robust loss를 사용한다.

### 4.2 Cloud mask loss

관측 cloud probability:

```text
C_obs[p] in [0,1]
```

모델 cloud probability:

```text
C_hat[p] = sigmoid((tau_cloud[p] - tau0) / s_tau)
```

또는 RTTOV cloudy-clear BT 차이:

```text
C_hat[p] = sigmoid((|BT_clear - BT_cloudy| - dBT0) / s_BT)
```

loss:

```math
J_{mask} = BCE(C_{hat}, C_{obs})
```

또는 soft Dice:

```math
J_{dice} = 1 - \frac{2\sum C_{hat}C_{obs}}{\sum C_{hat}+\sum C_{obs}+\epsilon}
```

### 4.3 구름 위상 loss

모델 hydrometeor partition:

```math
q_{liq} = q_c + q_r
```

```math
q_{ice} = q_i + q_s + q_g
```

```math
f_{ice} = \frac{q_{ice}}{q_{liq}+q_{ice}+\epsilon}
```

```math
f_{liq} = \frac{q_{liq}}{q_{liq}+q_{ice}+\epsilon}
```

mixed-phase indicator:

```math
f_{mix} = 4 f_{liq} f_{ice}
```

위성은 column 전체보다 cloud top에 민감하므로, soft cloud-top weighting을 둔다.

```math
F^{top}_{ice}(p) = \sum_k w^{top}_{p,k} f_{ice}(p,k)
```

```math
F^{top}_{liq}(p) = \sum_k w^{top}_{p,k} f_{liq}(p,k)
```

관측 phase probability:

```text
P_obs = [P_clear, P_liquid, P_ice, P_mixed]
```

모델 phase probability:

```text
P_hat = [P_clear, P_liquid, P_ice, P_mixed]
```

loss:

```math
J_{phase} = -\sum_p conf_{phase}(p) \sum_k P_{obs,k}(p) \log(P_{hat,k}(p)+\epsilon)
```

### 4.4 Hydrometeor partition loss

```math
J_{partition} = \sum_p m_{phase}(p) \rho(F^{top}_{ice}(p) - P^{obs}_{ice}(p))
```

liquid/mixed도 같은 구조로 둔다.

### 4.5 Cloud-top BT/height loss

IR window channel 중심:

- IR105
- IR112
- IR123
- IR133
- IR087

```math
J_{ctop} = \sum_p C_{obs}(p) \rho\left(\frac{BT^{hat}_{IR}(p) - BT^{obs}_{IR}(p)}{\sigma_{ctop}}\right)
```

cloud-top pressure/height가 추정 가능하면:

```math
J_{ctop,p} = \rho(\log P^{hat}_{ctop} - \log P^{obs}_{ctop})
```

### 4.6 Texture / edge loss

```math
J_{edge} = \sum_c \rho(\nabla BT^{hat}_c - \nabla BT^{obs}_c)
```

phase boundary에도 적용 가능하다.

```math
J_{phase-edge} = \rho(\nabla F^{top}_{ice} - \nabla P^{obs}_{ice})
```

### 4.7 시간적 상전이 loss

자료동화 구간 내 cloud phase evolution을 맞추는 항:

```math
J_{phase-time} = \sum_t \rho\left[(F_{ice}^{hat}(t+1)-F_{ice}^{hat}(t))
 - (P_{ice}^{obs}(t+1)-P_{ice}^{obs}(t))\right]
```

이 항은 구름의 액상→빙상 전환, mixed-phase 유지/소멸, cloud-top phase evolution을 직접 제약한다.

---

## 5. Active 자료동화 control 설계

### 5.1 State increment controls

기본 weak-constraint control:

```text
η_t = {
  η_th, η_qv,
  η_qc, η_qr, η_qi, η_qs, η_qg,
  η_nccn, η_nc, η_ni, η_nr, η_bg
}
```

간단한 post-physics form:

```math
x_{t+1} = M_t(x_t) + \eta_t
```

이 방식은 구현이 가장 쉽고, `grad_η_t`가 observation adjoint와 직접 연결된다.

### 5.2 Process-rate controls

상전이/미세물리 과정을 능동적으로 조정하기 위해 process multiplier를 둔다.

```text
α_freeze
α_melt
α_riming
α_deposition
α_autoconv
α_accretion
α_sedimentation_special
```

주의: `α_sedimentation_special`은 다른 pointwise rate multiplier와 동렬로 취급하지 않는다. sedimentation의 `mstep`은 CFL 기반 정수 substep count이고 oracle 외부/no-grad 결정이므로 `v_t * exp(α)`가 `mstep`을 바꾸면 불연속·미분불가능 경계가 생긴다. sedimentation control은 다음 둘 중 하나로 별도 구현한다.

```text
option A: mstep 고정 후 falk/flux 또는 sedimentation tendency에만 multiplier 적용
option B: sedimentation α는 discrete-control/outer-loop parameter로 분리하고 KDM6AD VJP 대상에서 제외
```

각 process rate `R`에 대해:

```math
R' = R \exp(\alpha)
```

장점:

- rate positivity 보장
- VJP로 `∂J/∂α` 계산 가능
- state clamp로 `∂J/∂q_in = 0`이 되는 dead-gradient 셀에서도, rate가 clamp 이전 활성 과정에 걸려 있으면 `∂J/∂α`가 살아남을 수 있다.

운영 bitwise-lock 보호:

- `α=0`이면 수학적으로 `R'=R`이지만, 운영 mp137 bitwise forward에는 α-control node 자체를 넣지 않는다.
- `process_control_enabled=false`이면 기존 rate kernel을 그대로 호출하고, `true`일 때만 `R * exp(alpha)` 노드를 추가한다.
- 이렇게 해야 α=0 no-op의 inert성을 매번 bitwise rescan으로 증명하지 않아도 된다.

### 5.3 Partition controls

위상 분배를 직접 제어하는 control:

```text
Δ_liquid_to_ice
Δ_cloud_to_precip
Δ_snow_to_graupel
```

예:

```math
q_c' = q_c - \Delta_{liq\to ice}
```

```math
q_i' = q_i + \Delta_{liq\to ice}
```

이 control은 반드시 mass conservation 및 latent heating consistency constraint와 함께 써야 한다.

Partition control은 soft penalty만으로 보존시키지 않는다. 기본은 conserve-by-construction이다.

예: liquid-to-ice conversion control

```math
q_c' = q_c - \Delta
```

```math
q_i' = q_i + \Delta
```

```math
\theta' = \theta + \frac{L_f^{process}}{c_{pm}\,\pi}\Delta
```

여기서 `L_f^{process}`는 분기별 실제 잠열상수여야 한다. 예를 들어 melting/freezing/deposition 계열은 같은 상수 하나로 처리하지 말고, KDM6AD 각 process가 쓰는 `xlf0`, `xls-xl(T)` 등의 분기별 정의와 일치시킨다.

운영 bitwise-lock 보호:

- `partition_control_enabled=false`이면 partition-control 및 latent-heat bookkeeping op를 아예 삽입하지 않는다.
- `Δ=0`이라도 보존 bookkeeping 노드가 추가되면 bitwise forward가 달라질 수 있으므로 운영 경로와 DA 경로를 분리한다.

### 5.4 물리 제약

필수 regularization:

```math
J_{pos} = \sum ReLU(-q)^2
```

자유 state/tendency increment에는 soft penalty를 적용한다.

```math
J_{mass} = \|\Delta(q_v+q_c+q_r+q_i+q_s+q_g) - source/sink\|^2
```

단, partition/process controls는 가능하면 penalty가 아니라 construction으로 보존한다.

```text
free η-increment:
  positivity/mass/energy penalty 필요

partition/process control:
  mass + latent heating conserve-by-construction 우선
  penalty는 residual guardrail로만 사용
```

```math
J_{smooth} = \lambda_h \|\nabla_{xy}\eta\|^2 + \lambda_z \|\partial_z \eta\|^2
```

phase-temperature consistency:

```text
warm cloud에서 ice 과다 금지
very cold cloud에서 liquid-only 과다 금지
mixed-phase 온도 범위는 허용
```

---

## 6. VJP 설계

### 6.1 수학적 정의

One-step KDM6AD:

```math
x_1 = M(x_0)
```

VJP:

```math
M'(x_0)^T u = \frac{\partial \langle M(x_0), u \rangle}{\partial x_0}
```

자료동화에서 `u`는 RTTOV/GK2A image loss에서 넘어온 `∂J/∂x_1`이다.

### 6.2 C++ Handle::vjp 구현 설계

현재 C++에는 이미 `state_dot`과 `State::fields()`가 있으므로 다음 구조로 구현한다. 아래 스케치의 `impl_->graph_options`는 현 Handle에 이미 존재하는 필드가 아니라, §8에서 제안하는 신규 metadata/option 필드를 추가한다는 전제이다.

```cpp
State Handle::vjp(const State& u) const {
    TORCH_CHECK(impl_, "Handle is moved-from");
    TORCH_CHECK(!impl_->closed, "Handle is closed");
    TORCH_CHECK(!impl_->value_only, "Handle is value-only");

    auto scalar = state_dot(impl_->state_out, u);

    auto in_fields_ptr = impl_->state_in.fields();
    std::vector<torch::Tensor> inputs;
    inputs.reserve(in_fields_ptr.size());
    for (auto* p : in_fields_ptr) {
        inputs.push_back(*p);
    }

    std::vector<torch::Tensor> grads = torch::autograd::grad(
        {scalar},
        inputs,
        {},
        impl_->graph_options.retain_graph,
        impl_->graph_options.create_graph,
        true
    );

    State grad_state;
    auto grad_fields = grad_state.fields();
    for (size_t i = 0; i < grad_fields.size(); ++i) {
        if (i < grads.size() && grads[i].defined()) {
            *grad_fields[i] = grads[i];
        } else {
            *grad_fields[i] = torch::zeros_like(inputs[i]);
        }
    }

    return apply_active_mask(grad_state, impl_->graph_options.active_field_mask);
}
```

기본 자료동화 정책:

```text
retain_graph = false
create_graph = false
```

### 6.3 Python Handle.vjp 구현 설계

Python oracle에서는 먼저 다음을 구현해 수학적 검증을 수행한다.

```python
def vjp(self, u: State) -> State:
    self._ensure_derivative_ready()
    scalar = state_dot(self.state_out, u)
    grads = torch.autograd.grad(
        scalar,
        tuple(self.state_in),
        retain_graph=False,
        create_graph=False,
        allow_unused=True,
        materialize_grads=True,
    )
    return State(*grads)
```

보강 필요:

- active_fields mask
- None grad zero 처리
- retain_graph/create_graph option
- close lifecycle

### 6.4 C ABI VJP 설계

`kdm6_handle_vjp_c`(및 `kdm6_handle_jvp_c`, `kdm6_step_ad_c`)는 **구현 완료**되어 fp64 경로에서 동작한다 (`test_c_abi.cpp`의 adjoint-identity 테스트 green, ctest 16/16). 아래 packed layout이 그 ABI 계약이다.

#### packed layout

공식 layout (2026-06-11 구현에서 확정 — Fortran 규약으로 교체):

```text
field-major double vector, 총 12 * im*kme*jme 개
field order = th, qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg
각 field 블록 = FORTRAN (im, kme, jme) COLUMN-MAJOR — 운영 state 배열과
동일 규약. Fortran 측은 REAL(8) :: u(im,kme,jme,12) 로 선언해 state 배열과
똑같이 채우면 된다 (1-based A(i,k,j) 의 블록 내 0-based 오프셋
= (i-1) + im*(k-1) + im*kme*(j-1); n번째 field 블록 시작 = (n-1)*im*kme*jme).
내부 (B,K) 텐서 layout 지식 불요 — bridge 가 staging 을 수행한다.
```

(초안의 (B,K)-C-order layout 은 im=jme=1 에서만 우연히 일치 — 비자명
타일에서 뒤섞임. 비자명 타일 검증: 컬럼 독립성 기반 layout 증명 테스트
`test_c_abi_vjp_packed_layout_nontrivial_tile`.)

#### handle shape metadata

`kdm6_handle_t`에 shape를 저장한다.

```cpp
extern "C" struct kdm6_handle_t {
    std::unique_ptr<kdm6::Handle> impl;
    int im;
    int kme;
    int jme;
};
```

`kdm6_step_c`에서 handle 생성 시:

```cpp
auto* h = new kdm6_handle_t{std::move(result.handle), im, kme, jme};
*handle = h;
```

#### VJP C ABI 구현

```cpp
extern "C" int kdm6_handle_vjp_c(
    kdm6_handle_t* h,
    const double* u_packed,
    double* grad_out_packed
) {
    if (!h || !h->impl) return KDM6_ERR_NULL_POINTER;
    if (!u_packed || !grad_out_packed) return KDM6_ERR_NULL_POINTER;
    if (h->impl->is_closed()) return KDM6_ERR_HANDLE_CLOSED;
    if (h->impl->is_value_only()) return KDM6_ERR_VALUE_ONLY;

    try {
        auto u = unpack_packed_state_double(u_packed, h->im, h->kme, h->jme);
        auto grad = h->impl->vjp(u);
        pack_packed_state_double(grad, grad_out_packed, h->im, h->kme, h->jme);
        return KDM6_OK;
    } catch (const c10::NotImplementedError&) {
        return KDM6_ERR_NOT_IMPLEMENTED;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "kdm6_handle_vjp_c: %s\n", e.what());
        return KDM6_ERR_INTERNAL;
    } catch (...) {
        return KDM6_ERR_INTERNAL;
    }
}
```

---

## 7. JVP 설계

### 7.1 역할

JVP는 다음에 사용한다.

1. tangent-linear 검증
2. VJP와의 inner-product test
3. incremental 4D-Var inner loop
4. Hessian-vector product
5. channel별 hydrometeor observability 분석

### 7.2 JVP 구현 정책: torch.func.jvp는 장기 목표

현 oracle/custom autograd Function 경로에서는 forward-mode `jvp` rule이 없는 op가 존재할 수 있다. 따라서 `torch.func.jvp`를 즉시 주 경로로 두지 않는다.

기본 정책:

```text
default JVP policy:
  VJP first
  double-VJP / adjoint-product route for Hessian-vector products
  FD-JVP diagnostic for smoke and regression
  torch.func.jvp only after all custom Functions have setup_context+jvp rules
```

Python 장기 목표 코드는 다음 형태이지만, 이는 `jvp` rule readiness gate를 통과한 뒤에만 활성화한다.

```python
def jvp(self, v: State) -> State:
    self._ensure_derivative_ready()
    if self.func is None:
        raise RuntimeError("Handle has no func for JVP")

    def f(s: State) -> State:
        return self.func(s, self.forcing, self.params, self.dt)

    _, tangent = torch.func.jvp(f, (self.state_in,), (v,))
    return tangent
```

현재 구현 우선순위는 `jvp_fd`와 inner-product/FD directional derivative 검증이다.

### 7.3 C++ JVP 정책

C++ native JVP는 VJP보다 후순위이다.

권장 순서:

1. Python/C++ VJP 구현
2. FD-JVP diagnostic 구현
3. double-VJP / adjoint-product 기반 Hessian-vector product 경로 검증
4. 모든 custom autograd Function의 forward-mode rule 준비 후 Python `torch.func.jvp` 활성화
5. 필요 시 native C++ forward AD 구현

FD-JVP diagnostic:

```text
jvp_fd(v) = [M(x + eps v) - M(x - eps v)] / (2 eps)
```

운영 최적화의 주 경로는 VJP이고, JVP는 검증 및 Hessian-vector product에 사용한다.

---

## 8. 동적 연산그래프 제어 설계

### 8.1 GraphMode

```cpp
enum class GraphMode : int {
    ValueOnly = 0,
    RecordGraph = 1,
    LocalGraphForVjp = 2,
    CheckpointRecompute = 3,
    DiagnosticFullGraph = 4,
};
```

### 8.2 GraphOptions

```cpp
struct GraphOptions {
    GraphMode mode = GraphMode::ValueOnly;
    uint32_t active_field_mask = 0x0FFF;
    bool retain_graph = false;
    bool create_graph = false;
};
```

### 8.3 기본 정책

운영 forward:

```text
GraphMode::ValueOnly
value_only = true
NoGradGuard / InferenceMode allowed
handle = nullptr
```

DA local graph:

```text
GraphMode::LocalGraphForVjp
InferenceMode 밖에서 실행
active fields는 requires_grad leaf로 재생성
custom Function이 InferenceMode tensor를 물고 들어가지 않도록 checkpoint는 detach/clone된 일반 tensor로 저장
```

짧은 테스트:

```text
GraphMode::RecordGraph
value_only = false
handle 보존
```

자료동화 window backward:

```text
GraphMode::LocalGraphForVjp
checkpoint state에서 one-step graph 재생성
VJP 수행
handle.close()
```

긴 window:

```text
forward: ValueOnly + checkpoint 저장
backward: LocalGraphForVjp로 step별 recompute
```

### 8.4 checkpoint/recompute algorithm

Forward dtype 정책:

```text
preferred DA mode:
  x = x0.to(float64)
  for t in window:
      checkpoint[t] = detach_clone(x)   # fp64 checkpoint
      x = kdm6_step_ad(x, forcing[t].to(float64), value_only=true).state_out

forecast-comparison mode:
  운영 f32 forecast trajectory와 별도 저장
  DA fp64 trajectory와 차이는 consistency artifact로 평가
```

즉 4D-Var inner-loop의 기본 선형화 기준점은 fp64 DA trajectory이다. 운영 f32 checkpoint를 fp64로 cast해서 recompute하는 혼합 모드는 허용하더라도 다음처럼 명시적으로 이름 붙인 diagnostic mode로만 둔다.

```text
mixed f32-checkpoint -> fp64-recompute mode:
  checkpoint source = operational f32 value-only forecast
  adjoint point     = cast(checkpoint_f32, float64)
  meaning           = 운영 예보 궤적 자체도, 순수 fp64 궤적도 아닌 casted point에서의 선형화
  use               = transition diagnostic only
```

Forward skeleton, preferred fp64 DA mode:

```text
x = x0.to(float64)
for t in window:
    forcing64 = forcing[t].to(float64)
    checkpoint[t] = detach_clone(x)   # fp64 checkpoint
    x = kdm6_step_ad(x, forcing64, value_only=true).state_out
    if obs_time:
        run RTTOV/GK2A loss on DA fp64 trajectory or mapped RTTOV profile
        store obs_adj[t] = ∂J_obs/∂x_t
```

Backward skeleton, preferred fp64 DA mode:

```text
adj = 0
for t reversed:
    adj += obs_adj[t+1]
    forcing64 = forcing[t].to(float64)
    local = kdm6_step_ad(checkpoint[t], forcing64, value_only=false)
    adj = local.handle.vjp(adj)
    local.handle.close()
    adj += obs_adj[t]
```

일반 `kdm6_step(...)` skeleton은 운영 f32 또는 transitional diagnostic 설명에만 사용하고, 실제 DA inner-loop skeleton은 위처럼 `kdm6_step_ad(...)`와 fp64 checkpoint로 표기한다.

이 방식은 full graph를 window 전체에 보존하지 않으므로 메모리 안정성이 높다.

필수 forward-determinism gate:

```text
For each checkpoint state x_t:
  y_value = kdm6_step(x_t, value_only=true).state_out
  y_graph = kdm6_step(x_t.requires_grad_leaf(), value_only=false).state_out
  assert bitwise_equal_or_strict_allclose(y_value, y_graph)
```

운영 f32 경로에서는 bitwise equality를 요구하고, DA fp64 adjoint forward에서는 fp64 재현성과 FD/VJP consistency를 요구한다. custom autograd Function이 `GradMode && !InferenceMode && requires_grad`에 따라 forward 구현을 분기하더라도 값 자체는 동일해야 한다. 이 테스트 없이는 checkpoint/recompute adjoint가 같은 forward point의 선형화라고 주장할 수 없다.

---

## 9. RTTOV/GK2A와의 adjoint 연결

### 9.1 observation-space adjoint

BT residual:

```math
r = \frac{BT^{hat} - BT^{obs}}{\sigma_c}
```

Huber derivative:

```math
\psi_\delta(r) =
\begin{cases}
r, & |r| \le \delta \\
\delta \operatorname{sign}(r), & |r| > \delta
\end{cases}
```

BT adjoint:

```math
\lambda_{BT} = m w_t w_c w_p \frac{\psi_\delta(r)}{\sigma_c}
```

### 9.2 RTTOV cloudy VJP

주 경로는 RTTOV-K다. RTTOV가 cloud/all-sky 관련 K/Jacobian을 제공하는 경우 이를 native observation-operator VJP로 사용한다.

```math
\lambda_{cloud-input} = H_{cloud}'(x)^T \lambda_{BT}
```

우선순위:

1. RTTOV-K / RTTOV Jacobian native output
2. RTTOV direct + validated cloudy K parser
3. differentiable optical surrogate는 gradient provider 후보
4. finite-difference K는 small-tile 검증/대체 진단용

초기 all-sky/cloudy K가 충분하지 않으면 FD-K를 production 주 경로로 승격하지 말고, surrogate 또는 bridge VJP 검증에만 사용한다.

### 9.3 KDM6AD DSD/phase bridge VJP

RTTOV cloud input adjoint는 바로 KDM6AD state adjoint가 아니다. 중간에 KDM6AD DSD 및 optical-property bridge가 필요하다.

Bridge operator:

```text
KDM6AD hydrometeor state
  qc, qi, qr, qs, qg
  nc, ni, nr, nccn, bg
    -> KDM6AD-consistent DSD diagnostics
       rslope / lamda / effective radius / category density / hydrometeor category mapping
    -> RTTOV cloud/scattering profile variables
    -> RTTOV cloudy BT
```

일관성 제약: bridge가 `(q,n) -> Reff/Dm/lamda`를 임의 재유도하면 안 된다. KDM6AD 내부 DSD 규약과 동일해야 한다.

- 권장 1순위: KDM6AD가 계산한 DSD 진단값(`rslope`, `lamda`, `Reff`, category proxy)을 diagnostic output으로 노출하고 bridge가 그대로 사용한다.
- 대안: bridge가 KDM6AD와 동일한 상수, f32-stepwise pidnc/pidni, μ, lamda evaluation form, lamda bounds를 사용해 재유도한다.
- double-precomputed 상수나 다른 evaluation form으로 Reff를 계산하면 KDM6AD forward의 입자크기 가정과 RTTOV adjoint bridge가 물리적으로 어긋난다.

예:

```text
qc + nc -> liquid effective radius / optical depth
qi + ni -> ice effective radius / optical depth
qr + nr -> rain Dm / rain optical-scattering proxy
qs      -> snow category profile
qg + bg -> graupel density/size proxy
```

따라서 VJP chain은 다음처럼 분리한다.

```text
λ_BT
  -> RTTOV-K VJP
  -> λ_RTTOV_cloud_profile
  -> DSD/optical bridge VJP
  -> λ_qc, λ_qi, λ_qr, λ_qs, λ_qg, λ_nc, λ_ni, λ_nr, λ_nccn, λ_bg
  -> KDM6AD Handle.vjp
```

이 DSD/optical bridge는 별도 operator로 구현하고, JVP/VJP inner-product 및 FD 검증을 독립적으로 통과해야 한다.

### 9.4 KDM6AD state adjoint

cloud input adjoint를 KDM6AD state로 변환한다.

대상:

```text
λ_qc, λ_qi, λ_qr, λ_qs, λ_qg,
λ_nc, λ_ni, λ_nr,
λ_nccn, λ_bg,
λ_th, λ_qv
```

이 adjoint가 `Handle::vjp`의 입력 `u`가 된다.

---

## 10. 검증 설계

### 10.1 Python unit tests

추가할 테스트:

```text
test_handle_vjp_matches_autograd_grad
test_handle_jvp_inner_product
test_jvp_fd_consistency
test_cloud_active_gate_skips_clear_state
test_checkpoint_recompute_one_step_vjp
```

### 10.2 C++ tests

기존:

- `test_autograd_endtoend.cpp`
- `test_c_abi.cpp`

추가:

1. Handle VJP vs backward gradient

```text
kdm6_step(value_only=false)
state_out adjoint u 생성
handle.vjp(u)
scalar = state_dot(state_out, u)
scalar.backward()
leaf.grad와 vjp 결과 비교
```

2. C ABI VJP smoke

```text
kdm6_step_c(... value_only=0 ...)
handle != nullptr
u_packed 생성
kdm6_handle_vjp_c(...)
grad_out finite
close
```

3. packed layout roundtrip

```text
State -> packed -> State
field-major ordering 검증
```

4. inner product test

```math
\langle Jv, u \rangle \approx \langle v, J^T u \rangle
```

C++ native JVP가 없으면 FD-JVP diagnostic 또는 Python double-VJP/FD 경로로 inner-product를 검증한다. 특히 double-VJP/Pearlmutter route는 dummy adjoint `u`를 도입해 `J^T u`를 만든 뒤 `⟨J^T u, v⟩`를 `u`로 미분함으로써 `Jv` 자체를 fp 정확도로 산출할 수 있다. 따라서 inner-product test는 가능하면 FD-JVP가 아니라 double-VJP 산출 `Jv`로 수행하고, FD는 smoke/scale diagnostic으로 제한한다. `torch.func.jvp`는 custom Function forward-mode rule이 준비된 뒤 별도 gate로 활성화한다.

숨은 전제: double-VJP/Pearlmutter route는 `create_graph=true` VJP와 custom autograd Function의 double-backward 가능성을 요구한다. 따라서 `FmaAcc`, `LibmLog`, `RgmmaT`, Python `_RgmmaF32` 등 custom Function에 `once_differentiable` 또는 C++ 등가 제한이 없는지 확인하고, 각 backward가 다시 미분 가능한 연산으로 구성되는지 별도 테스트해야 한다.

추가 테스트:

```text
test_custom_functions_double_backward_ready
test_pearlmutter_jvp_matches_fd_small_tile
test_inner_product_uses_pearlmutter_jvp_when_available
```

---

## 11. 구현 우선순위

### Phase 0: 구현 전 결정/게이트 고정

1. DA adjoint forward는 fp64로 분리한다.
   - 운영 f32 `kdm6_step_c`는 bitwise forecast 경로로 보존한다.
   - DA는 Python oracle 또는 신규 fp64 `kdm6_step_ad(_c)` 경로에서 시작한다.
2. JVP 기본 경로를 재정의한다.
   - `torch.func.jvp`는 custom Function forward-mode rule 준비 전까지 비활성/장기 목표.
   - VJP 우선, FD-JVP diagnostic, double-VJP/Hessian-vector route를 먼저 검증한다.
   - double-VJP/Pearlmutter route는 custom Function double-backward readiness test를 통과한 뒤 정밀 JVP 경로로 사용한다.
3. forward-determinism gate를 테스트로 고정한다.
   - value_only forward와 graph forward가 같은 point를 재현하는지 검증한다.
4. RTTOV-K를 cloudy VJP 주 경로로 두고, FD-K는 small-tile 검증/대체 진단으로 제한한다.

### Phase 1: Python VJP 검증

1. `runtime.py`의 `Handle.vjp` 구현
2. active field mask 추가
3. VJP vs `loss.backward()` 비교
4. finite-difference directional derivative test
5. FD-JVP diagnostic 및 inner-product test
6. DSD/optical bridge VJP 독립 검증

### Phase 2: C++ VJP

1. `runtime.h`에 `GraphOptions`, `FieldMask`, shape metadata 설계 추가
2. `runtime.cpp`의 `Handle::vjp` 구현
3. `Handle::jvp`는 deferred 또는 FD-JVP diagnostic
4. `test_autograd_endtoend.cpp`에 VJP 검증 추가
5. value_only graph forward-determinism test 추가

### Phase 3: C ABI VJP

1. `kdm6_handle_t`에 `im/kme/jme` 저장
2. packed double State unpack/pack helper 추가
3. `kdm6_handle_vjp_c` 구현
4. `test_c_abi.cpp`에 value_only=0 + VJP 테스트 추가
5. f32 운영 VJP와 fp64 DA VJP의 precision/status를 artifact에 명시

### Phase 4: 자료동화 window driver

1. forward: value_only + checkpoint 저장
2. observation time: RTTOV/GK2A loss와 state adjoint 계산
3. backward: local graph recompute + VJP
4. handle.close 메모리 안정성 검증
5. InferenceMode 밖 local graph 생성 보장

### Phase 5: active controls

1. post-tendency `η_t` control
2. pre-state increment control
3. process-rate `α` controls, runtime flag로 운영 경로에서 완전 제거 가능하게 구현
4. partition controls, mass/latent heat conserve-by-construction

---

## 12. 최종 설계 요약

현재 KDM6AD 코드는 자료동화용 VJP/JVP/동적연산그래프 제어를 추가하기 좋은 구조를 이미 갖고 있다.

이미 존재하는 것:

- `kdm6_fn`은 실제 differentiable forward이다.
- `kdm6_step(value_only=false)`는 handle을 만든다.
- `from_fortran_arrays(... requires_grad=true)`는 autograd leaf state를 만든다.
- C++ `State::fields()`, `state_dot()`, `zeros_like_state()`가 이미 있다.
- C ABI와 Fortran ISO_C에 VJP/JVP 함수 signature가 이미 있다.
- `test_autograd_endtoend.cpp`가 graph integrity와 finite-difference 검증 기반을 제공한다.

부족한 것:

- Python `Handle.vjp` 구현, `Handle.jvp`는 double-VJP/FD diagnostic 우선 및 `torch.func.jvp`는 forward-mode rule 준비 후 활성화
- C++ `Handle::vjp` 구현
- C++/C ABI packed VJP 구현
- handle shape metadata
- graph mode / active field mask
- checkpoint/recompute window driver
- active microphysics controls

최소 구현 핵심:

```text
1. Handle::vjp 구현
   scalar = state_dot(state_out, u)
   grad = torch::autograd::grad(scalar, state_in.fields())

2. C ABI VJP 구현
   u_packed -> State
   handle->vjp(u)
   grad State -> grad_out_packed

3. shape metadata 저장
   kdm6_handle_t { impl, im, kme, jme }

4. Python도 동일한 방식으로 Handle.vjp 구현
   JVP는 double-VJP/Pearlmutter 또는 FD diagnostic으로 먼저 검증
   torch.func.jvp는 custom Function jvp rule 준비 후 활성화

5. test_autograd_endtoend/test_c_abi에 VJP 검증 추가

6. 자료동화 window에서는 full graph 저장 대신 checkpoint/recompute VJP 사용
```

최종 운영 구조:

```text
GK2A/RTTOV cloudy image loss
  -> λ_BT
  -> RTTOV-K / native cloudy Jacobian VJP
  -> λ_RTTOV_cloud_profile
  -> KDM6AD-consistent DSD/optical bridge VJP
  -> λ_KDM6AD_state(t)
  -> KDM6AD local graph recompute on fp64 DA checkpoint
  -> Handle.vjp
  -> λ_KDM6AD_state(t-1), grad_controls(t)
  -> optimizer update
```

최종 설계 문장:

KDM6AD 수행 코드는 이미 `value_only=0`에서 autograd leaf state와 `Handle`을 생성하는 구조를 갖고 있으므로, 자료동화용 graph 제어는 기존 운영 forward API를 보존한 채 `Handle::vjp`를 `state_dot(state_out,u)`와 `torch::autograd::grad`로 구현하고, C ABI에서는 field-major packed double adjoint를 State(B,K)로 변환해 VJP 후 다시 packed gradient로 반환하는 방식으로 시작한다. DA inner-loop는 fp64 checkpoint/recompute trajectory를 기본 선형화 기준점으로 삼고, 운영 f32 trajectory와는 별도 consistency artifact로 비교한다. 이후 `GraphMode`, `active_field_mask`, `checkpoint/recompute` driver, KDM6AD-consistent DSD/optical bridge를 추가하여 cloud-active 구간에서만 hydrometeor 중심 VJP를 수행한다. JVP는 우선 double-VJP/Pearlmutter 또는 FD diagnostic으로 검증하고, Python `torch.func.jvp`는 custom autograd Function들의 forward-mode rule이 준비된 뒤 활성화한다.
