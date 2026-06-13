# 모델면 RTTOV 관측연산자 설계 (Model-side RTTOV Observation Operator)

> **위치 / 관계**: 이 문서는 KDM6AD 저장소에 둔다(설계가 구동하는 코드 —
> `kdm6_torch/kdm6/rttov_bridge.py`, `da_window.py`, `runtime.py`(Handle.vjp/jvp),
> `coordinator.py` — 가 모두 여기 있기 때문). adjoint **수학** 체인(BT residual,
> RTTOV cloudy VJP, DSD bridge VJP, state adjoint)과 loss, checkpoint/recompute
> window는 **상위 설계 문서 [`kdm6ad+da.md`](./kdm6ad+da.md) §4·§8.4·§9에 이미 정의**되어
> 있다. 본 문서는 그것을 **재서술하지 않고 참조**하며, 그 문서에 비어 있던 한 가지
> 질문 — *"RTTOV를 모델 적분의 어디서·언제 실행하고, 그 출력을 obs adjoint로
> 어떻게 되돌리는가"* — 즉 **모델면 실행 아키텍처**만 채운다.
> `kdm6ad+da.md`의 upstream 원본은 `/Users/yhlee/AD-RTTOV/kdm6ad+da.md`이며,
> 본 저장소의 사본은 교차참조 해결용 frozen snapshot이다(단방향, upstream이 canonical).

---

## 0. 목적

**최종 목적: GK2A AMI 16채널 관측 BT를 같은 16채널 RTTOV 모의 BT와 비교하는 전천(all-sky)
위성 자료동화 구축.** 즉 구름 영향 복사휘도(cloud-affected radiance)를 *오염이 아니라 신호*로
사용해, 모델 미세물리 상태가 관측 BT를 설명하도록 KDM6AD를 미분 가능 관측연산자로 동화한다.

이를 위해 모델 상태 `x(t)`를 관측공간(16채널 BT)으로 사상하는 **관측연산자 H**가 필요하고,
이 문서는 그 H를 **KDM6AD kernel 내부가 아니라 모델면(model-side) observation operator**로
두는 설계를 정의한다. 구체적으로:

1. RTTOV direct/K를 **관측 valid time과 일치하는 완료된 모델 상태** `x(t_obs)`에서 수행한다.
2. RTTOV-K가 돌려주는 profile adjoint `λ_profile`를 **KDM6AD-consistent `rttov_bridge` VJP**를 통해
   KDM6AD state adjoint `λ_state`로 변환한다.
3. 그 `λ_state`를 `kdm6ad+da.md §8.4`의 window backward가 호출하는 `obs_adj[t]`로 주입한다.

이 설계의 가치는 adjoint 수식이 아니라 **시간 정합 + 실행 경계(module boundary)**의
명확화에 있다.

---

## 1. 핵심 원칙 (Core Claims)

다음 여섯 주장이 본 설계의 뼈대이며, 이후 모든 절은 이를 구체화한다.

1. **RTTOV는 KDM6AD substep 내부가 아니라 모델면 observation operator에서 수행한다.**
   KDM6AD kernel(`kdm6_step_ad`)은 순수 미세물리 1-step이고, RTTOV는 그 step들이 완료되어
   만들어진 *상태*에 작용한다. RTTOV를 substep 안에 넣으면 sub-cycle마다 위성 RT를 돌려야 하고,
   미세물리 autograd 그래프와 RTTOV의 Fortran adjoint가 뒤섞여 경계가 사라진다.

2. **RTTOV 수행 시점은 관측 valid time과 일치하는 completed model state `x(t_obs)`이다.**
   `kdm6ad+da.md §8.4` forward skeleton의 다음 줄이 바로 이 지점이다:
   ```text
   if obs_time:
       run RTTOV/GK2A loss on DA fp64 trajectory or mapped RTTOV profile
       store obs_adj[t] = ∂J_obs/∂x_t
   ```
   본 문서는 이 한 줄의 내부를 정의한다.

3. **초기 구현은 시간보간(FGAT/4D-interpolation) 없이 model step end time과 obs valid time을 맞춘다.**
   즉 `t_obs`는 반드시 어떤 checkpoint된 step 경계 `t_k = window_start + k·model_dt`와 일치해야 한다.
   불일치 관측은 (보간 대신) **거부**한다. 시간보간은 v2 이후 과제다.

4. **RTTOV direct와 RTTOV-K는 동일 profile/options/channel/geometry를 사용해야 한다.**
   K가 direct의 진짜 선형화이려면 같은 profile 객체, 같은 chanprof, 같은 coefficient/option 집합,
   같은 geometry에서 호출되어야 한다. 이를 **config hash**로 잠근다(§7, M5 `test_direct_k_config_match`).

5. **RTTOV-K profile adjoint는 KDM6AD-consistent `rttov_bridge` VJP를 통해 KDM6AD state adjoint가 된다.**
   `λ_BT → (RTTOV-K) → λ_profile → (rttov_bridge VJP) → λ_state → Handle.vjp`.
   이 체인의 수학은 `kdm6ad+da.md §9`, bridge 구현은 `kdm6_torch/kdm6/rttov_bridge.py`에 있다.

6. **목표는 all-sky 16채널이므로 cloud/scattering 경로와 hydrometeor bridge가 부차가 아니라 핵심이다.**
   GK2A AMI 16채널(VIS/NIR 6 + IR 10)에 대한 RTTOV 전천 cloudy/scattering RT를 쓴다.
   `RttovCloudProfile`(clw/ciw/rain/snow/graupel + reff_*; §4.4)이 정확히 all-sky가 요구하는
   입력이다 — 즉 cloud-active gate(`kdm6ad+da.md §3`)·cloud/phase loss(`§4.2/§4.3`)·bridge
   cloudy 경로(§6)·RTTOV cloudy-K(M5 `test_rttov_k_cloud_fd`)가 1순위 검증 대상. **단계화**:
   IR 10채널(thermal, AD-RTTOV ami/501 ch8–16 검증 기반)을 all-sky 1차 타깃으로, VIS/NIR 6채널
   (solar 반사 — solar RT + 주간 한정 + solar geometry 의존)은 후속.

---

## 2. 시간 정합 설계 (Time Synchronization)

### 2.1 정합 정책

```text
관측 valid time  t_obs
모델 step 경계    t_k = window_start_time + k · model_dt   (k = 0 … N)
정합 조건        ∃ k : |t_obs − t_k| ≤ obs_time_tolerance
거부 조건        위 k 가 없으면 그 관측은 이 window에서 사용하지 않음(보간 금지)
```

`obs_time_tolerance`는 부동소수 시각 비교용 작은 허용오차(예: 0.5 s)이지 보간 창이 아니다.
정합된 관측은 그 `k`(=`model_step_index`)에 바인딩되고, RTTOV는 **checkpoint된 상태
`checkpoint[k]`** 위에서 수행된다.

### 2.2 checkpoint 경계 제약 (핵심)

`kdm6ad+da.md §8.4`의 window는 forward에서 각 step end 상태를 `checkpoint[t]`로 detach 저장하고,
backward에서 그 checkpoint로부터 local 1-step 그래프를 재구성해 `Handle.vjp`를 호출한다.
따라서:

> **관측은 checkpoint된 step 경계에만 붙을 수 있다.** `model_dt`가 관측 간격을 정수 분할하지
> 않으면 정합 불가 → scheduler가 hard precondition으로 거부한다 (M1 `test_obs_schedule_rejects_off_step_obs`).

이것은 제약이지 손실이 아니다. obs adjoint는 forward에서 `obs_adj[k] = ∂J_obs/∂x_k`로 저장되고,
backward에서 해당 step 진입 시 누적된다 — window 알고리즘과 정확히 맞물린다.

### 2.3 fp64 trajectory 위에서 수행

RTTOV loss/adjoint는 **DA fp64 trajectory**(`kdm6ad+da.md §0.1.A`, `§8.4` preferred mode)
위에서 평가한다. 운영 f32 forecast 궤적은 별도이며, fp64-vs-f32 차이는 consistency artifact로만
본다. 즉 `checkpoint[k]`는 fp64이고, bridge·RTTOV input 빌드도 fp64 입력을 받는다.

---

## 3. 모델 state 기준점 (Reference State)

| 항목 | 값 |
|---|---|
| 기준 상태 | `x(t_obs) = checkpoint[k]` (완료된 fp64 모델 상태, detached) |
| 미세물리 변수 | `kdm6ad+da.md`의 12 prognostic: th, qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg |
| forcing | rho, pii, p, delz (bridge가 preamble 재실행 시 사용) |
| 정밀도 | fp64 (DA adjoint forward) |
| 미분 기준 | 이 상태에서의 선형화 — backward의 `Handle.vjp` 입력 `u = λ_state` |

RTTOV는 이 상태를 **읽기만** 한다(detached checkpoint). adjoint는 backward에서 local recompute
그래프를 통해 흐른다.

---

## 4. 필요 변수 목록 (Variable & Preparation Tables)

### 4.1 시간/스케줄 변수

| 변수 | 의미 |
|---|---|
| `window_start_time` | 자료동화 window 시작 valid time |
| `window_end_time` | window 종료 valid time |
| `model_dt` | 모델 step 간격(= sub-cycle 누적 후 step end 간격) |
| `obs_valid_times` | 관측별 valid time 목록 |
| `obs_time_tolerance` | step 경계 정합 허용오차(보간 창 아님) |
| `model_step_index` | 정합된 관측이 바인딩되는 step index `k` |

### 4.2 모델 profile 변수 (column → RTTOV profile)

| 변수 | 비고 |
|---|---|
| `p(k)` | 층별 기압 [Pa→hPa 변환] |
| `T(k)` | 온도 = θ·Π (th, pii로부터) |
| `qv(k)` | 수증기 혼합비 → RTTOV Q [**gas_units, qv_convention 고정 필수**] |
| `rho(k)` | 공기밀도 (bridge content 계산용) |
| `pii(k)` | Exner — T 복원에 사용 |
| `delz(k)` | 층 두께 |
| `surface_pressure` | 표면 기압 |
| `skin_temperature` | 표면 skin 온도 |
| `surface_type` | sea/land/sea-ice (RTTOV surftype) |
| `terrain_height` | 표면 고도 |
| `lat/lon` | 위경도 |
| satellite/solar geometry | zenith/azimuth (위성·태양) |

### 4.3 KDM6AD cloud 변수 (bridge 입력)

```text
qc, qr, qi, qs, qg      (mass mixing ratio)
nc, ni, nr              (number concentration)
nccn                    (CCN)
bg                      (graupel volume mixing ratio — rime density proxy)
```

### 4.4 RTTOV cloud/profile 변수 (bridge 출력 = `RttovCloudProfile`)

> `kdm6_torch/kdm6/rttov_bridge.py`의 `RttovCloudProfile`과 **정확히 일치**한다.

| 변수 | 단위 | 산출 |
|---|---|---|
| `clw` | g/m³ | rho·qc·1e3 |
| `ciw` | g/m³ | rho·qi·1e3 |
| `rain` | g/m³ | rho·qr·1e3 |
| `snow` | g/m³ | rho·qs·1e3 |
| `graupel` | g/m³ | rho·qg·1e3 |
| `reff_liq` | µm | effectRad_kdm6 (Cohard-Pinty generalized gamma; naive (μ+3)/2 금지) |
| `reff_ice` | µm | effectRad_kdm6 (rslope_i·Γ(3+μi)/(2Γ(4+μi))) |
| `reff_snow` | µm | 0.5·rslope_s |
| `rain_dm` | µm | avedia_r (λ_nr carrier) |
| `graupel_rime_frac` | — | bg/qg, **qg≤1e-15에서 0 게이트**(inactive graupel, adjoint=0) |

### 4.5 관측 변수

```text
BT_obs / radiance_obs       관측 밝기온도/복사휘도 (16채널)
channel_id                  GK2A AMI 16채널: VIS/NIR 6 (VI004/005/006/008, NR013/016)
                            + IR 10 (SW038, WV063/069/073, IR087/096/105/112/123/133).
                            all-sky 1차 타깃 = IR 10; VIS/NIR 6 = solar 후속.
valid_time                  관측 valid time (→ checkpoint 경계 정합, §2)
quality_mask                관측 품질 마스크
cloud_mask / cloud_probability   구름 마스크/확률 (all-sky: cloud-active gate 신호원)
obs_error sigma             채널별 관측오차 σ_c (loss 정규화)
bias correction             채널별 편향 보정
```

### 4.6 RTTOV 준비사항

```text
coefficient file            rtcoef (예: ami/501)
channel list                사용 채널
gas options                 gas_units(=2 ppmv moist 등), 활성 기체
O3 option                   오존 profile 사용 여부/소스
cloud/scattering options    all-sky/cloudy RT 옵션, RTTOV-SCATT 여부
emissivity/BRDF             표면 방출률/반사 atlas
hydrotable/cloud optical    수상체 광학 테이블
chanprof mapping            (profile, channel) 매핑
direct/K config hash        direct·K 동일성 잠금 해시 (§7)
```

### 4.7 adjoint 변수

```text
λ_BT                관측공간 BT adjoint (kdm6ad+da.md §9.1)
λ_profile           RTTOV profile-level adjoint (RTTOV-K 출력)
λ_KDM6AD_state      미세물리 state adjoint (bridge VJP 출력 = Handle.vjp 입력 u)
λ_controls          active control adjoint (kdm6ad+da.md §5; grad_η / grad_α)
```

---

## 5. 모델 column/profile extractor

**모듈**: `model_profile_builder.py`

```python
extract_model_columns(checkpoint_state, forcing, geometry, surface) -> ModelColumns
build_rttov_profiles(model_columns, rttov_config) -> RttovProfiles
```

- `extract_model_columns`: detached fp64 checkpoint와 forcing에서 RTTOV가 요구하는 column
  변수(p, T=θ·Π, qv, surface, geometry)를 뽑는다. T는 `T = th · pii`로 복원한다.
- `build_rttov_profiles`: column을 RTTOV profile 객체로 사상한다.
  - **단위/규약 게이트**: qv → RTTOV Q 변환은 `qv_convention`과 `gas_units`를 명시하지 않으면
    실패해야 한다(AD-RTTOV heuristic `require-explicit-qv-convention-before-rttov-bridge`).
  - 기압 단조성(아래→위 감소 또는 RTTOV 규약)을 검증한다 (M2 `test_pressure_monotonic`).
  - 외삽 금지: 모델 grid가 RTTOV target pressure를 벗어나면 거부.

---

## 6. KDM6AD cloud/DSD bridge

**모듈**: 기존 `kdm6_torch/kdm6/rttov_bridge.py` (이번 세션 확정, 변경 불필요)

`dsd_diagnostics(state, forcing, xland, ncmin_land, ncmin_sea)` →
`rttov_cloud_profile(...)` → `RttovCloudProfile`.

핵심 일관성 제약 (`kdm6ad+da.md §9.3`):

- bridge는 `(q,n) → rslope/lamda/Reff`를 **임의 재유도하지 않는다.** 스킴 자신의
  `preamble_torch`를 직접 재실행한다(같은 f32-stepwise pidnc/pidni, lamda eval-form, clamp).
- `xland`/`ncmin_land`/`ncmin_sea`는 **forward step과 동일하게** 주어야 한다 — per-cell ncmin이
  cloud-slope inactive gate에 들어가므로, 누락 시 land cell에서 rslopec가 스킴과 갈라진다
  (M3 `test_bridge_xland_ncmin_consistency`).
- effective radius는 스킴 자신의 `effectRad_kdm6`(F:4042) 1:1 포팅 — naive standard-gamma
  (μ+3)/2 금지(cloud 4.51× 과대; adversarial review F2).
- `graupel_rime_frac`은 qg≤1e-15에서 0으로 게이트(inactive graupel adjoint=0; Codex review).
- DA 대상은 fp64 oracle 경로 — fp64 state를 넣는다.

이 bridge는 순수 torch 텐서 연산이므로 VJP/JVP가 `torch.autograd`로 합성된다(custom autograd
Function 없음). 독립 게이트는 `kdm6_torch/tests/test_rttov_bridge.py`.

---

## 7. RTTOV input builder + direct runner

**모듈**: `rttov_input_builder.py`, `rttov_runner.py`

```python
build_rttov_input(rttov_profiles, rttov_cloud_profile, rttov_config) -> RttovInput
run_rttov_direct(rttov_input) -> RttovDirectOutput   # BT_hat, radiance, quality
```

- `RttovInput`은 profile + cloud profile + chanprof + options + geometry + surface를
  하나의 객체로 묶는다.
- **direct/K 동일성**: `run_rttov_direct`와 `run_rttov_k`는 동일 `RttovInput`과 동일
  `rttov_config`를 사용해야 한다. `rttov_config.hash()`(coefficient+channel+gas+cloud option+
  geometry)를 양쪽이 공유하고, mismatch 시 실패 (M5 `test_direct_k_config_match`).
- RTTOV direct/K는 **외부 Fortran**(RTTOV 14.1, AD-RTTOV wrapper)이며 torch autograd가 아니다.
  본 모듈은 그 wrapper를 감싸는 interface contract이고, 실제 함수명/파일명은 후속 구현 때 채운다.

---

## 8. 관측 matching + loss

**모듈**: `obs_loss.py`

```python
compute_obs_loss(BT_hat, obs, masks, sigma) -> (J_obs, lambda_BT)
```

loss와 λ_BT의 **수학은 `kdm6ad+da.md §4(GK2A-RTTOV cloud/phase-aware loss)·§9.1`에 정의**되어
있다(BT residual, Huber ψ_δ, cloud/phase/partition/cloud-top/texture loss, λ_BT = m·w·ψ_δ(r)/σ_c).
본 모듈은 그것을 **구현**하고, 다음을 보장한다:

- 관측·RTTOV 양쪽 quality가 0인 (profile, channel)만 metric/gradient에 포함
  (AD-RTTOV: RTTOV `QUALITY==0`도 mask에 포함해야 함 — open tension).
- bias correction은 residual 정의 시점에 적용.
- λ_BT는 RTTOV-K 입력 seed로 전달.

---

## 9. RTTOV-K / profile adjoint + KDM6AD bridge VJP 연결

**모듈**: `rttov_runner.py`(K), `rttov_obs_operator.py`(연결)

```python
run_rttov_k(rttov_input, lambda_BT) -> lambda_profile      # RTTOV-K, 외부 Fortran
profile_adjoint_to_state_adjoint(lambda_profile, ...) -> lambda_state   # bridge VJP
```

전체 adjoint 체인 (수학 = `kdm6ad+da.md §9.1–9.4`):

```text
λ_BT
  → RTTOV-K VJP            (외부 Fortran 전통 adjoint, §9.2)
  → λ_profile             (RTTOV profile-level adjoint; PROFILES_K = BT sensitivity)
  → DSD/optical bridge VJP (rttov_bridge VJP, torch.autograd, §9.3)
  → λ_qc … λ_bg, λ_th, λ_qv  (§9.4)
  → Handle.vjp(u = λ_state)  (KDM6AD state adjoint, runtime.py)
```

### 9.1 가장 위험한 이음매: RTTOV-K ↔ torch 경계 (Interface Contract)

RTTOV-K는 Fortran 전통 adjoint(손코딩), bridge VJP는 torch autograd다. 이 **이음매에서
`λ_profile`의 변수 레이아웃·단위가 bridge VJP 입력과 정확히 일치**해야 한다. broadcastable
하지만 잘못된 shape는 silent하게 adjoint를 오염시킨다(F1-SHAPE class). 따라서:

```text
계약 (interface contract):
  λ_profile 의 각 필드(clw/ciw/rain/snow/graupel/reff_*/rain_dm/rime_frac)는
  RttovCloudProfile 의 동일 필드와 동일 shape·동일 단위로 정렬되어야 한다.
  profile-level T/Q sensitivity(PROFILES_K)는 BT 기준 미분으로 해석한다
  (AD-RTTOV: rttov-profiles-k-bt-sensitivity-contract).
```

- RTTOV-K의 cloud/scattering K가 충분히 검증되기 전에는 FD-K를 production 주 경로로 승격하지
  않는다(`kdm6ad+da.md §9.2`). FD-K는 bridge VJP 검증·surrogate에만 쓴다.
- `profile_adjoint_to_state_adjoint`는 `λ_profile`을 bridge의 forward 입력 텐서들에 대한
  `torch.autograd.grad` seed로 사용해 `λ_state`를 얻는다(bridge가 순수 torch이므로 자동).

---

## 10. DA window callback 연결

**모듈**: `rttov_obs_operator.py`

```python
build_obs_schedule(window_cfg, obs_valid_times, obs_time_tolerance) -> ObsSchedule
obs_adjoint_callback(t, x_t) -> lambda_state | None      # da_window 의 obs_adjoint
```

`obs_adjoint_callback`은 `kdm6ad+da.md §8.4`/`da_window.py`의 `obs_adjoint(t, x_t)` 시그니처를
구현한다:

```text
def obs_adjoint_callback(t, x_t):
    obs = schedule.get(t)            # t 가 정합된 step이 아니면 None
    if obs is None:
        return None                  # 관측 없는 step → window는 순수 VJP만
    profiles  = build_rttov_profiles(extract_model_columns(x_t, ...), cfg)
    cloud     = rttov_cloud_profile(x_t.state, forcing, xland, ncmin_land, ncmin_sea)
    rin       = build_rttov_input(profiles, cloud, cfg)
    direct    = run_rttov_direct(rin)
    J, lam_BT = compute_obs_loss(direct.BT_hat, obs, masks, sigma)
    lam_prof  = run_rttov_k(rin, lam_BT)                 # 동일 rin/cfg (§7)
    lam_state = profile_adjoint_to_state_adjoint(lam_prof, ...)
    return lam_state                 # = da_window backward 의 obs_adj[t]
```

- `t`가 정합 안 된 관측이거나 관측이 없으면 `None` → window는 그 step에서 obs 기여 없이
  순수 VJP만 수행(M6 `test_obs_callback_no_obs_returns_none`).
- 반환된 `lam_state`는 **State covector `∂J_obs/∂x_t`** 이고, `da_window.py`가 detach해
  `obs_adj[t]`로 저장한 뒤 backward에서 **미세물리 adjoint에 더한다**(`da_window.py:255`
  `_add_states`; `handle.vjp`는 step M 전용이라 obs operator는 거기 흘리지 않는다 — §14.3).
- 위 `run_rttov_k` + `profile_adjoint_to_state_adjoint`(명시적 VJP 분해)와 §14.3의
  `RttovObsOp` + LOCAL `autograd.grad`(자동 합성)는 **같은 covector 계약의 두 구현**이다 —
  out-of-process backend(§14.2)를 쓰면 후자가 자연스럽다.
- **module boundary 요약**:

  | 모듈 | 책임 |
  |---|---|
  | `model_rttov_scheduler.py` | obs↔step 정합, schedule 생성, off-step 거부 |
  | `model_profile_builder.py` | checkpoint → RTTOV profile (T=θΠ, qv 규약, 단조성) |
  | `rttov_input_builder.py` | profile+cloud+chanprof+options → RttovInput, config hash |
  | `rttov_runner.py` | RTTOV direct/K 실행 (외부 Fortran wrapper) |
  | `obs_loss.py` | residual·mask·loss·λ_BT (§4 수학 구현) |
  | `rttov_obs_operator.py` | 위를 엮어 `obs_adjoint_callback` 제공 (da_window 연결) |

---

## 11. 검증 계획

> M3는 대부분 **이미 구현·통과** 상태(`kdm6_torch/tests/test_rttov_bridge.py` — 이번 세션). 신규는
> M1·M2·M4·M5·M6.

### M1 scheduler
```text
test_obs_schedule_exact_match          obs valid time == step end → 정합
test_obs_schedule_rejects_off_step_obs model_dt가 obs 간격 미분할 → 거부(checkpoint 제약)
test_obs_schedule_boundary_obs         window 시작/끝 경계 관측
```

### M2 profile builder
```text
test_profile_shapes                    column/profile shape 일치
test_temperature_from_th_pii           T == th·pii (fp64)
test_pressure_monotonic                RTTOV 규약대로 단조
test_units                             qv→Q 변환, gas_units/qv_convention 미명시 시 실패
```

### M3 bridge (대부분 기존)
```text
test_bridge_clear_state_finite         [기존] 청천 상태 유한
test_bridge_cloudy_nonzero             cloudy 상태 nonzero content/Reff
test_bridge_xland_ncmin_consistency    [기존 test_bridge_honors_xland_ncmin_gate]
test_bridge_vjp_fd                     [기존 test_bridge_vjp_fd_directional]
test_rime_frac_inactive_graupel_gate   [기존, 이번 세션] qg=0,bg>0 → 0, adjoint 0
```

### M4 RTTOV direct
```text
test_rttov_direct_single_profile_smoke 단일 profile 실행 smoke
test_rttov_direct_batch_smoke          batch 실행
test_rttov_direct_selected_channels    채널 subset
```

### M5 RTTOV-K
```text
test_rttov_k_temperature_fd            dBT/dT vs central FD
test_rttov_k_qv_fd                     dBT/dQ vs central FD
test_rttov_k_cloud_fd                  dBT/dcloud vs FD (bridge 통해)
test_direct_k_config_match             direct·K config hash 동일성
```

### M6 DA callback
```text
test_obs_callback_no_obs_returns_none  관측 없는 step → None
test_obs_callback_obs_time_returns_adjoint  정합 step → λ_state
test_da_window_with_mock_rttov         mock RTTOV로 window backward == full-graph
test_da_window_with_real_rttov_smoke   실제 RTTOV smoke
```

---

## 12. 구현 우선순위

```text
P1  model_rttov_scheduler.py + M1        (가장 위험 적고 정합 정책 고정)
P2  model_profile_builder.py + M2        (단위/규약 게이트 — 물리 정합의 1순위)
P3  bridge 재사용 검증 + M3              (대부분 done; rime-frac/xland 확인)
P4  rttov_input_builder + rttov_runner direct + M4   (외부 RTTOV wrapper smoke)
P5  rttov_runner K + interface contract + M5         (RTTOV-K↔torch 이음매)
P6  rttov_obs_operator.obs_adjoint_callback + M6     (da_window 연결, mock→real)
```

각 단계는 `kdm6ad+da.md`의 해당 절을 근거로 한다(P3→§9.3, P5→§9.2/§9.4, P6→§8.4).

---

## 13. 위험요소와 대응

| 위험 | 영향 | 대응 |
|---|---|---|
| obs time ≠ checkpoint 경계 | 정합 불가/silent skip | scheduler hard precondition + M1 거부 테스트; v2에서 FGAT |
| RTTOV-K↔torch shape/단위 불일치 | silent 오염 adjoint (F1-SHAPE) | §9.1 interface contract + per-field shape 검증 |
| direct≠K config | K가 direct 선형화 아님 | config hash 잠금 + M5 |
| qv 단위/규약 누락 | bridge 물리 무효 | M2 미명시-실패 게이트 |
| bridge가 DSD 재유도 | 입자크기 가정 어긋남 | preamble 재사용 강제(§6); effectRad_kdm6 1:1 |
| f32 NaN corner | adjoint 비유한 | DA는 fp64 경로 전용(`kdm6ad+da.md §0.1.A`) |
| RTTOV cloudy K 미성숙 | gradient 신뢰도 | FD-K는 검증용만, production 승격 금지(§9.2) |
| 두 저장소(KDM6AD↔AD-RTTOV) drift | 설계/사실 불일치 | snapshot 단방향, upstream=AD-RTTOV canonical |
| libtorch+RTTOV-OpenMP 스레딩 충돌 | T10/T11 클래스 크래시 재발 | RTTOV out-of-process 격리(§14); OMP fence 상속 |

---

## 14. KDM6AD ↔ AD-RTTOV 통합 방안 (확정 2026-06-13)

RTTOV는 AD-RTTOV에 있고 DA 기계(bridge/window/runtime)는 KDM6AD에 있다. 두 repo를 어떻게
협력시키는가의 결정사항.

### 14.1 자산 위치 및 의존 방향
- **RTTOV 14.1 바이너리 + coefficients + atlases는 AD-RTTOV/external/rttov14에 고정**(~GB,
  복제하지 않음). KDM6AD는 단일 설정점 `AD_RTTOV_HOME`(env/config)으로 참조한다.
- **의존 방향: KDM6AD → AD-RTTOV.** operator·window·loss·runner는 KDM6AD model-side에 산다
  ([[rttov-runs-at-model-observation-valid-time]]). AD-RTTOV의 기존 ~30개 `kdm6ad_rttov_*`
  스크립트는 fixture/alpha-chain-rule diagnostic **prior art**이며 DA 경로가 아니다.

### 14.2 RTTOV 호출 = out-of-process (스레딩 격리)
KDM6AD는 libtorch+libomp 스레드풀 자동 init 충돌(T10/T11; `run_kdm6ad.sh`의 단일스레드
fence가 그 산물)과 이미 싸웠다. pyrttov를 같은 프로세스에 로드하면 RTTOV의 OpenMP가 더해져
동일 충돌 클래스가 재발할 수 있다. 따라서:

> **RTTOV는 별도 프로세스로 격리해 호출한다**(subprocess `run.sh` 또는 pyrttov-in-child).
> `runDirect`+`runK`의 **config 동일성(§7)은 같은 프로세스 보장 대신 config-hash로 명시 강제**한다.
> 관측은 substep마다가 아니라 checkpoint 경계에서만 호출되므로 프로세스/직렬화 오버헤드는 수용 가능.
> 부모 셸 OMP fence(`OMP_NUM_THREADS=1` 등)는 RTTOV child에도 상속시킨다.

pyrttov in-process(runDirect/runK가 같은 Rttov 객체라 config 동일성이 구조적)는 스레딩이
검증된 뒤 성능 최적화 backend로 둔다 — `rttov_runner.py`를 backend-추상 인터페이스로 설계.

### 14.3 비-torch RTTOV를 torch 그래프에 넣는 법: `RttovObsOp`
RTTOV(out-of-process, 비-torch)는 **custom `torch.autograd.Function`**로 감싼다:

```text
class RttovObsOp(torch.autograd.Function):
  forward(ctx, profile_tensors, cloud_tensors):
      rin = build_rttov_input(...); ctx.save(rin, config_hash)
      return runDirect(rin).BT_hat                # out-of-process
  backward(ctx, lambda_BT):
      lam_profile = runK(rin, lambda_BT)          # out-of-process, 동일 rin/hash
      return unpack(lam_profile) → grad(profile_tensors, cloud_tensors)
```

**중요 — `da_window`의 `obs_adjoint(t,x_t)` 계약과의 정합** (Codex stop-review):
`da_window.run_da_window`의 `obs_adjoint(t, x_t)`는 **State covector `∂J_obs/∂x_t`를 직접
반환**하는 계약이다(`da_window.py:190` `u = obs_adjoint(t, xt)` → `:196` `obs_adj[t] =
detach(u)`). backward에서 `obs_adj[t]`는 **`handle.vjp`를 통과하지 않고** `_add_states`로
누적된다(`:247` `adj = handle.vjp(adj)` 는 미세물리 step M 전용, `:255` `adj =
_add_states(adj, obs_adj[t])`). 따라서 `RttovObsOp`는 **callback 내부의 LOCAL autograd
그래프에서만** 쓰이고, 그 결과 covector를 detach해 반환한다 — window-level backward나
`Handle.vjp`로 흘려보내지 않는다:

```text
def obs_adjoint_callback(t, x_t):           # da_window 가 호출 (covector 반환 계약)
    obs = schedule.get(t)
    if obs is None: return None
    leaves = fresh_requires_grad_leaves(x_t)         # detached checkpoint → fresh fp64 leaves
    cloud  = rttov_cloud_profile(leaves.state, forcing, xland, ncmin_*)  # 순수 torch bridge
    prof   = build_rttov_profiles(extract_model_columns(leaves, ...), cfg)
    BT_hat = RttovObsOp.apply(prof.tensors, cloud.tensors)   # 비-torch RTTOV가 그래프 진입
    J, _   = compute_obs_loss(BT_hat, obs, masks, sigma)
    (lam_state,) = torch.autograd.grad(J, [leaves])          # LOCAL grad — 여기서 닫힘
    return State(*(g.detach() for g in lam_state))           # = obs_adj[t]  (window가 ADD)
```

- `RttovObsOp.backward`(runK ⊗ λ_BT)와 하류 `rttov_cloud_profile`(순수 torch)이 이 LOCAL
  `autograd.grad` 안에서 **자동 합성**된다. §9.1의 F1-SHAPE 이음매는 `RttovObsOp.backward`의
  `unpack(lam_profile)` 한 지점에 국소화된다(autograd 경계 = process 경계 = backend 한 곳).
- window가 `obs_adj[t]`(=이 반환 covector)를 미세물리 adjoint에 **더하는** 것이지, obs operator가
  `Handle.vjp`를 호출하는 게 아니다. 두 adjoint(관측·역학)는 `da_window` backward에서 합산된다.

### 14.4 building blocks 재사용 = import (복사 금지)
humidity 단위변환·RTTOV pressure-grid 유도·`kdm6ad_rttov_mapping` 등 AD-RTTOV의 검증된
building block은 **`AD_RTTOV_HOME`에서 import**한다(복사하면 drift; 30개 스크립트가 이미 쓰는
upstream 코드). KDM6AD 신규 코드는 이들을 호출만 한다.

### 14.5 통합 precondition (구현 P4 이전)
- `AD_RTTOV_HOME` 설정 + RTTOV 14.1 build·coefficient(ami/501)·atlas 존재 확인.
- out-of-process RTTOV가 부모 OMP fence를 상속하는지 smoke로 검증(libtorch 동거 크래시 클래스).
- `rttov_config.hash()`가 direct·K 양쪽에서 동일함을 단언(M5 `test_direct_k_config_match`).
- pyrttov runK 경로를 쓸 경우, K 출력 레이아웃이 `RttovCloudProfile` 필드와 정렬되는지 계약 검증.

---

## 부록 A. 교차참조 지도

| 본 문서 절 | 근거 (kdm6ad+da.md) | 코드 |
|---|---|---|
| §2 시간정합 | §8.4 checkpoint/recompute | `da_window.py` |
| §6 bridge | §9.3 DSD bridge VJP | `rttov_bridge.py` |
| §8 loss | §4 GK2A-RTTOV loss, §9.1 | (구현 예정 `obs_loss.py`) |
| §9 adjoint 체인 | §9.1–9.4 | `runtime.py` Handle.vjp |
| §10 callback | §8.4 backward skeleton | `da_window.py` obs_adjoint |
| controls | §5 state/process/partition controls | `process_controls.py`, `da_window.py` |

관련 AD-RTTOV/wiki(upstream, 읽기 전용): `concepts/ad-rttov-reference-observation-operator`,
`concepts/rttov-profiles-k-bt-sensitivity-contract`,
`procedures/kdm6ad-to-rttov14-ami501-tq-jacobian-workflow`,
`decisions/use-rttov-14-1-as-initial-baseline`.
