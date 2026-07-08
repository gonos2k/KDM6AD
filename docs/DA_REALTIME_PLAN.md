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
- **실관측 인제스트 코어** (§4 마지막 항목의 검증가능 부분, 2026-07-06):
  `obs_ingest.py` — ObsPayload 스키마 공식화(기존 암묵 규약 명문화), haversine
  collocation(관측→최근접 컬럼, grid-agnostic — 이상화 케이스의 all-0
  XLAT/XLONG은 퇴화 그리드로 loud 거부), payload→(B,nch) 컬럼 정렬. 통합 규약:
  **미배정 컬럼 = obs_quality=1** → 기존 양측-QC mask가 자동 배제(driver 무변경
  소비, 통합 테스트로 확인). 충돌은 최근접 승자+카운트, far-gate 집계. **GK2A
  AMI L1B 파일 디코더는 이 스키마를 만드는 어댑터로 유보** — 실데이터 없이 쓴
  디코더는 검증 불가(인터페이스만 고정, 데이터 확보 시 구현).

## 6. 실관측 실험 케이스 (확정, 2026-07-06)

**실험 사례 = bitwise 캠페인과 동일 케이스** (KLFS LC05 실사례) — 37↔137 f32
bitwise가 12h×np4로 검증된 바로 그 구간에서 실관측 DA를 수행한다 (parity 검증
구간과 실험 구간의 일치 = 운영 물리 신뢰 구간 안에서의 실험).

- **모델 수행 구간**: `klfs_lc05_fcst.202507190000` — **2025-07-19 00:00 ~ 12:00
  UTC** (12h 적분; 캠페인 기록 kdm6ad-10step-bitwise-achieved-2026-07-02).
- **필요 GK2A AMI L1B (UTC)**:
  - 전 구간 커버(권장 — 창 위치 자유): **2025-07-19 00:00–12:00 UTC, 10분 간격
    (73슬롯)**, FD 또는 한반도 영역.
  - 최소(T₀=00 UTC, 3h 창, 실증 3-슬롯 구성): 01:00 / 02:00 / 03:00 UTC.
  - 채널: AMI IR 16채널 세트 (현 obs operator 구성; clear-sky 1차).
- **데이터 확보 후 파이프라인** (순서):
  1. L1B → ObsPayload 어댑터 작성·검증 (스키마는 obs_ingest로 고정됨).
  2. 케이스 wrfout의 실그리드 XLAT/XLONG으로 collocation 실검증
     (이상화-케이스 퇴화 가드 통과 확인).
  3. 실관측 innovation 민감도 사이클 (Tier-0 경로) → 조인트 DA 분석 (Tier-1).
- 주의: 캠페인 당시 `wrfinput_d01`은 이후 b_wave 작업으로 덮임 — 실험 재수행
  시 LC05 입력(wrfinput/wrfbdy/wrfchainp) 복원 필요. `wrfinput_d01.37`의
  2007-06-01은 별개의 이전 사례 사본(본 실험과 무관).

### 6.1 GK2A 입력자료 조달 목록 (확정)

파일명 규격: `gk2a_ami_le1b_<채널>_<영역해상도>_<YYYYMMDDhhmm>.nc` (NMSC).
영역 **KO(한반도, LC 투영) 권장** — KLFS LC05 도메인 부합, FD 대비 소용량.

- **시각 슬롯 (UTC)**: 2025-07-19 00:00 ~ 12:00, 10분 간격 = **73슬롯**
  (`202507190000` … `202507191200`).
- **clear-sky 1차 최소셋 — IR/SWIR 10채널** (obs operator 채널 7–16):
  `sw038 wv063 wv069 wv073 ir087 ir096 ir105 ir112 ir123 ir133`
  → 730 파일 (~수 GB, KO).
- **solar 확장 +6채널** (REFL-K 경로는 live 검증 완료 — 확보 권장):
  `vi004 vi005 vi006 vi008 nr013 nr016` → 전체 1,168 파일 (~10 GB급).
- **축소 시작 옵션**: IR 10ch × 3슬롯(01/02/03 UTC) = 30 파일 (~수백 MB).
- **보조자료 (권장)**: L2 구름탐지 `gk2a_ami_le2_cld_ko020lc_<시각>.nc` × 73 —
  clear-sky 관측 선별·obs_quality 플래그 소스. 지오로케이션 별도 파일 불필요
  (KO/FD 고정격자 — L1B 투영 메타데이터로 위경도 산출), DN→BT 계수 L1B 내장.
- **출처**: NMSC 자료서비스(datasvc.nmsc.kma.go.kr) 기간 일괄신청 / Open API.
- **모델측 동시 조달**: LC05 입력 3종 `wrfinput_d01`/`wrfbdy_d01`/
  `wrfchainp_d01` (2025-07-19 00 UTC) 복원 — 위성자료와 함께 실험의 전제.

### 6.2 파이프라인 진행 (2026-07-06)

- **① L1B→ObsPayload 어댑터: 완료** (`obs/gk2a_l1b.py` + 실데이터 검증).
  실배송 KO 세트(00·01 UTC, 2분 주기, 00시는 16채널 완비 480파일)에서 확인된
  사실: **KO 재격자 산출물엔 검정계수가 없음**(ela020ge 재격자 시 탈락) → 같은
  날짜 FD 원본(noaa-gk2a-pds S3)에서 채널별 계수를 추출해
  `obs/data/gk2a_ami_cal_202507190000.json`으로 동결(provenance 포함).
  검증: LCC 지오로케이션 pyproj 교차 |Δ|max 6e-14° + 원점 (38,126) 불변식;
  IR105 BT 204.7–300.7K/평균 272.9K (7월 한반도 물리 정합); DN→BT는 AD-RTTOV
  검증 로직 1:1 이식 + 손계산 게이트. 주의: SW038 주간 태양혼입(376K) —
  3.8μm 주간 사용은 제외/특별처리 대상.
- 다음: ② 실사례 wrfout(실그리드) 확보 시 collocation 실검증 → ③ 실관측
  innovation 사이클. (모델측 LC05 입력 복원이 병목 — §6 주의사항.)
- **②③ 실그리드 collocation + 첫 실관측 innovation 완료** (2026-07-07): LC05
  입력 3종을 `KDM6AD+/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS/`에서
  발견 (wrfinput = 2025-07-19 00 UTC, 234×282×39 실지리, USE_THETA_M=1;
  wrfbdy/wrfchainp 동반; KDM6AD+ observations/gk2a에 00–03 UTC FD 원본 4.4GB도
  확보돼 있음). wrfinput 자체가 t=0 상태 → 모델 재실행 없이 진행:
  - collocation 실검증: 50,625 관측(8km 솎음) → 26,019 컬럼 배정(39%), 충돌 0.
    실규모 첫 접촉이 26GB OOM 결함(전체 거리행렬)을 노출 → 청크 처리로 수정.
  - **첫 실관측 O-B** (B=256 층화, clear-sky H): 맑음-추정 표본에서 window 채널
    **ir112 −0.04K/1.19K, ir123 +0.05K/1.16K** (mean/std) — 검정→변환→지오로케이션
    →collocation→상태유도→RTTOV 7단 체인의 계통오차 부재 증명. 전체 표본의 큰
    음의 O-B(−20K대)는 구름 시그니처(clear-sky H의 구조적 한계 — all-sky가 다음).
  - **첫 실관측 adjoint**: J=5.19e5(σ=1K), ∂J/∂th 최대 감도 k=10 (~792hPa —
    IR window 가중함수의 교과서적 위치). 29초/256컬럼.
  - 게이트: test_real_innovation_lc05.py (외부자산 4종 skipif; 로컬 실검증용).
  남은 것: 창 진화 실험(00→01 UTC 관측 동화)은 LC05 3h 재적분(run_hours=3)
  필요 — 모델 실행은 사용자 결정 사항.
- **④ 첫 실관측 창-DA 분석 사이클 완료** (2026-07-07) — 계획의 최종 목표 달성:
  - LC05 3h 재적분: 격리 실행 디렉토리(host/lc05_da_run, 심링크 팜 — 캠페인
    bitwise 산출물 무손상), 5분 히스토리 37프레임. **1차 시도는 KDM6AD+의 6/24
    구식-dylib 바이너리가 sim 00:25에서 "kdm6ad: NaN after copy-back"으로 붕괴
    → 현행 frozen dylib(§53 수정 포함, 7/4 빌드)로 교체 후 같은 지점 통과** —
    §53 시리즈의 독립적 실사례 안정성 검증.
  - 창 00→01 UTC (T=12×dt300, forcing=5분 실궤적 프레임), 실 GK2A KO 관측
    t=0(10ch)+t=12(9ch; 01시 ir133 전결측은 quality 마스킹으로 자동 처리),
    구름-QC(양 슬롯 IR105≥285K; clear-sky H 유효범위), CVT(th 0.8K/qv 8%,
    하층 12레벨)+L-BFGS 5회, B=128 층화.
  - **결과: J 11676.9 → 10972.5 (단조 6.0% 감소, 213s)**; 증분 max|δth|=2.6K,
    최대 레벨 k=9(~800hPa) — t=0 adjoint 감도 피크(k=10)와 독립 일치(관측
    정보가 IR window 가중함수 고도에 정확히 주입됨). OSSE(−42%) 대비 작은
    감소는 실관측의 줄일 수 없는 잔차(대표성·바이어스·clear-sky 한계) 위의
    정직한 개선.
  - 인프라 실측 메모: WRF netCDF-4 히스토리는 writer 보유 중 직접 판독 불가
    (HDF error) — 사본 스냅샷은 프레임 경계에서 유효(13프레임 판독 성공).
  - **3h 재적분 SUCCESS COMPLETE** (2026-07-07): 37프레임(00:00→03:00 UTC, 5분
    간격) 완비 — 현행 frozen dylib의 실사례 3h 무결 완주(구식 dylib 25분 붕괴와
    대조). 산출물 host/lc05_da_run/klfs_lc05_fcst.202507190000. 이로써 3h 창
    (T=36) 실험과 FD 02·03 UTC 관측 확장의 모델측 재료 완비.
- **⑤ 3h 창(T=36) 4-슬롯 실관측 DA 완성** (2026-07-07): FD(전구) 어댑터 신규 —
  geos 역변환에서 **업스트림(AD-RTTOV) 잠복 버그 2종 발견·수정**(① cfac/lfac
  counts-per-degree를 라디안 오독 — 부위성점에서만 무증상, ② lfac<0 규약의
  s3 부호 반구 반전 — 적도에서 무증상; 둘 다 대칭점-검증의 맹점). 교차-투영
  게이트: 같은 스캔의 KO(LCC) vs FD(geos) wv063 |ΔBT| 중앙값 **0.114K** —
  두 독립 투영·검정 경로의 부픽셀 상호 증명. 4-슬롯 창 (00 KO·01 KO·02 FD·
  03 FD, 4슬롯 전부-맑음 2,159→층화 128): **J 20897→20084 (단조 3.9%, 358s)**,
  증분 max 0.84K·peak k=10(세 번째 독립 IR-가중함수 일치). 다중 슬롯 제약이
  증분을 온건화(1h 2.6K→0.84K)하는 4D-Var 정합 효과 확인. 3h 구름 이동으로
  전-슬롯 맑음 컬럼 급감(10k→2.2k) — all-sky 확장 가치의 정량 근거.
- **⑥ 첫 실관측 ALL-SKY innovation** (2026-07-07) — kdm6ad+da.md 본류 개통:
  구름 컬럼(관측 IR105<270K, B=24)에서 clear-sky H의 구조 잔차 mean −46.4K가
  all-sky H에서 **−13.6K로 흡수(~70%), 24/24 컬럼 전부 개선**. 남은 잔차는
  모델 x0의 구름 위치/두께 오차 — DA가 줄여야 할 "올바른 잔차". **하이드로
  미티어 실관측 gradient 최초 산출**: ∂J/∂qc~1.2e9·∂J/∂qi~4.8e8·∂J/∂qs~3.6e8
  (KDM6 DSD-일관 브리지: qc→HYDRO6, qi+qs→HYDRO7) — 관측→구름상태 역전파
  경로 실증(창 adjoint와 연결 시 미세물리 과정 제약의 전제). 단일-컬럼 all-sky
  루프 558ms/col(§1 실측 483ms 정합; 배치-cloud 보류는 레버 ~1.3× 실측 근거
  유지). 구현 규약: batched_clear_bt와 동일 K-flip/Pa→hPa + 모델탑 blend
  (t 1.0/q 4.0 octaves) + 탑상부 응결수 0-마스크. 게이트:
  test_real_allsky_beats_clear_on_cloudy_columns (다수결 개선 + ∂J/∂qi≠0).
- **⑦ 첫 실관측 ALL-SKY 4D-Var** (2026-07-07) — 설계문서 목표 1의 실증: 창
  00→01 UTC, 양-슬롯 구름 컬럼 B=24, all-sky H + **구름상태 제어**(CVT σ:
  qc/qi/qs 상대 30% — q=0 레벨 자동 σ=0, cross-tree kink 소비 규칙 정합).
  **J 103850→78289 (24.6% 감소, 231s)** — clear-sky 창(6.0%)의 4배: 구름
  잔차는 줄일 수 있는 모델 오차이기 때문. 증분 배분이 물리적으로 옳음:
  qs +35.7%·qc +9.9% (구름장이 주 조정), th +0.03% (온도 거의 무변화) —
  관측→구름장 정보 경로의 실측 증명. 이로써 "hydrometeor 분포의 능동 동화"
  (kdm6ad+da.md 목표 1)가 실관측에서 동작.
- **채널 표준 확정 — 깨끗한 IR 9채널** (사용자 지시, 2026-07-07): sw038(3.8μm)
  주간 태양혼입 배제를 관측측 표준으로 명시(`CLEAN_IR_CHANNELS` = WV 3 + IR 6;
  01 UTC 슬롯은 ir133 결측으로 8). 조사 결과 **sw038은 애초에 J에 든 적이
  없음** — RTTOV 모델측 rad_quality가 전 실험에서 이미 플래그, 양측-QC가 자동
  배제 (t=0 O−B 통계에 sw038 행 부재가 증거). 따라서 기존 실측치(①–⑦) 전부
  깨끗한-IR 기준으로 유효하며, clean-IR 재실행의 J 궤적 소수점 일치가 회귀
  증명. 이제 배제가 관측측(payload)에서도 명시적 — 이중 안전장치.
- **⑧ 첫 실관측 미세물리 파라미터 gradient** (2026-07-07) — G4 × all-sky ×
  창 adjoint의 합류: warm-구름 24컬럼 all-sky 창(00→01 UTC)에서 dJ/dθ 산출 —
  **dJ/dPEAUT +620.6 (FD 앵커 +690.3, 동일 부호·자릿수; rel 10%는 FD측 잡음
  바닥 — RTTOV ASCII 양자화+f32-계단+cfrac 게이트 3중첩, 순수 오라클 창 FD는
  7.3e-5였음)**, dJ/dNCRK1 +1.91, dJ/dECCBRK +22.5, dJ/dNCRK2 +8e-15. 로그-
  감도 θ·dJ/dθ: **NCRK1 5,783 ≫ PEAUT 248 > ECCBRK≈NCRK2 ~22** — 이 케이스
  에서 관측이 가장 세게 제약하는 것은 빗방울 충돌 계수. 전 파라미터 양(+) =
  warm-rain 전환·충돌 과대 방향 신호. 47s/adjoint 창(B=24) — 관측 기반
  파라미터 추정(θ를 제어에 포함한 최소화)의 전제 완비.
- **⑨ 첫 실관측 상태+파라미터 결합 4D-Var** (2026-07-07) — 목표 최종 시연:
  제어 = CVT 상태 ⊕ 파라미터 4종(상대 σ_θ=20%), J = ½‖v‖²+½‖v_θ‖²+J_obs.
  **J 63297→46389 (26.7% 단조, 328s)**. 파라미터 분석: **NCRK1 −38.9%**
  (⑧ 로그-감도 지배 예측 그대로 실현), PEAUT −2.9%, NCRK2/ECCBRK ~0%
  (약신호 → prior 구속 — CVT 설계 의도). 상태 증분 온건(δth 0.63K).
  gradient 분석(⑧)과 최소화 결과(⑨)의 자기일관 확인. 해석 한계 명시:
  단일 케이스·1h 창의 선호값 — 기후학적 보정은 다수-케이스 앙상블 반복의
  통계(그 기계가 오늘 완성된 것).
- **⑩ 분석보고서 발행** (2026-07-07): 분석·파라미터 증분과 RTTOV–GK2A 비교의
  종합 보고서 — `docs/reports/da_analysis_report_lc05_20250719.html` (아티팩트
  게시본과 동일; 그림 7종: 채널별 맑음 O−B·구름컬럼 clear/all-sky 덤벨·J 수렴
  4실험·O−B→O−A RMS·상태증분 노름·증분 연직 프로파일·파라미터 감도/증분).
  신규 산출: **O−B→O−A 관측공간 검증** — t=0 RMS 14.89→13.99 K, t=12 33.66→
  32.66 K (J −24.6% 대비 완만한 개선은 정직한 결과: σ-스케일 증분은 구름 양을
  조정하나 위치 오차는 초기장 진폭만으로 제거 불가 — 순환 동화의 영역);
  증분 연직구조 δth 최대 930 hPa(경계층)·δqs 중상층 빙정대 — 물리 정합.

### 6.3 체계 재설계 — 관측 전처리의 정식 단계화 (사용자 지시, 2026-07-07)

원칙: **자료동화는 수치모델 도메인에서 수행된다.** 위성 관측은 동화·검증 이전에
모델 격자·해상도로 전처리되어야 하며, 하류(J·adjoint·검증·영상)는 전처리
산출물만 소비한다.

```
[1] 어댑터    gk2a_l1b(KO)/gk2a_l1b_fd(FD) → ObsPayload (원해상도)
[2] 전처리    superob.py — 전 모델도메인(234×282) 모델격자 관측장, 슬롯별 저장
              · superob: 셀당 quality-0 화소 평균, min_pixels 미달 셀 quality=1
              · mapping 전환 방식: 화소→셀 사상은 시불변 — 1회 구축·저장 후
                슬롯당 0.1 s (haversine 재계산 188 s 대비 1,880×; bitwise 동일 검증)
              · 실측: 2 km 전화소(413,716) → IR105 전 도메인 커버 100%
[3] 동화      SuperObs만 소비 (최근접-단일화소 payload_to_column_obs는 점검증용)
[4] 검증·영상  같은 SuperObs·같은 모델격자 (O−B/O−A, 채널별 반영률, 2-D 비교)
```

산출물: host/lc05_da_run/obs_products/{gk2a_superob_<ts>.pt, ko_to_lc05_mapping.pt}
  - **superob 현업-시간 달성** (지시 반영, 2026-07-07): brute-force 전쌍
    haversine(187s)을 KD-트리(단위구면 3-D; 현거리≡대원거리 단조)로 교체하고
    전 경로를 O(N log B)로 리팩터링 — **끝-대-끝 슬롯당 1.3s (사상 재사용 시
    0.5s)**: 읽기+DN→BT+지오로케이션 0.3s / KD 사상 0.6s(1회) / index_add 집계
    0.2s. 산출물 bitwise 동일 검증. 73슬롯 전량 전처리 ≈ 40s 거리.
- **루프-내 QC의 mask-게이밍 병리 발견·처방** (2026-07-07, 장면 실험): 상태의존
  rad_quality mask는 J에 불연속을 만들어 최적화기가 "증분으로 컬럼을 플래그
  영역에 밀어 J에서 탈락"시키는 착취를 허용 — 24×24 장면 v3 실측: J −8.2% 중
  ~7.7%p가 mask 탈락분(108항), 동일-집합 진짜 개선 ~0.5%. **처방(표준):
  QC mask를 H(x_b)에서 1회 평가·동결(outer-loop QC)** — v4 적용. 소급 진단:
  기존 24-컬럼 층화 실험(⑦⑨)은 고정-집합 RMS +6.0%/+3.0%로 **진짜 개선 확인**
  (병리는 위치-오차 지배 장면에서 도드라짐). 후속: da_driver
  _innovation_term에 동결-mask 옵션 승격 예정.
- **Codex 적대적 검토 — 전 도메인 dual-loop 계획** (2026-07-07): 8개 공격면 중
  7개에서 DEFECT 판정 (동결 QC mask만 CONFIRMED-SAFE). 대응 분류:
  · **즉시 수정**: D5 j-합산 순서(→ 컬럼 고정순서 fsum, 워커수 무관 결정론);
    성능결함(프로브에 adjoint 기계 사용, 12스텝 60분 → 값-전용 forward 6분).
  · **실측 반박 예정**: D2 J-부분공간 비정확 주장 — mstep 배치-전역 루프바운드는
    실재하나 per-column 게이트로 값-항등 (test_da_parallel의 샤딩≡순차 bitwise가
    동일 기전의 반례) → 표적 게이트 테스트로 고정 예정.
  · **인지된 테스트 단순화** (엄밀형에서 해소): D1 prior 재베이스·θ 복리·½‖v_θ‖²
    앵커 부재, D4 분석-궤적 구름 오분류 잔여, D7 param 단계 목적함수 부분 불일치.
  · **표시 수정**: D6 영상 rq(현재상태) vs J(동결 mask) 라벨링; D-superob
    동률 정책·사상 재사용 계약(길이만 검사 → lat/lon 해시 추가) 예정.
  실측 특기: 시각별 동결 분할의 정당성 수치 확인 — 창 1h 동안 구름 생성 5,269
  /소멸 15,011 (31% 컬럼 부류 변경).
- **dual estimation mainline 승격** (외부 적대검토 blocker 대응, 2026-07-07):
  `oracle/kdm6/da_dual.py` — `run_dual_minimizer` 정식 API. ① 단일 L-BFGS
  클로저에 J = ½‖v_x‖²+½‖v_θ‖²+J_obs (검토 blocker-1); ② **log-파라미터 CVT**
  θ=θ_b·exp(σ_log·v_θ) — 양수성 구조 보장, 데모의 상대-선형(음수 θ 가능) 대체
  (결함-4); ③ **n_valid 불변 게이트** — obs_eval이 (j,adj,n_valid) 반환 시
  클로저 간 유효항 수 변화에 RuntimeError (mask-게이밍 구조적 금지, blocker-2);
  ④ cfrac-regime fixed 해석 제한 명문화 (blocker-3); ⑤ j_trace = JSON 직렬화
  가능 dict 목록 (권고-5). 게이트 5종: 무관측 dual prior(정확 일치) · 결합
  클로저 FD(상태 1e-5·θ 2e-3) · 양수성+비활성 고정 · mask-게이밍 회귀 ·
  기계가독 trace. 스위트 580 passed.
- **dual API 방어 완결** (재검토 7항 대응, 2026-07-08): ① 2-튜플 obs_eval
  거부 (기존 상태의존-mask 경로의 우회 차단) ② mask **서명 동결** —
  동일-개수 치환 게이밍도 거부 ③ `make_dual_frozen_obs_eval` — clear-sky
  표준 어댑터 (H(x_b) 동결 mask + n_valid + sha256 서명 반환) ④ 서명 훅이
  cfrac-regime 해시도 수용 (all-sky 어댑터 규약) ⑤ ParamPrior NaN/Inf·active
  오타 loud 거부 ⑥ 케이스 삭제 finally 승격 (실패 경로 포함) ⑦ all-sky
  connected-field(th/qv/qc/qi/qs/nc/ni) None-grad = 구조적 단절로 거부.
  게이트 9종, 스위트 584 passed.
- **dual 어댑터 방어 완결 2차** (재검토 blocker 2건+high 3건, 2026-07-08):
  ① 어댑터 손실을 `compute_obs_loss`(Huber·full-shape·bias·sigma·masked-NaN
  방어)로 교체 — 수제 quadratic의 안전장치 우회 제거 ② clear-sky connected
  필드(th/qv)는 `autograd.grad(allow_unused=False)` — 구조적 단절 거부
  ③ 동결 궤적의 θ_b를 param_prior에서 강제 주입 (window_config.params와의
  조용한 불일치 차단) ④ 서명 필수 기본값 (`require_signature=True`; 합성
  테스트만 opt-out) ⑤ θ=θb·exp(σv) 오버플로 FloatingPointError + 클로저
  finite 가드. η/η_pre 궤적 의미론은 직전 run_da_window-프로브 전환으로 기해결.
  어댑터 테스트 강화: 궤적-기준 mask 선택의 수치 검증(t0=0/t2=16) + 내부 상태
  변화 하 서명 불변. 게이트 12종, 스위트 587 passed.
- **⑩ 전 도메인 교대 dual-estimation 완주** (v8, 2026-07-08, 벽시계 7.7h):
  KLFS LC05 2025-07-19 00–01 UTC, 234×282(경계 10 제외), 시각별 동결 분할
  (창중 부류변경 31% 실측), 동결 QC mask, J-부분공간 9,346컬럼, all-sky
  10-워커 샤딩(결정론 j). 교대 K=2: J 14,343,920→14,313,843 (누적 −0.21%,
  θ 반단계 기여 −0.10% — 루프간 J 하강으로 실증). **θ 궤적: NCRK1 −35.2%
  (3030→1962)** — 24컬럼 결합추정(−38.9%)과 두 방법·두 규모 수렴. 상태
  증분의 영상 반영은 미세(t12 ir105 RMS −0.15%) — max_iter=2 예산 +
  J-솎음 국한 + 위치-오차 지배(장면 진단 유지)의 설계된 한계. 완주 과정
  적발·고정 결함: 경계 완충대 K 오버플로, K-인덱스 4자리 한계(nprof×nch),
  프로브 adjoint 비용 10×, 케이스 디렉토리 107GB 디스크 고갈(즉시-삭제
  finally), spawn 3종 함정. 루프별 영상 페이지:
  docs/reports/dual_loop_imagery_lc05_20250719.html (artifact 77df7706).
  재현성: v7↔v8 J·θ 소수점 동일 (결정론 파이프라인 실증).
