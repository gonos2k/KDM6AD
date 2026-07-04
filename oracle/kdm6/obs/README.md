# `kdm6/obs/` — 모델면 RTTOV 관측연산자 (scaffold)

설계: [`KDM6AD/model-side-rttov-observation-operator.md`](../../../model-side-rttov-observation-operator.md).
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

## 성숙도 / 구현 우선순위
- **즉시 가능(clear-sky T/Q)**: ami/501 O3+CO2 coef(predictor 54L) + pyrttov/run.sh 완비. t→T, qv→Q는
  매핑테이블상 `clear_sky_baseline_compatible`. → P1·P2·P4·P5(T/Q)·P6 먼저.
- **차단(all-sky cloud/hydrometeor)**: matching `rttov_hydrotable_gkompsat2_1_ami*` **부재**(IASI donor만).
  cloud 경로(reff→Deff, HYDRO 슬롯, user-Deff)는 hydrotable 확보 전 설계 단계 stub. AMI hydrotable이
  **최종목적(all-sky 16채널)의 결정적 blocker**다(설계 §1.7/§13/§14.5).

전부 stub(NotImplementedError) — 구현은 위 우선순위로.
