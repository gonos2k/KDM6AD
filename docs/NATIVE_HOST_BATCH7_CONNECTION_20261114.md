# Native host batch7: 입력·기록 연결의 현재 경계

이 문서는 [#593의 84파일 A4 합성 소스](NATIVE_HOST_BATCH6_CAPTURE_CONTRACT_20261114.md) 뒤에 준비한 연구용 연결을 기록한다. 운영 `libtorch/`·`oracle/`의 물리 구현은 바꾸지 않았다. 등록된 native `(203,149)` 열의 **45입력·필수 93호출·전체 최대 100호출 / 900초** 배치는 실행하지 않았다. successor는 `DRAFT_BLOCKED`, 과학·물리 단위 상태는 `INCONCLUSIVE`다.

## 공개 자료에서 연결한 것

| 단계 | 현재 검사 | 남은 근거 |
| --- | --- | --- |
| FD 역할과 입력 | [v2 소비자](../harness/evidence/native_host_execution_successor_2026-11-13/condition_consumer_v2.py)는 기존 receipt의 gate 입력을 재검증하고, 중심·끝점 역할을 고정된 624단어 입력·input ID·capture 호출 순서에 대조한다. ID·순서 교환은 FD 전에 거부한다. | 새 v2 payload 전체를 재표기·재해시한 자료의 실행 출처는 독립 인증되지 않는다. 직접 제출한 v2 payload에서는 gate 입력을 내지 않고 `UNRESOLVED`로 중단한다. |
| 같은 호출 복사 | [opt-in ABI 경로](../harness/evidence/native_host_execution_successor_2026-11-13/batch5_abi_core.py)는 capture-on의 live context를 지우기 전 v2 원시 기록을 복사하고, graph에서는 같은 handle·token의 metadata만 복사한다. 실패 시 기존 정리·순서 차단을 유지한다. | fake ABI 검증 범위다. 실제 A7 DSO에서 복사한 전 호출 자료나 loader 출처는 아직 없다. |
| 영수증 자산 | [v3 bridge](../harness/evidence/native_host_execution_successor_2026-11-13/condition_receipt_bridge_v3.py)는 same-call 복사 결과의 입력 624단어·출력 468단어·강수·DSO 표기·기록 순서를 고정 계획의 45 capture-on 슬롯과 연결한다. | 해시와 DSO 표기는 여전히 제출자 주장이다. 완전히 다시 작성한 일관된 자료를 분별하지 못하므로 `SPEC_ONLY / NOT_ELIGIBLE`을 유지한다. 혼합 one-step phase의 FD 투영은 `UNSUPPORTED`다. |
| 단계·selector | [phase 초안](../harness/evidence/native_host_execution_successor_2026-11-13/phase_selector_draft.py)은 98개 v2 소스 위치와 별도 A7 v1 필드 18개를 고정하고, 검토된 family/step·좌표·ordinal 구조를 검사한다. | 모든 호출·층·substep에서 실제 방출됐는지, optional/미실행의 이유, 원래 조건과 같은 source인지에 대한 완전한 census는 없다. 결과는 `STRUCTURE_ONLY_INCOMPLETE`다. |
| graph checkpoint | 중복된 rain/primal 조회를 하나로 줄이고 같은 selector의 서로 다른 seed가 primal cache를 공유하게 했다. 동일 selector·seed/cotangent 요청의 중복은 ABI 호출 전에 거부한다. | 실제 KDM graph에서 중간 primal·JVP·VJP와 독립 FD를 연결한 결과는 없다. |

후속 phase 구조 보강은 고정된 runtime 경로에서 microphysics 기록의 **`one_step_call == outer + 1`**을 요구한다. 호출·epoch·반복·ordinal은 Boolean을 배제한 정확한 정수이며 C++ `uint64_t` 범위를 넘을 수 없다. 소스에서 확인되지 않은 phase는 계속 거부한다. 이 검사는 입력 구조의 모순을 막지만 실제 기록의 완전한 동적 census는 아니다.

소스 계보는 기존 A4 84파일에 [A5 조건 hook 층과 A7 선택량 층](../harness/evidence/native_host_execution_successor_2026-11-13/producer_source_batch6_layers/README.md)을 순서대로 적용한다. A5는 warm/cold의 **원래 두 소비 Boolean**과 scalar·loop 제어값 14곳을, A7은 일곱 수송 변수의 outer gate가 선택한 상태·fall 및 별도의 ProgB BG 재설정 18곳을 보존한다. A5/A7은 추가 원시 기록 지점이며 완료된 19조건 동적 coverage나 실제 보존 flux 수가 아니다. 마지막 층은 여전히 84파일이고 macro OFF에서 이전 소스로 돌아가는 정적 검사를 통과했다.

격리 macOS A5+A7 소스는 DSO 빌드·로드와 export **28개**, 모델 미진입 연구용 CTest **4/4**를 통과했다. 소스 snapshot SHA-256은 `033558eb6f771beb76d6ba8ebbc1aa126c4abafd4eb6d53dcabd3361cb8a1038`, DSO SHA-256은 `175a75c7b33638d802fe3d28144d1301a4fc6ac86f79fabfc433b666b0b4d6b8`, 비공개 빌드 영수증 SHA-256은 `e397671ef60139064cd135fcfc7ec156c153a07420c3380642d0641440eaacb4`다. 첫 CTest 명령은 PATH에 실행 파일이 없어 시험 전에 실패했고, 절대 경로 재실행 **4/4**가 영수증에 남아 있다.

다음 전용 CI 후보는 임시 빌드가 삭제되기 전 macro ON **DSO·미실행 parity 실행 파일·컴파일 명령·JUnit·최종 A7 소스 snapshot·이전 층의 해시 목록·빌드 receipt**를 최대 **64 MiB**의 아티팩트로 보존한다. 업로드 파일이 없으면 CI가 실패한다. 별도 읽기 검증기는 각 파일의 경로·크기·해시와 독립적으로 제공한 source·바이너리·OS/아키텍처·Python ABI·Torch·컴파일러·빌드 옵션을 비교하고 `VERIFIED_BUILD_ASSET_ONLY / NOT_ELIGIBLE`로 끝난다. 이전 층의 전체 파일 바이트는 보존 대상이 아니라 해시 목록이며, 아티팩트 검증은 실제 모델 실행을 인증하지 않는다. 이 보존 경로의 **hosted 결과와 실제 용량은 아직 확인되지 않았다.**

## 실행을 보류한 이유와 다음 완료 조건

이전 A4 소스의 합성 value-only parity CTest **1건**은 통과했지만, 바뀐 A5+A7 DSO에는 그 결과를 소급하지 않는다. 현재 전용 CI는 A7 parity 실행 파일을 **빌드·목록 검사만** 하고 `CONTAINMENT_PENDING`으로 기록하며, macro ON의 모델 미진입 CTest **4개**만 실행하도록 계획했다. 호스트·RTTOV 호출은 없다.

실제 graph 시험을 시작하려면 다음을 같은 후보에서 확인해야 한다.

1. 독립 watchdog이 worker의 실제 프로세스 그룹을 **실행 전** 인수하고 wall·RSS·반복 종료 신호·감독자 강제 종료 시 잔존 그룹을 스텁에서 처리한다. 후보 기록과 완료 확인은 분리한다. 현재 Darwin 초안에는 이 외부 containment와 확인 파일이 없어 graph/value matrix를 실행하지 않았다.
2. 계획 입력·실제로 로드한 DSO·Torch·빌드 소스의 해시, 35개 이하 합성 호출의 시작·완료·실패·미시작 영수증을 결합한다. 제출자가 모두 다시 쓴 해시만으로 실행을 인증하지 않는다.
3. 같은 selector·층·graph handle에서 primal·JVP·VJP를 읽고, **실제 f64에 표현된 입력 간격**의 독립 FD를 두 안정 보폭에서 비교한다. 기록된 조건·substep이 바뀌거나 필수 항목이 없으면 `INCONCLUSIVE`로 남긴다. 지금의 fixture 초안은 source/mock 시험만 통과했고 KDM graph 호출은 없다.
4. A7 수송 자료는 후보→독립 cap→outer 선택→ProgB reset의 **알고리즘 항**으로 먼저 연결한다. 실제 면별 departure/arrival·바닥 export, 밀도·수농도·BG 체적의 단위를 확인하기 전에는 물리 보존이나 미분 수지 합격으로 읽지 않는다.

이 조건과 선택된 synthetic graph 시험이 끝난 뒤에야 별도 `EXECUTION_READY` 계획을 첫 native 호출 전에 커밋할 수 있다. 현재 저장한 코드·소스·합성 시험은 그 승인 근거가 아니다.
