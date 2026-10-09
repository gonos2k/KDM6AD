# main b679 추가 검토 — 상태와 새 prior 산술

| ID | 확인 | 처리/근거 | 상태 |
| --- | --- | --- | --- |
| REMOTE1 | main 공백과 후속 PR을 구분 | main b679 유지, PR394 head01048862 open/CI5 성공을 실제 조회 | 완료 — main 병합 해소로 소급하지 않음 |
| ROUTE2/PARAM2 | 앞선 두 조건부 통합 공백 | PR394의 명시 all-sky·active=() helper와12 구성시험 근거 재사용 | PR의 새 경로에서 종결, main 기존 기본 경로는 유지 |
| COST1 | prior 포함 −.5/−.8 냉각점 | 같은7채널과 온위 .8K/Exner로 Jb+Jo 대조 | 완료 — 샘플 비단조, 전체 장벽/solver 실패 증명 아님 |
| BOUND1 | 포화 등식의 공동 최소 prior | Tb±2K에서 정상점·20,001 격자 및 독립 convexity 대조 | 완료 — .118183, 제한 두 제어 순간 경계만 |
| SEED1 | 수학 최소점을 실제 증분으로 채택하는가 | 초기 v=0 유지. qv=qs는 활성화/구름·RTTOV·관측 적합도 아님 | 자동 적용하지 않음 |
| SCORE1 | 완성도 중복 가산 | main54/75는 검토자 관리 평가, 추가 scalar/PR/CI 점수0 | 72% 유지 |
| RUN1 | 새 유효 목표시각 상태 | 격리case 준비 근거 재사용 | 미실행·장시간 실행 범위 응답 대기 |
| SCI1 | 실제 관측 대응·T/Q 분석 | R1/R2/D1–D4/S17·QA/time/parallax/footprint 별도 | OPEN |

[추가 계산 보고서](REPORT_main_b679_prior_boundary_2026-10-10.md)와
[기존 통합 체크리스트](CHECKLIST_pr393_tq_integration_2026-10-09.md)를 함께 읽는다.
현재 PR에서 구현된 것을 “미게시 변경”이나 “현재 main에 이미 반영됨”으로 부르지 않는다.
