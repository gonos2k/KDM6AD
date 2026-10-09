# PR393 e619 추가 검토 — T/Q 실행 연결 해소

고정 검토 기준 e6198816, 병합 main ce77afa2. 이전 strict 품질·포화잔차·MPI·거리·
소산·실제 국소 H∘M 검증은 원래 범위에서 유지한다. 두 P2는 아직 수행되지 않은
T/Q 연구의 상위 구성 공백이며 과거 실제 분석 오류로 소급 해석하지 않는다.

| ID | 질문/공백 | 처리 | 상태 |
| --- | --- | --- | --- |
| ROUTE2 | clear 배경이 clear H에 고정돼 구름의 직접 복사가 빠지는가 | 새 단일-column helper는 allsky=[0], clear=[]로 고정. 물리 분류는 metadata로 보존 | 구현·실제 factory 경로의 합성 H 시험 완료 |
| PARAM2 | State sigma=0만으로 물리매개변수도 고정되는가 | 기존 dual에 default_param_prior(active=()) 전달. 네 sigma_log=0·baseline 고정 | 구현·고정 상태/매개변수 계약 확인 완료 |
| SLOT1 | frozen 품질 기준이 실제 H(M(xb))인가 | 기본 고정 물리매개변수로 관측슬롯 배경을 계산해 x_slot_bg로 전달 | source/실행 구성 확인 완료 |
| STATE1 | T/Q 초기 제어와 이후 미세물리 반응을 분리하는가 | th sigma=.8 K, qv log sigma=.08/lower12, 나머지0. full-window pullback 뒤 initial th/qv projection | 비영 혁신·CVT→M→합성 H→J 방향 검사 완료 |
| SUPPORT1 | 7개 배경·trial 고정 S가 유지되는가 | 6/7 배경은 최소화 전에 거부. strict trial·signature·ObsEvalResult 유지 | 배경 부족/품질 예외 회귀 완료 |
| COMPAT1 | 기존 full-domain 기본 동작을 보존하는가 | full-domain 함수 미변경. 기존 clear factory와 .2/all-active prior 비교 시험 | 기존 clear H의 잠열 T/Q 반응 유지 |
| PRIOR1 | −.8 K what-if의 prior 포함 비용은 무엇인가 | Δθ/σθ 및 ln(1.06)/.08 공개값 산술 | 23.1226955332·13.035224%는 조건부 산술, 실제 분석 아님 |
| COUNT1 | max_iter를 실제 호출 횟수로 잘못 보고하는가 | 성공 callback 결과와 기존 window/audit counter만 보고. 미계측 내부 KDM/RTTOV 횟수는 None | 정의 명시 완료, 예외 후 성공 결과 없음 |
| RUN1 | 새 정상 목표시각 native 실행 | 기존 격리 case 준비 유지 | 미실행·기존 실행 범위 질문 응답 대기 |
| SCI1 | 실제 관측 대응 및 분석 사례 | 새 상태의 포화·control mask·7채널·native interfaces/가정을 확인한 뒤 실행 | R1/R2/D1–D4/S17 OPEN |

e619 명세를 기본 run_fulldomain_analysis에 그대로 전달하지 않는다.
[da_single_column.py](../../oracle/kdm6/da_single_column.py)는 기존 하위 API를 조립하는
별도 연구 경로다. 데이터 취득·빌드·pool 생성을 하지 않지만, 실제 설정이면 configured
H를 통해 RTTOV를 실행할 수 있다. 이번에는 합성 H의 구성시험만 실행했다.

관리용 main53/75·PR39354/75는 유지하며 연결 구현·시험 수로 점수를 올리지 않는다.
새 solver·pseudo-RH·구름 seed·수상체/물리식 변경은 없다.
