# 동일 호스트 열 batch6 계측 계약의 현재 상태

이 문서는 [#593의 차단된 successor](../harness/evidence/native_host_execution_successor_2026-11-13/README.md)를 바탕으로, 다음 **한 구현 묶음**에서 생산자·기록·소비자를 연결하기 위한 현재 산출물과 미해결 조건을 기록한다. native `(203,149)` 열, B=1·K=39, f64 Legacy, 20초, 45입력·최대 100호출·900초는 계획 범위다. **등록된 native 열 배치·WRF·RTTOV 실행은 수행하지 않았다.** 별도 macro OFF CTest에는 합성 fixture에서 KDM 계산을 수행하는 시험이 포함된다.

## source-only와 합성 시험에서 확인한 것

| 항목 | 확보한 근거 | 아직 차단된 연결 |
| --- | --- | --- |
| 소스 계보 | [증분 계측 patch](../harness/evidence/native_host_execution_successor_2026-11-13/producer_source_batch6/README.md)가 #593의 76개 재구성 파일에서 77개 파일을 오프라인 복원하고 개별 SHA를 검사 | 공개 재생은 DSO 빌드·loader·실행 사실을 독립 인증하지 않음 |
| 값 selector | `entry.t/qv/nc_post/nccn_post/cpm/xl` 여섯 입구 값의 39층 × 호출 규칙과 실제 fake ABI 값 기록의 정규화를 검사 | 이 여섯 값만 source-backed draft; 추가 hook 감사에서 확인한 다른 119개 대응 항목과 66개 미대응 항목, 19개 부분 마스크는 차단 |
| 같은 graph 값 | handle·세대 토큰·record에 묶인 f64 원시 단어 checkpoint의 합성 시험 | 실제 KDM graph의 중간값·JVP/VJP·FD를 아직 연결하지 않음 |
| 같은 호출 총강수 | off 모드는 내부 hook 0개인 결과 전용 context, on/graph는 해당 `FnResult.rain_increment`를 별도 slot에 결합하는 소스·합성 시험 | 실제 세 모드의 원시 총강수와 468개 상태 출력의 일치 미측정; 기존 설치 DSO는 새 강수 sidecar가 없음 |
| 조건·FD 소비 | 가상 완전 mask 집합의 변화와 일정 변화를 `BRANCH_CROSSING`으로 전달하는 합성 v2 bridge | 19개 실제 마스크 생산·비활성 증거, receipt v2와 `adapt_many()`의 실제 자료 연결 없음 |
| 침강·수지 | [알고리즘 진단 ledger 계약](NATIVE_HOST_BATCH6_ALGORITHMIC_LEDGER_CONTRACT_20261114.md)의 top/interior/bottom 및 gate·잔차 정의 | 21개 물리적 departure/arrival/export, 질량·수농도·BG 측도와 보존 판정은 미해결 |

격리 macOS 최종 후보 소스는 CTest **3/3**을 통과하고 DSO를 `dlopen`만 했다. 시험 중 f32/f64 잘못된 진입은 모델 연산과 출력 쓰기 전에 거부됐다. 비공개 후보 영수증 SHA-256은 `c0294dbfc28ba3e3b4aea0dac815df58df7b0ff203202da4e2ba9d4e9f6d1274`, DSO SHA-256은 `35c4623e2287eeb8296d01783103b900d5bd9a96f93771b266aa7b8c7a483df8`이다. 이 영수증은 합성 빌드·기호·loader 범위이며 native 계산 실행 영수증이 아니다. [증분 hook 감사](../harness/evidence/native_host_execution_successor_2026-11-13/producer_source_batch6/hook_coverage_delta.json)는 35개 소스 호출 지점에서 새 대응 18개를 확인해 전체를 **125/191**로 집계하지만 실제 방출 수로 세지 않는다.

재구성 소스의 전용 CI driver를 로컬 macOS arm64·Python 3.9.10·Torch 2.8.0에서 시험했다. macro OFF는 **21 CTest·기본 export 14개**, macro ON은 **3 CTest·연구용 포함 export 24개**가 통과했다. 기록한 명령 경과시간 합계는 약 **795초**이며, OFF 컴파일 **562초**, ON 컴파일 **176초**였다. 비공개 전체 영수증 SHA-256은 `bb8a5e6434bf3742e821da68e8ba85fe876fde4304a4a004c90c72c717097302`이다. 이 비교는 같은 로컬 실행의 구성별 비용이며 hosted Linux·macOS CI 시간이나 실제 native 배치 시간을 뜻하지 않는다. 실행이 시작된 뒤 CI driver에 추가한 JUnit skip·실패 영수증 검사는 unit 시험 8개와 실제 3-test JUnit 파일로 확인했고, OFF 전체 CTest의 JUnit 형식은 다음 hosted 실행에서 확인해야 한다.

## 같은 최종 소스 빌드 전에 닫을 계약

1. **필수 record manifest:** 원자 ID와 원래 텐서·mask, full event identity, 조건부 존재·비활성 이유, 방향별 JVP/VJP 요구 및 실제 `batch5_abi_core` 출력 형식을 한 스키마로 고정한다. 동적 substep 개수는 같은 호출의 일정 기록에서 검증한다. 여섯 입구 selector 초안이 전체 coverage를 대신하지 않는다.
2. **새 조건의 생산·소비:** 19개 제안 마스크의 실제 피연산자와 `<,=,>`·우선순위, outer/family/substep, 비활성 증거를 source에 연결하고, 버전 올린 receipt → 조건 정규화 → `adapt_many()` → FD 판정까지 합성 교차 반례를 통과시킨다. 현재 합성 bridge의 가상 universe를 실행 자료로 주장하지 않는다.
3. **적용량·측도:** 기존 노드의 활성화·포화조정·열 적용 전후를 함께 보존한다. 침강의 `d_out/d_in`은 gate를 적용한 **알고리즘 진단 항목**과 clamp·저장 잔차로 나누되, 면별 물리적 보존량이라고 부르기 전에 host/ABI 단위와 독립 interface 수지를 확인한다.
4. **실행 인프라:** 재구성한 소스의 macro OFF/ON 빌드·export·assertion·`-ffp-contract=off`를 전용 CI에서 확인하고, 실제 runner·외부 watchdog·loader/DSO 출처·직렬화 비용을 고정한다. 현재 [CI driver](../harness/evidence/native_host_execution_successor_2026-11-13/producer_source_batch6/ci_build.py)는 합성 도구 시험을 통과했으며 실제 OFF/ON 빌드 검증은 별도 결과로 기록한다. 소스·정책·필수 항목이 확정된 **별도 `EXECUTION_READY` 계획을 첫 실제 호출 전에 커밋**한다.

필수 기록 또는 같은 호출의 강수·graph 값이 누락되거나, 100회·900초 한도에서 필요한 중간 미분 조회를 완료할 수 없으면 해당 배치를 `INCOMPLETE`로 기록한다. 선택 호출의 설치 DSO는 강수 sidecar가 없으므로 상태 468개 비교만 허용하거나 명시적으로 건너뛰며 다른 호출의 강수를 빌리지 않는다. `scientific_status`와 `physical_unit_status`는 계속 `INCONCLUSIVE`다.
