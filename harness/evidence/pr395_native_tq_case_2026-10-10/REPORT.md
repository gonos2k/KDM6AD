# 새 native–T/Q 사례: 준비와 실행 시작

PR394 병합 main `8e5aab06`을 기준으로 미완료 작업을 진행했다. 사용자가
2026-10-10 05:21 JST에 진행을 지시했고, 05:26 JST에 새 격리 native 실행을
시작했다. 원래 IC·경계 입력을 사용하며 과거 forecast/restart는 입력으로 쓰지 않는다.

실제 PID 체인 99148→99157→99158, 1×1 MPI, 1 thread 제한과 mp337/variant 2/dry 1
시작 표지를 확인했다. `lsof`로 격리 KDM6 library와 연구 환경 Torch의 실제 로딩
경로를 확인했다. 바이너리/library는 보관된 build receipt와 일치하지만 현 PR에서
새로 빌드한 것으로 주장하지 않는다. 고정 dt 20초는 effective namelist의
`use_adaptive_time_step=.false.` 및 `step_to_output_time=.false.`에서 확인했다.
실제 argv에는 `--fixed-dt`가 없으며 두 사실을 분리해 기록했다.

서버 재시작 후에도 같은 프로세스가 계속 적분 중임을 확인했다. 시작/진행은
완료 증거가 아니다. 종료코드·harness validity·8개 실제 저장시각·필수 변수 존재가
확인되기 전에는 새 입력을 분석에 사용하지 않는다. 초기 `iofields_filename` 경고
12회가 있었고 적분은 계속됐으나, 출력 필드의 성공 적용을 따로 승인하지 않는다.

준비된 intake는 정확한 새 run과 05:55:40–05:58:00의 8개 Times를 확인한 뒤
고정 j86/i48의 39층을 읽는다. 중심압력은 저장 P/PB의 f64-first 합이며 interface
P8W는 보관 host `calc_p8w`의 Python REAL(4) 전사이다. 실제 host P8W 출력이나
raw PH/PHB 자체와 동일한 물리량으로 표현하지 않는다. 배경·native window·압력·
forcing은 private NPZ에 보존하고 모델 위 참조대기와 기체 가정은 별도로 기록한다.

새 분석은 첫 05:55:40 배경에 고정 forcing/20초 local M을 적용한 nominal
05:56:00 슬롯이다. 새 BT를 보기 전 `obs_time=1`, `max_iter=3`, zero control,
온위 prior 0.8 K·수증기 log prior 0.08/하단12층, 관측 sigma 1 K·bias 0,
물리매개변수 고정·고정7채널·strict trial 품질을 선언했다. full-host 다음 시각의
실제 상태와 local M의 결과를 동일시하지 않는다. baseline Jo0는 같은 helper의
배경-slot H(M(xb)) probe에서 얻으며 별도 native 초기시각 H를 반복하지 않는다.

저장 실행기는 성공 반환과 정확히 한 번의 final audit 뒤에 초기 배경·반환 초기·
배경 슬롯·최종 슬롯의 모든 12개 State 성분과 forcing/Exner/frozen rhoD/pressure를
보존한다. 실제 T·상대 qv·액상 포화비·phase-aware ratio·QC/NC는 그 배열에서
진단한다. 레벨 합은 물량/입자 inventory가 아니며 named-process 공급량으로
해석하지 않는다. 실패 시 성공 checkpoint를 발행하지 않고 자동 재시도하지 않는다.

관측 packet은 선택 VIIRS QA byte 0의 해석을 확인했지만 AMI per-pixel UTC,
CTH datum 및 공통 footprint는 아직 확정하지 못했다. nominal-center 시나리오 A를
사용하며 실제 픽셀시각 정합 또는 독립 물리검증의 승인으로 표현하지 않는다.

저장 경계 합성 검사 5개(원래 3개 포함), import/누락입력 거부·구문·ruff·whitespace와 Green/Red
소스 점검을 수행했다. 검사들은 native/RTTOV 실행을 대신하지 않는다. 새 consumer는
아직 실행 전이며 단일-case continuation이 native 완료 receipt를 기다린다.
native가 invalid이거나 소비 코드가 바뀌면 continuation은 분석 없이 중단한다.

현재 관리용 54/75(72%)를 유지한다. 실제 실행 결과·기상학적 채택 여부는 이후
receipt와 저장 상태를 검토해 기록하며 준비/시험 수로 완료도를 올리지 않는다.

[체크리스트](../CHECKLIST_pr395_native_tq_case_2026-10-10.md) ·
[관측 대응](../pr395_observation_matchup_2026-10-10/SUMMARY.md) ·
[intake](../pr395_native_tq_intake_2026-10-10/README.md) ·
[상태 저장](../pr395_tq_state_capture_2026-10-10/README.md)

## 07:13 후속 검토 반영

이전 실패 checkpoint 진단의 최종 callback은 알려진 [1,39] f64 영배열과
9개 수상체/입자 필드 해시가 일치한다. 이 좁은 동일성 판단은 가능하며, 그 결과를
구름 복원으로 해석하지 않는다. 초기 qv 상대증분 상한과 k3 액상 포화비 상한
97.23%도 [공개 receipt 산술](../pr395_endpoint_bounds_2026-10-10/REPORT.md)로 확인했다.
일반적인 상태벡터/기울기 복원 또는 중간 구름 존재 판정은 하지 않았다.

새 driver는 v_state/v_parameter, b_sigma, 고정매개변수와 **최종 전체 제어공간
기울기**를 private NPZ에 추가한다. 실제 optimizer 객체의 기존 final audit 뒤
parameter.grad를 읽으므로 H 수반과 다르며 추가 closure/M/H를 실행하지 않는다.
기록한 제어와 CVT로 수락 초기장/매개변수를 정확히 재구성해 반환점과 일치함을
확인한다. optimizer history는 step 반환 직후/pre-audit, 최종 gradient는 post-audit
자료로 구분한다. 원본 L-BFGS를 호출하는 관찰기의 한정 quadratic 값·gradient
비간섭도 확인했다. 이 시험을 native/RTTOV 사례로 계산하지 않는다.

기존 optimizer는 직접적인 종료 이유를 반환하지 않으므로 해당 값은 UNKNOWN이며,
실제 n_iter/func_evals/보폭·tolerance 정보와 final gradient를 남긴다. 정상 반환이나
예산 값만으로 수렴을 선언하지 않는다. solver를 대체하거나 자동 재시도하지 않는다.

기존 **대기 프로세스만** 철회하고 아직 어떤 consumer도 실행되지 않았음을
확인한 뒤, 보완 소스 hash를 pin한 continuation v2를 시작했다. native PID 99158은
계속 적분하며 재시작/중단하지 않았다. old continuation의 철회 receipt와 source
revision은 보존한다. 새 정상 목표시각/분석 결과는 여전히 완료 전이다.
