# 합성 예산 실행기와 다음 계측 계약의 보완

이 묶음은 #589 검토에서 재현한 **반복 종료 신호**와 **시간 예산 누락** P2 두 건을 고치고, 다음 native `(203,149)` 열 계측의 실행 영수증과 FD 입력에 필요한 조건·필드 계약을 더 구체화한다. #588의 [45개 입력](../harness/evidence/native_host_preflight_2026-11-12/README.md), 100회·900초 한도와 Legacy f64 B=1 물리 경로는 그대로다. **새 KDM·WRF·RTTOV 호출이나 계측 DSO 빌드는 하지 않았다.**

## 반복 신호와 전체 시간 예산

`execute_budget.py`는 최초 자산 검증 **전에** 단조시계로 예산을 시작한다. 첫 종료 신호는 취소를 요청하고, 정리 중 들어온 추가 신호는 번호를 기록하되 또 예외를 던져 정리를 끊지 않는다. TERM 유예, SIGKILL, leader 회수, 남은 그룹 확인을 끝내고 실행 중 호출을 `failed`, 나머지를 미시작/건너뜀으로 기록한다.

영수증은 먼저 `INCOMPLETE` 임시 상태로 원자 저장한다. 최종 직렬화·`fsync` 뒤에도 시간을 검사하고 상한을 넘으면 보정된 `INCOMPLETE`를 저장한다. 합성 완료는 영수증의 SHA와 계획 SHA를 묶은 별도 `completion.json`이 있을 때만 검증 가능하다. 보정 저장 실패는 `FinalReceiptError`로 반환되며 완료 표식을 남기지 않는다. 표식 작성 자체가 늦어 상한을 넘는 경우에도 표식을 제거하고 `INCOMPLETE`로 바꾼다. OS 스케줄링이나 파일시스템 지연을 물리적으로 중단시킨다는 약속은 아니며, **초과 사실을 완료로 잘못 기록하지 않는** 계약이다.

짧은 합성 예산에서 최초 검증이나 마지막 저장을 각각 2.2초 지연시킨 반례, TERM 유예 중 약 0.1초 간격의 두 신호, 보정 저장 실패, 표식 시간 초과, 잔존 프로세스 그룹을 시험했다. 두 신호 사례는 자식 그룹 정리와 첫 호출 실패·남은 호출 미시작을 확인한다. 생산 실행은 여전히 무조건 차단되고, 합성 모드의 SHA 고정 스텁만 사용한다.

## 미래 영수증에서 FD 입력까지의 바이트 계약

`receipt_schema.py`는 고정 계획의 45개 capture-on 입력마다 **#586 기준 capture의 Boolean 1,170개와 일정 195개 식별자**를 가진 조건 자산을 요구한다. runtime/one-step/substep/열/층/stage/field/ordinal을 구분하고, 같은 입력의 제출된 호출 순번·파일 SHA와 연결한다. 다른 층·substep의 거짓 마스크를 비활성 값의 근거로 사용할 수 없다. 새 계측에서 추가할 19개 마스크는 아직 계측 소스와 함께 고정되지 않았으므로 이 버전의 adapter가 임의로 받아들이지 않는다.

`fd_input_adapter.py`는 이 조건 자산, 계획 입력 624단어, capture off/on 출력 468단어와 **21개 실제 표현 방향의 JVP 출력**을 합쳐 고정 계획의 중심·끝점·`+2h`별 FD 입력을 구성한다. 큰 PII 진단 보폭의 교차와 작은 판정 보폭의 교차를 각각 검출하는 합성 시험, 빠진 조건·다른 호출 조건·재해시한 출력 불일치 거부 시험을 포함한다. 이는 **기준 capture에 기록된 분기 집합**만 다루고, 모든 물리 분기의 안정성을 인증하지 않는다. 중간 과정의 effective 접선, 실제 DSO/로더 실행과 물리량 측도도 미검증이므로 adapter 결과는 `fd_gate_ready=false`, `NOT_ELIGIBLE_UNVERIFIED_PROVENANCE`다.

## 구체적인 계측 필드의 현재 상태

[소스 고정 필드 계약](../harness/evidence/native_host_preflight_2026-11-12/field_contract.json)은 공개 `libtorch` 소스 10개를 별도 SHA 고정 archive로 보존하고, 일곱 그룹에 **28개 값·접선 측정 항목과 19개 제안 마스크**를 소스 표현식·소비 지점과 연결한다. 현재 계획에서 모든 새 항목은 **`BLOCKED`**다. NC 입구 제한·post-melt/post-freeze 재계산·마지막 DSD 제한, PII→온도/비열/포화/활성화, 실제 rate–cap 두 피연산자, 7종 침강의 최상층 flux와 내부 상태 소비 지점, `FnResult` 총강수, 열·BG 체적 항목을 구분했다.

기존 51-stage 값 CSV는 이 항목들의 모든 live AD 텐서나 실제 적용 departure/arrival를 포함하지 않는다. 이 필드 계약은 실행 소스의 위치를 찾은 **계측 설계**이며, 설치 DSO의 빌드 계보나 새 항목의 실행·물리 단위 승인 근거가 아니다. 특히 저장된 후보 sedimentation flux를 실제 제한 후 이동량으로 바꾸어 읽거나 BG를 QG 질량으로 등치하지 않는다. 새 19개 마스크와 중간 접선이 준비되면 source·build·field-contract 후속 버전을 먼저 고정해야 한다.

## 남은 완료 조건

현재 `SPEC_ONLY` 계획의 DSO SHA와 실행 영수증은 비어 있다. 실제 호출을 허용하려면 별도 등록한 `EXECUTION_READY` 후속 계획, 격리 DSO·ABI 생산자, 빌드·로더·입출력 출처와 계측 on/off 원시 출력 비침습성이 필요하다. 그런 자료가 생겨도 단위·적용 수지, 전체 호스트 forcing 연쇄, native 39/40층 RTTOV BT·비용 미분은 각각 판정해야 한다. `scientific_status`와 `physical_unit_status`는 계속 `INCONCLUSIVE`다.
