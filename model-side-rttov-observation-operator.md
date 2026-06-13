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
   `λ_BT → (RTTOV-K) → λ_profile → (rttov_bridge VJP) → λ_state = ∂J_obs/∂x_t`.
   이 `λ_state`는 obs operator의 출력 covector로, da_window가 `_add_states`로 미세물리 adjoint에
   **더한다** — obs operator는 `Handle.vjp`를 호출하지 않는다(§9/§10/§14.3). `Handle.vjp`는 window의
   역학 step M 전용이다. 체인 수학은 `kdm6ad+da.md §9`, bridge 구현은 `rttov_bridge.py`.

6. **목표는 all-sky 16채널이므로 cloud/scattering 경로와 hydrometeor bridge가 부차가 아니라 핵심이다.**
   GK2A AMI 16채널(VIS/NIR 6 + IR 10)에 대한 RTTOV 전천 cloudy/scattering RT를 쓴다(AMI는 unified
   VISIR scatt — MW RTTOV-SCATT 아님). `RttovCloudProfile`(clw/ciw/rain/snow/graupel + reff_*; §4.4)이
   정확히 all-sky가 요구하는 입력이다 — cloud-active gate(`kdm6ad+da.md §3`)·cloud/phase loss
   (`§4.2/§4.3`)·bridge cloudy 경로(§6)·RTTOV cloudy-K(M5 `test_rttov_k_cloud_fd`)가 1순위 검증 대상.
   **단계화**: IR 10채널 1차, VIS/NIR 6채널(solar 반사 — RTTOV는 thermal=BT, solar=REFLECTANCE를
   `btrefl`로 반환하므로 loss·residual이 채널별로 BT/refl 분기 필요)은 후속.

### 1.7 성숙도 현황 (maturity status, 2026-06-13 적대적 검토)
**현재 능력 ≠ 최종 목적.** AD-RTTOV에서 지금까지 검증된 것은 **clear-sky** AMI ami/501 ch8–16의
T/Q `PROFILES_K` vs BT central-FD chain-rule(corr 0.9995; `rttov-profiles-k-bt-sensitivity-contract`)
뿐이다. **아직 한 번도 수행되지 않은 것**: AMI에 대한 cloud/hydrometeor K. §6 bridge의 torch-side
VJP는 구현·게이트 통과(`test_rttov_bridge.py`)이나, 그 하류 RTTOV-side cloud/scattering K(Fortran)와
H1/H2/H3 수상체 광학 매핑은 scaffold다. **결정적 차단요인**: matching `rttov_hydrotable_gkompsat2_1_ami*`
부재로 AMI native hydrometeor run 자체가 현재 불가(§13/§14.5, hot.md). 따라서 §0·원칙 6의 all-sky
주장은 **현재 구현된 능력이 아니라 연구 목표**다.

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
| 미분 기준 | 이 상태에서의 선형화 — callback의 LOCAL `autograd.grad`가 obs covector `λ_state = ∂J_obs/∂x_t` 생성(da_window가 `_add_states`로 누적; `Handle.vjp` 아님 — §14.3) |

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
gas options                 GasUnits=2(ppmv_wet), MmrHydro=False(g/m³ — 적대적검토), 활성 기체
adk_bt / store_rad          adk_bt=True(K seed=BT space) + store_rad=True(Bt 노출) — 필수, §14.5
O3 option                   오존 profile 사용 여부/소스
cloud/scattering options    all-sky cloudy RT (AMI는 unified VISIR scatt; MW RTTOV-SCATT 아님)
hydro size param            positive HydroDeff6/7 입력(setHydroDeffN; reff→Deff; number-moment 경로)
emissivity/BRDF             표면 방출률/반사 atlas
hydrotable/cloud optical    AMI-matching rttov_hydrotable_gkompsat2_1_ami* (현재 부재 — §13/§14.5)
chanprof mapping            (profile, channel) 매핑
direct/K config hash        방어적 assert (단일 runK가 direct≡K 구조 보장 — §14.2)
```

### 4.7 adjoint 변수

```text
λ_BT                BT cotangent ∂J_obs/∂BT_hat (autograd가 생성; runK seed 아님 — §8/§9)
λ_profile           RTTOV profile-level adjoint (RttovObsOp.backward의 K^T·λ_BT)
λ_KDM6AD_state      obs covector ∂J_obs/∂x_t (=λ_state; da_window가 _add_states로 누적, Handle.vjp 아님)
λ_controls          active control adjoint (kdm6ad+da.md §5; grad_η / grad_α)
```

---

## 5. 모델 column/profile extractor

**모듈**: `model_profile_builder.py`. **요구: 전 경로 순수-torch·leaves로부터 미분가능**
(`RttovObsOp.apply` 이전 — §14.3 그래디언트 전파 계약). numpy 변환은 grad를 끊는다.

```python
# 통합 순수-torch 변환 (§14.3 0)단계): leaves → RTTOV 단위/grid 텐서들
model_to_rttov_tensors(leaves, forcing, cfg, xland, ncmin_*) -> tuple[Tensor, ...]
#   gas/T side: extract_model_columns ∘ (qv→Q ppmv-moist) ∘ (model-level→layer/level 보간 W)
#   cloud side: rttov_cloud_profile(=bridge §6)가 이미 g/m³·µm로 emit → 그대로 사용(재변환 금지)
#               + reff(µm)→Deff(µm) ×2 (RTTOV는 effective DIAMETER 입력)
```

- **단위 source of truth(정정 Round-2)**: cloud content(g/m³)·reff(µm)는 **bridge가 이미 emit**한다
  (`rttov_bridge.py:194-198`). model_to_rttov_tensors는 **그 출력을 재변환하지 않는다**(이중변환 금지).
  남은 변환은 (a) gas qv→Q, (b) reff→Deff ×2, (c) 보간 W뿐.
- `extract_model_columns`: detached fp64 checkpoint와 forcing에서 column 변수(p, T=θ·Π, qv,
  surface, geometry)를 **torch 연산으로** 뽑는다. T는 `T = th · pii`(torch).
- **단위/규약 게이트**: qv→Q 변환은 `qv_convention`·`gas_units`(=2 ppmv_wet) 미명시 시 실패
  (`require-explicit-qv-convention-before-rttov-bridge`); 변환식은 **torch**(∂Q/∂qv 자동 미분).
- **보간**: model-level→RTTOV grid 로그압력 보간은 per-profile 1회 계산한 **상수 torch 행렬**.
  **grid는 hard-code 금지 — coef/fixture에서 derive**(`_rttov_reference/rttov_profile_pressure_grid.py`).
  두 grid를 혼동 말 것: **user profile grid**(bridge가 KDM6AD column을 여기로 보간 — W가 타깃)와
  **coef predictor grid = 54 levels**(RTTOV 내부; user가 안 건드림, RTTOV가 자체 보간). RTTOV-14 AMI는
  **layer-based**라 W는 T/Q/content를 **layers**로, PHalf를 **levels**로 보간한다. ami/501 fixture는
  **nlayers=69 / nlevels=70**(p.txt 69줄, p_half.txt 70줄)이나 입력마다 다르므로 derive(GFS=nlevels 70).
  Wᵀ가 autograd 자동 합성 — numpy 보간 금지.
- p/PHalf는 **forcing 상수(미분 대상 아님)** — Pa→hPa 스케일링은 numpy pack 단계에 둬도 무방
  (상수라 grad 불필요). 단조성 검증(M2); 외삽 금지.
- RTTOV-14 AMI는 **layer-based**: T/Q/gases/content/Deff는 **layers(P=VerticalProfilesRW)**,
  PHalf만 **levels(VerticalProfilesLevelsRWD)**, `Nlayers = Nlevels−1`(profile.py:124).
  ami/501 fixture는 **nlayers=69**(p/t/q/co2/o3.txt=69줄), **nlevels=70**(p_half.txt=70줄).
  count는 hard-code 금지 — fixture/coef에서 derive(GFS-collocated는 nlevels=70 등 입력마다 다름).
  **coef predictor 54L은 별개**(rttov13pred54L; RTTOV가 user 69층→54 내부 보간, user가 안 건드림).

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

## 7. RTTOV input builder + runner (single runK)

**모듈**: `rttov_input_builder.py`, `rttov_runner.py`

```python
pack_rttov_input(rttov_tensors, rttov_config) -> RttovInput   # 직렬화만(단위변환 없음, §14.3)
run_rttov_k(rttov_input) -> RttovKOutput   # K-matrix + direct BT(out.Bt) 동시 — 별도 runDirect 불요
# run_rttov_direct(rttov_input) -> ...      # (선택) value-only 진단 runner — adjoint 경로 아님
```

- `RttovInput`은 profile + cloud profile + chanprof + options + geometry + surface를
  하나의 객체로 묶는다.
- **단일 runK가 BT+K 동시 산출**(§14.2) → forward는 runK 1회. 별도 `run_rttov_direct`는
  value-only 진단용 옵션일 뿐 adjoint 경로가 아니다(M4 direct-smoke도 그 한정).
- **direct/K config-hash는 방어적 assert**(정합성 보장 아님 — 단일 runK가 구조적으로 보장, §14.2).
  `rttov_config.hash()`(coefficient+channel+gas+cloud option+geometry); 별도 value-only direct를
  쓸 때만 mismatch 검사 의미 (M5 `test_direct_k_config_match`).
- RTTOV는 **외부 Fortran**(RTTOV 14.1, pyrttov/AD-RTTOV wrapper)이며 torch autograd가 아니다 —
  `RttovObsOp`가 그래프 진입점(§14.3). 실제 함수명/파일명은 후속 구현 때 채운다.

---

## 8. 관측 matching + loss

**모듈**: `obs_loss.py`

```python
compute_obs_loss(BT_hat, obs, masks, sigma) -> J_obs   # torch scalar (BT_hat에 미분가능)
```

loss의 **수학은 `kdm6ad+da.md §4(GK2A-RTTOV cloud/phase-aware loss)·§9.1`에 정의**되어 있다
(BT residual, Huber ψ_δ, cloud/phase/partition/cloud-top/texture loss). 본 모듈은 그것을
**torch scalar `J_obs`로 구현**하고, 다음을 보장한다:

- 관측·RTTOV 양쪽 quality가 0인 (profile, channel)만 metric/gradient에 포함. RTTOV 측은
  `RttovKOutput.rad_quality`(store_rad=True 보장; pyrttov __init__.py:1097에서 _doStoreRad가 저장)에서
  읽어 `mask = obs_quality_ok & (rad_quality==0) & cloud_gate`를 **detached 0/1 가중**으로 ψ_δ(r)/σ에
  곱한다 — clip된 cloudy radiance(Deff clip의 `qflag_hydro_deff_limits` 포함)는 J_obs·λ_BT에 정확히 0
  기여(M5 `test_rttov_quality_excludes_clipped_channel`: rad_quality≠0 → 해당 (p,c)의 λ_state==0).
- bias correction은 residual 정의 시점에 적용하는 **detached static(또는 VarBC-frozen) per-channel
  offset** — obs측 가산 shift이므로 ∂J/∂state 불변(VarBC면 그 parameter는 별도 control).
- **λ_BT는 compute_obs_loss의 출력이 아니다(정정).** λ_BT = ∂J_obs/∂BT_hat은 callback의
  `autograd.grad`가 만드는 **cotangent**이고, `RttovObsOp.backward`가 받는 grad-output이다.
  runK는 λ_BT를 seed로 받지 않는다(§9/§14.3) — `λ_BT = m·w·ψ_δ(r)/σ_c`는 그 cotangent의 해석식.

---

## 9. RTTOV-K / profile adjoint + KDM6AD bridge VJP 연결

**모듈**: `rttov_runner.py`(K), `rttov_obs_operator.py`(연결)

```python
# ⚠ 적대적 검토 정정(2026-06-13): pyrttov runK는 lambda_BT를 받지 않는다.
# runK(channels)는 채널별 단위 seed(btrefl_k/rad_k=ones, pyrttov:913-914 — 사용자
# 설정 불가)로 FULL K-matrix를 계산한다(accessor TK/GasesK/getItemK/getHydroDeffNK,
# shape [...,nchannels,nlayers]). 따라서 채널 contraction은 호출자가 직접 한다:
K = run_rttov_k(rttov_input)                               # 전체 Jacobian (채널 dim 포함)
lambda_profile = contract_K_with_lambda_BT(K, lambda_BT)   # λ_profile = Σ_c K[c]·λ_BT[c]
profile_adjoint_to_state_adjoint(lambda_profile, ...) -> lambda_state   # bridge VJP
```

전체 adjoint 체인 (수학 = `kdm6ad+da.md §9.1–9.4`):

```text
λ_BT
  → RTTOV-K (full K-matrix) + 호출자 채널 contraction K^T·λ_BT   (외부 Fortran, §9.2)
  → λ_profile             (RTTOV profile-level adjoint; PROFILES_K=∂BT/∂profile은
                           adk_bt=True일 때만 — §4.6/§9.1)
  → DSD/optical bridge VJP (rttov_bridge VJP, torch.autograd, §9.3)
  → λ_qc … λ_bg, λ_th, λ_qv  (§9.4)  ← 이것이 곧 λ_state = ∂J_obs/∂x_t (체인 종료)
  ⇒ da_window가 detach 후 _add_states로 미세물리 adjoint에 누적 — Handle.vjp를 통과하지 않는다(§10/§14.3).
     (window-level 역학 pullback M_0^T…M_{t-1}^T만 Handle.vjp 사용 — obs operator의 일이 아님)
```

> **참조 화해 (kdm6ad+da.md §9.4 vs 본 정밀 계약).** 자매 snapshot `kdm6ad+da.md §9.4`는
> "이 adjoint가 `Handle::vjp`의 입력 `u`가 된다"고 적는다. 이는 **window 누적 framing의 coarse
> 표현**으로, obs covector λ_state가 `adj`에 합류한 뒤 *이전* step들의 Handle.vjp가 그 누적 adj를
> 역학으로 pullback한다는 뜻이다(틀린 게 아님). 그러나 **정밀 계약은 본 문서 §10/§14.3 + 구현
> `da_window.py`가 owns**: obs operator(RttovObsOp+bridge)는 자체 LOCAL `autograd.grad`로 λ_state를
> 만들 뿐 **Handle.vjp를 직접 호출하지 않으며**, λ_state는 `_add_states`로 더해진다(`:255`). 두
> 진술은 같은 수학의 다른 granularity다. snapshot은 frozen(upstream=AD-RTTOV)이라 수정하지 않고
> 본 주석으로 화해한다.

### 9.1 가장 위험한 이음매: RTTOV-K ↔ torch 경계 (Interface Contract)

RTTOV-K는 Fortran 전통 adjoint(손코딩), bridge VJP는 torch autograd다. 이 이음매는
**bridge 출력 필드와 RTTOV-K 출력이 1:1 동일 shape가 아니다** — 적대적 검토(2026-06-13)가
pyrttov 실제 레이아웃을 확정했으므로, 계약은 **비대칭 라우팅 테이블**로 명시한다(F1-SHAPE class).

```text
계약 (interface contract, pyrttov 실측 기반):
  1. K 레이아웃: runK 후 hydrometeor/gas Jacobian은 결합 배열 GasesK
     [ngases, nprofiles, nchannels, nlayers]에 들어가고(__init__.py:421), 필드별 접근은
     item-id 인덱스 view(getItemK / HydroN_K / HydroDeffN_K, :1227-1243)다 —
     RttovCloudProfile 필드별 별도 배열이 아니다.
  2. item-id 맵 — ★ AMI는 VIS/IR all-sky이므로 MW RTTOV-SCATT 규약(RAIN=HYDRO1…) 금지.
     VIS/IR 규약(rttype.py:94, AD-RTTOV hydro_visir 50lev + kdm6ad_native_hydro_visir_writer.py:128):
     content 슬롯과 Deff 슬롯을 **같은 N**으로 짝짓는다 — 액체운: content HYDRO6(CLWD)+Deff HYDRO_DEFF6,
     빙운: content HYDRO7(BAUM ice)+Deff HYDRO_DEFF7. RTTOV-14는 **CLW/ice Deff 슬롯만** 존재하고
     **rain/graupel Deff item은 없다**(rttype.py:94-98). KDM6AD 5종(qc/qr/qi/qs/qg)→VIS/IR hydro type
     매핑 자체가 frontier(§13; H1/H2/H3 scaffold).
  3. 채널 contraction은 호출자가: λ_field[p,l] = Σ_c K_field[p,c,l]·λ_BT[p,c].
  4. T sensitivity는 TK [nprofiles,nchannels,nlayers]; gas(Q)는 getItemK(gas_id).
  5. BT-K 전제: TK/GasesK가 ∂BT/∂profile인 것은 adk_bt=True일 때만. runK는 radiance-K도
     같이 만들므로(rad_k seed), GK2A loss=BT-residual이면 adk_bt=True 필수(§4.6).
  6. RTTOV-14 K-shape: TK/GasesK/PK는 **nlayers**, PHalfK만 **nlevels**(__init__.py:394-423).
     ami/501 nlayers=69/nlevels=70(fixture-derived); coef predictor 54L과 혼동 금지.
```

**입자크기 = number-moment adjoint 경로 (CRITICAL).** bridge가 내보내는 reff(effective
RADIUS, µm)는 RTTOV-14가 effective DIAMETER(HydroDeffN)로 받는다 — **Deff_µm = 2·reff_µm**.
그리고 RTTOV-K가 ∂BT/∂Deff(getHydroDeffNK)를 주는 것은 **positive Deff를 EXPLICIT 입력 profile
item으로 넣었을 때뿐**이다(reff_liq→setHydroDeffN(.,6), reff_ice→setHydroDeffN(.,7)). gate는
RTTOV가 **`hydro_deff>0`인지**다(rttov_calc_hydro_deff.F90:125; K adjoint도 `>0` 분기에서만
profiles_k%hydro_deff로 흐르고 ELSE는 0 — _k.F90:97-100/:122). ★ `ClwdeParam/IcedeParam`은
**'user' enum 값이 아니다**(그런 값 없음 — rttov_const.F90 clwde_martin=1/nicede_param=4, pyrttov 기본
1; ELSE 분기 내부 파라미터화 선택자일 뿐). positive Deff를 안 넣으면 **λ_Deff≡0 → λ_nc=λ_ni≡0**.
**단, RTTOV-14에는 CLW·ice Deff 슬롯만 있고 rain/graupel Deff item은 없다**(rttype.py:94-98) —
따라서 user-Deff가 살리는 것은 **λ_nc·λ_ni뿐**이다. **λ_nr·λ_bg는 obs operator에 경로가 아예 없다**
(rain_dm/rime_frac은 bridge carrier일 뿐 RTTOV 입력 슬롯 없음) → obs-side에서 **0이 정답**이고
그 민감도는 동역학 VJP가 운반한다. 즉 number-moment 중 nc/ni만 all-sky 관측신호로 복원된다(M5).
user-Deff-off 검출은 covector의 None-검사로는 **불가**(K=0이라 grad는 None이 아니라 connected-zero) —
**M5에서 positive HydroDeff6/7 입력 단언 + getHydroDeffNK 비영(非零) probe**로 잡는다(아래 §10 주).

- `reff_*/rain_dm/rime_frac`은 bridge 측 carrier일 뿐 RTTOV-K에 1:1 대응 필드가 없다 —
  λ는 위 HydroDeffN_K(입자크기)와 content-K(질량)로 라우팅된다.
- RTTOV-K의 cloud/scattering K가 충분히 검증되기 전에는 FD-K를 production 주 경로로 승격하지
  않는다(`kdm6ad+da.md §9.2`). FD-K는 bridge VJP 검증·surrogate에만 쓴다.

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
    obs_list = schedule.get(t)       # 정합된 step의 obs footprint LIST(§4.1), 아니면 None
    if not obs_list:                 # None 또는 빈 list
        return None                  # 관측 없는 step → window는 순수 VJP만
    # ★ 한 step에 footprint 여러 개 가능 → compute_obs_loss를 list에 대해 합산(아래 J).
    leaves    = fresh_requires_grad_leaves(x_t)         # detached checkpoint → fresh fp64 leaves
    # ★ apply 이전 변환은 전부 순수-torch (leaves→RTTOV-unit). 한 단계라도 numpy면 grad 끊김(§14.3).
    rttov_tensors = model_to_rttov_tensors(leaves, forcing, cfg,   # extract+단위+reff→Deff+보간W
                                           xland, ncmin_land, ncmin_sea)  # cloud는 rttov_cloud_profile 경유
    BT_hat    = RttovObsOp.apply(*rttov_tensors)        # forward: runK 1회(BT+K 캐시), 단위변환 없음
    J         = sum(compute_obs_loss(BT_hat, o, masks, sigma) for o in obs_list)  # footprint합산; scalar(λ_BT는 autograd가 생성)
    # leaves는 State(12 텐서) → grad inputs는 tuple(leaves)로 풀어 넘긴다(State 자체는 grad 입력 불가).
    # ★ materialize_grads 금지: 그건 '합법적 0'(nccn)과 '끊긴 필수 경로'(λ_nc 등)를 둘 다 0으로
    #   덮어 버그를 숨긴다(Codex stop-review). 대신 declared-zero만 0, 필수 None은 loud-fail.
    grads = torch.autograd.grad(J, tuple(leaves), allow_unused=True)  # None 허용, materialize 안 함
    return assemble_obs_covector(leaves, grads)         # 아래 — 필수 경로 None이면 raise
```

**covector 조립 — 구조적 단절만 loud-fail (Round-2 정정 2026-06-13).** None grad의 의미는 둘:
**합법적 무경로**(obs operator에 RTTOV 입력 슬롯이 아예 없음 — nccn, 그리고 RTTOV-14에 Deff item이
없는 nr/bg) vs **구조적 단절**(apply-이전 변환이 numpy로 끊겨 연결돼야 할 필드가 None). 전자는 0이
정답(동역학 VJP가 운반), 후자는 버그다. 따라서 **무경로 허용목록만 0, 나머지 None은 loud-fail**:

```text
# obs operator에 RTTOV 입력 경로가 '없어야 정상'인 필드(0이 정답; 동역학 VJP가 담당):
OBS_ZERO_OK = {'nccn', 'nr', 'bg'}
#   nccn: BT에 직접 경로 없음.  nr/bg: RTTOV-14에 rain/graupel Deff item 없음(rttype.py:94-98)
#         → rain_dm/rime_frac은 bridge carrier일 뿐 RTTOV 입력 슬롯 없음(§9.1). user-Deff는
#         λ_nc·λ_ni만 살린다.

def assemble_obs_covector(leaves, grads):
    out = []
    for name, g in zip(State._fields, grads):     # th,qv,qc,qr,qi,qs,qg,nccn,nc,ni,nr,bg
        if g is None:
            if name in OBS_ZERO_OK:
                g = torch.zeros_like(getattr(leaves, name))   # 합법적 0 (무경로)
            else:
                raise RuntimeError(
                    f"obs adjoint 구조적 단절: λ_{name}=None. apply-이전 변환이 numpy로 끊김"
                    f" (model_to_rttov_tensors가 전부 torch여야 — §14.3). silent-zero 금지.")
        out.append(g.detach())
    return State(*out)
```

연결되어 있으나 그 state에서 값이 0인 grad(예: qi=0 셀의 ∂J/∂qi≈0)는 **정상** — 검사는 "값이
0인가"가 아니라 "그래프에 연결됐는가(None 아닌가)"다. 이 검사는 **구조적 단절(numpy break)만** 잡는다.
**user-Deff-off는 여기서 못 잡는다**(Round-2 reverify): nc→reff→Deff→apply 경로가 torch로 연결돼
있으면, RTTOV가 Deff를 무시(default param)해 getHydroDeffNK=0이어도 grad는 **None이 아니라
connected-zero**라 통과한다. 따라서 user-Deff 모드 검출은 covector가 아니라 **M5에서
positive HydroDeff6/7 입력 단언 + getHydroDeffNK 비영 probe**로 한다(§9.1/§14.5).

- `t`가 정합 안 된 관측이거나 관측이 없으면 `None` → window는 그 step에서 obs 기여 없이
  순수 VJP만 수행(M6 `test_obs_callback_no_obs_returns_none`).
- 반환된 `lam_state`는 **State covector `∂J_obs/∂x_t`** 이고, `da_window.py`가 detach해
  `obs_adj[t]`로 저장한 뒤 backward에서 **미세물리 adjoint에 더한다**(`da_window.py:255`
  `_add_states`; `handle.vjp`는 step M 전용이라 obs operator는 거기 흘리지 않는다 — §14.3).
- **채널 contraction은 `RttovObsOp.backward` 안에서** `λ_profile=Σ_c K[c]·λ_BT[c]`로 일어난다
  (runK는 λ_BT를 seed로 받지 않음 — §9/§14.3 정정). 위 LOCAL `autograd.grad`가 그 backward와
  하류 bridge VJP(순수 torch)를 자동 합성한다.
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

### M5 RTTOV-K  (적대적 검토 2026-06-13 반영)
```text
test_rttov_k_temperature_fd            dBT/dT vs central FD (TK, adk_bt=True 확인)
test_rttov_k_qv_fd                     dBT/dQ vs central FD (getItemK; ∂Q/∂qv torch-side 포함)
test_rttov_k_cloud_fd                  dBT/dcontent vs FD (getHydroNK 6/7 = CLWD/BAUM content; NOT MW HYDRO1-5)
test_rttov_k_deff_fd                   dBT/dDeff vs FD (getHydroDeffNK; ★nc/ni number-moment 경로)
test_user_deff_mode_or_fail            positive HydroDeff6/7 입력 아니면 hard-fail (λ_nc/λ_ni 생존)
test_getHydroDeffNK_nonzero_probe      ★ user-Deff-off의 유일한 검출: K_deff 비영 probe(covector는
                                       connected-zero라 못 잡음 — Round-2 reverify). DEFF6/7만 존재
test_adk_bt_and_store_rad_set          adk_bt=True & store_rad=True 강제 (radiance-K 혼동 차단)
test_hydro_units_mmr_false             MmrHydro=False & GasUnits=2 (단위 계약)
test_reff_to_deff_x2                   Deff_µm == 2·reff_µm 변환 검증
test_K_channel_contraction             λ_profile = Σ_c K[c]·λ_BT (full-K-matrix 직접 contraction)
test_direct_k_single_runK              forward runK 1회가 BT+K 동시 산출 (별도 runDirect 불요)
```
※ refuted(재검증): "HydroEsba_k/UserHydroOptParam 경로 필요" 주장은 반박됨 — HydroDeff 입력
경로(위)가 입자크기 미분의 정답이며 EsbA opt-param 경로는 불필요.

### M6 DA callback
```text
test_obs_callback_no_obs_returns_none  관측 없는 step → None
test_obs_callback_obs_time_returns_adjoint  정합 step → λ_state
test_required_paths_connected          ★ RTTOV 경로 있는 필드(th,qv,qc,qr,qi,qs,qg,nc,ni)는
                                       grad=None 아님(연결); 끊기면 assemble_obs_covector가 raise
test_no_path_fields_zero               nccn/nr/bg는 None→0 허용(RTTOV-14에 rain/graupel Deff 없음)
test_structural_sever_raises           apply-이전 numpy 단절 시 연결돼야 할 필드 None → loud-fail
test_pre_apply_path_is_torch           model_to_rttov_tensors 출력이 leaves.grad_fn에 연결됨
# ※ user-Deff-off 검출은 M6가 아니라 M5(test_user_deff_*) — covector는 connected-zero라 못 잡음
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
| **AMI hydrotable 부재** (적대적검토 blocking) | all-sky cloud-K 검증 불가(최종목적 차단) | matching `rttov_hydrotable_gkompsat2_1_ami*` 확보 전엔 IASI donor=실행만/science 아님; §14.5 precondition |
| **입자크기 미분 경로 단절** (blocking) | user-Deff 아니면 λ_nc=λ_ni≡0(nc/ni만; nr/bg는 RTTOV Deff 없어 obs-path 자체 없음) | reff→Deff(×2) positive HydroDeff6/7 EXPLICIT 입력(gate=hydro_deff>0, 'user' enum 없음); M5 비영 probe(covector 못 잡음) |
| **covector 무경로 vs 단절 혼동** (major) | nr/bg를 필수로 요구하면 매 호출 false-raise | nr/bg/nccn=OBS_ZERO_OK(0 정답); 단절(numpy)만 raise(§10) |
| **단위/보간 Jacobian이 torch 밖** (blocking) | λ_qv·λ_x에서 ∂Q/∂qv·∂(interp) 누락 | qv→Q·reff→Deff·보간(W→profile grid; RTTOV-14 layer-based, fixture nlayers=69/nlevels=70 derive, coef 54L과 혼동 금지)을 torch 연산(상수 W)으로; cloud content는 bridge가 이미 g/m³ — 재변환 금지 §14.3-units |
| **radiance-K vs BT-K 혼동** (major) | TK/GasesK가 BT가 아닌 radiance면 loss 불일치 | adk_bt=True+store_rad=True 강제, config-hash 포함(§4.6/§14.5) |
| **RTTOV QUALITY 마스킹 미정의** (major) | clip된 cloudy radiance가 gradient 오염(all-sky 1차 사안) | rad_quality(store_rad 보장)==0 detached mask로 ψ_δ/σ 가중; bias=detached static offset(∂J/∂state 불변); M5 quality-exclude 테스트(§8) |
| runK 더블런/config-identity | 비용·선형화점 불일치 | forward에서 runK 1회(=direct BT+K), config-hash는 방어 assert로 강등(§14.2) |
| custom-Function 정확성 | ctx.save 오용·grad arity | 비텐서는 ctx.<attr>; backward는 forward 입력 순서대로 grad 반환(§14.3) |

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
> 관측은 substep마다가 아니라 checkpoint 경계에서만 호출되므로 프로세스/직렬화 오버헤드는 수용 가능.
> 부모 셸 OMP fence(`OMP_NUM_THREADS=1` 등)는 RTTOV child에도 상속시킨다.

**direct/K 동일성 — 단일 runK로 구조적 보장(적대적 검토 정정).** pyrttov `runK`는 K-matrix와
direct BT를 **한 호출에 동시 산출**한다(`_doStoreRad`, `out.Bt`). 따라서 forward에서 `runK` 1회로
BT를 얻고 K를 캐시하면 별도 `runDirect`가 불필요하고 direct≡K 선형화점이 **같은 호출이라 자동 일치**한다.
§7/§14.5의 config-hash는 이제 *정합성 보장*이 아니라 **방어적 assert**로 강등(별도 value-only runDirect를
다른 곳에서 쓸 때만 의미). 단, out-of-process child는 **runK가 부른 단일 Rttov 인스턴스/coef-load 안에서**
일어나야 보장이 성립한다(별개 프로세스의 두 load는 보장 못 함 — child가 한 인스턴스로 처리).

pyrttov in-process(같은 Rttov 객체)는 스레딩이 검증된 뒤 성능 최적화 backend로 둔다 —
`rttov_runner.py`를 backend-추상 인터페이스로 설계.

### 14.3 비-torch RTTOV를 torch 그래프에 넣는 법: `RttovObsOp`
RTTOV(out-of-process, 비-torch)는 **custom `torch.autograd.Function`**로 감싼다:

**그래디언트 전파 계약 (load-bearing, Codex stop-review 2026-06-13).** `obs_adjoint`는 detached
state를 받으므로(아래 `da_window.py:200`) gradient는 callback **내부 local graph**에서만 흐른다.
그 graph가 leaves까지 닫히려면 **`RttovObsOp.apply` 이전의 model→RTTOV 변환 전체가 leaves로부터의
순수-torch 함수**여야 한다 — 그래야 `RttovObsOp.backward`가 돌려준 grad가 변환을 거슬러 leaves에
도달한다. 한 단계라도 numpy면(기존 bridge 스크립트 `kdm6ad_rttov_profile_bridge.py:116` 보간,
`humidity_unit_conversion.py:26` 단위변환이 그러함) **그 경로의 leaves grad가 None**이 되어
∂J/∂th·∂J/∂qv 등이 전파되지 않는다(= "callback이 gradient를 전파 못 함"의 정확한 원인).

```text
# 0) model→RTTOV 변환: 전부 순수-torch, leaves로부터 미분가능 (§5+§6+§7 통합)
#    gas/T: extract_columns + (qv→Q ppmv-moist) + (보간 W→profile grid; RTTOV-14 layer-based,
#           T/Q/content=layers·PHalf=levels, ami/501 nlayers=69/nlevels=70 derive — coef 54L 혼동 금지)
#    cloud: rttov_cloud_profile(bridge §6)가 이미 g/m³·µm emit → 그대로 + (reff→Deff ×2)
#           (content 재변환 금지 — bridge가 단위 source of truth)
#    ⇒ rttov_tensors = (T_lay, Q_lay, clw, ciw, rain, snow, graupel,
#                       deff_liq, deff_ice, skin, t2m, q2m, …)  — 모두 RTTOV 단위/grid
rttov_tensors = model_to_rttov_tensors(leaves, forcing, cfg)   # 순수 torch, grad 연결

class RttovObsOp(torch.autograd.Function):
  # ★ apply 입력 = 이미 RTTOV 단위/grid인 torch 텐서들. forward는 단위변환을 하지 않는다
  #   (직렬화만). 변환은 위 0) 단계에서 끝났고 그 Jacobian은 autograd가 자동 합성한다.
  forward(ctx, T_lay, Q_lay, *cloud_and_surface_tensors):
      rin = pack_rttov_input(T_lay, Q_lay, ...)   # numpy로 직렬화만 (단위변환 없음)
      out = runK(rin, channels)                   # 1회 — K-matrix + direct BT 동시 산출
      ctx.config_hash = h                         # 비-텐서는 ctx.<attr> (save_for_backward 아님)
      ctx.K = read_K_accessors(out)               # dict{'T','Q','HYDRO6','HYDRO7',...,'HYDRO_DEFF6/7'}
                                                  #   → numpy [nprofiles,nchannels,nlayers] (§9.1)
      return torch.as_tensor(out.Bt, dtype=T_lay.dtype, device=T_lay.device)  # _bRad['bt']
      # ↑ custom Function이므로 out.Bt가 numpy/grad-less여도 backward가 grad를 공급(별도 runDirect 불필요)
  backward(ctx, lambda_BT):
      # ctx.K 는 pyrttov numpy 배열 → torch로 올려야 einsum 가능(numpy×torch 혼합은 런타임 에러).
      Kt = {k: torch.as_tensor(v, dtype=lambda_BT.dtype, device=lambda_BT.device)
            for k, v in ctx.K.items()}
      # 채널축 contraction (K는 ∂BT/∂(apply 입력 = RTTOV-unit var)이므로 grad는 같은 단위계):
      #   grad_T_lay = einsum('pcl,pc->pl', Kt['T'],          lambda_BT)
      #   grad_Q_lay = einsum('pcl,pc->pl', Kt['Q'],          lambda_BT)  # getItemK(gas)
      #   grad_clw   = einsum('pcl,pc->pl', Kt['HYDRO6'],     lambda_BT)  # 액체운 content(CLWD)
      #   grad_ciw   = einsum('pcl,pc->pl', Kt['HYDRO7'],     lambda_BT)  # 빙운 content(BAUM)
      #   grad_deff_liq = einsum('pcl,pc->pl', Kt['HYDRO_DEFF6'], lambda_BT)  # 입자크기(同N pairing 6↔6)
      #   grad_deff_ice = einsum('pcl,pc->pl', Kt['HYDRO_DEFF7'], lambda_BT)  # 7↔7 (content슬롯 N == Deff슬롯 N, §9.1)
      # forward 입력 순서와 정확히 같은 arity의 grad 튜플 반환(차등불가 입력은 None).
      return (grad_T_lay, grad_Q_lay, *grads_in_input_order)

BT_hat = RttovObsOp.apply(*rttov_tensors)          # 비-torch RTTOV가 그래프 진입
# 이제 grad 경로: J → BT_hat → [RttovObsOp.backward: K^T·λ_BT] → rttov_tensors
#                → [0)의 순수-torch 변환(Wᵀ·단위 Jacobian)] → leaves. 완전히 닫힘.
```

**§14.3-units — 변환을 apply 이전 torch에 두는 이유.** apply 입력이 RTTOV-unit이면 `K=∂BT/∂(입력)`
이므로 backward의 grad가 곧 그 입력의 cotangent다. 변환을 forward 안(numpy)에서 하면 K는
RTTOV-unit 미분인데 grad를 model-unit 입력에 귀속시켜 **변환 Jacobian(∂Q/∂qv, Wᵀ 등)이 누락**되고,
애초에 leaves→apply 경로가 numpy로 끊긴다. 보간은 per-profile 1회 계산한 **상수 torch 행렬 W**
(`prof = W @ col`)로, 단위변환은 torch 연산(∂Q/∂qv 해석식 포함)으로 둔다.

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
    rttov_tensors = model_to_rttov_tensors(leaves, forcing, cfg, xland, ncmin_*)  # 전부 순수-torch
    BT_hat = RttovObsOp.apply(*rttov_tensors)        # 비-torch RTTOV가 그래프 진입(단위변환 없음)
    J      = compute_obs_loss(BT_hat, obs, masks, sigma)   # scalar (λ_BT는 autograd 생성)
    grads  = torch.autograd.grad(J, tuple(leaves), allow_unused=True)  # None 허용(materialize 금지)
    return assemble_obs_covector(leaves, grads)      # declared-zero만 0, 필수 None은 raise(§10)
```

- `RttovObsOp.backward`(runK ⊗ λ_BT)와 하류 `rttov_cloud_profile`(순수 torch)이 이 LOCAL
  `autograd.grad` 안에서 **자동 합성**된다. §9.1의 F1-SHAPE 이음매는 `RttovObsOp.backward`의
  `unpack(lam_profile)` 한 지점에 국소화된다(autograd 경계 = process 경계 = backend 한 곳).
- window가 `obs_adj[t]`(=이 반환 covector)를 미세물리 adjoint에 **더하는** 것이지, obs operator가
  `Handle.vjp`를 호출하는 게 아니다. 두 adjoint(관측·역학)는 `da_window` backward에서 합산된다.

### 14.4 building blocks 재사용 = reference copy (정책 갱신 2026-06-13)
humidity 단위변환·RTTOV pressure-grid 유도·`kdm6ad_rttov_mapping`·`rttov_ascii` 등 AD-RTTOV의
검증된 building block은 **`kdm6_torch/kdm6/obs/_rttov_reference/`에 verbatim reference 복사**한다
(provenance 마커; upstream=AD-RTTOV canonical, 재동기 가능; 코드 디렉토리 분리 §14.1 유지).
- **단, 이들은 scalar-float API**라 torch 경로에 직접 못 쓴다(§14.3-units: 단위변환·보간은
  apply 이전 torch여야 grad 전파). 따라서 **단위변환(∂Q/∂qv 해석식)·보간(W 상수행렬)은 reference
  공식·상수를 보고 `model_profile_builder.py`에 torch로 재구현**한다 — reference를 호출하면 grad 끊김.
- **매핑 테이블·ascii 파서**는 데이터/파싱(미분 경로 아님)이라 그대로 import/사용 가능. 단 매핑의
  hydrometeor 행은 VIS/IR 슬롯 규약(§9.1)으로 재해석(원본 `*_candidate`는 clear-sky baseline 표기).
- (이전 "import-not-copy"에서 갱신: scalar→torch 재구현이 어차피 필요하므로 reference 복사가
  실용적이고, AD-RTTOV 원본은 보존·재동기 가능.)
- **RTTOV 바이너리/coef/atlas는 복사 금지** — AD-RTTOV에 고정, `AD_RTTOV_HOME`으로 참조(§14.1).

### 14.5 통합 precondition (구현 P4 이전; 적대적 검토 2026-06-13 반영)
- `AD_RTTOV_HOME` 설정 + RTTOV 14.1 build·coefficient(ami/501)·atlas 존재 확인.
- out-of-process RTTOV가 부모 OMP fence를 상속하는지 smoke로 검증(libtorch 동거 크래시 클래스).
- **BT-K 강제**: `adk_bt=True` (thermal K seed를 BT 공간으로) + `store_rad=True` (pyrttov `Bt` 노출).
  미설정 시 TK/GasesK는 radiance-K라 BT-residual loss와 불일치 → fail-closed. config-hash에 포함.
- **입력 단위/슬롯 계약**: `Profiles.GasUnits = 2(ppmv_wet)` (pyrttov 기본 1=kg/kg),
  `Profiles.MmrHydro = False` (bridge content는 g/m³; 기본 True=kg/kg). qv_convention 게이트와
  동급으로 "명시 또는 실패".
- **user-Deff 모드 강제 (number-moment 경로 생존 조건)**: reff_*→Deff(×2)를 `setHydroDeffN(.,6/.,7)`로
  **positive EXPLICIT 입력**(gate=`hydro_deff>0`; `ClwdeParam/IcedeParam`엔 'user' enum 없음 — 정수
  기본값 유지). positive Deff 미입력(내부 파라미터화)이면 λ_nc=λ_ni≡0 → M5에서 hard-fail.
- **AMI hydrotable 부재(blocking, §13)**: all-sky AMI cloud-K는 matching `rttov_hydrotable_gkompsat2_1_ami*`
  필요. 현재 `AD_RTTOV_HOME`에 없음 — IASI substitute donor(VISIR, 실행은 되나 AMI-science-valid 아님,
  hot.md)만 존재. 이 자산 확보 전엔 all-sky cloud-K는 검증 불가.
- pyrttov runK 출력은 결합 GasesK + item-id view(§9.1) — `RttovCloudProfile` 필드별 1:1 배열이 아니므로
  라우팅 테이블로 계약 검증(M5/M6).

---

## 부록 A. 교차참조 지도

| 본 문서 절 | 근거 (kdm6ad+da.md) | 코드 |
|---|---|---|
| §2 시간정합 | §8.4 checkpoint/recompute | `da_window.py` |
| §6 bridge | §9.3 DSD bridge VJP | `rttov_bridge.py` |
| §8 loss | §4 GK2A-RTTOV loss, §9.1 | (구현 예정 `obs_loss.py`) |
| §9 adjoint 체인 | §9.1–9.4 | `RttovObsOp`(K^T·λ_BT) + `rttov_bridge.py` VJP (Handle.vjp 아님) |
| §10 callback | §8.4 backward skeleton | `da_window.py` obs_adjoint(covector 반환); 역학 VJP만 `runtime.py` Handle.vjp |
| controls | §5 state/process/partition controls | `process_controls.py`, `da_window.py` |

관련 AD-RTTOV/wiki(upstream, 읽기 전용): `concepts/ad-rttov-reference-observation-operator`,
`concepts/rttov-profiles-k-bt-sensitivity-contract`,
`procedures/kdm6ad-to-rttov14-ami501-tq-jacobian-workflow`,
`decisions/use-rttov-14-1-as-initial-baseline`.
