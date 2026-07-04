# 버그 리포트: `share/module_bc.F` — `flow_dep_bdy_qnn`의 배열 전치/OOB 및 z_sum 결함

- **작성일**: 2026-07-03
- **파일**: `host/KIM-meso_v1.0/share/module_bc.F` (subroutine `flow_dep_bdy_qnn`, ~L2480-2615)
- **도입 시점**: "20250113 CCN init … added by yhlee" 커스텀 확장 (KDM6 CCN(qnn) 스칼라의 유입 경계 프로파일)
- **심각도**: **Critical** — MPI 다중 랭크(np≥2)에서 **비소유 메모리 읽기(OOB)** → 실행마다 다른 결과(비재현), 조건부 NaN 폭주, WRF abort
- **영향 스킴**: mp_physics=37(KDM6)·137(KDM6AD) 공통 (P_QNN 스칼라를 쓰는 모든 구성). WSM6 등 qnn 없는 스킴은 무관
- **상태**: 수정 적용 완료(하단 §6), 판정 실험 진행 중

---

## 1. 한 줄 요약

qnn(CCN) 스칼라의 specified-경계 프로파일 루틴이 `dz8w`를 **전치된 인덱스** `dz8w(i,j,k)`로 읽고(실제 선언은 `(i,k,j)`), `xland` 더미를 **잘못된 차원** `(ims:ime, kms:kme)`로 선언하여, 도메인 경계 랭크에서 **배열 바깥 수 MB 떨어진 힙**을 읽는다. 그 쓰레기 값이 `exp(-z_sum/scale_h)`에 들어가 경계행 qnn이 실행마다 달라지고(NaN/Inf 포함), 이후 이류·미시물리(활성화)로 도메인 전체에 확산된다.

## 2. 관측된 증상 (전부 이 버그로 소급)

| 증상 | 실측 |
|------|------|
| np≥2에서 run-to-run 비재현 | 같은 명령 2회 실행 → step 2에 QNCCN **43,154셀** 상이 (np1은 완전 결정적) |
| 조건부 NaN 폭주 | 한 실행에선 step 2에 QNCCN NaN 6,890셀(도메인 북단 j=281행에서 탄생), 쌍둥이 실행에선 0셀 |
| 경계행 이상값 | j=279-280 행이 NCCN 하한(1e8)으로 도배 — 오염된 경계 qnn이 활성화를 폭주시킨 여파 |
| mp137(np4) 크래시 | NaN이 T/QV/QC로 전파 → 래퍼 NaN 가드 fatal → MPI_ABORT → 타 랭크 "Socket closed" 연쇄 (MPI 전송 문제로 오인되었음) |
| 대조군 | WSM6(qnn 없음) np2 = 완전 bitwise 재현 → 호스트 WRF/MPI 결백. 순정(계측 제거) KDM6 빌드도 재현 실패 → 스킴 경로 내 결함 확정 |

## 3. 근본 원인 (3중 결함)

### 3-1. `dz8w` 전치 인덱싱 (핵심, OOB)
```fortran
REAL, DIMENSION( ims:ime , kms:kme , jms:jme ), INTENT(IN) :: dz8w   ! 선언: (i,k,j)
...
z_sum = z_sum + dz8w(i,j,k)    ! 4개 경계 분기 모두에서 (i,J,K)로 읽음 — 전치!
```
선형 오프셋 = `(i-ims) + (j-kms)·nx + (k-jms)·nx·nz`. 도메인 북단 랭크(예: np2에서 jms≈137, j=282)의 Y-end 분기에서 `(k-jms)`가 −136…−98이 되어 **배열 시작보다 약 3.5~5 MB 아래**의 비소유 힙/해제된 MPI 버퍼를 읽는다. 읽힌 값은 힙 상태(ASLR, 이전 통신 잔재)에 따라 실행마다 달라짐 → **비재현의 근원**. np1에서는 같은 전치 오류라도 오프셋이 자기 소유 메모리 안(결정적 쓰레기)에 머물러 "항상 같은 잘못된 값" → 결정적으로 보였음.

또한 `dz8w`는 Registry i1 변수로 **타일 내부만 계산**되고 halo/경계 존은 미기록 — 인덱스가 옳았더라도 spec 존에서 읽는 것 자체가 미정의 값이다(전치가 그 위에 OOB를 얹은 구조).

### 3-2. `xland` 더미 선언 차원 오류 (OOB)
```fortran
REAL, DIMENSION( ims:ime , kms:kme ), INTENT(IN) :: xland   ! 잘못: 2번째 차원이 k
...
if (xland(i,j)==1) then    ! j=282 접근 — kms:kme(1:40) 훨씬 밖
```
호출측(`solve_em.F:2894+`)은 실제 `(ims:ime, jms:jme)`인 `grid%xland`를 전달 — 수신 선언이 틀려 j>kme 접근이 전부 OOB. land/sea 분기가 쓰레기에 좌우됨.

### 3-3. `z_sum` 적분 논리 결함 (물리 오류)
`z_sum`이 (a) j-루프 밖에서 1회만 0으로 초기화되고, (b) k-외측/i-내측 루프에서 **행의 모든 (k,i)에 걸쳐 계속 누적**되며, (c) 유입 분기에서만 누적된다. 컬럼별 고도 적분이어야 할 값이 행 전체 누적값이 되어, 인덱스가 옳았더라도 경계 CCN 프로파일이 물리적으로 무의미했다.

## 4. 왜 진단이 어려웠나 (오인 경로)

1. 크래시가 mp137에서 먼저·자주 발현 — libtorch가 상주한 힙의 쓰레기가 더 험해(NaN/거대값) 래퍼 NaN 가드에 즉시 걸림 → "**mp137의 MPI 구조 결함**"으로 오인.
2. rank 하나가 NaN-fatal로 죽으면 다른 랭크들이 vader SIGSEGV / tcp `readv: Can't assign requested address`로 죽음 → "**MPI 전송(shm/tcp) 문제**"로 오인 (실제로 vader-고유 SIGSEGV 사례도 일부 있으나, 다수는 이 버그의 연쇄).
3. np1은 결정적이고 12h 완주 → 경계/병렬 관련성 은폐.
4. 증폭기 존재: `module_mp_kdm6.F:3219`/`:1966`의 **FP-정확-동등 게이트** `if(pcond .eq. -qci/dtcld)`가 1-ULP 차이를 O(1e8) qnn 점프(nc 전량→nccn 덤프 유무)로 증폭 — 확산 속도가 비정상적으로 빨라 미시물리 내부 버그처럼 보였음. (이 게이트 자체는 결정적이므로 비재현의 근원은 아님 — 별도 개선 후보로 하단 §7.)

## 5. 진단 사다리 (재현 방법 포함)

```
① mp37 np2 자기재현: 같은 명령 2회 → step2 QNCCN 43k셀 상이 (FAIL)
② WSM6 np2 자기재현: PASS → 호스트/MPI 결백
③ 계측 전부 제거(-DKDM6_SUBSTEP_DUMP 삭제) 순정 빌드: 여전히 FAIL → 스킴 경로 확정
④ numtiles=1: 여전히 FAIL → 타일링 배제
⑤ NaN 최초 좌표: (k=8, j=281=도메인 북단행, i=97+) → 경계 루틴 지목
⑥ 코드 감사(3축 병렬 + 적대검증): flow_dep_bdy_qnn의 전치/선언/적분 3결함 확정
```
재현: SS real case, `mpirun -np 2`(1D-Y 분해), mp_physics=37, 3분(9스텝) 적분 2회 후 `strict_bitwise_nc.py` frame 비교. north 랭크가 j=282 경계행을 가질 때 발현.

## 6. 적용한 수정 (share/module_bc.F)

1. 4개 경계 분기의 `dz8w(i,j,k)` → **`dz8w(i,k,j)`**
2. `xland` 더미 선언 `(ims:ime, kms:kme)` → **`(ims:ime, jms:jme)`**
3. 루프 재구성: **i(또는 j) 외측 / k 내측**, `z_sum`을 **컬럼마다 0으로 리셋** 후 k-상승 시 **분기와 무관하게 무조건 누적** (고도는 흐름 방향과 무관하므로)

수정은 mp37/mp137 공용 WRF 경로이므로 **양 트리에 동일하게 적용되어 페어 bitwise 정합성을 해치지 않음**. 경계 spec-존의 qnn 값은 (쓰레기→물리값으로) 달라지므로, **수정 전 산출물과의 bitwise 비교는 무효**가 되며 새 기준 페어가 필요함.

## 7. 남은 권고 (별도 이슈)

- `module_mp_kdm6.F:3238`, `:1966` — `if (pcond .eq. -qci/dtcld)`류 **FP-정확-동등 분기**.
  **⚠️ 2026-07-04 실측으로 초기 권고 철회 — 현상 유지가 정답.** 12분·전도메인 계측(KDM6_GATE_DIAG)
  결과: 게이트는 12분당 **8,511만 회** 발화하는데 그중 **74.9%(6,371만)가 청천(qci=0) 셀**이다.
  청천 셀에서 `pcond`는 F:3231 기본식으로 `0`이 되고 `-qci/dtcld = -0 = 0`이라 게이트가 발화하여
  잔존 droplet number `nci(1)`을 **CCN 저장소 nci(3)로 재활용**한다(증발한 핵의 CCN 복귀 — 물리적으로
  타당). 이 재활용 덕분에 리포트가 우려했던 **qmin-패딩 number 누수는 현재 0**이다.
  - 초기 권고(옵션 A: full-evap 한정 명시 플래그)로 바꾸면 이 청천-셀 재활용이 사라져, 그 nci(1)이
    qmin 패딩에 파괴된다 → **12분당 315,445 셀에서 총 ~1.29×10¹¹ droplet 손실**(number 비보존).
    즉 옵션 A는 개선이 아니라 **회귀**다. (초기 분석은 게이트가 full-evap에서만 발화한다고 오판했음;
    실제로는 F:3231 기본-pcond 경로 때문에 청천 셀에서도 발화한다.)
  - parity 위험도 없음(12h × np4 12/12 bitwise가 mp37==mp137 통과를 증명). 게이트는 결정적이고,
    이를 위험하게 만들던 업스트림 비결정(flow_dep_bdy_qnn)은 이미 수정됨.
  - **결론: 게이트를 변경하지 않는다.** (측정 계측은 검증 후 제거; 결과만 여기 기록.)
- `dz8w`가 spec 존에서 본질적으로 미기록인 문제: 경계 프로파일에 dz8w 대신 결정적으로 정의된 고도(z_at_w 기반 또는 표준대기)를 쓰는 것이 더 견고.
- **⚠️ adjoint(TL/AD) 경로 stale (Codex 리뷰 2026-07-04 발견, pre-existing, 별도 과제).**
  `wrftladj/solve_em_ad.F`의 qnn 경계 처리가 forward 모델 진화를 따라오지 못함:
  - L3007 forward-recompute 호출: `ccn_conc` 다음에 `scale_h, dz8w, xland`를 빠뜨리고 바로 `ids`로
    넘어가 인자가 밀림 → 명시적 인터페이스면 컴파일 실패, 아니면 차원 오염.
  - L5956 `a_flow_dep_bdy_qnn` 호출: `ccn_conc`조차 없는 **더 오래된 시그니처** → adjoint 루틴 자체가
    RAS(ccn_conc)·yhlee(scale_h/dz8w/xland) 추가 이전 버전 기준.
  - **활성 dyn_em mp37/mp137 parity 경로엔 무관**(em_real은 wrftladj 미빌드). 4DVAR/adjoint 빌드 시에만
    발현. 3007만 부분 수정하면 5956/a_루틴이 여전히 어긋나 "컴파일되나 틀린" 상태가 되므로, adjoint
    재생성(TAPENADE 또는 수동 유도)으로 qnn 경계의 새 CCN-프로파일 코드에 대한 adjoint를 재도출하는
    별도 작업으로 처리해야 함(모델 소유자 판단 필요). 부분 hand-patch 금지.

## 8. 검증 상태 (2026-07-03 16:00 갱신)

- [x] 수정 컴파일 통과
- [x] **mp37 np2 자기재현 bitwise: STRICT BITWISE PASS**
- [x] **QNCCN NaN 0건** (10프레임 전수)
- [x] **mp137 np4 크래시 소멸 (rc=0) + 자기재현 STRICT BITWISE PASS**
- [x] **mp37↔mp137 np4 페어: STRICT BITWISE PASS** — MPI 병렬에서도 두 트리 정합
- [ ] np4 12h(2160스텝) 페어 게이트 — 진행 중 (~17:45 판정)
