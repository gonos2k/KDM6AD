# 동일 호스트 열 batch6 계측 계약의 현재 상태

이 문서는 [#593의 차단된 successor](../harness/evidence/native_host_execution_successor_2026-11-13/README.md)를 바탕으로, 다음 **한 구현 묶음**에서 생산자·기록·소비자를 연결하기 위한 현재 산출물과 미해결 조건을 기록한다. native `(203,149)` 열, B=1·K=39, f64 Legacy, 20초, 45입력·최대 100호출·900초는 계획 범위다. **등록된 native 열 배치·WRF·RTTOV 실행은 수행하지 않았다.** 별도 macro OFF CTest에는 합성 fixture에서 KDM 계산을 수행하는 시험이 포함된다.

## 현재 판정 — PR #593 head `de47a3f1`

최종 **84파일** 재구성 소스는 [Linux·macOS 전용 CI](https://github.com/gonos2k/KDM6AD/actions/runs/43545036341)에서 각각 macro OFF **21/21**, macro ON **5/5** CTest를 통과했다. JUnit 실패·오류·skip은 0개였고 C ABI export는 OFF **14개**, ON **28개**였다. CI 임시 병합과 PR head의 Git tree가 `1d37c6c4…`로 같았다. ON 시험에는 실제 KDM을 호출한 **합성 B=1·K=39 f64 value-only fixture 한 건**의 capture off/on 원시 상태 **468개**와 same-call 강수 단어 비교가 포함된다. 이는 native 45입력 실행, 중간 graph 미분, 물리 수지 또는 설치 DSO 검증이 아니다. successor는 계속 `DRAFT_BLOCKED`, 과학·단위 상태는 `INCONCLUSIVE`다.

## source-only와 합성 시험에서 확인한 것

| 항목 | 확보한 근거 | 아직 차단된 연결 |
| --- | --- | --- |
| 소스 계보 | [증분 계측 patch](../harness/evidence/native_host_execution_successor_2026-11-13/producer_source_batch6/README.md)가 #593의 76개 파일에서 A5 77개를 복원한다. [후속 네 층](../harness/evidence/native_host_execution_successor_2026-11-13/producer_source_batch6_layers/replay.py)은 v2 기록 스키마 82개, named hook 83개, 진단 기록 83개, 합성 parity CTest를 더한 84개 파일의 목록과 SHA를 순서대로 검사한다 | 공개 재생은 DSO 빌드·loader·실행 사실을 독립 인증하지 않음 |
| 값 selector | `entry.t/qv/nc_post/nccn_post/cpm/xl` 여섯 입구 값의 39층 × 호출 규칙과 실제 fake ABI 값 기록의 정규화를 검사 | 이 여섯 값만 source-backed draft; 추가 hook 감사에서 확인한 다른 119개 대응 항목과 66개 미대응 항목, 19개 부분 마스크는 차단 |
| 같은 graph 값 | handle·세대 토큰·record에 묶인 f64 원시 단어 checkpoint의 합성 시험 | 실제 KDM graph의 중간값·JVP/VJP·FD를 아직 연결하지 않음 |
| 같은 호출 총강수 | off 모드는 내부 hook 0개인 결과 전용 context, on/graph는 해당 `FnResult.rain_increment`를 별도 slot에 결합하는 소스·합성 시험 | 실제 세 모드의 원시 총강수와 468개 상태 출력의 일치 미측정; 기존 설치 DSO는 새 강수 sidecar가 없음 |
| 조건·FD 소비 | 가상 mask·일정 교차를 전달하는 bridge와 별도의 `SPEC_ONLY` [v2 소비자 초안](../harness/evidence/native_host_execution_successor_2026-11-13/condition_consumer_v2.py)이 기록 역할·B/K·동적 누락·거짓 원인 연결을 검사한다. 각 그룹에 선언한 실제 소비 Boolean 또는 진단 비교가 관측되지 않으면 일치 판정을 막고, 진단 비교 변화도 역할을 보존해 교차로 전달한다. 별도 [C ABI 읽기 초안](../harness/evidence/native_host_execution_successor_2026-11-13/condition_abi_v2_reader.py)은 고정 POD·원시 단어와 부분 실패를 fake ABI에서 검사한다 | 실제 19개 그룹 전체의 생산·비활성 증거, source-backed 인과 관계, receipt v2와 `adapt_many()`의 실제 자료 연결 없음 |
| 침강·수지 | [알고리즘 진단 ledger 계약](NATIVE_HOST_BATCH6_ALGORITHMIC_LEDGER_CONTRACT_20261114.md)의 top/interior/bottom 및 gate·잔차 정의 | 21개 물리적 departure/arrival/export, 질량·수농도·BG 측도와 보존 판정은 미해결 |

격리 macOS 최종 후보 소스는 CTest **3/3**을 통과하고 DSO를 `dlopen`만 했다. 시험 중 f32/f64 잘못된 진입은 모델 연산과 출력 쓰기 전에 거부됐다. 비공개 후보 영수증 SHA-256은 `c0294dbfc28ba3e3b4aea0dac815df58df7b0ff203202da4e2ba9d4e9f6d1274`, DSO SHA-256은 `35c4623e2287eeb8296d01783103b900d5bd9a96f93771b266aa7b8c7a483df8`이다. 이 영수증은 합성 빌드·기호·loader 범위이며 native 계산 실행 영수증이 아니다. [증분 hook 감사](../harness/evidence/native_host_execution_successor_2026-11-13/producer_source_batch6/hook_coverage_delta.json)는 35개 소스 호출 지점에서 새 대응 18개를 확인해 전체를 **125/191**로 집계하지만 실제 방출 수로 세지 않는다.

재구성 소스의 전용 CI driver를 로컬 macOS arm64·Python 3.9.10·Torch 2.8.0에서 시험했다. macro OFF는 **21 CTest·기본 export 14개**, macro ON은 **3 CTest·연구용 포함 export 24개**가 통과했다. 기록한 명령 경과시간 합계는 약 **795초**이며, OFF 컴파일 **562초**, ON 컴파일 **176초**였다. 비공개 전체 영수증 SHA-256은 `bb8a5e6434bf3742e821da68e8ba85fe876fde4304a4a004c90c72c717097302`이다. 이 비교는 같은 로컬 실행의 구성별 비용이며 hosted Linux·macOS CI 시간이나 실제 native 배치 시간을 뜻하지 않는다. 실행이 시작된 뒤 CI driver에 추가한 JUnit skip·실패 영수증 검사는 unit 시험 8개와 실제 3-test JUnit 파일로 확인했고, 최종 84파일 소스의 OFF·ON JUnit 결과는 위 hosted CI에서 확인했다.

그 뒤의 v2 스키마 층은 기존 ABI를 보존하면서 역할별 기록, B/K·층·열·scalar 좌표, 원시 control 단어, context 세대 및 성공한 forward 이후의 읽기 제한을 별도 ABI로 정의한다. 격리 macOS에서 **v2 스키마만 포함한 macro ON 소스**는 합성 CTest **4/4**, 기존 24개와 새 4개를 합친 export **28개**, DSO 로드에 통과했다. 해당 영수증 SHA-256은 `7d75f357c62e6207c63c0f5000b98032b8d60acb41b36677055cea30ca5253cb`이다. 이 결과는 아직 39개 named hook 층의 빌드 결과가 아니며, 실제 19개 마스크의 방출·완전성을 검증하지 않는다. named hook 39곳은 기존 소스의 실제 Boolean 텐서와 피연산자에 대한 **정적 관측 위치**다. 추가 비교만 하는 진단과 실제 소비 Boolean을 구분하며, 원래 계산식을 바꾸지 않는다는 소스 검사는 통과했다. 이 v2 스키마 시점에는 최종 층의 빌드·원시 출력 비침습성이 미확인이었으며, 현재의 제한된 합성 결과는 위에 구분해 기록했다.

이후 **83개 파일의 named hook 층**을 같은 격리 빌드에 증분 적용했다. macro ON 합성 CTest **4/4**, export **28개**, DSO 로드 및 소스 파일 83개 해시 일치를 확인했다. 결합 영수증 SHA-256은 `e046a7348c43b74e4e4d3edb29213bb729dff9a511675d2da47fbf0cf0671362`, DSO SHA-256은 `61b3a5b727996230d2d0c6e19b9391c002be113a57b706d3837bf240da923afa`이다. 컴파일 명령은 `-ffp-contract=off`, 네 시험 소스는 `-UNDEBUG`를 유지했다. 이 CTest는 hook 39곳의 native 열 실행을 포함하지 않는다. macro OFF에서는 새 hook 줄을 제거하면 v2 소스로, v2 층을 제거하면 A5 소스로 돌아간다는 소스 대조를 수행했으며, **A2 시점에는 최종 OFF 빌드가 미확인이었고, 현재 84파일 hosted 결과는 위에 기록했다.**

세 번째 진단 층은 같은 83개 파일에 **45개** 원시 피연산자·별도 비교·scalar control 기록을 추가한다. 격리 macOS macro ON 증분 빌드에서 합성 CTest **4/4**, export **28개**, DSO 로드와 83파일 해시 일치가 다시 확인됐다. 진단 층 영수증 SHA-256은 `8f8870b357646d3669c72673ce0937725b3f68e90b2ff52cc66cdb5005853b47`, DSO SHA-256은 `ed1a117ec49bd442a5994f3132ceb8d1589c603af525709db0116ea3ce479751`이다. 이 시험도 새 45개 진단 지점을 실제 입력으로 모두 실행하지 않았고, A3 시점에는 최종 OFF 빌드와 비침습성이 미확인이었으며, 현재 A4의 제한된 결과는 위에 기록했다. 실제 45입력 비용은 여전히 미측정이다.

같은 A3 DSO에서 별도 **합성 B=1·K=39 f64 컬럼**을 호출했다. 동일한 624개 입력 배열을 사용한 capture-off/on 두 값 호출의 상태 출력 버퍼 **468개 원시 단어**와 같은 호출 총강수 원시 단어가 모두 일치했다. off에서 v1 기록은 0개이고 v2 외부 읽기는 거부됐으며, on에서는 v1 기록 **22,250개**, v2 기록 **7,947개**가 생성됐다. 호출·좌표 메타데이터를 확인했고 검사 시간은 약 **2.045초**다. 비공개 합성 probe 영수증 SHA-256은 `fe31fe95c5efac8eb3c865c068411f09a63ad0a56661941306d9c9e10b13b161`; 입력·출력 패킷 SHA-256은 각각 `5597c8a1770f65f7e4eadc6be78c196cd61fab5dc9b150e6a2e9dab77ce6ff42`, `88a8db00e86b9ff585377f99a90c3b7a1a781ee3ac2ab33f16b31a10eefd97de`다. **이 시험은 KDM을 합성 컬럼에서 실행했다.** 등록된 native `(203,149)` 열, 전체 45입력, 실제 19개 마스크 coverage, AD·FD, 물리 수지 또는 RTTOV 근거로 확대하지 않는다.

이 probe를 macro ON 전용 **공개 A4 CTest**로 고정했다. 출력 468개와 강수 버퍼에 NaN 표식을 먼저 채워 미기록 값을 거부하고, 각 호출 뒤 입력 624개 단어를 `memcmp`로 확인한다. 최종 84파일 소스의 새 격리 macOS 빌드에서 해당 CTest **1/1**, 기존 네 시험을 포함한 전체 연구용 CTest **5/5**가 통과했다. 예상 export **28개**, `-ffp-contract=off`, 시험 assertion 활성, 소스 전후 84파일 SHA와 실제 DSO·loader SHA도 확인했다. 최종 DSO SHA-256은 `829ba6c83040ee80fe5c16160475b67667a343f47b10501a8a969c860763ce78`, 비공개 빌드 영수증 SHA-256은 `39170e43072d43e26c206fd44c3166e2c93a29d3badaaa19d41abb792e0531f2`다. 이 검사는 **합성 입력 한 건의 값 비침습성**이며 native 입력 전체나 중간 미분의 비침습성을 인증하지 않는다. 최종 macro OFF 빌드와 양 플랫폼 hosted CI 결과는 위 현재 판정에 반영했다.

## 같은 최종 소스 빌드 전에 닫을 계약

1. **필수 record manifest:** 원자 ID와 원래 텐서·mask, full event identity, 조건부 존재·비활성 이유, 방향별 JVP/VJP 요구 및 실제 `batch5_abi_core` 출력 형식을 한 스키마로 고정한다. 동적 substep 개수는 같은 호출의 일정 기록에서 검증한다. 여섯 입구 selector 초안이 전체 coverage를 대신하지 않는다.
2. **새 조건의 생산·소비:** 19개 제안 마스크의 실제 피연산자와 `<,=,>`·우선순위, outer/family/substep, 비활성 증거를 source에 연결하고, 버전 올린 receipt → 조건 정규화 → `adapt_many()` → FD 판정까지 합성 교차 반례를 통과시킨다. 현재 합성 bridge의 가상 universe를 실행 자료로 주장하지 않는다.
3. **적용량·측도:** 기존 노드의 활성화·포화조정·열 적용 전후를 함께 보존한다. 침강의 `d_out/d_in`은 gate를 적용한 **알고리즘 진단 항목**과 clamp·저장 잔차로 나누되, 면별 물리적 보존량이라고 부르기 전에 host/ABI 단위와 독립 interface 수지를 확인한다.
4. **실행 인프라:** 재구성한 소스의 macro OFF/ON 빌드·export·assertion·`-ffp-contract=off`를 전용 CI에서 확인하고, 실제 runner·외부 watchdog·loader/DSO 출처·직렬화 비용을 고정한다. 현재 [CI driver](../harness/evidence/native_host_execution_successor_2026-11-13/producer_source_batch6/ci_build.py)는 합성 도구 시험과 양 플랫폼 OFF/ON 빌드·CTest를 통과했다. 이는 미래 native 실행 runner의 검증과 별개다. 소스·정책·필수 항목이 확정된 **별도 `EXECUTION_READY` 계획을 첫 실제 호출 전에 커밋**한다.

필수 기록 또는 같은 호출의 강수·graph 값이 누락되거나, 100회·900초 한도에서 필요한 중간 미분 조회를 완료할 수 없으면 해당 배치를 `INCOMPLETE`로 기록한다. 선택 호출의 설치 DSO는 강수 sidecar가 없으므로 상태 468개 비교만 허용하거나 명시적으로 건너뛰며 다른 호출의 강수를 빌리지 않는다. `scientific_status`와 `physical_unit_status`는 계속 `INCONCLUSIVE`다.
