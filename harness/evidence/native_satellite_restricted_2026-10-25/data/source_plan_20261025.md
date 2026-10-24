# KDM6AD 단일 사례·전영역 위성자료 실험: 다음 단계 실행 계획

- 최초 작성: 2026-10-24 / **개정: 2026-10-25, 한국시간**
- 최신 검토 기준: **PR #447**, commit **45f6bd8f4842c361f8e619183321a5ee1bb79f49**. 2026-10-25 06:34:16 한국시간에 병합된 결과를 반영한다.
- 이전 계획과의 관계: PR #446 기준의 “전영역 실행을 구현한다”는 계획은 PR #447의 완료 근거로 대체한다. 이번 문서는 완료한 작업을 보존하고 다음 한 번의 실험을 구체화한다.
- 이번 검토에서 직접 수행: 공개 증거 66개 파일(133,963,622 bytes)의 해시 검사, NumPy 공개 산술 replay, 새 제한 제어 후보의 저장 산출물 재구성.
- 이번 검토에서 수행하지 않은 것: 새로운 KDM·RTTOV·host 실행, 실제 분석 갱신 적용, 저장소 코드 변경·PR 작성.
- 원칙: 단순·명료·간단·직관적인 코드. 현재 함수와 산출물을 재사용하고, 새 물리식·solver·범용 실행 프레임워크를 추가하지 않는다.
- 의존관계 검토: 게시된 Graphify query와 실제 소스를 대조했다. 이 환경에는 Graphify 실행 도구가 없어 새 graph refresh를 수행한 것으로 주장하지 않는다.

## 1. 결론과 다음 목표

**한 사례의 전영역 실험은 PR #447에서 이미 정상적인 음성 결과로 완주했다.** 전체 영역의 관측 연결, 기준 비용·기울기, 독립 방향차분, 세 번의 실제 전영역 T/Q trial, 결과 표·지도·receipt가 존재한다. 결과는 COMPLETED_NO_ACCEPTABLE_UPDATE이며 세 trial 모두 관측 지원을 잃어 거절되었다.

따라서 다음 목표는 다음과 같이 좁힌다.

> **같은 사례·같은 물리 연산자·같은 381,528개 관측 지원을 유지하면서, 실제로 수용 가능한 제한된 T/Q 갱신 한 번을 전영역 forward로 확인하고, 그 상태 변화와 tendency 전달을 함께 정리한다.**

이번 검토에서는 실패가 발생한 기존 블록 전체의 T/Q를 기준값으로 고정하는 후속 후보를 공개 저장값으로 재구성했다. alpha=1 후보의 재구성 목적함수는 11.153458878209252에서 **11.144979224162192**로, 약 **0.076027%** 감소했다. 이는 **새 모델 실행 전의 산술적 후보 평가**이며, 실제 갱신 수용·예보 개선으로 표시하지 않는다.

가장 짧은 다음 실행은 이 후보를 고정하고 원래 129블록을 **한 번 실제 forward 재평가**하는 것이다. 기존 기준 gradient 캠페인이나 새 전영역 자료 수집부터 반복할 필요는 없다.

## 2. 현재 확인된 완료 상태

### 2.1 사례와 공간 범위

| 항목 | 확인된 내용 |
|---|---|
| 위성 | GK2A AMI L1B, KO 명목 2025-07-19 00:00 |
| 모델 | MP137 저장 상태 2025-07-19 00:00:40 |
| 연산 | 20초 고정 forcing 국소 미세물리 map |
| Native 영역 | 234×282 = 65,988개 열 |
| 수직 구조 | 39 mass levels / 40 interfaces |
| KDM 분할 | 128×B512 + 1×B452 = 129블록; 패딩·경계 crop 없음 |
| 채널 | 10 WV073, 11 IR087, 12 IR096, 13 IR105, 14 IR112, 15 IR123, 16 IR133 |
| 물리 경로 | norm_actual + actual-departure QR + 기존 cleanup/finish |
| 직접 제어 | Native moist-theta perturbation 및 dry QV mixing ratio |
| 고정 입력 | MU/PH, 기타 초기 상태, 지표·기하·관측·상수 |
| 소유·coverage | 모든 native 중심이 제공된 KO footprint 안에 있으며 65,988개 unique pixel owner |
| 원시 자료 | 제공된 16채널 inventory 완료, 비용에는 위 7채널 사용 |

이것은 native 모델 영역 전체의 실험이다. 위성 full disk 전체나 원시 16채널 전체를 최적화한 실험은 아니다. MU/PH를 고정해도 T/Q에 의존하는 EOS·압력·Exner 경로는 살아 있다. 20초 국소 map을 실제 다음 host timestep이나 00:01 예보로 부르지 않는다. [근거 1, 2]

### 2.2 자료 부족과 연산자 거부를 분리한다

| 단계·사유 | 열 수 | 채널 값 수 |
|---|---:|---:|
| 원시 KO source QC 통과 | 65,988 | 461,916 |
| Native profile 적격 | 65,540 | 458,780 |
| Baseline RTTOV quality 0 / 고정 비용 지원 | **54,504** | **381,528** |
| 초기 NC/NI 음수로 제외 | 7 | 49 |
| 미세물리 후 active QC / nonpositive NC로 제외 | 441 | 3,087 |
| Profile 적격 중 RTTOV quality로 제외 | 11,036 | 77,252 |

비용에 쓰인 열은 전체의 약 82.5968%다. 나머지 열도 계산과 제외 사유 기록에는 포함된다. 지도에서 빈 영역은 제공된 위성자료의 구멍과 동일하지 않다. Negative BG 두 열은 입자수 거부와 구분되며 기존 지원에 포함된다. [근거 1, 3]

### 2.3 수치 결과와 이번 재검산

| 항목 | 결과 |
|---|---:|
| 고정 Z | 381,528 |
| 관측 비용 numerator | 4,255,356.85888542 |
| 기준 J_total = J_obs | 11.153458878209252 |
| 기준 J_reg | 0 |
| 활성 theta/QV 자유도 | 각 2,125,656개 |
| 실행 기록의 전역 dot 상대오차 | 2.0207926076829038e-16 |
| 이번 공개 배열 replay의 dot 상대오차 | 4.411634227890259e-16 |
| 이번 공개 replay 상태 | REPLAY_PASSED |
| 이번 검토의 새 KDM/RTTOV/host 호출 | 0 |

실행의 numerator-first dot과 공개된 normalized-gradient dot은 반올림 경로가 다르다. 둘을 bitwise 동일한 수치라고 표현하지 않는다. 공개 replay는 파일·인덱스·고정 지원·비용·gradient contraction·trial vector·최종 상태를 확인하며 사설 커널을 독립 실행한 검증은 아니다.

기존 sparse FD는 원래 블록 0, 34, 40, 128에서 epsilon 1e-6 및 3e-7로 통과했다. 더 큰 epsilon의 실패·branch 변경 이력도 보존되어 있다. 이번 후속은 원래 비용·물리 연산자의 새 미분 캠페인을 요구하지 않는다. [근거 1, 4, 5]

### 2.4 기존 세 trial은 그대로 거절 상태다

| alpha | 전영역 실행 | 손실 profile | 손실 채널 값 | 실패 블록 | 기존 결과 |
|---|---|---:|---:|---:|---|
| 1 | 65,988열 / 129블록 | 29 | 203 | 25 | 거절 |
| 0.5 | 65,988열 / 129블록 | 18 | 126 | 18 | 거절 |
| 0.25 | 65,988열 / 129블록 | 13 | 91 | 13 | 거절 |

모든 새로운 손실 사유는 post_microphysics_profile_invalid: active QC requires positive native NC다. 전체 비용은 null/invalid이며 유한한 일부 관측만의 비용으로 원래 trial의 개선을 주장할 수 없다. 기존 최종 입력 증분은 0, 최종 BT와 J는 baseline과 같다. Gradient는 비영이므로 정지점에 도달했다고 판정한 것도 아니다. [근거 1, 6]

## 3. 다음 실험의 핵심 선택: 실패 블록의 제어만 동결한다

### 3.1 왜 기존 블록 전체를 고정하는가

KDM은 B512/B452 안에서 공유 스케줄과 열 간 의존성을 가질 수 있다. 실패한 열의 T/Q만 고정하고 같은 블록의 다른 열을 바꾸면 실패 열 출력도 달라질 수 있다. 따라서 이번 최소 후속에서는 **실패가 발생한 원래 KDM 블록 전체**를 기준 입력에 고정한다.

이 동결은 관측 마스크를 줄이는 조치가 아니다. 동결 블록의 모든 baseline-supported 관측은 여전히 같은 비용에 들어간다. 바뀌는 것은 직접 갱신할 수 있는 T/Q 자유도다.

복잡한 제약 최적화나 새로운 alpha 탐색을 먼저 구현하지 않고, 이미 계산된 세 후보와 기준값으로 검토할 수 있는 제어 부분공간을 사용한다. 이는 기존 실패 결과를 보고 정한 **사후 탐색 실험**으로 별도 식별한다.

### 3.2 이번 공개 배열에서 계산한 동결 집합

세 trial에서 손실한 profile 집합은 13개 ⊂ 18개 ⊂ 29개로 포함된다. 합집합은 29개 열이며 그 원래 블록은 25개다. 블록 ID는 0-based다.

~~~text
1, 35, 51, 52, 53, 54, 60, 62, 64, 66,
67, 69, 70, 73, 82, 89, 91, 93, 100, 102,
108, 109, 113, 118, 124
~~~

| 구분 | 규모 |
|---|---:|
| 동결할 원래 블록 | 25 |
| 동결 블록의 native 열 | 12,800 |
| 그중 baseline-supported 열 | 11,442 |
| 나머지 블록 | 104 |
| 나머지 블록의 native 열 | 53,188 |
| 나머지에서 갱신 가능한 supported 열 | 43,062 |
| 유지되는 활성 theta/QV 자유도 | 각 1,679,418개, 기존의 약 79.0070% |
| 유지되는 scaled-gradient L2 norm 비율 | **96.4165%** |
| 비용에서 유지되는 관측 지원 | **381,528개 전체, 변경 없음** |

자유도 개수는 실제 모든 성분이 비영으로 변한다는 뜻이 아니라 갱신 가능한 집합의 크기다. 최종 그림에 동결 블록과 증분 경계를 함께 표시한다. 계산 분할에 따른 경계가 있으므로 공간적으로 매끈한 분석장이나 일반화된 해법으로 해석하지 않는다.

### 3.3 수학적 정의

원래 scaled control gradient를 g_z라 두면

\[
d_0=-g_z/\|g_z\|_\infty .
\]

P는 위 25블록의 T/Q 제어만 0으로 만드는 좌표 투영이다.

\[
d_R=P d_0,\qquad z_R(\alpha)=\alpha d_R.
\]

**투영한 뒤 infinity norm으로 다시 정규화하지 않는다.** 원래 좋은 블록에서 계산했던 입력과 같아야 기존 trial 산출물을 재사용할 수 있다.

이 방향은 baseline에서

\[
g_z^\mathsf{T}d_R
=-\frac{\|Pg_z\|_2^2}{\|g_z\|_\infty}\le0
\]

이며 이번 재계산 값은 약 -0.19090924482427482다. 그러나 비선형 실제 비용 감소는 이 국소 식만으로 보장하지 않는다.

## 4. 저장 산출물로 평가한 새 후보

### 4.1 재구성 방법과 성립 조건

원래 각 block call은 자신의 native 입력으로 KDM·profile·RTTOV를 실행한다. 비용은 블록별 관측 numerator의 합이고, prior는 제어 자유도별 제곱합이다. 따라서 다음 조건 아래에서 새 후보 비용을 저장값으로 재구성할 수 있다.

- 원래 블록 사이에 물리 상태·난수·스케줄 등 숨은 cross-call 상태가 없다.
- 블록 안의 결합은 원래 full-B 그대로 보존한다.
- 입력·build·template·관측·소유자·m0·w·Z가 같은 자료다.
- 좋은 블록은 해당 alpha의 원 trial 입력과 정확히 같다.
- 동결 블록은 baseline 입력과 정확히 같다.
- Prior에 공간 상관이나 블록 간 결합을 새로 넣지 않는다.

현재 runner의 독립 chunk job 구조와 공개 인덱스·control hash를 확인했다. 실제 전영역 확인은 이 조합이 실행 결과와도 일치하는지 검증하는 마지막 단계다. 숨은 실행 상태나 다른 runtime이 발견되면 재구성값은 screening 결과로만 유지한다. [근거 7, 8]

N_b,alpha를 원 trial의 좋은 블록 관측 numerator, N_b,0를 baseline numerator라 두면

\[
J_R(\alpha)=
\frac{\sum_{b\notin B_{\rm bad}}N_{b,\alpha}
+\sum_{b\in B_{\rm bad}}N_{b,0}
+\frac12\|\alpha P d_0\|_2^2}{Z}.
\]

BT 자체를 good-block trial + frozen-block baseline으로 조합하고 원래 Huber 함수를 다시 계산한다. 기존 invalid trial의 null 비용이나 반올림된 평균을 사용하지 않는다. Prior도 새 z_R에서 다시 구한다.

이번 산술 결과는 기존 objective_chunk 및 finalize_objective 함수의 결과와 정확히 일치하는지 대조했다.

### 4.2 계산 결과 — 아직 새 모델 실행 결과가 아니다

| 후보 | 고정 지원 | J_obs | J_reg | J_total | 기준 대비 감소율 |
|---|---|---:|---:|---:|---:|
| Baseline | 381,528 | 11.153458878209252 | 0 | 11.153458878209252 | — |
| 제한 alpha=1 | 보존 | 11.144974111655065 | 0.000005112507127 | **11.144979224162192** | **0.0760271%** |
| 제한 alpha=0.5 | 보존 | 11.148830482911926 | 0.000001278126782 | 11.148831761038707 | 0.0414859% |
| 제한 alpha=0.25 | 보존 | 11.150906190956684 | 0.000000319531695 | 11.150906510488380 | 0.0228841% |

기존 acceptance threshold는

\[
\epsilon_J=10^{-10}+10^{-12}|J_B|
=1.1115345887820926\times10^{-10}
\]

이다. 이를 바꾸지 않는다. 재구성 세 후보 모두 이를 넘는 감소를 보였으므로, 기존 탐색 순서에서 첫 통과 후보인 **alpha=1**을 실제 확인 대상으로 고정한다.

- 최대 native theta_m 입력 증분: 약 0.14039748926644405 K.
- 최대 상대 QV 입력 증분: 0.02, 즉 기준 QV의 2%.
- 선정 control z의 SHA-256:

~~~text
1177f076e4d8421bfe855f3fd9e064d54bedcf353fcda211c35a4d7059710c38
~~~

이 후보를 아직 accepted analysis라고 부르지 않는다. 0.076%는 작은 진단적 비용 감소이며 큰 warm bias의 해결이나 예보 skill 향상으로 해석하지 않는다.

## 5. 실제 수행 순서

| 단계 | 목적·작업 | 산출물 | 완료 조건 |
|---|---|---|---|
| S0 완료 근거 고정 | PR447 원 실험과 이번 replay를 기준으로 삼고 기존 P0–P5를 닫음 | parent_run, source pins, 공개 replay receipt | 원래 완료·거절 결과를 바꾸지 않음 |
| S1 새 후보 명세 | 25블록 mask, 원 d0, alpha=1, 전체 z·m0·Z·비용 설정 고정 | restricted_candidate.json / control NPZ | control hash와 재구성 비용 일치 |
| S2 최소 runner 연결 | 기존 chunk 실행에 새 z를 전달하는 단일 확인 단계 추가 | 작은 helper·runner 변경, 필요한 집중 검증 | 원래 baseline/trial 기본동작 유지 |
| S3 실제 전영역 확인 | 동일 자산·runtime으로 원래 129블록 forward 및 실제 RTTOV direct | 129 receipt, full BT/quality/profile/state/finish | 모든 m0 유지, 유효한 전역 비용 감소 |
| S4 Tendency 전달 정리 | 저장 before/raw/clean/finish와 rate 정의·수신 상태를 대조 | rate crosswalk, rate arrays, 상태·rate 변화 진단 | 공식·단위·source·receiver가 연결됨 |
| S5 결과 판정 | baseline/새 실제 결과/재구성 예상값 비교, 지도·통계·제약 기록 | FINAL, 보고서·지도·manifest | 실제 수용·거절·재현 불일치를 명확히 구분 |

### S0 — 이번 검토에서 수행한 부분

공개 증거 66개 파일의 SHA-256/size를 확인했다. 공개 NumPy replay가 전체 인덱스·support·cost·trial vector·unchanged final을 통과했다. 세 trial의 손실 집합과 블록 합집합을 계산하고 제한 후보 비용까지 재계산했다.

새 KDM·RTTOV·host 호출은 0이다. 비공개 모델 입력의 진위나 실제 관측 pixel UTC를 확인한 결과로 확대하지 않는다.

### S1 — 새 실행 명세를 고정한다

다음 항목을 새 manifest에 넣는다.

- parent_run_id: b2779685e0f5ef6c8d6627e4d74a4904d2dbea06bb3052b4c0586c28dbb27fc7.
- 원 실험 publication manifest SHA-256: bc67f05376b52f9f11c30f88e83988bcb0772f7701698885c7f5e88ed12355b5.
- 제공된 full-grid indices, m0, weights, baseline state, normalized native gradient 및 세 trial array의 해시.
- 25개 동결 블록 ID, 동결 규칙, 원 분할 512/452.
- 원래 gradient에서 만든 d0를 투영하며 재정규화하지 않는다는 정의.
- alpha=1, 위 candidate control hash, 예상 J_obs/J_reg/J_total.
- 기존 sigma=1 K, zero bias, Huber delta=1, lambda=1, 기존 cost acceptance.
- physics/build/coefficients/template/runtime pins와 새 orchestration source.
- 새로운 실행 ID·출력 폴더. 원 실험 결과와 cache를 수정하지 않는다.
- Private baseline 129블록의 finish/rate 배열 존재와 해시를 확인한다. 없으면 rate 차이 산출을 위해 아래의 별도 value-only 재생 예산을 적용한다.

PR447은 출판 commit이다. 실제 원 실험의 source authority는 source_v3와 기록된 source/build hash이며, main 기반 commit·후속 source 해석이 별도로 기록되어 있다. 원 논문식 결과를 “현재 checkout이 그대로 실행했다”고 바꾸지 않는다. 재사용할 실행 자산은 parent source manifest와 맞춰야 한다. [근거 1, 9]

### S2 — 코드 변경을 작게 유지한다

새 범용 workflow나 optimizer를 만들지 않는다.

| 기존 파일 | 최소 추가 책임 |
|---|---|
| harness/native_satellite_objective.py | 원래 step을 만든 뒤 지정 블록의 z만 0으로 만드는 순수 helper, 동일 함수로 비용 재계산 |
| harness/run_native_satellite_case.py | hash-bound parent baseline과 명시된 z를 읽어 단일 전영역 confirmation 수행 |
| harness/summarize_native_satellite_case.py | restricted-control 유형·동결 블록·예상/실제 비용·rate 교차표 출력 |

run_trials의 기존 세 alpha 의미와 ALLOWED_ALPHA를 바꿀 필요가 없다. 새로운 확인 단계를 명시적으로 분리하되, 실제 block job·support check·atomic receipt·summary는 기존 것을 호출한다. prepare와 native-observation 물리 함수를 다시 작성하지 않는다.

필요한 검증은 새 경계에 집중한다.

1. 최대 gradient가 동결 블록에 있는 작은 사례에서도 원 norm을 유지하는지 확인.
2. 실패 열 하나가 속한 **블록 전체**가 동결되고 다른 블록 z는 그대로인지 확인.
3. 관측 마스크·Z는 그대로이고 prior만 새 z로 재계산되는지 확인.
4. 다른 block mask/control hash의 receipt를 resume하지 못하게 확인.

이것은 구현한 분기만 반복하는 형식적 검사가 아니라, 재정규화·열/블록 혼동·관측 축소·오래된 cache 혼합을 막는 확인이다. 전체 CI나 기존 미분 캠페인을 확대하지 않는다.

### S3 — 실제 전영역 forward 한 번

초기 설정은 기존에 사용한 3 workers, 각 worker/RTTOV child 1 thread를 기준으로 하되 같은 실행 환경을 확인한다. 다른 하드웨어면 작은 실행 확인 후 병렬도를 정한다. 기존 원 블록과 source-bound runtime을 유지한다.

- 원래 129블록 전체를 실제 실행한다. Frozen block도 실제 baseline 입력으로 계산한다.
- 새 KDM forward 129회, 실제 RTTOV direct 최대 129회.
- 새 RTTOV-K·KDM JVP/VJP·전체 baseline 재산출은 요구하지 않는다.
- 관측·weights·m0·Z는 parent와 동일하다.
- 실제 결과가 재구성 예상과 원래 정밀도·실행 계약 아래 일치하는지 대조한다.
- 고정 지원을 하나라도 잃으면 비용을 유효하게 만들려고 마스크를 줄이지 않는다.
- 실제 J가 기존 threshold를 넘게 감소해야 수용한다.
- 예상과 실제가 다르면 source/runtime, K/direct 출력, cache identity와 숨은 실행 의존성을 분리해서 조사한다. 수용 판정에 영향을 주는 불일치를 새 tolerance로 덮지 않는다.

모든 블록이 완료되기 전에는 성공을 반환하지 않는다. 중단 시 같은 input/control hash의 완료 블록만 이어받는다.

### S4 — QC/NC 실패 원인과 tendency를 함께 남긴다

현재 실패 사유는 **optical profile 입력 조건**을 식별한다. raw KDM NC가 언제 0이 되었는지, 특정 과정이 원인인지까지 입증한 것은 아니다.

가능한 경우 기존 private per-block trial NPZ에서 다음을 추출한다.

- Baseline과 각 실패 trial의 native 인덱스·수직 level.
- 초기 NC, raw/clean QC와 NC, post-finish rho_d, NC_opt.
- QC>0 및 NC<=0의 정확한 위치, 최소 양수값과 subnormal 여부.
- raw NC>0인데 NC_opt==0이 되는 binary64 underflow 사례 수.
- Cleanup·clip·cloud branch와 원래 지원 상태.
- 원인 구분: raw moment pair, cleanup 경계, 변환/수치 문제, 기타 profile 조건.

공개 trial observation NPZ에는 BT/quality/profile_valid가 있으며 전체 QC/NC 중간 배열은 없다. 현재 산술 검토만으로 위 level별 원인을 확정했다고 쓰지 않는다. Private 원 자료가 있으면 모델 호출 없이 추출한다. 없고 추가 진단이 필요하면 원래 실패 alpha=1의 **25 full-B 블록만** KDM·profile 수준에서 재현하고 RTTOV는 생략하는 별도 진단을 최대 25회로 제한한다. 다른 alpha의 추가 재현은 새 질문과 예산이 필요하다.

이 진단의 완료가 이미 재구성 가능한 제한 후보를 고르는 데 필요한 전제는 아니다. 후보 확인과 병렬로 처리하되, 최종 보고서에서 원인이 확인된 범위만 말한다.

## 6. Tendency 전달의 정의와 산출물

### 6.1 세 가지 변화를 구분한다

1. **입력 제어 증분:** x_R−x_B. 이번 restricted analysis가 native T/Q에 가한 변경.
2. **국소 미세물리 적용 변화:** 각 입력에서 prep→KDM→cleanup/finish를 거친 before/after 상태 차이.
3. **Tendency 반응 차이:** tau(x_R)−tau(x_B). 입력 갱신이 물리 경향에 미친 변화.

원래 PR447에서 accepted 입력 증분은 0이었지만, baseline 미세물리 상태 변화와 tendency는 비영이었다. 두 지도를 혼동하지 않는다.

RTTOV에는 rate 자체가 직접 들어가는 것이 아니라 **finish가 만든 상태와 EOS/profile**이 들어간다. H_RATE를 이미 갱신된 상태에 다시 더해 이중 적용하지 않는다.

### 6.2 현재 finish의 정확한 식

전/후 dry-potential-temperature와 dry mixing ratio를 (theta0,q0,c0), (theta1,q1,c1)로 쓰며 후 상태는 cleanup을 거친 값이다. a는 고정된 native finish 계수, dt=20 s다. 아래 T0는 이전 상태 theta0와 다른 고정 기준온도이며, parent finish 설정의 값(현재 기록은 300 K)을 사용한다.

\[
m=\operatorname{clip}(\theta_1-\theta_0,\,-L\,dt,\,+L\,dt),
\quad A=1+a q_0,\quad B=1+a q_1,
\]

\[
N=mB+a(q_1-q_0)\theta_1,
\qquad T_{\rm full}=\theta_0A+N .
\]

| 출력 | 정확한 정의 | 단위·의미 |
|---|---|---|
| H_RATE | N/dt | K/s, finish-defined moist-theta heating memory |
| QV_RATE | (q1−q0)/dt | kg/kg dry air/s |
| QC_RATE | (c1−c0)/dt | kg/kg dry air/s |
| t_new_after | Tfull−T0 | 적용된 moist-theta perturbation, K |

H_RATE는 dry-theta 변화의 clip과 QV cross-term을 포함한다. 물리 온도 T의 변화율, BT 변화율, analysis 입력 증분/20 s로 대체하지 않는다. [근거 10, 11]

기존 applied-state audit는 129회 value-only C++ replay에서 finish·native profile·밀도·cleaned-cloud 저장값의 bitwise 일치와, 저장 rate에서 같은 계산 순서의 공식값을 뺀 잔차 0을 기록한다. **실수 대수의 역산식이 모든 부동소수점 연산 순서에서도 bitwise 0이라는 별도 주장으로 바꾸지 않는다.** [근거 10]

### 6.3 다음 실행에서 전달할 자료

기존 저장 finish와 새 confirmation의 finish에서 다음을 내보낸다. 새 계산을 반복하기 위한 항목이 아니라 이미 생긴 값을 구조화하는 작업이다.

| 산출물 | 내용 |
|---|---|
| tendency_crosswalk.json | producer stage, receiving state field, 좌표·단위·부호·dt·수식·source hash |
| baseline rate fields | 기존 private 저장물의 H/QV/QC rate, native index/level |
| restricted-candidate rate fields | 실제 새 confirmation에서 생성된 같은 세 필드 |
| delta_rate fields | 후보−baseline, 같은 좌표·단위 |
| rate_relation_audit.json | 공식 재계산, 비교 수, 최대 잔차, finite·정밀도·적용 상태 관계 |
| raw/cleanup/applied 진단 | 적용 변화와 cleanup sink를 구분한 지도·수직 통계 |

현재 공개 publication manifest에는 별도 전체 rate tensor 파일이 나열되어 있지 않고, audit·source·집계가 제공되어 있다. 실제 전체 rate 전달을 하려면 보존된 private block 결과에서 배열을 export한다. 같은 계산을 이미 수행했다는 사실과 배열 파일을 사용자/후속 모듈에 전달했다는 사실을 구분한다.

Baseline rate 배열이 남아 있지 않으면 선택지는 명확하다. 동일 parent 입력·연산자로 baseline value-only KDM 129회를 별도 실행하여 rate를 재생하거나, 이번에는 후보 rate만 전달하고 baseline 대비 delta_rate 전달은 미완료라고 표시한다. 전자는 RTTOV·K/JVP/VJP를 요구하지 않으며, baseline 관측 비용·gradient 캠페인을 다시 여는 작업은 아니다.

Float64 한 rate[65,988,39]는 약 20.6 MB다. 세 rate를 변수별 파일 또는 기존 chunk 형식으로 나누면 하나의 큰 파일로 묶을 필요가 없다. 저장 포맷은 현재 NPZ/JSON 관례를 따른다.

QR/QI/QS/QG 등으로 넓힐 경우 (q_clean−q_pre)/dt는 **offline 진단 rate**라고 표시하고 현재 검증된 host RATE 필드와 혼동하지 않는다. NC/NI는 원본 host 단위가 미인증이므로 공식적인 host 입자수 tendency로 인증하지 않는다.

Host RK·동역학 수신까지 “전달 완료”라고 부르려면 별도 host step의 수신 전/후 상태와 실제 소비한 field를 검증해야 한다. 현 GK2A 국소 사례 완주의 gate로 host 실행을 추가하지 않는다.

## 7. 산출물과 기상학적 판독

### 7.1 최종 보고 묶음

- Parent baseline, original rejected trials, 새 restricted candidate를 구분하는 상태표.
- 전체 65,988열 포함과 129블록 완료표.
- m0=381,528, weights 및 Z 불변 확인.
- Baseline / 예상 재구성 / 실제 새 실행의 J_obs, J_reg, J_total.
- 관측·모의 BT와 모의−관측 잔차 지도; 공통 색상범위·지원 마스크 사용.
- 채널별 bias, MAE, RMSE, p95와 잔차 변화.
- 입력 theta_m/QV 증분과 25개 동결 블록 경계.
- 실제 물리 변화 및 tendency, 후보−baseline tendency 변화.
- QC/NC 조건 위반의 위치·수준·단계별 원인과 미확인 항목.
- 실행·데이터·라이브러리·계수 해시, 실패와 resume, wall/RSS.

### 7.2 큰 warm bias는 남아 있다

PR447 기준 채널별 bias와 RMSE는 다음과 같다. Bias는 model−observed BT이다.

| 채널 | Bias K | RMSE K |
|---|---:|---:|
| WV073 | +3.435 | 8.306 |
| IR087 | +12.221 | 19.083 |
| IR096 | +11.345 | 14.267 |
| IR105 | +12.548 | 19.936 |
| IR112 | +12.017 | 19.665 |
| IR123 | +10.938 | 18.427 |
| IR133 | +8.270 | 13.989 |

예를 들어 재구성 alpha=1의 IR105 bias는 약 +12.539 K, RMSE는 약 19.925 K다. 이것은 큰 잔차를 해결한 결과가 아니다. 이번 마일스톤은 **지원 보존 갱신과 적용 상태 전달이 작동하는가**이다. 그 다음에 실제 잔차 분포가 지목하는 원인을 하나씩 실험한다. [근거 1, 이번 산술 재구성]

이번 사례의 시간·관측·물리 가정은 계속 붙인다.

- 명목 슬롯과 모델 상태 간 40초 차이, 실제 pixel UTC 미인증.
- 제공된 좌표와 native 영역의 겹침·owner 검증과 원 제공기관 navigation 진위는 별개.
- IR133 spectral identity는 조건부.
- 초기 host 수농도 단위는 미인증·미이관.
- 고정 upper reference·trace gases·표면 가정.
- QR/QG 직접 광학 연결 범위 및 전체 water/energy/number closure 제한.
- 강수 유출은 기존 applied-state audit에 기록되지 않아 완전 물수지 폐합 근거가 아님.

같은 장면으로 후보를 만들고 평가한 결과이며 독립 검증·다른 날짜 일반화·예보 skill로 해석하지 않는다.

## 8. 자원·일정·실행 예산

### 8.1 추가 모델 호출

| 작업 | KDM forward | RTTOV direct | K/JVP/VJP |
|---|---:|---:|---:|
| 공개 replay·후보 재구성: 이번 검토 완료 | 0 | 0 | 0 |
| 선택 후보 실제 전영역 confirmation | **129** | **최대 129** | **0** |
| 기존 저장 rate export·집계 | 0 | 0 | 0 |
| Baseline rate 배열 부재 시 선택적 rate 재생 | 추가 129 | 0 | 0 |
| Private 중간값 부재 시 선택적 원인 진단 | 최대 25 | 0 | 0 |

기존 자료가 남아 있다는 기본 경로에서는 추가 KDM 129 + direct RTTOV 최대 129로 계획한다. Baseline gradient, 3회 old trial, 16개 FD endpoint를 반복하지 않는다.

### 8.2 시간과 메모리

기존 full trial의 median task wall은 약 64–65초, maximum은 약 70–73초다. 3 worker로 129블록을 처리한다고 단순 계산하면 작업시간 합 기준 약 46분이지만, 이는 실제 stage wall-time 측정값이 아니다. Startup·I/O·대기·실행 환경을 고려해 **실행 창은 1–2시간을 가안으로 확보**하고 새 단계의 실측을 남긴다.

기존 trial의 maximum recorded worker RSS는 0.53–0.56 GiB, child RSS는 약 0.43 GiB다. Cumulative high-water 값이므로 이를 합산해 동시 전체 시스템 peak라고 부르지 않는다. Baseline의 비싼 RTTOV-K 재실행을 피하는 것이 가장 큰 계산 절감이다. [근거 1, 12]

### 8.3 권장 일정: 준비된 실행 자산 기준 2–3 작업일

| 시점 | 작업 | 완료 증거 |
|---|---|---|
| 이번 검토 완료 | Parent 공개 replay, 25블록 집합, 3개 restricted 후보 비용 | 해시·수치 재검산, 아래 부록 |
| 1일차 오전 | Manifest, restricted helper, 단일 confirmation 연결 | 후보 z hash·원 목적함수·집중 검증 |
| 1일차 오후 | 동일 자산 확인 후 전129블록 confirmation | 129 receipt·고정 지원·실제 비용 |
| 2일차 | Rate export·crosswalk·QC/NC 진단·지도·결론 | 적용 상태·tendency·수치 결과 |
| 필요 시 3일차 | 실행 불일치/미보존 중간값의 한정 진단 | 구체적 원인·제한·추가예산 기록 |

자료/증거 담당은 원 실험 source와 private 저장물, 구현 담당은 후보 생성·runner, 검토 담당은 support·단위·rate·해석을 맡는다. 새 사례나 전체 재검증을 병렬 작업의 범위에 넣지 않는다.

## 9. 완료 판정

| 상태 | 판정 |
|---|---|
| 원 실험: COMPLETED_NO_ACCEPTABLE_UPDATE | PR447의 완료 상태로 유지 |
| 새 후보: SCREENED_CANDIDATE_READY | 이번 공개 산술에서 지원과 비용 감소를 확인; 새 실제 실행 전 |
| 새 실행: RESTRICTED_UPDATE_ACCEPTED | 실제129블록 완료, 동일 m0/Z, 유효한 비용 감소, 적용 상태·rate 산출물 완성 |
| 새 실행: RESTRICTED_UPDATE_NOT_ACCEPTED | 정상 실행했으나 지원/비용 조건 미충족. 이 제한 부분공간의 음성 결과 |
| 새 실행: REPRODUCTION_MISMATCH | 저장값 재구성과 실제 결과가 실행 계약에서 설명되지 않음; 원인분리 필요 |
| 새 실행: INCOMPLETE | 입력·자산 접근 실패, 미완료 블록, 저장/identity 오류 |

동결 부분공간에서 수용되지 않았다는 결과를 전체 T/Q 공간에 feasible update가 없다는 증명으로 바꾸지 않는다. 이번에는 실제 전영역 확인 **한 번**으로 후보를 판정하고, 실패하면 이유를 남긴다. 자동으로 더 작은 alpha, 새 floor, 다른 마스크를 계속 탐색하지 않는다.

### 최종 체크리스트

- [ ] 원 PR447의 완료·세 거절 결과를 보존했다.
- [ ] 새로운 제어 부분공간이 25개의 원래 full-B 블록으로 정확히 정의되었다.
- [ ] 원 gradient norm을 보존하고 투영 후 재정규화하지 않았다.
- [ ] 모든 baseline 관측 381,528개와 weights/Z를 유지했다.
- [ ] 새 전체 control hash와 parent 데이터·build·config가 고정되었다.
- [ ] 실제129블록을 원 shape로 재평가하고 완전한 receipt를 남겼다.
- [ ] 실제 J와 재구성 J를 구분하여 기록하고 수용 여부를 판정했다.
- [ ] 입력 증분·미세물리 적용 변화·tendency 변화가 구분된다.
- [ ] H/QV/QC rate의 좌표·공식·단위·수신 상태가 연결되었다.
- [ ] 자료·물리 가정과 작은 비용 감소의 해석 한계를 명시했다.
- [ ] 코드 변경이 기존 objective/runner/summary의 작은 경계 안에 머문다.

## 10. 실행 명령과 제안 인터페이스

### 현재 존재하며 이번에 실행한 공개 검산

~~~bash
python -m harness.replay_native_satellite_case \
  harness/evidence/native_satellite_case_2026-10-25/data
~~~

이 명령은 NumPy 산술 검산이며 KDM·RTTOV·host를 호출하지 않는다.

### 새 확인 단계의 제안 명세

다음은 **구현할 인터페이스의 제안**이며 현재 실행 가능한 옵션이라고 표시하지 않는다.

~~~json
{
  "experiment_type": "restricted_block_confirmation_v1",
  "parent_run_id": "b2779685e0f5ef6c8d6627e4d74a4904d2dbea06bb3052b4c0586c28dbb27fc7",
  "parent_publication_manifest_sha256": "bc67f05376b52f9f11c30f88e83988bcb0772f7701698885c7f5e88ed12355b5",
  "freeze_blocks_0based": [1,35,51,52,53,54,60,62,64,66,67,69,70,73,82,89,91,93,100,102,108,109,113,118,124],
  "direction": "original_d0_then_zero_whole_frozen_blocks",
  "renormalize_after_projection": false,
  "selected_alpha": 1.0,
  "control_z_sha256": "1177f076e4d8421bfe855f3fd9e064d54bedcf353fcda211c35a4d7059710c38",
  "fixed_baseline_support": true,
  "globalZ": 381528,
  "expected_screen_J_total": 11.144979224162192,
  "cost_accept_atol": 1e-10,
  "cost_accept_rtol": 1e-12,
  "max_full_domain_confirmation_runs": 1,
  "workers": 3,
  "threads_per_worker_and_child": 1,
  "export_applied_tendencies": ["H_RATE","QV_RATE","QC_RATE"]
}
~~~

RTTOV 계수·라이브러리·native 입력 경로는 parent의 실제 source manifest에 묶고 사설 실행 환경에서 해시를 대조한다. 공개 경로 문자열만으로 사설 자산이 이 환경에 존재한다고 가정하지 않는다.

## 11. 다음 이후의 과제

이번 확인이 끝나면 두 갈래가 남는다.

- 수용되면, 관측 지원을 보존한 제한 갱신의 실제 상태/tendency 반응을 근거로 더 넓은 제어 공간을 설계한다.
- 수용되지 않으면, 이번 동결 부분공간과 실행 재현의 구체적 실패 원인을 분리해 기록한다.

그 다음에 필요한 경우 QC/NC moment-pair 제약을 고려한 방향, 물리 과정의 출입량·수농도 변화, 시간·SRF·cloud optics 잔차를 하나씩 실험한다. NC floor·clear-sky 대체·지원 축소·새 물리 variant는 현재 후보 수용을 위한 임시 조치로 넣지 않는다. 원 물리 연산자를 바꾸는 개선은 별도 source·실험·미분·물리 근거를 갖춰야 한다.

현재 사용자 목표에 대한 진행 방향은 **이미 완주한 한 사례를 유지하면서, 저장 근거로 구체화한 후보 하나의 실제 전영역 갱신과 tendency 전달을 닫는 것**이다.

## 부록 A. 이번 검토의 직접 재검산 기록

공개 파일은 위 commit의 publication manifest에 적힌 SHA-256과 byte 수로 확인했다. 총 66개 artifact이며 133,963,622 bytes이다. 모델 재실행 없이 원 replay를 실행해 다음을 얻었다.

~~~json
{
  "status": "REPLAY_PASSED",
  "native_columns": 65988,
  "blocks": 129,
  "globalZ": 381528.0,
  "observation_numerator": 4255356.85888542,
  "baseline_J": 11.153458878209252,
  "published_dot_relative_error": 4.411634227890259e-16,
  "new_KDM_RTTOV_host_calls": 0,
  "publication_manifest_sha256": "bc67f05376b52f9f11c30f88e83988bcb0772f7701698885c7f5e88ed12355b5",
  "replayer_sha256": "a9cfe38239072ba5584ab518ebf0cd6e78cee8badc2a98c2528214bee9202ec4"
}
~~~

제한 후보의 핵심 재계산은 다음과 같다. 아래는 새 runner 명령이 아니라 **해시 검증을 마친 배열에 적용한 산술 절차**를 설명하는 코드다.

~~~python
# Existing published arrays:
# flat[65988], baseline_bt, trial_bt/quality/profile_valid for each alpha,
# observed_bt, m0, weights, active[2,65988,39], native_gradient, native_scales.
# verify all hashes and all original 129 partitions before entering this code.

losses = [
    m0 & ((t["quality"] != 0) | ~np.isfinite(t["bt"])
          | ~t["profile_valid"][:, None])
    for t in trials
]
lost_union = np.logical_or.reduce([loss.any(axis=1) for loss in losses])
bad_blocks = np.unique((flat // 512)[lost_union])
frozen_rows = np.isin(flat // 512, bad_blocks)

g_z = np.where(active, native_scales * native_gradient, 0.0)
d0 = -g_z / np.max(np.abs(g_z))
d_R = d0.copy()
d_R[:, frozen_rows, :] = 0.0     # no re-normalization

for alpha, trial in zip((1.0, 0.5, 0.25), trials):
    z = alpha * d_R
    predicted = trial["bt"].copy()
    predicted[frozen_rows] = baseline_bt[frozen_rows]
    # Retain baseline quality/profile validity on frozen rows;
    # verify every entry of m0 is valid for this assembled candidate.
    numerators = []
    for start in range(0, 65988, 512):
        stop = min(start + 512, 65988)
        support = {"m0": m0[start:stop], "weights": weights[start:stop]}
        item = objective_chunk(predicted[start:stop],
                               observed_bt[start:stop], support)
        numerators.append(item["numerator"])
    result = finalize_objective(numerators, 381528.0, z, active)
    # result is a reconstructed screening objective, not a new model execution.
~~~

제어공간 투영 후에도 관측 지원은 바뀌지 않는다. 추가 regularization은 새 z의 전역 제곱합으로 계산하며, 기존 objective helper와 독립적인 NumPy numerator 계산을 대조했다.

## 부록 B. 제한 후보 산술 결과

아래는 이번 직접 계산의 기계 판독용 결과이다. assembled_support_preserved와 screen_acceptance는 저장값 재구성의 판정이며 실제 모델 수용 상태가 아니다.

~~~json
{
  "schema": "kdm6ad.plan.restricted_block_screen.v1",
  "interpretation": "Post-hoc arithmetic screening of a new restricted-control candidate. No new KDM/RTTOV calls or accepted model update. Blockwise reconstruction assumes deterministic independent original calls; full-domain forward must verify.",
  "parent_run_id": "b2779685e0f5ef6c8d6627e4d74a4904d2dbea06bb3052b4c0586c28dbb27fc7",
  "publication_manifest_sha256": "bc67f05376b52f9f11c30f88e83988bcb0772f7701698885c7f5e88ed12355b5",
  "baseline_J": 11.153458878209252,
  "globalZ": 381528,
  "lost_union_profiles": 29,
  "bad_blocks_0based": [
    1,
    35,
    51,
    52,
    53,
    54,
    60,
    62,
    64,
    66,
    67,
    69,
    70,
    73,
    82,
    89,
    91,
    93,
    100,
    102,
    108,
    109,
    113,
    118,
    124
  ],
  "bad_block_count": 25,
  "frozen_native_columns": 12800,
  "frozen_baseline_supported_columns": 11442,
  "remaining_blocks": 104,
  "remaining_native_columns": 53188,
  "active_theta_QV_original_each": 2125656,
  "active_theta_QV_retained_each": 1679418,
  "active_theta_QV_frozen_each": 446238,
  "retained_scaled_gradient_L2_fraction": 0.9641647280914948,
  "projected_slope": -0.19090924482427482,
  "projection_formula_slope": -0.1909092448242748,
  "re_normalized_direction": false,
  "screened_candidates": [
    {
      "alpha": 1,
      "assembled_support_preserved": true,
      "J_obs": 11.144974111655065,
      "J_prior": 0.000005112507127035091,
      "J_total": 11.144979224162192,
      "delta_total_from_baseline": -0.008479654047059526,
      "original_objective_helper_exact_match": true,
      "screen_acceptance": {
        "decreased": true,
        "baseline_cost": 11.153458878209252,
        "trial_cost": 11.144979224162192,
        "decrease": 0.008479654047059526,
        "required_decrease": 1.1115345887820926e-10
      },
      "percent_total_decrease": 0.07602712431769848,
      "control_sha256": "1177f076e4d8421bfe855f3fd9e064d54bedcf353fcda211c35a4d7059710c38",
      "max_abs_delta_theta_K": 0.14039748926644405,
      "max_abs_relative_delta_QV": 0.02
    },
    {
      "alpha": 0.5,
      "assembled_support_preserved": true,
      "J_obs": 11.148830482911926,
      "J_prior": 0.0000012781267817587727,
      "J_total": 11.148831761038707,
      "delta_total_from_baseline": -0.004627117170544537,
      "original_objective_helper_exact_match": true,
      "screen_acceptance": {
        "decreased": true,
        "baseline_cost": 11.153458878209252,
        "trial_cost": 11.148831761038707,
        "decrease": 0.004627117170544537,
        "required_decrease": 1.1115345887820926e-10
      },
      "percent_total_decrease": 0.04148593921464698,
      "control_sha256": "8a4639d4ecde381e6158772811a59334731f6c3388ae3a5c9e43646ce8323d7b",
      "max_abs_delta_theta_K": 0.07019874463322202,
      "max_abs_relative_delta_QV": 0.01
    },
    {
      "alpha": 0.25,
      "assembled_support_preserved": true,
      "J_obs": 11.150906190956684,
      "J_prior": 3.1953169543969317e-7,
      "J_total": 11.15090651048838,
      "delta_total_from_baseline": -0.002552367720872084,
      "original_objective_helper_exact_match": true,
      "screen_acceptance": {
        "decreased": true,
        "baseline_cost": 11.153458878209252,
        "trial_cost": 11.15090651048838,
        "decrease": 0.002552367720872084,
        "required_decrease": 1.1115345887820926e-10
      },
      "percent_total_decrease": 0.022884091372396585,
      "control_sha256": "3e2d4ecd877cfb0e31c0c820e3f2a88c1240cba4e18f28072da75fc37f3d0289",
      "max_abs_delta_theta_K": 0.03509937231661101,
      "max_abs_relative_delta_QV": 0.005
    }
  ],
  "new_KDM_RTTOV_host_calls": 0
}
~~~

## 근거 목록

저장소 근거는 PR447 commit에 고정했다. 위 부록 A/B의 재검산과 새 제한 후보는 이번 검토의 직접 계산이며 원 보고서가 이미 실행했다고 주장한 결과와 구분한다.

1. [PR447 전체 사례 실행·지원·수치·trial·자원 보고서](https://github.com/gonos2k/KDM6AD/blob/45f6bd8f4842c361f8e619183321a5ee1bb79f49/harness/evidence/native_satellite_case_2026-10-25/REPORT.md)
2. [현행 native KO7 사례 계약 및 구현 범위](https://github.com/gonos2k/KDM6AD/blob/45f6bd8f4842c361f8e619183321a5ee1bb79f49/docs/NATIVE_SATELLITE_CASE.md)
3. [정확한 source/profile/model support 및 채널 통계](https://github.com/gonos2k/KDM6AD/blob/45f6bd8f4842c361f8e619183321a5ee1bb79f49/harness/evidence/native_satellite_case_2026-10-25/data/summary.json)
4. [NumPy 공개 arithmetic replay 구현](https://github.com/gonos2k/KDM6AD/blob/45f6bd8f4842c361f8e619183321a5ee1bb79f49/harness/replay_native_satellite_case.py)
5. [기존 공개 arithmetic replay 기록](https://github.com/gonos2k/KDM6AD/blob/45f6bd8f4842c361f8e619183321a5ee1bb79f49/harness/evidence/native_satellite_case_2026-10-25/PUBLIC_ARITHMETIC_REPLAY.json)
6. [기존 세 trial의 control hash·분할·거절 기록](https://github.com/gonos2k/KDM6AD/blob/45f6bd8f4842c361f8e619183321a5ee1bb79f49/harness/evidence/native_satellite_case_2026-10-25/data/trials/trials.json)
7. [기존 objective·scaled direction·global prior·acceptance 구현](https://github.com/gonos2k/KDM6AD/blob/45f6bd8f4842c361f8e619183321a5ee1bb79f49/harness/native_satellite_objective.py)
8. [기존 독립 chunk runner·원 partition·trial 실행](https://github.com/gonos2k/KDM6AD/blob/45f6bd8f4842c361f8e619183321a5ee1bb79f49/harness/run_native_satellite_case.py)
9. [원 실험의 source/build/input attribution](https://github.com/gonos2k/KDM6AD/blob/45f6bd8f4842c361f8e619183321a5ee1bb79f49/harness/evidence/native_satellite_case_2026-10-25/data/source_manifest.json)
10. [적용 물리 audit: bitwise·rate 관계·moment·수지 한계](https://github.com/gonos2k/KDM6AD/blob/45f6bd8f4842c361f8e619183321a5ee1bb79f49/harness/evidence/native_satellite_case_2026-10-25/data/applied_physics_audit.json)
11. [정확한 finish map과 named rates·단위·derivative](https://github.com/gonos2k/KDM6AD/blob/45f6bd8f4842c361f8e619183321a5ee1bb79f49/docs/APPLIED_FINISH_AD.md)
12. [원 실행 resource audit](https://github.com/gonos2k/KDM6AD/blob/45f6bd8f4842c361f8e619183321a5ee1bb79f49/harness/evidence/native_satellite_case_2026-10-25/RESOURCE_AUDIT.json)
13. [해시가 고정된 공개 publication manifest](https://github.com/gonos2k/KDM6AD/blob/45f6bd8f4842c361f8e619183321a5ee1bb79f49/harness/evidence/native_satellite_case_2026-10-25/data/publication_manifest.json)
14. [관측 매칭·footprint·distance 검증 범위](https://github.com/gonos2k/KDM6AD/blob/45f6bd8f4842c361f8e619183321a5ee1bb79f49/harness/evidence/native_satellite_case_2026-10-25/data/geometry_coverage.json)
15. [Rate audit의 실제 실행 소스](https://github.com/gonos2k/KDM6AD/blob/45f6bd8f4842c361f8e619183321a5ee1bb79f49/harness/evidence/native_satellite_case_2026-10-25/data/execution_sources/audit_saved_case_physics.py.txt)
16. [Native observation adapter와 optical profile 적격성](https://github.com/gonos2k/KDM6AD/blob/45f6bd8f4842c361f8e619183321a5ee1bb79f49/harness/native_observation_batch.py)
17. [기존 실패·step revision 이력](https://github.com/gonos2k/KDM6AD/blob/45f6bd8f4842c361f8e619183321a5ee1bb79f49/harness/evidence/native_satellite_case_2026-10-25/data/history.json)
