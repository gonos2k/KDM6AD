# Batch6 조건 기록 v2 계약 — 실행 전 초안

이 문서는 #588의 고정 조건 계약(**1,170 Boolean·195 일정 키**)을 변경하지 않고, #593의 새 sidecar와 제안 마스크 19개를 FD 판정에 연결할 후속 스키마를 정의한다. [합성 bridge](../harness/evidence/native_host_execution_successor_2026-11-13/condition_bridge_v2.py)는 분기 교차 전파를, 별도 [v2 소비자 초안](../harness/evidence/native_host_execution_successor_2026-11-13/condition_consumer_v2.py)은 역할·좌표·동적 census·누락 차단을 시험한다. 후자는 호출자가 선언한 site와 인과 관계를 검사하므로 실제 소스 관계의 증거가 아니다. 실제 마스크 생산·receipt·`adapt_many()` 소비는 아직 연결되지 않아 상태는 `DRAFT_BLOCKED`·`NOT_ELIGIBLE`이다.

## 기록의 역할과 좌표

각 원자 기록은 `CONSUMED_BOOL_TENSOR`, `DIAGNOSTIC_COMPARISON`, `OPERAND`, `CONTROL_SCALAR`, `NOT_EVALUATED` 중 하나의 **역할**을 갖는다. `clamp`나 `minimum` 주위에서 추가 계산한 `<,=,>` 비교는 원래 연산자가 소비한 Boolean이라고 부르지 않는다. 원래 Boolean이 `where`에 들어가는 경우에는 실제 사용한 그 텐서를 보존한다. 입력·mode·runtime/one-step 호출·outer loop·family·substep 번호·stage·source hook ID·field·event ordinal을 함께 기록한다.

`scope=layer`는 B=1/K=39의 실제 층과 top-first `k_zero`, bottom-first `39−k_zero`를 기록한다. `scope=column`은 B=1이고 층 번호가 없다. `scope=scalar`의 C++ 제어값·threshold도 가짜 39층을 만들지 않는다. scalar에는 원래 선언 dtype·원시 단어와 **연산 시점의 cast 후 dtype·단어**를 구분한다. `op_f32`, `midpoint_trace`, `dtcld`, `n`, EPS 및 각 cap 상수가 여기에 해당할 수 있다. 값 0, 비활성, 미실행은 서로 다른 상태다.

## 존재 조건과 일정

같은 호출에서 저장한 실제 `loops`, main/ice의 `mstepmax`와 층별 `mstep`, outer·family gate로 **예상 substep 집합**을 만든다. `n=1..mstepmax`의 연속성, 해당 층의 원래 gate, 필수 record의 층별·반복별 개수와 ordinal을 검사한다. 바깥 store gate가 비활성이라도 침강 candidate 연산은 그 전에 실행될 수 있고, preamble은 reslope 경로에서 반복될 수 있다. 따라서 비활성 store를 후보 연산 미실행으로 바꾸거나 source 줄당 기록 1개를 가정하지 않는다.

`NOT_EVALUATED`는 같은 호출·outer/family/n/층의 **원인 predicate 또는 optional 입력 부재**를 가리키는 검증된 이유가 있을 때만 허용한다. 누락 행을 false나 0으로 채우지 않는다. 요청되지 않은 기록, 중복 identity, 일정에 없는 n, 끊긴 ordinal, 다른 호출에서 빌린 mask는 거부한다.

현재 C++ v2 초안의 `NOT_EVALUATED`는 같은 scope의 소비 Boolean이 거짓일 때의 참조만 표현하며, optional 입력이나 반복 미진입을 그 값으로 꾸며 내지 않는다. v2 외부 읽기는 같은 호출의 forward가 성공 확정된 뒤에만 가능하고, raw scalar control의 복사 성공은 유한성이나 물리적 의미의 승인과 구분한다. Python 소비자 초안은 해당 C ABI 결과와 아직 연결되지 않았으며, 그룹별로 선언한 소비 Boolean 또는 진단 비교의 관측이 없으면 국소 수치 일치 태그를 차단한다. 진단 비교의 변화도 교차로 전달하되 원래 연산의 소비 Boolean으로 표시하지 않는다. 현재의 단일 `event_ordinal=0`·main/ice 예시 census 역시 실제 반복 source hook 전체의 수를 인증하지 않는다.

## 19개 제안 마스크의 구현 경계

현재 소스에 이름 있는 실제 Boolean이 있는 예는 NC snap의 `nc_orig>=ncmin`(optional이 있을 때), lambda의 `active`·하한·상한 선택, DSD·cleanup gate, satadj의 `is_super`·`is_sub_with_cloud`, main/ice store gate와 ProgB `active`·`zero_den`이다. 이를 **동일 텐서**와 정확한 invocation으로 보존한다.

반면 NC/NCCN 입구 clamp, 온도 floor, safe-pow EPS floor, 활성화 raw-rate clamp와 NCCN 비음수 clamp에는 원래 소비되는 독립 Boolean이 없다. 원시 피연산자·effective threshold와 추가 `<,=,>` 진단값을 구분해 남긴다. 포화압 `minimum`은 실제 두 피연산자를 보존하고 비교는 진단으로 분리한다. satadj의 inline min/max 피연산자, warm/cold 비교, ProgB의 dtype별 밀도 경계는 원래 연산 순서에서 **한 번만 materialize하고 그 같은 텐서를 원래 소비 연산에 전달하는 변경**이 필요한지 소스별로 검토한다. 변경 후에는 macro OFF 동일성, macro ON의 f32/f64 원시 출력 비침습성, tie·JVP/VJP·독립 방향차분을 별도로 확인한다. 19개는 umbrella ID이며 substep당 Boolean 19개를 자동 생성한다는 의미가 아니다.

현재 추가한 45개 진단 기록은 기존 값·마스크 hook의 일부 비교를 **별도로 다시 계산**하므로 계측 비용과 보존 메모리가 증가할 수 있다. 원래 산술은 바꾸지 않았지만 출력 비침습성은 아직 실측하지 않았다. `<,=,>`가 모두 거짓인 NaN 피연산자를 정상적인 세 갈래 선택으로 읽지 않도록, 소비 단계에서 피연산자의 유한성과 effective 비교 dtype을 확인해야 한다. scalar 기록은 선언된 C++ `double`의 원시 단어만 보존하며 f32를 거친 값의 비교 시점 표현을 자동 인증하지 않는다.

## FD 소비자 연결 기준

버전 올린 receipt는 capture-on 호출·입력·asset SHA와 전체 record census를 결합한다. 새 조건 배열은 기존 v1 자료와 구분해 정규화하고, 중심·양끝점·NC `+2h`의 identity 합집합과 일정 차이를 검증한다. 정당하게 비활성인 항목은 타입이 있는 부재 상태로 보존하고, **선택한 두 보폭에서 새 mask 또는 일정이 바뀌면 `BRANCH_CROSSING`**으로 전달한다. 진단용 큰 보폭의 교차는 기록하지만 작은 두 보폭의 국소 판정을 자동으로 막지 않는다. 자료가 불완전하거나 생성 출처가 미검증이면 수치 태그와 무관하게 `NOT_ELIGIBLE`이다.

완료 기준은 원시 기록 → v2 receipt 검증 → 조건 정규화 → `fd_input_adapter.adapt_many()` → `fd_gate.evaluate()`가 같은 호출 자료에서 이어지고, mask 반전·일정 변화·누락·중복·비활성 이유 위조를 합성 반례로 거부하는 것이다. 현재 2백만 record 상한과 100호출·900초 예산에서 실제 record 수·직렬화·graph 보존 비용은 측정되지 않았다. 범위를 넘거나 원래 피연산자·dtype·호출 위치를 묶지 못하면 실행 계획을 `INCOMPLETE`로 남긴다.
