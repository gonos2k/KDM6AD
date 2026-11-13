# 동일 호스트 열 batch5 계측 소스의 현재 범위

이 문서는 #592의 `DRAFT_BLOCKED` successor를 실제 실행 자료로 승격하지 않고, 그 이후 준비한 **공개 macro-gated 계측 소스**의 구현·검증 범위를 기록한다. 기준 입력은 native `(203,149)`의 39층, 624개 f64 단어이며 기존 계획은 45입력·최대 100호출·900초를 유지한다. 이번 작업에서 KDM/WRF/RTTOV 호출은 수행하지 않았다.

## 소스와 빌드

`KDM6_BATCH5_RESEARCH_CAPTURE`는 기본 `OFF`다. `runtime.cpp`, `coordinator.cpp`, `thermo.cpp`, `satadj.cpp`, `progb.cpp`, `sedimentation.cpp`의 계측 분기를 제거한 소스가 부모 공개 코드와 바이트 단위로 같음을 대조했다. 계측 `ON`은 원래 텐서·선택 피연산자와 조건 mask를 보존한다. 이 소스 대조만으로 `ON`의 원시 출력 비침습성은 입증되지 않는다.

격리 macOS arm64 빌드에서 C++ 합성 시험 `batch5_sidecar`와 `batch5_intermediate_ad`가 **2/2 통과**했다. `-ffp-contract=off`와 테스트의 `-UNDEBUG`를 컴파일 명령에서 확인했다. 공유 DSO를 빌드해 batch5 값 복사 기호 다섯 개와 기존 f64 joint AD 기호의 export를 확인하고, `dlopen`만 수행해 로드된 Torch 경로를 기록했다. 격리 DSO SHA-256은 `db100f6f4be94724fbc80b021c613af63fc12cbb4158330ea54f6c6a48b383d5`, 비공개 빌드 영수증 SHA-256은 `38b329c586da1841810367c829c0c15d326a499ecfa423b80b2dbdd7beec6f7b`이다. 운영 설치 DSO는 변경하지 않았다. 공개 CI의 양 플랫폼 macro `ON` 빌드는 아직 확인하지 않았다.

## 무엇을 기록할 수 있는가

현재 C ABI의 batch5 v1 sidecar는 값 전용 호출에서 원시 f32/f64/Boolean 단어와 버전·크기를 검사한 POD 메타데이터를 복사한다. 입력·호출·outer loop·substep 계열/순번·열·층·stage·field·event 순번을 구분하고, B=1·K=39가 아닌 층 기록을 거부한다. graph 모드의 값 복사는 거부한다. `FnResult` 총강수 텐서는 반환 직전 별도로 보존하며, 침강은 `falk`, 제한된 `d`, 전후 상태와 주·빙상 gate를 기록한다. 눈·싸락눈 강수는 총강수의 부분량으로 구분한다.

같은 소스에 **내부 C++ 합성 시험용** 중간 JVP kernel을 추가했다. 16개 state+forcing leaf와 방향, 1–64개 부동소수 scalar를 받아 double reverse로 접선을 계산하며 `CONNECTED`, `NO_GRAPH_PATH`, `UNCONNECTED`를 구분한다. 이 kernel은 아직 sidecar record와 실제 C ABI graph handle·seed·cotangent identity에 결합되지 않았다. 합성 시험 통과를 21개 실제 표현 방향의 중간 접선 검증으로 세지 않는다.

## 공개 소스 감사와 차단 조건

현재 [source-only 감사](../harness/evidence/native_host_execution_successor_2026-11-13/README.md)는 298개 guarded hook callsite와 331개 가능한 stage/field 라벨을 검사한다. 191개 카탈로그 항목 중 **107개에서 직접 hook 조각**을 식별했고 84개는 직접 연결이 미확정이다. 제안 마스크 19개 모두에 부분 조각이 있으나 완성·실행 검증은 없다. 특히 7종 침강의 실제 출발·도착·바닥 유출에 해당하는 **21개 항목**은 후보 flux와 공동 clamp만으로 귀속할 수 없다. 모든 28개 요구 그룹은 `BLOCKED`다.

소스의 침강 갱신은 top-first 층에서 후보 `falk`를 저장하고, 출발 후보 `d_k`와 위층으로부터의 도착 후보 `d_above`를 **독립적으로** 제한한 뒤 `clamp(state_k-d_k+d_above,0)`을 적용한다. 따라서 둘의 값이나 접선이 곧바로 보존 수지의 실제 적용량이 되지 않는다. 수농도와 `BG=brs`의 물리 측도도 미확정이다. 현재 자료로 질량·수농도·체적 보존을 판정하지 않는다.

값 전용 runner의 등록 실행 진입점은 계속 차단된다. 합성 검사는 계획된 호출 순서·입력 624단어와 sidecar의 begin/copy/clear, 실패 정리, 비유한 중간값 거부를 확인한다. 실제 호출에 앞서 새 source/DSO/loader·외부 watchdog·필수 필드와 방향별 live record 계약을 하나의 커밋된 `EXECUTION_READY` 후속 계획으로 고정해야 한다. 그다음 같은 입력의 capture off/on 468개 출력 원시 비트와 graph/FD 결과를 대조해야 한다. 현재 `scientific_status`와 `physical_unit_status`는 `INCONCLUSIVE`다.
