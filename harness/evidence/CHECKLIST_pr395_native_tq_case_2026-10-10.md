# 새 native–T/Q 사례 진행 체크리스트

기준 main은 PR394 병합 `8e5aab06`이다. 사용자는 2026-10-10 05:21 JST에
미완료 작업 진행을 지시했다. 준비된 358분 예보의 새 격리 실행과 그 상태를
사용한 한정 분석을 진행한다. 과거 launcher-invalid 자료의 지위는 유지한다.

| ID | 작업 | 완료 조건 | 현재 |
| --- | --- | --- | --- |
| KEEP | 기존 종결 유지 | MPI·거리·소산·국소 미분·all-sky/parameter pin·strict 품질을 재개하지 않음 | 유지 |
| RUN-PRE | 새 native 실행 사전점검 | 원래 IC/경계·정적자료, namelist, 실행파일·library 식별, 1 rank/thread, 이전 output/restart 미사용 | 실제 loader·1×1·variant 2·dry 1 시작 표지 확인 |
| RUN | 새 목표시각 실행 | 자연 종료상태와 harness validity, 실제 8개 Times 05:55:40–05:58:00 확인 | 05:26 JST 시작, WRF PID 99158; 정상 종료/목표 출력 대기 |
| MATCH | 고정 관측 대응 | QA·픽셀/scan UTC·높이/시차·footprint의 확인값과 사전 가정 구분 | 선택 QA 해석 확인. nominal 시나리오 A 선언; 픽셀 UTC·CTH datum·공통 footprint 미확정 |
| INTAKE | 새 native 입력 | 고정 j86/i48·native 39층에서 State/Forcing/압력·표면·기하를 식별, 배경/slot UTC 계산 | 코드·import·누락입력 거부 확인, 새 유효 결과 대기 |
| SAVE | 상태 보존 | background/accepted initial·background/final slot·forcing·Exner·frozen rhoD·pressure를 private NPZ와 hash로 보존 | 저장 경계 3개 합성 검사 통과; 실제 결과 저장 대기 |
| BASE | 실제 RTTOV baseline | 새 입력에서 AMI10–16 7/7 품질·actual profile·지원집합 고정 | 새 유효 상태 대기 |
| ANALYSIS | 한정 T/Q 분석 | zero control, parameter pin, strict S, same-H final audit, Jb/Jo/J·증분·slot QC/NC 기록 | 새 유효 상태 대기 |
| PHYS | 결과 해석 | 물리 T·상대 qv·포화비·구름 반응과 초기 증분/모델 반응/좌표변환·reservoir를 구분 | 상태 저장 후 |
| REVIEW | Green/Red와 PR | 실제 확인 범위·실패/미계측 항목·잔여 한계를 기록하고 새 PR 제출 | 진행 중 |

준비·실행 중·정상 반환·수치적 유효·관측 대응·물리적 채택을 구분한다.
함수/시험/CI 개수로 점수를 올리지 않으며 현재 관리용 54/75(72%)를 유지한다.
관측 불일치를 이유로 좋은 이웃 셀을 고르거나 sigma/bias를 사후 조정하지 않는다.
native time-step 비교·다중열·미사용 사례는 첫 한정 사례 이후 별도 연구로 남긴다.

새 native BT를 보기 전에 분석 범위를 선언했다: 새 05:55:40 초기 상태에
고정 forcing과 20초 local KDM 한 step을 적용해 nominal 05:56:00을 평가한다.
`obs_time=1`, `max_iter=3`, zero control, observation sigma 1 K/bias 0 K,
th prior 0.8 K/qv log prior 0.08 하단 12층, 기타 초기 상태 및 물리매개변수 고정이다.
이 슬롯은 AMI 픽셀 UTC 일치를 뜻하지 않는다. 품질 예외 발생 시 중단하고
성공 checkpoint를 발행하지 않는다. full-host 결합·시간간격 실험과 구분한다.

서버 재시작 뒤 PID 99148→99157→99158이 그대로 살아 있음을 확인했다.
모델을 중복 실행하지 않았다. 단일-case continuation은 종료 receipt 뒤에만
intake와 분석을 호출하도록 시작했으며, 소비 소스가 바뀌거나 native가 invalid이면
중단한다. 시작 상태와 저장 설계의 점검은 실제 종료/분석 결과를 대신하지 않는다.
