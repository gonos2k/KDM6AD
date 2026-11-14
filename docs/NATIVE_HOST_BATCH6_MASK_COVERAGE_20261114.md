# Batch6 제안 조건 19개: 소스 기록과 남은 증거

이 표는 [격리 소스의 A2·A3 층](../harness/evidence/native_host_execution_successor_2026-11-13/producer_source_batch6_layers/README.md)을 소스로 대조한 **정적 목록**이다. 19개 그룹 중 18개에 적어도 하나의 v2 기록 지점이 있고, `warm_cold_gate`에는 없다. 이는 호출·층·반복에서 실제 기록이 방출됐다는 수가 아니다. 모든 그룹은 `PARTIAL/BLOCKED`이며 등록된 native 열의 FD 판정 자격은 `NOT_ELIGIBLE`이다.

후속 [A5 소스 층](NATIVE_HOST_BATCH7_CONNECTION_20261114.md)은 warm/cold의 원래 두 소비 Boolean을 추가했다. 이 표의 18/19 수치는 **A2·A3 시점**의 정적 감사로 유지한다. A5에서도 전체 19개 그룹의 동적 실행 coverage가 입증된 것은 아니다.

`C`는 원래 연산이 소비하는 Boolean 텐서, `D`는 추가 진단 비교, `O`는 기존 값 피연산자, `S`는 선언된 C++ scalar의 원시 단어다. `D`를 `C`로 해석하거나, 비활성 결과를 미실행으로 바꾸지 않는다. 현재 `NOT_EVALUATED` 기록은 0개다.

| 제안 그룹 | 현재 직접 연결한 소스 기록 | 실행용 계약에서 남은 항목 |
| --- | --- | --- |
| `entry_nc_floor` | `O` NC 입구, `D` 0과의 세 비교, `S` 0 | 실제 clamp 피연산자·effective f32 변환 및 호출별 값 대조 |
| `entry_nccn_bounds` | `O` NCCN 입구, `D` 하한·상한 비교, `S` 경계 | 두 clamp 순서·effective dtype·실제 분기 결과 |
| `snap1_per_cell_gate` | optional 존재 시 `C` NC≥NCmin, `O` NC·NCmin | QC≤EPS와 optional 원인·층별 비활성 증거 |
| `snap2_per_cell_gate` | optional 존재 시 `C` NC≥NCmin, `O` NC·NCmin | snap1과 별도 호출 identity, QC·optional·threshold |
| `lambda_active` | `C` Q/N 경계와 active, `O` Q/N | 실제 Q/N threshold·동률·세 lambda 호출의 순서 |
| `lambda_bounds` | `C` lambda 하한·상한과 선택, `O` lambda | 두 경계 scalar·동률·호출별 우선순위 |
| `dsd_ncmin` | `C` NC≥NCmin, `O` NC·NCmin | optional 원천과 fallback, 동률·실제 선택 |
| `dsd_ncmax` | `C` NC>NCmax, `O` 제한 전 NC | NCmax scalar·동률·저장 결과 |
| `cleanup_qc` | `C` QC 유지, `O` QC | Qmin scalar·cleanup 전후값·동률 |
| `temperature_floor` | `O` T, `D` 1 K 비교, `S` 선언값 1 | 반복 호출 위치, effective 비교 표현과 최종 선택 |
| `water_es_cap` | `O` 원시 ES·cap, `D` 세 비교, `S` .99 | 압력·상한 연산 시점과 f32 변환·동률 |
| `satadj_paths` | `C` super/sub/cloud-evap, `O` Q/QC/work1 | 실제 응결·증발 cap 피연산자, DT/Qmin·반환량 |
| `safe_pow_floor` | `O` activation 호출의 비율, `D` EPS 비교, `S` EPS | 원래 clamp 호출 identity·effective threshold·동률 |
| `ncact_preclamp` | `O` numerator, `D` 0 비교, `S` 0/DT | raw NC 후보·제한 적용량·effective DT 표현 |
| `nccn_cap_clamp` | `O` NCCN/raw rate/cap, `D` 세 비교, `S` 0/DT | 두 `minimum` 피연산자·동률·실제 적용량 |
| `main_transport_gate` | `C` 열 active, `O` 열 mstep | 실제 outer/main `mstepmax`, n 연속성·schedule 결합 |
| `ice_transport_gate` | `C` 열 active, `O` 열 mstep | 실제 outer/ice `mstepmax`, n 연속성·schedule 결합 |
| `warm_cold_gate` | 직접 v2 기록 없음 | 원래 각 소비 위치의 `pre.supcol>=0`을 같은 Boolean 노드로 보존하거나 별도 `D`로 제한 |
| `progb_density_gate` | `C` active/zero-den, `O` QG/BG/밀도 | `op_f32`·midpoint scalar, 밀도 경계·OR 피연산자 |

`clamp/min`에는 독립적으로 소비되는 Boolean이 없는 항목이 있다. 이 경우 원시 피연산자와 `D`가 경계 진단 자료이며, 실제 branch mask라고 주장하지 않는다. `<,=,>` 세 비교는 NaN에서 모두 거짓일 수 있어, 소비자가 피연산자의 유한성을 확인해야 한다. 현재 scalar `S`는 선언된 `double` 단어이며 실제 f32 비교 시점의 변환 단어를 인증하지 않는다.

다음 한 계측 변경에 묶을 우선 항목은 원래 warm/cold Boolean, NC/DSD/lambda의 threshold와 optional 출처, main/ice 일정 control, 반복 thermo 호출의 source identity다. satadj·ProgB의 inline 피연산자는 원래 연산 순서와 그래프를 유지하는 단일 materialization 설계가 필요하다. 이후 source-backed selector·동적 census·영수증·loader를 고정하고, off/on 원시 출력과 필요한 JVP/VJP·FD를 같은 실제 호출에서 검증해야 한다. 합성 한 컬럼의 값 parity는 이 조건을 대체하지 않는다.
