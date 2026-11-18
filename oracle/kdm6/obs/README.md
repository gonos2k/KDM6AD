# `kdm6/obs/` — 모델면 RTTOV 관측연산자

현재 기능과 검증 상태는 [기능표](../../../docs/STATUS.md#observation-operator-rttov)에 기록한다.
저장된 native 검증에는 실제 RTTOV-K와 독립 BT·비용 중앙차분을 사용한
clear-sky 및 선택 all-sky 사례가 있다. 실행 입력·바이너리와 검증한
방향·분기는 [native 관측 검증](../../../docs/NATIVE_OBSERVATION_AD.md)에 기록한다.

Historical design reference: `KDM6AD/model-side-rttov-observation-operator.md`
(external design file, not shipped in the public repository).
관측 valid time의 완료 모델 상태(checkpoint 경계)에서 RTTOV direct/K를 **out-of-process**로 수행하고,
profile adjoint를 KDM6AD-consistent bridge VJP(`../rttov_bridge.py`)로 state adjoint로 변환해
`../da_window.py`의 `obs_adj[t]`로 주입한다.

## 모듈 (설계 §10)
| 모듈 | 역할 | 검증 | 단계 |
|---|---|---|---|
| `model_rttov_scheduler.py` | obs↔step-end 정합, off-step 거부 | M1 | P1 |
| `model_profile_builder.py` | leaves→RTTOV-unit **torch** 텐서(§14.3-units) | M2 | P2 |
| (bridge 재사용) `../rttov_bridge.py` | DSD/optical → RttovCloudProfile | M3 | P3(기구현) |
| `rttov_input_builder.py` | torch→numpy RttovInput 직렬화 | M4 | P4 |
| `rttov_runner.py` | out-of-process runK(BT+K 동시) | M4/M5 | P4/P5 |
| `obs_loss.py` | BT residual·Huber → scalar J_obs | — | — |
| `rttov_obs_operator.py` | `RttovObsOp` + `obs_adjoint_callback` + `assemble_obs_covector` | M5/M6 | P6 |

`_rttov_reference/` — AD-RTTOV building block의 verbatim 복사(공식·상수·매핑 reference). scalar라
torch 경로엔 직접 못 씀 — README 참조.

## 외부 의존 (AD_RTTOV_HOME)
- 기본 `AD_RTTOV_HOME = /Users/yhlee/AD-RTTOV` (코드 디렉토리 분리 — RTTOV 바이너리는 여기 고정, §14.1).
- coef: `external/rttov14/src/rtcoef_rttov14/rttov13pred54L/rtcoef_gkompsat2_1_ami_o3co2.dat`
  (**coef predictor 54 levels** — RTTOV 내부 보간 grid, user profile grid 아님).
- user profile grid은 **별개**이며 입력 데이터가 결정: RTTOV-14 AMI는 layer-based라 ami/501 fixture는
  nlayers=69(p/t/q.txt)·nlevels=70(p_half.txt), GFS-collocated는 nlevels=70. profile_builder가
  fixture/coef에서 **derive**(hard-code 금지).
- runner: pyrttov(`rttov_wrapper_f2py.so`, runDirect/runK) 또는 subprocess `run.sh` fixture.

## 구현된 구름 매핑과 실행 조건

- clear-sky는 온도·수증기 프로파일과 RTTOV-K를 비용함수의 1차 미분에 연결한다.
- 선택 all-sky VIS/IR 경로는 QC를 액체, QI+QS를 얼음에 매핑하고,
  NC·NI와 밀도로 유효직경을 계산한다. CFRAC은 이진 gate이며,
  QR·QG의 독립 광학 슬롯은 현재 매핑에 없다.
- 실제 실행에는 선택한 설정에 맞는 외부 RTTOV, 계수와 구름 광학 자료가
  필요하다. 검증 범위는 해당 실행에서 고정한 자료, 채널과 분기에 한정된다.

## Explicit KMA BT research coordinate

`make_live_run_k(case_dir, fixture_case_dir=fixture, ami_kma_bt=True)` returns
model BT and every K row in the paired KMA v3.0 coordinate for thermal AMI channels
8–16. It uses TOTAL radiance from the same K run and the coefficient file actually
consumed by that case. `RttovObsOp` then contracts the converted K against the
cost's KMA-coordinate cotangent. The default native RTTOV/solar path is unchanged.

Use source-paired KMA observations and declare bias/error scales in that same
coordinate. This mode requires positive finite TOTAL radiance in every row,
including flagged rows; zero/nonpositive placeholders are explicitly unsupported.
It preserves quality flags and rejects solar channels. Cached external K supplies
first-order derivatives only. The [retained live cost check](../../../harness/evidence/REPORT_live_KMA_cost_2026-10-04.md)
validates one NC direction with a diagnostic 1 K scale; it does not approve the
error model, SRF compatibility or a complete DAWindow trajectory.
