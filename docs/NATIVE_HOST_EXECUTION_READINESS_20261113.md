# 동일 호스트 열의 실제 계측 실행 준비 점검

이번 점검은 #591에서 수정한 합성 감독자·FD 입력 계약을 **실제 DSO/ABI 생산자**로 연결하기 전에 source, 빌드 자산, 필요한 피연산자를 대조한 결과다. native `(203,149)` 열의 45개 f64 입력·100회 호출·900초 한도는 [기존 계획](../harness/evidence/native_host_preflight_2026-11-12/README.md)에 고정돼 있다. **새 계측 DSO를 빌드하거나 모델을 실행하지 않았다.**

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

비공개 격리 사본에 macro-gated C++ sidecar **초안**을 만들었지만 물리 source의 실제 측정 지점에는 연결하지 않았다. 새 DSO는 빌드하지 않았고, sidecar의 export·thread·graph 수명·비침습성도 검증하지 않았다. 비공개 runner 역시 기존 C ABI의 buffer·JVP/VJP 호출 준비와 합성 watchdog만 포함하며 등록 실행 진입점은 차단한다. 이 초안의 존재를 28개 측정 항목이나 19개 새 마스크의 구현으로 집계하지 않는다.

[후속 successor 초안](../harness/evidence/native_host_execution_successor_2026-11-13/README.md)은 #588 부모 계획, #591 정책 버전, 45개 입력과 100개 호출을 유지한다. 소스 diff, 원자적 tensor catalog, 컴파일러, 새 DSO·의존성, loader, 외부 watchdog의 필수 hash는 모두 비어 있고 상태는 `DRAFT_BLOCKED`다. 합성 구조 시험이 통과해도 `EXECUTION_READY`로 바꾸지 않는다. 특히 새 19개 마스크는 #586의 1,170개 기준 마스크를 검사하는 현재 adapter가 수용하지 못하므로, 생산자·스키마·계획의 후속 버전을 **첫 실제 호출 전에 함께 고정**해야 한다.

초안의 [원자적 소스 목록](../harness/evidence/native_host_execution_successor_2026-11-13/atomic_catalog_draft.json)은 28개 요구 그룹을 **191개 source-site·피연산자·차단 사유**와 19개 제안 마스크로 분해하고, 공개 `libtorch` 소스 10개 archive의 정확한 줄과 SHA로 대조한다. QV/QC/QR/QI/QS/QG 입출력, NC의 서로 다른 rate·적용 항, 7종 침강의 최상층/내부 후보와 출발·도착·바닥의 미해결 분리를 포함한다. 이 목록의 순서는 **카탈로그 순서**이지 실행 시각의 연산 순서가 아니다. 모든 새 기록은 아직 `BLOCKED`이며, inline minimum 노드와 실제 적용 수송량은 `UNRESOLVED`다. 초안 SHA를 successor에 연결했지만 실행 가능한 원자적 field-catalog 해시 칸은 계속 비어 있다.

검증기는 제출된 목록 전체를 고정 SHA의 원본과 비교해 다른 주석 줄을 소비 지점으로 재해시한 자료도 거부한다. 이는 **현재 초안의 참조가 바뀌지 않았다는 보장**이며, 그 소스 줄이 실제 실행 graph의 올바른 원인·미분 노드라는 독립 증명은 아니다. 다음 카탈로그 개정에는 새 소스 핀과 검토가 필요하다.

## 다음 한 빌드를 시작할 조건

1. 각 요구 그룹을 **원자적 source tensor·선택 피연산자·mask·층/열/outer loop/substep identity**로 분해하고, 값 전용 기록과 graph-connected live JVP/VJP의 수명·비활성 규칙을 소스에 대응시킨다. 불명확한 물리 측도는 `BLOCKED`로 유지한다.
2. 그 카탈로그를 반영한 하나의 격리 계측 소스·C ABI 생산자·확장된 condition schema를 함께 검토한다. macro-off 원래 source-order와 macro-on 출력의 원시 비트 비침습성, graph 값/JVP/VJP와 종료·thread·오류 경로를 확인한다.
3. 독립 build/DSO/Torch/loader hash와 실제 외부 watchdog을 확보한 **별도 `EXECUTION_READY` 계획을 Git 커밋으로 먼저 고정**한다. 이후에만 45입력의 100회 한도·900초 호출을 시작하고 실패·미실행을 모두 기록한다.

이 조건을 만족하기 전에는 NC·PII의 국소 FD 합격, 질량·수농도·열·체적 수지 또는 전체 host·GK2A–RTTOV 민감도를 주장하지 않는다. `scientific_status`와 `physical_unit_status`는 `INCONCLUSIVE`다.
