# 실제 제한 T/Q 분석의 명세 — 준비와 실행을 구분

이 문서는 실행 승인이나 최적화 결과가 아니다. 현재 `c543b98c`의 기존 solver와
strict 품질 callback을 사용하고 새 solver·복원/retry·포화조정식을 추가하지 않는다.
새 유효 native 상태와 명시된 관측 대응 시나리오를 확보한 뒤 첫 분석의 범위를 정한다.

## e619 추가 검토에서 확정한 실행 연결

이 명세를 기본 `run_fulldomain_analysis()`에 그대로 연결하지 않는다. 그 함수는
배경에서 clear/all-sky를 나누고 네 warm-process 매개변수를 .2 prior로 활성화하는
기존 결합 추정 경로다. 별도 [run_single_column_analysis](../../oracle/kdm6/da_single_column.py)가
아래 구성으로 기존 factory·CVT·dual 최소화기를 조립한다:

- allsky_pos=[0], clear_pos=[]: 실제 물리 배경 분류는 보존하지만 H 선택에 쓰지 않는다.
- default_param_prior(active=()): peaut/ncrk1/ncrk2/eccbrk를 기본 기준값에 고정한다.
  State sigma=0만으로 매개변수가 고정된다고 해석하지 않는다.
- obs_time≥1: 실제 M(xb)의 관측슬롯을 계산해 frozen 품질 probe에 제공한다.
- 7채널 배경 지원을 확인한 뒤 strict S를 유지한다. 6개만 남으면 분석을 시작하지 않는다.
- caller의 원래 forcing window와 ncmin/xland·native pressure center grid를 유지한다.
  p_half는 그대로 전달하지만 helper만으로 native interface의 원자료 정체까지 인증하지 않는다.
- 성공 callback 결과·기존 window/final-audit 횟수를 보고한다. max_iter를 실제 M/H 호출
  수로 부르지 않고 미계측 내부 호출·실패 시 완료되지 않은 결과는 별도로 한정한다.

실제 호출은 새 유효 native column/forcing와 검증된 관측·광학 설정을 준비한 뒤 한다.
worker pool은 caller가 관리한다. 숨은 custom params·eta/eta_pre·partition·pseudo-RH
경로는 이 첫 연구 helper에서 사용하지 않는다. 초기 T/Q가 고정하지 않은 QC/NC 등의
적분 중 반응은 full-window pullback에 남는다.

## 고정할 상태와 제어

- 현재 후보 j86/i48와 고유 39층 중심/경계 압력·T/Q/수상체를 유지한다. 외부 모델,
  reanalysis, fixture-grid remapping을 대체하지 않는다. 과거 exit1 자료는 진단용이다.
- `make_default_cvt()`의 기존 시작값은 **온위 sigma=0.8 K**, 하단 12층 qv의
  **log-space sigma=0.08**이다. 물리 온도와 온위는 Exner를 통해 구분한다.
  이 값은 관측 sigma=1 K와 다른 prior 가정이며 검정된 B가 아니다.
- 초기 제어는 0을 기준으로 한다. 기존 −0.8 K what-if 점을 원래 배경으로 바꾸거나
  구름 seed로 사용하지 않는다. 만약 별도 시작 제어를 선택한다면 배경을 유지하고
  그 증분의 prior 비용을 포함한 탐색 조건으로 사전에 명시해야 한다.
- 현재 clear 배경의 0 수상체 직접 곱셈형 제어는 비활성이다. 최초 분석은 T/Q 경로를
  평가하고 NCCN·NC를 임의로 켜서 잔차를 맞추지 않는다. 새 상태가 유구름이어도
  T/Q 한정 분석이 되도록 기존 builder의 sigma_overrides에서 qc/qr/qi/qs/qg/
  nc/ni/nr/nccn/bg를 모두 0으로 사전 선언한다. 이는 별도 분석 제어범위이며
  운영 builder 기본값을 변경하는 것이 아니다. 실제 활성 control mask는
  새 배경에서 builder가 만든 결과를 기록하며 이전 51개를 자동 복사하지 않는다.

## 목적함수와 실행 경계

`J=Jb+Jo` 전체를 사용한다. 7채널(AMI 10–16), 관측 sigma=1 K, bias=0,
Huber delta=1, 배경에서 동결한 S와 strict trial 품질을 유지한다. 새 배경에서 이
사전 선언 7채널이 모두 지원되는지 먼저 확인한다. 지원이 줄어들면 동등한 분석으로
보상하지 않고 그 상태를 진단 결과로 기록한다.

전방 M의 시간창·forcing·밀도좌표는 실제 선택된 연산자에 연결한다. 기존 국소 20초
고정 forcing 미세물리는 전체 host 역학–수송 연산자의 대체 검증이 아니다.
광학 dry-density reference와 호출별 runtime dry-density도 구분한다.

현재 실패 계약은 **품질 예외 발생 시 실행 중단, 성공 결과 미발행**이다. 예외 뒤
trial parameter 또는 optimizer state가 수락점으로 복원됐다고 가정하지 않는다.
실패 객체를 이어서 사용하지 않고 해당 실험을 실패로 기록한다. 자동 재시도는 없으며,
향후 도입 시 수락 제어/optimizer state 복원 또는 새 optimizer로 재시작·재시도 한계·
종료조건을 별도로 정한다. 일반 ValueError를 모두 잡아 무시하거나 S를 축소하지 않는다.

## 실제 결과가 갖춰야 할 기록

| 항목 | 확인할 내용 |
| --- | --- |
| 출처 | native 실행·소스/빌드/입력, 종료/저장시각, 관측 원자료/대응 시나리오 |
| 선언 | 초기 제어, state/parameter prior, sigma/bias, controls·forcing·시간창 |
| 각 평가 | Jb·Jo·Jtotal, 실제 지원/품질, 제어증분 크기, 적용 분기·유한성 |
| 최종 수락 | 기존 closure의 수락 제어 재평가 결과, 지원집합 불변, 실제 전체 비용 변화 |
| 실패 | 실패 단계/예외·실행 상태, 성공 산출물과 구분. 진단용 scratch의 존재를 성공으로 해석하지 않음 |

관측항의 14.94% what-if 감소를 전체 prior 포함 분석이나 예측 개선으로 승격하지 않는다.
정상 종료한 native 실험도 QA/시공간·기하 대응의 자동 승인은 아니다. 이후 시간간격,
다중열·미사용 자료와 포화조정 연구변형은 각각 별도 실험으로 남긴다.
