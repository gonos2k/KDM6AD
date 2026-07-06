# DA_REALTIME_PLAN — RTTOV 조인트 자료동화+민감도, 실시간 지향 계획

결정일: 2026-07-05. 근거: 코드베이스 4-축 준비도 감사 + 스케일링 프로브 + 4-검토자 정밀
검토(전 항목 실측 재검증, live RTTOV 측정 포함). 이 문서는 그 결정을 고정한다.

## 0. 목표와 제약

- **목표**: KDM6AD fp64 DA 경로의 JVP/VJP/HVP(연산그래프 재사용)로 고전 DA의 추가 연산
  (수작업 TLM/adjoint, 유한차분 Hessian)을 대체하는 **효율 동화+민감도 체계**. 동화창 **3시간
  고정**(dt=300s → 36스텝), 실시간 운영 지향.
- **불변 제약**: 37↔137 f32 bitwise parity 최우선 — `libtorch/src`·`bridge`·`include`(dylib)는
  코드 동결. 본 계획의 모든 작업은 oracle/harness/driver 계층에서만 수행한다.
- **Phase-1은 오프라인**(offline-only) — 호스트(wrftladj) qnn adjoint stale 이슈는 온라인
  host-4DVAR에만 해당하며 본 계획 범위 밖(BUGREPORT 참조).
- **환경 결합**: live RTTOV는 이 머신의 `AD_RTTOV_HOME=/Users/yhlee/AD-RTTOV` 트리에 의존
  (exe + ami coef/hydrotable + ami/501·cloud 픽스처). 타 머신에선 live tier가 skip됨.

## 1. 실측 기반 (이 수치들이 모든 설계 결정의 근거)

측정 조건: 이 머신(64GB), kme=40, dt=300, 단일스레드(브리지 `at::set_num_threads(1)` 강제).

### 마이크로피직스 fp64 AD 경로 (`kdm6_step_ad_c`)
- 클린 단가: **fwd ≈ 0.46 s / vjp ≈ 0.48 s / jvp ≈ 1.05 s per 1k 컬럼** (B=2048–8192 선형).
- 그래프 기록 오버헤드 **+17–24%** (B≥512). 반복 VJP = 0.95×첫 VJP (retained-graph 재적용 성립).
- JVP = **2.1–2.3× VJP** (Pearlmutter double-VJP). covector 희소성은 backward 비용에 무영향.
- **대류 마진 2–3×**: 프로브 IC는 mstep=1(바닥). 현실적 stretched-grid 대류 컬럼은 mstep 11–18
  → fwd 2.0× / vjp 2.9× / jvp 3.3×. **mstep은 batch-global** — 무거운 컬럼 1개가 샤드 전체를
  재가격(1/512 heavy ≈ 512/512 heavy 실측).
- 메모리 벽 없음(B=8192에서 RSS ~15GB/64GB, swap 0). 샤드 상한 2048–4096의 근거는 메모리가
  아니라 **지연 granularity + JVP-피크 RSS(~7GB/proc @2048) + mstep 클러스터링 효율**.

### 3h 창 adjoint (run_da_window, checkpoint/recompute)
- 창 gradient 비용 = **36×fwd(체크포인트) + 36×(재계산 fwd+graph + vjp)** + n_obs×RTTOV-K.
  (체크포인트 forward 스윕 포함 — 누락 시 30–40% 과소평가.)
- **여러 obs 시각(≤18슬롯)의 covector는 한 번의 adjoint 스윕에 합성** — 모델 스윕에 n_obs
  배수 없음 (bitwise 게이트 테스트 확인).
- retained-graph CG 상각: 36그래프 유지 ≈ 8.3GB(B=128)/17.8GB(B=512), **B=2048은 불가**
  (56–133GB). 상각은 B≤512에서만; B=2048은 recompute-per-sweep.
- η(weak-constraint) gradient는 같은 스윕의 부산물(무비용)이나 제어차원 ~37× — Phase-1은
  strong-constraint(η=None).

### RTTOV H-연산자 (live 실측)
- clear-sky 16ch full-K: **20 ms/프로파일**(한계), 케이스 고정비 76 ms. **all-sky: 483 ms/프로파일
  (clear의 25×)** — all-sky의 지배 레버는 배치가 아니라 **thinning과 모드 선택**.
- 배치 레버 ~3–5×(clear), 샤딩 3.5–6.8× — 합쳐 ~10× (100× 아님).
- 배치 캡 = 픽스처 프로파일 디렉토리 수(기본 6; 템플릿 복제로 ≤999 확장 가능 — 실증됨).

### 사이클 예산 (3h 창, 대류 마진 포함)
| 모드 | 조건 | 사이클 시간 |
|------|------|------------|
| 민감도 전용 | B=2048, clear ~3k obs | **~4–10분 (오늘 가능, 비샤딩)** |
| 조인트 GN DA (recompute) | B=2048, 2×5 GN | 40–60분급 |
| 조인트 GN DA (10분 목표) | B≤512 + 내부≤5 + retained 상각 | ~10–13분 |

## 2. 티어 구조 (승인된 롤아웃)

- **Tier 0 — 민감도-전용 실시간 사이클** (즉시 착수): frame reader + live FD anchor +
  mstep-aware 샤드 구성. 산출물 = `WindowResult(adj_x0, grad_eta*)` 민감도 리포트.
  clear-sky ~3k obs에서 10분 사이클 내 동작이 수락 기준.
- **Tier 1 — 조인트 DA 30–60분급**: + minimizer(diagonal-B CVT + L-BFGS strong_wolfe,
  strong-constraint) + RTTOV 배치화(3-사이트).
- **Tier 2 — 조인트 DA 10분급**: + 창-선형화 API(36 핸들 유지 + 반복 vjp, B≤512 샤드).

## 3. 작업 항목 (정밀 검토로 재스코핑된 정의)

### T0-1. wrfout frame → State/Forcing reader (`oracle/kdm6/io/`)
단순 필드맵이 아님 — **조용히-틀리는 파생 4종**이 본체:
1. **THM→th 역변환**: wrfout `T`는 use_theta_m=1(기본)일 때 moist perturbation theta
   (θm = θ(1+Rv/Rd·qv)) — θ로 역변환 후 +T0(300). 생략 시 습윤층에서 th ~1% 오차.
2. **rho 재구성**: `ALT`는 restart 전용 → full pressure/EOS로 재구성
   (호스트 phy_prep의 rho=(1+qv)/alt 관례를 미러).
3. **PH/PHB→dz8w**: geopotential 수직 destagger로 delz 산출.
4. **t=0 nccn 폴백**: 첫 프레임에서 wrapper의 ITIMESTEP==1 초기화 미러.
필드 존재 확인됨: QNCCN/QNCLOUD/QNICE/QNRAIN/**QIB(=bg)** 전부 kdm6adscheme 히스토리 필드 —
결측·스핀업 불필요. 검증: 커밋된 1-컬럼 픽스처 + 파생 4종 각각의 단위 테스트.

### T0-2. live FD anchor (1개 테스트, `@needs_cloud_live`)
단일 레이어 T(및 qc) 섭동 → live RTTOV forward 2회 추가 → 중앙 FD vs K-수축 covector 성분,
느슨한(수 %) 허용오차. **K 단위 오해석(ppmv vs kg/kg, per-μm)이 현 테스트를 전부 통과하는
유일한 무방비 silent-wrong-gradient 클래스**를 닫는다.

### T0-3. mstep-aware 샤드 구성 (driver 유틸)
no-grad vmax 프리패스로 컬럼별 mstep 예측 → 유사 mstep끼리 샤드 묶기. batch-global
재가격 방지로 코드 무변경 2–3× 회수. 가드 2종을 드라이버 스펙에 명시: 샤드별
`default_run_k`(per-call mkdtemp, 공유 `make_live_run_k` 금지), `KDM6_SUBSTEP_DUMP` unset.

### T1-4. minimizer (driver)
strong-constraint(η=None) + **CVT v=B^{-1/2}(x0−xb)** (상태 ~10자릿수 스팬 → raw L-BFGS
악조건) + `torch.optim.LBFGS(strong_wolfe)`, `.grad`는 run_da_window의 adj_x0 수동 할당.

### T1-5. RTTOV 배치화 (3-사이트)
(a) case-writer: 프로파일 디렉토리 복제 + 6-cap 해제(≤999); (b) model_profile_builder:
1-D p 가드 완화 + 공유 fixture layer grid로 전 컬럼 보간(실용 단순화); (c) runner 경로 검증.

### T2-6. 창-선형화 API (oracle/da_window 확장, 물리 무변경)
36 per-step 핸들 유지 + CG 반복마다 반복 vjp 재적용. B≤512 전용(메모리). run_da_window는
현재 핸들을 즉시 닫으므로 API-레벨 확장.

## 4. 이후 결정 항목 (본 계획 범위 밖, 명시적 보류)

- 스레드 fence 해제(`at::set_num_threads(1)` — frozen bridge): 샤딩으로 부족할 때만.
  dylib 변경 + 12h×np4 재검증 사안.
- C-핸들 창 체인 + cross-tree adjoint parity 테스트: 운영 물리(C++) 전환 게이트.
- G4 파라미터 gradient(oracle 측만): 파라미터 민감도 필요 시.
- 실관측(GK2A AMI L1B) 인제스트 + collocation: OSSE 이후.
- HVP-obs: 현 GN-only(K 상수 취급)가 표준 — full-Newton 필요 시 FD-of-K.

## 5. 실주행 기록 (2026-07-05, 이 머신 — 동시부하 오염 캐비앳)

Tier 0+1 조립 직후 실프레임(SS wrfout t=1) + live RTTOV-14로 실측:

- **민감도 사이클** (B=128, 3h 창 36스텝, 관측 {12,24,36}): J=83.78, ∂J/∂x₀가
  섭동 위치(하층 th)에 정확히 국소화. **벽시계 60.1 s** (진실 창 생성 포함;
  실사이클은 ~절반) — 10분 실시간 예산의 1/10.
- **조인트 DA 분석** (동일 구성 + CVT+L-BFGS max_iter=5): J 83.78→48.88 (-42%),
  J_b=20.3/J_obs=28.6 분할, 창 적분 6회. **배경 th 오차 -28.1%** (17.89→12.87,
  진실 대비, BT 관측만으로). **벽시계 234 s (~4분)** — 창적분당 ~39 s.
- 검증 게이트(모두 통과): zero-innovation 자기일관성(J=0, adj=0 정확히),
  양측 QC mask(진실측 플래그 y 배제), live FD anchors, 분석의 J·오차 동시 감소.
- 실주행이 드러낸 이슈 2건(§3 T0-1과 별개, 둘 다 실측 해결): 모델 상단(60 hPa)
  위 기준 프로파일 필요(클램프 연장은 RTTOV reg-limits 전 채널 플래그);
  이상화 SS 수분 바닥(41 ppmv)로 Q 블렌드 4옥타브 필요(스윕 실측; 실관측
  프레임에선 축소 가능 예상).
- **샤딩 스케일링 실증** (da_parallel, 2026-07-06): **1024 컬럼**(8 mstep-샤드×128,
  8 spawn workers) × 3h 창 민감도 = **92.5 s** — 단일 샤드(60.1 s)의 1.54×로 8×
  컬럼 처리(병렬 효율 ~65%, 동시부하 하). shard별 J 83.65–83.81(균질 케이스 정합,
  단일-샤드 재현 ✓), ‖adj_th‖=30.98 ≈ √8×단일샤드(10.96) ✓, 민감도 국소화 k=2
  유지 ✓. **10분 실시간 티어가 샤딩만으로 달성됨을 실측 확인.** 병렬≡순차
  bitwise 게이트는 test_da_parallel이 보증. (주의: 스크립트 소비자는
  `if __name__ == "__main__"` 가드 필수 — spawn이 메인 모듈을 재실행.)
- **cross-tree adjoint parity 실측** (§4 게이트 착수, 2026-07-06): C++ fp64
  `kdm6_step_ad_c` vs 오라클 Handle, 동일 IC/covector — smooth 점(dt=20)에서
  VJP/JVP 전 성분 **~5e-8 일치** (< 1e-6 게이트). 다중 subcycle(dt=300)에선
  미분-레벨 kink 발산 존재: forward 출력은 zero-패턴까지 일치하나 내부 게이트
  분기 선택이 트리별로 갈려 cell0의 소수 성분이 발산(VJP {ni,bg}, JVP
  {qc,qr,nc,nr}+knock-on {th,qv}) — 발자국을 회귀 스냅샷으로 고정
  (test_cross_tree_adjoint_parity). **DA 소비 규칙 확정: 사이클은 한 트리로
  자기일관되게(증분 계산·적용 동일 트리); 트리 교차는 smooth 성분에서만.**
- **G4 파라미터 gradient 배선** (§4 항목 완료, 2026-07-06, oracle 측만 — frozen
  dylib 무접촉): warm-phase 파라미터(PEAUT/NCRK1/NCRK2/ECCBRK)가 live(grad 켜짐
  또는 값 변경)면 phase-param builder로 흘러 ∂J/∂θ가 나온다. qck1의 REAL(4)
  f32-stepwise 유도는 텐서-안전 캐스트(_f32t, IEEE 동일 라운딩)로 미분 관통 —
  frozen 기본 경로는 byte-불변. Handle.param_grad/param_vjp +
  WindowConfig.param_grads(창 누적 Σ_t ∂⟨M,λ⟩/∂θ). FD 대조: 단일스텝 rel
  6.2e-4·창 7.3e-5 — 잔차는 f32-계단(ULP/h) 물리 바닥과 정확 일치. **파라미터
  민감도(4D-Var 보정)의 oracle-측 blocker 해소.**
