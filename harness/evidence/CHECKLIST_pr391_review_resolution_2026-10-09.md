# PR391 심층 검토 — 항목별 점검·해소 체크리스트

기준: 병합 PR391 `a85b39eb`. 사용자가 제공한 2026-10-09 심층 검토의 수치와
해석은 독립 확인 대상이다. 외부 검토 ZIP/원본 NetCDF를 실행한 것으로 계산하지
않고, 이번에 실제로 읽거나 실행한 소스·입력·빌드·경로를 별도 기록한다.
canonical/private host 및 운영 설치는 변경하지 않는다.

이 표의 식별자는 **PR391 국소 하위 점검**이다. C1(CVT), A1(국소 미분),
A2(새 비용), V1(이번 증거 검토)를 닫아도 내부 연구 체크리스트의 C1(native 다중열),
A1/A2/A3(기존 fixed-error/prior 연결), V1(미사용 검증) 상태를 바꾸지 않는다.
T1 행도 국소 진단 완료이며, 전체 host 시간간격·정확도 검증은 별도 OPEN이다.

| ID | 점검·해소 항목 | 필요한 근거 | 담당 | 상태 |
| --- | --- | --- | --- | --- |
| C0 | 종결된 최소 MPI·거리·한 프로파일 소산 계측 유지 | PR390/391 출처와 완료 범위 참조; 새 반례 없이 재시험하지 않음 | Root | CLOSED — 기존 범위 유지 |
| S1 | 고정 후보의 39층 P/T/Q·순서·단위 확인 | 실제 보관값·해시, native/RTTOV 층 방향, moist-air ppmv와 dry mixing ratio 역변환 | Green | CLOSED — archive/public 일치·실제 한 column 대응; [근거](pr391_clear_state_2026-10-09/result.json) |
| S2 | 포화 부족 독립 계산 | 공개 기본 상수의 f32 단계 반올림, NumPy–Torch 비교; 최대 비율·층·등압 냉각/습윤 gap | Green | CLOSED — 95.5344%, k3, 0.735416K·4.67433%; [검토](pr391_clear_state_2026-10-09/GREEN_review.md) |
| C1 | 실제 제어 가능 성분과 0 배경 CVT | 실제 기본/normalized 연구 설정·sigma/eps·active mask, T와 potential theta 관계, qc/nc/nccn 구분 | Green | CLOSED — 기본 51개(온위39·qv12); 78개 대안은 projection, optimizer 아님 |
| C2 | 구름분율·직경·RTTOV 미분 경계 | 실행 코드의 detach/threshold/clip과 실제 입력 전달; 직접 CVT 생성과 시간창의 간접 생성 구분 | Green/Red | CLOSED IN SCOPE — 실제 source·profile·mask; 0배경 직접 생성과 T/Q 간접 생성 분리 |
| F1 | 제한된 T/Q 전방 반응 | 실제 native 상태, 기존 selector2/dry-number 정책, 사전 선언된 경계 아래/위 perturbation·고정 forcing·qc/NC/T/Q 출력 | Red | CLOSED — −0.5K/+2% clear, −1K/+6% cloudy; [근거](pr391_tq_response_2026-10-09/REPORT.md) |
| A1 | 새 기준점의 국소 미분 | 전방 반응 확인 후 지원된 기준점에서 T/Q JVP/VJP·독립 FD; 유한 경계 통과를 국소 미분으로 해석하지 않음 | Red/Cost Green | CLOSED IN SCOPE — 선택층 5출력 및 약한 구름 full H∘M 방향 비용; 전체 Jacobian/경계횡단 아님 |
| A2 | 새 기준점의 실제 비용·QC 지원 | 원래 7채널·1K·0bias, 동일 profile/gas/기하/표면; 실제 RTTOV K/FD | Cost Green/Red | CLOSED IN SCOPE — −0.8K 약한 구름 J22.6160, FD 상대차1.61e−7·4.67e−8; 강한 두 경우 새32768로 7채널 비교 불가; [근거](pr391_tq_cost_2026-10-09/RESULT.json) |
| T1 | 국소 20/10/5초 비교 | 같은 종료시각·연속시간 forcing 또는 명시된 constant forcing·branch/substep·단위별 결과 | Red | CLOSED DIAGNOSTIC — 20초 constant-forcing partition 반응·branch변화 확인; 수렴차수/전체host T1은 OPEN |
| B1 | 분석 증분과 모델 수지의 분리 | delta initial inventory와 integration residual 별도; 물/수농도 source·sink 및 열/work/경계 누락항을 unknown으로 유지 | Root/Red | PARTIAL — 적용 satadj 물/latent transfer 및 NCCN clip +1e8 m^-3 명시; [contract](pr391_satadj_budget_contract_2026-10-09.md); 전체 S17/외부항 OPEN |
| O1 | 고정 관측 후보의 대응 요약 | QA·scan/pixel clock·높이/시차·기하/표면·footprint를 측정/검색/가정/미확정으로 구분 | Obs Green | SUMMARY COMPLETE, ADMISSION OPEN — 확인값/가정 분리, QA/clock 신규 종결 아님; [요약](pr391_observation_scope_2026-10-09/summary.md) |
| O2 | 사전 선언한 대응 시나리오 | 명목 중심·제품 시차 좌표·허용 clock 조건을 가정으로 구분; 잔차 최소 이웃 선택·sigma 보정 금지 | Obs Green | SCENARIOS DOCUMENTED — 선택·실행·물리 승인 아님; R2 OPEN |
| SEQ1 | 국소 연구 순서·결정문 갱신 | 관측 최소범위와 짧은 상태진단 병행; 국소 시간간격은 QA 종결 전 가능; 액상 우선·빙정/혼합상 경로 보존 | Root | LOCAL SEQUENCE APPLIED — DECISIONS 문서의 D1–D4 및 새 장시간 실행/물리 채택 결정은 OPEN |
| R1 | 물리 레짐·문턱값·moment pair·밀도 역할 채택 | 명시된 단위/좌표와 적용 측도, kernel/host/optical/inventory 관계 및 물리 근거 | Owner/science | OPEN — 국소 f64 반응·미분은 조건부 map 검증이며 물리 채택이 아님 |
| R2 | 유효 목표시각 native–독립관측 사례 | 정상 종료된 새 목표실행 및 QA·clock·기하/표면·공통 footprint 대응 | Owner/science | OPEN — O1/O2 요약 및 비용 진단 완료로 승인하지 않음 |
| V1 | 소스·수치·증거 회귀 및 Green/Red 검토 | 적절한 집중 검사, 실패/생략/미측정 범위, 그래프 코드/문서 의미 갱신 | Team | REVIEW COMPLETE — 세 verification/표현 P2 해소·출력/source 보존; 최종 검사·graph 상태는 [보고서](REPORT_pr391_review_resolution_2026-10-09.md) 참조 |
| H1 | 새 유효 목표시각 host 실행 | 별도 실행 결정, 새 wrapper/library/입력·출력구간·정상 종료·관측 대응 | Owner decision | OPEN — 이번 체크리스트로 장시간 실행을 자동 시작하지 않음 |
| H2 | 과거 358분 exit1 원인 | 역사적 실패·진단용 flag 보존, 새 실행의 유효성과 구분 | Separate investigation | OPEN — 현재 국소 연구의 영구 선행조건이 아님 |

## 해석·실행 기준

이번 해소 결과의 [종합 보고서](REPORT_pr391_review_resolution_2026-10-09.md)는
완료 범위와 B1/O1/H1/H2 및 R1/R2/S17/C1/V1의 미완료 조건을 구분한다.
과거 소산 5행의 계수 감소율·국소 beta*ltick 변화는
[한정 산술](pr391_extinction_row_arithmetic_2026-10-09.json)로 확인했으며
BT 오차율이나 원본 전체 투과율을 재구성한 것으로 표시하지 않는다.

- 기존 PR370–371, A1/A2/A3의 종결은 원래 실행 범위에서 유지한다. 현재 무구름
  상태에서 새로 확인할 질문과 기존 유구름 NC 방향 검증을 구분한다.
- 현재 공통 7채널·1 K·bias=0 및 고정 후보를 유지한다. 임의 qc seed, eps/pseudo-RH,
  사후 sigma/bias 조정, remapped 외부 모델/재분석 profile을 도입하지 않는다.
- 포화비 `q/qs`는 관측 RH `e/es`와 구분한다. 포화 경계까지의 대수적 gap은
  분석 증분의 적용 권고나 실제 상승 궤적이 아니다.
- f64 국소 미세물리 반응·미분, operational f32, 전체 host timestep 의존성과
  관측 비용/기상 원인 귀속을 별도 근거로 기록한다.
- 정확한 이산 미분, 유한값/정상 종료, 물리적으로 대응된 분석은 다른 완료 조건이다.
  측정하지 않은 물/수농도/열/외부/경계 항을 0으로 채우지 않는다.
- 항목은 실제 확인한 하위 범위만 CLOSED로 바꾸고 근거 링크를 단다. 한정된
  반응 실험은 과거 invalid native 실행이나 관측 QA를 승인하지 않는다.
