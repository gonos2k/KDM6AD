# 동일 호스트 열의 실제 계측 실행 준비 점검

이번 점검은 #591에서 수정한 합성 감독자·FD 입력 계약을 **실제 DSO/ABI 생산자**로 연결하기 전에 source, 빌드 자산, 필요한 피연산자를 대조한 결과다. native `(203,149)` 열의 45개 f64 입력·100회 호출·900초 한도는 [기존 계획](../harness/evidence/native_host_preflight_2026-11-12/README.md)에 고정돼 있다. 아래의 첫 격리 빌드는 이력으로 남긴다. 공개 증거 패킷에서 재구성하는 계측 소스와 새 격리 빌드의 현재 범위는 [batch5 소스 보고서](NATIVE_HOST_BATCH5_SOURCE_SCAFFOLD_20261113.md)에 정리했다. **KDM 기호를 호출하거나 모델을 실행하지 않았다.**

## P3 문구 정정

`synthetic_supervisor.py`가 자식의 반환 토큰·정상 종료·전체 시간을 검사한 **다음** 확인 파일을 원자적으로 공개한다. 그 공개가 확정 시점이다. 감독자가 공개 **이전**에 중단되면 확인 파일이 발급되지 않는다. 공개 **직후** 중단되면 이미 검사한 조건에 근거한 확인 파일이 남을 수 있다. 이는 #591의 정상 종료·예산 판정 결함이 아니며, 관련 docstring과 [이전 보고서](NATIVE_HOST_FINALIZATION_AND_SCHEDULE_20261113.md)의 문구를 바로잡았다.

## 실행 가능한 자산과 빠진 연결

기존 설치 f64 Legacy DSO의 SHA-256 `7adcb692…`, 격리 capture DSO의 SHA-256 `eabb607b…`가 #588 계획의 기록과 맞는 것을 파일에서 재확인했다. 격리 source copy는 #591 공개 `libtorch` tree `4db74c83…`를 `git archive`로 만든 후 비공개 연구 경로에 보관했다. CMake에는 `-ffp-contract=off`와 테스트 대상 `-UNDEBUG` 설정이 있다. 이 사실은 **새 계측 빌드의 출처가 확보됐다는 뜻이 아니다.**

| 묶음 | 실제 소스에서 확인한 연결 | 새 실행이 아직 막히는 이유 |
| --- | --- | --- |
| NC=0·PII | 입구 제한, post-melt/post-freeze 재계산, DSD 제한과 `T=TH·PII`, 비열·포화·활성화 값 경로가 존재 | 실제 원시/제한 피연산자, 선택 마스크와 같은 그래프의 살아 있는 접선이 45입력·모든 substep에서 계측되지 않음 |
| Rate–cap | 활성화 비율·raw numerator·NCCN cap과 두 minimum의 source 위치를 찾음 | 일부 피연산자가 inline 식이어서 사후 재계산을 원래 graph 노드로 부를 수 없음. source-order materialization과 비침습성 검토 필요 |
| 침강 7종 | 후보 `falk`, 층·위층의 `d`와 저장 상태 소비 지점이 존재 | 후보 flux나 cap 인자가 실제 제한 후 출발·도착량이라는 증거 없음. 독립 cap, 상단 projection, 바닥 유출과 저장 반올림을 함께 기록해야 함 |
| 총수분·강수 | `FnResult`에는 총강수 텐서가 있고 f64 C ABI는 상태 468개만 포장 | 총강수의 same-call 값·live 접선을 별도 테스트 sidecar로 보존해야 함. dry/moist 밀도·강수 측도가 미승인 |
| 명명 과정·열·BG | 일부 제한율, `t_pp/t_final`, `cpm/xl`, `bg/rhox` 값이 있음 | 과정별 제한 후 실제 적용량·반올림된 donor/recipient, 잠열·체적 수지 측도가 아직 정의·계측되지 않음 |

적용 수송량은 종·층·substep별로 **실제 출발량, 실제 도착량, projection 잔차와 바닥 유출**을 별개로 기록해야 한다. 두 cap이 독립적으로 적용될 수 있으므로 자동 상쇄를 가정하지 않는다. 활성화의 매끄러운 적용 분기에서 `A=ncact·dt`의 NC/NCCN 반대 부호와 `M=pcact·dt`의 qv/qc 전달은 출발점이지만, 증발 반환·reservoir floor/cap·cleanup과 측도가 실제 수지를 바꿀 수 있다. `BG=brs` 체적 좌표를 QG 질량과 곧바로 같다고 두지 않는다. JVP/VJP는 **실제로 적용한 양·층 가중치**의 곱·연쇄 규칙으로 도출하고 동일 그래프 내적 및 분기 내부 값 차분과 별도로 대조해야 한다.

## 소스 초안과 차단 상태

비공개 격리 사본에 macro-gated C++ sidecar **초안**을 만들고 runtime·coordinator·thermo의 일부 원시 값과 mask 지점에 좁은 hook을 연결했다. 이는 28개 측정 항목이나 19개 새 마스크의 완성, 모든 substep의 coverage, 실제 침강 적용량의 귀속을 뜻하지 않는다. 격리 DSO의 기호 export와 loader 경로는 확인했지만, graph 수명·출력 비침습성과 실제 호출 출처는 아직 입증되지 않았다. 비공개 runner의 등록 실행 진입점도 차단 상태다.

첫 좁은 소스의 정적 hook 대조는 **191개 원자 항목 중 45개**에 직접 연결 가능한 조각을 찾았다. 이후 소스 확장과 함께 수행한 새 감사에서는 **107개**로 늘었다. 두 숫자 모두 실제 호출에서 방출된 값·mask 또는 live 접선의 수가 아니다. 새 감사의 공개 재생 범위는 [batch5 소스 보고서](NATIVE_HOST_BATCH5_SOURCE_SCAFFOLD_20261113.md)와 그 패킷에 구분해 둔다. 28개 요구 그룹은 여전히 모두 차단 상태다.

격리 합성 빌드는 `KDM6_BATCH5_RESEARCH_CAPTURE=ON`, `-ffp-contract=off`, 테스트의 `-UNDEBUG` 조건에서 성공했다. 39층의 서로 다른 값을 사용한 top-first/bottom-first 원시 값·층 메타데이터, 잘못된 shape, thread 분리, graph 모드 값 읽기 거부를 CTest에서 확인했다. 합성 시험 영수증 SHA-256은 `de10381719d44d2e69bf83d9347d855073a6cdea9180e4568d5241e4d6b86257`이다. 이어 만든 격리 DSO SHA-256은 `92338de6a2f695c3dc49c8bbf7871bc705e775200fbcbffdb5f9b72ad02e3c75`이고, 다섯 batch5 기호와 기존 f64 joint JVP/VJP 기호의 export 및 loader 경로를 확인했다. DSO 영수증 SHA-256은 `cacd8b1bc2817139cb940b50ffa56f79f5f254716ee81dfeddec96a08e95037e`이다. 두 영수증은 비공개 격리 빌드 자료이며 **실제 KDM 출력·비침습성·중간 접선의 검증 자료는 아니다.**

과거 계측 소스의 `testing::record_stage`는 graph-connected 텐서를 보존한 선례지만, `stage.field`만으로 만든 map은 반복 substep의 값을 덮어쓸 수 있다. 새 초안은 순서 있는 event와 입력·호출·outer loop·substep 계열/순번·열·층·stage·field를 기록한다. 현재 C ABI는 버전·크기를 검사하는 **값 전용** 복사 경로만 제공하며 graph 모드의 원시 값 읽기를 거부한다. 21개 실제 표현 방향의 중간 JVP/VJP를 꺼내는 계약과 graph-handle 수명 검증은 아직 없다.

[후속 successor 초안](../harness/evidence/native_host_execution_successor_2026-11-13/README.md)은 #588 부모 계획, #591 정책 버전, 45개 입력과 100개 호출을 유지한다. 소스 diff, 원자적 tensor catalog, 컴파일러, 새 DSO·의존성, loader, 외부 watchdog의 필수 hash는 모두 비어 있고 상태는 `DRAFT_BLOCKED`다. 합성 구조 시험이 통과해도 `EXECUTION_READY`로 바꾸지 않는다. 특히 새 19개 마스크는 #586의 1,170개 기준 마스크를 검사하는 현재 adapter가 수용하지 못하므로, 생산자·스키마·계획의 후속 버전을 **첫 실제 호출 전에 함께 고정**해야 한다.

초안의 [원자적 소스 목록](../harness/evidence/native_host_execution_successor_2026-11-13/atomic_catalog_draft.json)은 28개 요구 그룹을 **191개 source-site·피연산자·차단 사유**와 19개 제안 마스크로 분해하고, 공개 `libtorch` 소스 10개 archive의 정확한 줄과 SHA로 대조한다. QV/QC/QR/QI/QS/QG 입출력, NC의 서로 다른 rate·적용 항, 7종 침강의 최상층/내부 후보와 출발·도착·바닥의 미해결 분리를 포함한다. 이 목록의 순서는 **카탈로그 순서**이지 실행 시각의 연산 순서가 아니다. 모든 새 기록은 아직 `BLOCKED`이며, inline minimum 노드와 실제 적용 수송량은 `UNRESOLVED`다. 초안 SHA를 successor에 연결했지만 실행 가능한 원자적 field-catalog 해시 칸은 계속 비어 있다.

[의미를 정정한 v2 패치](../harness/evidence/native_host_execution_successor_2026-11-13/atomic_catalog_consumer_patch_v2.json)는 과거 `consumer.location` 191개를 먼저 설명용 `context_location`으로 분리한다. 전체 v2 목록은 해시로 고정된 v1과 작은 패치에서 결정적으로 재구성하고 결과 SHA까지 확인한다. 같은 함수의 소스 사용이 확인된 `dep_sum_c` → `xlwork2_cold`와 `t_new` → 반환 상태 두 건만 `VERIFIED_SOURCE_USE`로 표시한다. 나머지 189개 원자 항목과 제안 마스크 19개의 실제 소비자는 `UNVERIFIED`다. 두 건도 **소스 사용 관계**이지 실행된 graph·계측·미분 검증이 아니다. 기존 successor의 실행용 field-catalog pin은 계속 비어 있다.

검증기는 제출된 목록 전체를 고정 SHA의 원본과 비교해 다른 주석 줄을 소비 지점으로 재해시한 자료도 거부한다. 이는 **현재 초안의 참조가 바뀌지 않았다는 보장**이며, 그 소스 줄이 실제 실행 graph의 올바른 원인·미분 노드라는 독립 증명은 아니다. 다음 카탈로그 개정에는 새 소스 핀과 검토가 필요하다.

## 다음 한 빌드를 시작할 조건

1. 각 요구 그룹을 **원자적 source tensor·선택 피연산자·mask·층/열/outer loop/substep identity**로 분해하고, 값 전용 기록과 graph-connected live JVP/VJP의 수명·비활성 규칙을 소스에 대응시킨다. 불명확한 물리 측도는 `BLOCKED`로 유지한다.
2. 그 카탈로그를 반영한 하나의 격리 계측 소스·C ABI 생산자·확장된 condition schema를 함께 검토한다. macro-off 원래 source-order와 macro-on 출력의 원시 비트 비침습성, graph 값/JVP/VJP와 종료·thread·오류 경로를 확인한다.
3. 독립 build/DSO/Torch/loader hash와 실제 외부 watchdog을 확보한 **별도 `EXECUTION_READY` 계획을 Git 커밋으로 먼저 고정**한다. 이후에만 45입력의 100회 한도·900초 호출을 시작하고 실패·미실행을 모두 기록한다.

이 조건을 만족하기 전에는 NC·PII의 국소 FD 합격, 질량·수농도·열·체적 수지 또는 전체 host·GK2A–RTTOV 민감도를 주장하지 않는다. `scientific_status`와 `physical_unit_status`는 `INCONCLUSIVE`다.
