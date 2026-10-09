# PR393 심층 검토 — 항목별 해소 체크리스트

검토 기준: 병합 main `ce77afa2`, PR393 head `c543b98c`(조회 시 미병합).
이 문서의 하위 ID는 공식 D1–D4/R1/R2/S17과 별개다. 이미 닫힌 근거는 원래
소스·입력·빌드·실행 범위에서 유지하며 문서나 산술 시험을 실제 기상 사례로 합산하지 않는다.

| ID | 확인할 질문 | 해소 산출물 | 담당 | 상태 |
| --- | --- | --- | --- | --- |
| KEEP1 | 고정 S의 trial 품질 검사 | PR393 두 callback·회귀·최신 head CI 연결 | Root/Red | CLOSED IN SCOPE — 기존 근거 재사용 |
| FAIL1 | 예외 후 수락점이 자동 복원되는가 | 설치 Torch의 source/version 및 1차원 합성 LBFGS 관찰 | Red | CLOSED IN SCOPE — 2.13.0 합성 x=1 잔류, 프로젝트 실제 분석 아님 |
| FAIL2 | 현재 실행의 실패 계약 | 품질 예외 시 중단·성공 산출물 미발행; retry/restore 미구현 명시 | Root/Red | CLOSED IN SCOPE — fail-closed 유지, 재시도 추가 안 함 |
| NUM1 | 포화식의 정확한 T 미분 | clamp 비활성 영역의 dq_s/dT 유도와 실제 scalar thermo AD 대조 | Green/Root | CLOSED IN SCOPE — 4점 상대차 최대 2.14e−15 |
| NUM2 | 저장 잔차 부호교대·감쇠 | Dimpl/Dexact, 선형 예측·저장 endpoint 비율 비교 | Green/Red | CLOSED IN SCOPE — 공개 값 재구성, 재적분하지 않음 |
| NUM3 | 개선식 도입 여부 | 기존 산술 보존, 대안 분모/root solve는 별도 연구변형으로 유보 | Root | 변경하지 않음 — 이번 필수 수정 아님 |
| N1 | 활성화·하한 보충·밀도변환 | 이전 적용항 기록 및 새 gate/임계 비율 대조 | Green | CLOSED IN SCOPE — F=.02202<.66815, b=0. 물리 채택은 별도 |
| OBS1 | 고정 후보의 관측 대응 | 확인값·가정·미확정 조건, 최소 비교 시나리오 | Green | 요약/공식 문서 대조 완료 — QA·epoch·height datum·footprint/R2는 OPEN |
| RUN1 | 새 유효 목표시각 실행 | 실제 harness/입력/설정에 연결한 구체 실행 범위와 완료 조건 | Green/Root | 격리 case 준비·preflight 완료 — 장시간 실행 범위 응답 대기, 미실행 |
| OPT1 | 실제 T/Q 분석 실험 | 고정 S·Jb+Jo·증분·분기·최종 재평가의 실행 명세 | Root | 명세 완료 — 실제 실행 미수행, 새 사례/범위 결정 OPEN |
| SCORE1 | 5영역 관리용 배점 | 49/75·53/75·54/75 산술과 주관적 배점 출처/한계 | Root | 정리·산술 확인 완료 — 정확성 확률/커버리지/남은 시간 아님 |
| EXT1 | 전체 host 시간간격·다중열·미사용 자료 | 각기 다른 후속 실험으로 명시 | Root | OPEN — 국소 분할 재검산으로 대신하지 않음 |

현재 탐색 기준은 고정 native j86/i48·AMI320/48·VIIRS205/27, 7채널,
sigma=1 K·bias=0, 기존 경험적 NCCN 하한이다. 이를 검정된 오차·유한 reservoir
보존모형·관측된 CCN 공급으로 부르지 않는다. 모델/관측의 BT·구름 존재가 맞는지를
사례 채택 조건으로 삼거나 더 잘 맞는 이웃 column을 사후 선택하지 않는다.

이 검토를 해소하기 위해 기존 포화조정 분모·물리식·solver를 변경하거나,
일반 ValueError를 삼키는 retry를 추가하지 않는다. 새 장시간 native 실행과 실제
T/Q 분석은 준비·범위 결정을 마친 뒤 별도 결과로 식별한다.

근거: [종합 해소 보고서](REPORT_pr393_review_resolution_2026-10-09.md),
[포화잔차](pr393_satadj_residual_2026-10-09/GREEN_review.md),
[예외 경로](pr393_optimizer_failure_2026-10-09/RED_review.md),
[관측 범위](pr393_observation_scope_2026-10-09/SUMMARY.md),
[실제 격리 case 준비](pr393_target_preparation_2026-10-09/PREPARATION.md),
[T/Q 분석 명세](PR393_limited_analysis_spec_2026-10-09.md).
