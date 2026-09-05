# Lunar 감사 해소 및 연결 경계 재검토

기준: PR #206 병합 `8bbacfc7333fc1680ec6df512e8e361a83b82160`.
사용자가 요청한 수학·공학·수치해석·기상학 검토의 후속 수정이다.
운영 f32 미세물리 연산, packed 상태/forcing 배열 및 9개 ABI 심볼은 유지한다.
입력 거부 조건, DA 제어/관측 계약, 진단 검증과 증거 표현을 수정한다.

## 원 감사 체크리스트

| ID | 해소한 계약 | 실행 근거 |
| --- | --- | --- |
| R1 | KO/FD NetCDF 결측 마스크를 DN 변환 전에 보존하고 품질을 unusable로 설정 | 두 실제 reader의 작은 NetCDF 파일 시험 |
| R2 | 관측·격자 좌표 유한성/범위, 비퇴화 격자, 유한한 양의 거리 기준 검사 | ingestion 및 SciPy/비-SciPy 공통 경계 시험 |
| R3 | 선택된 관측의 bias/gate를 ColumnObs에 함께 전달; 미지원 SuperObs/full-domain 옵션은 거부 | 배정 충돌 시 소유자와 부가 필드 일치 시험 |
| R4 | 원래 배경에서 `rho_d=rho_m/(1+qv_background)`를 고정하고 RTTOV 수함량에 사용 | 1.02 대 1.00 g/m³ 반례, 고정 밀도 미분, 실제 batched/shard 경계 시험 |
| R5 | `bg/qg`는 비체적(m³/kg); 질량 전용 partition은 고정 bg의 `[100 bg,900 bg]`와 donor 예산의 교집합만 사용 | 밀도 850에서 범위 이탈 반례, 양방향 caps/질량/미분 및 v3 결과 판정 시험 |
| R6 | FD 파일명 시각을 payload·SuperObs 저장/복원까지 전달 | 시각 round-trip 및 legacy 시각 없음의 명시적 처리 시험 |
| R7 | number-budget의 측도를 단위 계약에 조건부로 표시; density profile은 전체 잔차가 아닌 proxy | 진단 출력·입력 시험 |
| R8 | Fortran offline 검증을 모든 `(loop,chain,n,col,k)` 관계를 읽는 공통 replay로 연결 | 3개 loop 각각 q_post 1비트 변이를 거부; 실제 저장 스트림 516/6150 관계 검사 |
| R9 | symmetric CA 오차는 고정 `bt_background`와 `bt_clear`로 계산하는 내부 목적함수의 가중치 | 실제 callback covector와 고정 가중치 목적함수의 중앙 FD 비교 |
| R10 | runtime의 모든 상태/forcing이 같은 양의 `(B,K)`, dtype/device를 요구; 공유 forcing은 명시적 expand | broadcasting·빈 차원 거부 및 정상 handle/DA 시험 |
| C1 | C ABI scalar finite 검사와 VJP/JVP thread fence를 기존 경계와 통일 | hook 오류/출력 sentinel, shipped CTest·심볼·환경 계약 시험 |
| E1 | 비교할 n-member 파일 집합을 먼저 검사 | 빈/누락/불일치 집합 거부 |
| E2 | probe CLI가 실제 raw-bit/정밀도별 ULP 결과 키 사용 | 실제 subprocess 출력·JSON 시험 |
| E3 | 직접 NetCDF 진단도 마스크/비유한값/XLAND 영역 검사 | 합성 파일 반례 |
| E4 | tolerance helper의 report-only 종료와 strict gate를 명시적으로 구분 | 차이 1개인 파일의 report-only 동작 시험 |
| E5 | taxonomy의 필수 검증을 최적화로 제거되지 않는 예외로 구현 | `python -O` subprocess 시험 |
| E6 | Fortran 실패 stderr의 decoding 오류 인자를 수정 | 잘못된 바이트를 포함한 원 실패 메시지 보존 시험 |

코드 수정 완료는 실제 예보 영향의 측정 완료를 뜻하지 않는다. R4는 WRF 관례의
질량 함량 경계를 고친 것이며, 미확정 입자수 단위나 모든 PSD의 물리 해석을 확정하지 않는다.
R5의 invalid 원래 `(qg,bg)`는 해당 제어를 비활성화해 보존한다. 상태를 자동 복구하거나
새 체적 전달 물리식을 만들지 않는다. v2 partition 기록은 현재 v3 실행의 증거로 받지 않는다.

## 독립 연결 재검토

Green·Red 구현 담당과 별도로 `gpt-5.6-luna` Green·Red가 생산자→소비자 경계를
검토했다. 주 에이전트가 실행 반례와 계약을 대조하여 다음을 추가 반영했다.

- `rho_d`가 격자 선택·수직 반전·샤딩을 상태와 함께 통과한다. full-domain은 자신의
  원래 배경과 밀도가 일치하는지 확인하고 고정 관측 연산자 서명에 포함한다.
- 구름 미지원 generic OSSE는 진입 시 거부한다. all-sky batched 입력은 필요한
  압력 격자를 요구하며, 모델 상단 위 수함량과 구름 비율을 함께 0으로 둔다.
- SuperObs KDTree가 공통 좌표 검증을 우회하지 않는다. archive는 기존 tensor-only
  형식에서 키·모양·dtype·품질·유효 BT·기여 수를 검증한다. 빈 관측과 시각 없는 옛
  자료를 실제 손실/시각 0으로 해석하지 않는다.
- dictionary 관측 경로도 full-field quality와 broadcast 가능한 `[0,1]` gate를
  검사한다. 손실 함수는 비유한/음수/1 초과 keep weight를 거부한다.
- partition의 생성기와 결과 판정기가 같은 현재 `PartitionSpec`을 사용하고,
  질량 모멘트뿐 아니라 고정 `bg`의 diagonal 제어도 꺼져 있는지 검증한다.
- number-budget은 signed 최종 상태를 보존하면서 양의 forcing 측도와 비교할
  알고리즘 쌍을 검증한다. result는 중복 JSON 키, 비어 있는 증거 선언, 잘못된 파일/해시,
  여러 출력·입력 사이 같은 파일의 상충하는 해시를 거부한다. 선언하지 않은 파일의
  디렉터리 전수 검사는 이 digest verifier의 계약에 포함하지 않는다.
- 두 번째 Red 검토의 RCF1–4도 해소했다. KDTree는 최근접 탐색 후 공통 haversine
  거리로 판정해 `max_dist_km > πR`에서도 같은 배정을 한다. 사전 mapping은
  tensor/int64/길이/범위를 검증한다. 비교하는 G33R의 선언된 forcing·초기값·시간·fixture는
  정확히 같아야 한다. 상단 구름 제거는 공통 profile builder로 옮겨 단일 컬럼 callback에도
  적용했으며, 실제 runK 입력과 상단 밖 함량 미분 0을 회귀 시험으로 확인했다.

독립 검토의 잠정 지적도 그대로 확정하지 않았다. generic OSSE의 cloud 설정은 이미
하위 경계에서 거부됐으므로 이번 조기 거부를 기존의 조용한 cloud 누락 해소로 부르지 않는다.
DA partition 변경에 Fortran stage schema/새 arm은 필요하지 않다. 미사용 입경을 0으로
만들 필요도 없다. signed 최종 상태를 읽는 진단에 임의 양수 조건을 추가하지 않는다.

## 검증 상태

최종 로컬 전체 oracle: **874 passed / 32 skipped**. 초기 실행의 두 v2/v3 결과 판정
회귀는 같은 소비자 계약 수정으로 해소했다. 기존 live 시험은 12프레임 요구를 유지하며
4프레임 자산을 명시적으로 skip한다. 별도 portable 12단계 cloudy-column 시험은 실제
2-worker 전방을 직렬 결과와 raw `torch.equal`로 비교하고 xland/ncmin 전달도 확인했다.
skip은 실패 은폐나 12프레임 live 실행 완료로 집계하지 않는다.

최종 harness: **1,434 passed / 58 skipped / 308 deselected**.
CI와 같은 undefined-name 검사(F821/F822/F823)는 harness뿐 아니라 oracle 소스·시험까지
확장해 통과했다. 모든 검증은 이 PR 작업 트리에서 수행했다.

수정 후 독립 재검토: Green의 공통 cloud-top 경계 **44 passed / 6 skipped**,
Red의 RCF1–4 및 관련 소비자 경계 **178 passed / 13 skipped / 71 deselected**.
최종 지정 범위에서 새로 확인된 회귀는 없었다. Green의 앞선 판정에서 놓친 단일 컬럼
경로는 Red 반례로 발견해 수정·재검증했다. 이 결과를 전 파일·전 행·모든 분기의 증명으로
확대하지 않는다. 초기 감사 원 목록 208개 공개 소스 항목의 분담 검토와 이번 연결 경계
재검토는 깊이와 목적이 다른 근거다.

격리된 최신 PR 소스의 macOS shipped build(`KDM6_ENABLE_TEST_HOOKS=OFF`):
**CTest 17/17**, export **9개**, caller-owned 환경 계약 통과. 같은 바이너리를 사용한
oracle↔C++ 시험 **4 passed, 0 skipped**. 이는 해당 시험의 허용 오차/ULP 계약이며
WRF mp37↔mp137 전체 필드 raw-bit 비교를 대신하지 않는다. Overlay 4-check도 통과했으며
이 정적 검사는 계측 실행의 비침습성을 증명하지 않는다.

## 열린 과학적·외부 과제

- **M1:** 실제 10분 WRF에서 적용된 입자수 유출·유입과 전체 잔차를 다시 계측.
- **M2:** 최초 음수 QIB 발생 셀의 scalar 갱신 전후 피연산자와 경향 항 추적.
- **입자수 단위:** host Registry/PSD/kernel 경계를 닫고 변환 위치를 결정.
- 이번 실행에는 새 coupled WRF·live RTTOV 검증이 없다. 공개 CI/portable 시험은
  원래 12시간 host raw-bit parity 캠페인을 재실행한 증거가 아니다.
- 재사용 pixel mapping의 좌표·격자 순서 출처는 호출자 계약이다. 현재 공개 runner는
  nearest-pixel payload 경로이며, 계획된 offline SuperObs archive의 운영 결합은 별도다.
- private `host_fortran` 격리 사본과 실제 host wrapper/shim의 차이는 별도 유지관리
  항목이다. 이 PR은 사용하지 않는 사본의 동기화나 새 host 배포를 수행하지 않는다.
