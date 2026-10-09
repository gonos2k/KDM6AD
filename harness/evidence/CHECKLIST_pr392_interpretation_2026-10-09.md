# PR392 후속 — 분기·좌표·고정 지원집합 해석

검토 기준은 당시 미병합 PR392의 고정 head `5a7701ed`; 당시 main은 `a85b39eb`이다.
후속 작업 중 PR392가 `ce77afa2`로 병합됐으며 이번 변경은 그 main 기반 별도 PR이다.
직전 구름 생성·두 방향 H∘M 검증은 기존 출처/범위에서 종결로 유지한다.
새 KDM/RTTOV/host 실행 없이 공개값·이미 보관한 단계자료·현재 코드를 먼저 분석한다.

| ID | 질문 | 필요한 근거 | 담당 | 상태 |
| --- | --- | --- | --- | --- |
| KEEP1 | 기존 종결 유지 | PR370–371/A1–A3, MPI·거리·소산, 새 구름 생성/국소 H∘M 범위 연결 | Root | CLOSED — 재시험하지 않음 |
| BR1 | 약한 구름점의 활성화 하위분기 여유 | 현재 상수로 S=0·0.48% 경계 root, F(S), FD 폭 비교 | Green | CLOSED IN SCOPE — 전체 map 안전반경으로 해석하지 않음 |
| CO1 | 큰 NCCN qv 미분의 좌표 성분 | Nmin/ρM 항등식·저장 JVP와 비교; ρdry/optical reference 구분 | Green | CLOSED IN SCOPE — 물리적 입자 생성과 분리 |
| AP1 | 20/10/5초 누적 적용항 | 보관된 각 call 활성화·clip·응결·과포화·밀도; 재구성/미보관 구분 | Red | CLOSED IN SCOPE — 새 trace/모델 실행 없음 |
| AP2 | reservoir 해석 선택 | 유한 reservoir와 경험적 하한 모델을 구분; numerical refill 및 intercall 좌표 재평가 | Red/Root | 해석 완료 / 물리 선택 OPEN — 하한 삭제/보존 제약 강제 없음 |
| SU1 | 실제 고정 S 목적함수·trial 유효성 | frozen evaluator→clear/allsky→line-search 소스; 작은 fake-QC 반례 | Cost Green | CLOSED IN SCOPE — 수정 전 호출 경로의 합성 반례 |
| SU2 | 최소 거부 계약 보완 | 두 normalized-dry evaluator에서 선언된 S의 품질 상실 거부; legacy/helper opt-out 구분 | Green/Red/Root | CLOSED IN SCOPE — 18개 새 회귀 및 관련 165 passed/2 skipped, 최종 교차검토 완료. 예외 후 자동 재시도 없음 |
| OB1 | 고정 후보 관측 대응 | 기존 QA/time/parallax/footprint 확인값·가정·미확정 자료 재사용 | Root | SUMMARY MAINTAINED — 물리 대응 승인 OPEN |
| NEXT1 | 새 목표시각 native 실행 | 별도 결정 및 독립 source/input/output/정상 종료 근거 | Owner decision | OPEN — 옛 exit1 복구를 영구 선행조건으로 삼지 않음 |
| NEXT2 | 제한된 T/Q 최적화 | 유효 사례·고정 7채널/prior·trial 정의역·실제 감소 확인 | Owner decision | OPEN — 이번 해석으로 실행하지 않음 |

문서의 BR/AP/SU는 이 후속의 하위 ID다. 공식 D1–D4 및 R1/R2/S17·전체 host
시간간격·다중열·미사용 검증을 자동 종결하지 않는다. 1K·0bias·현재 후보·원래 7채널은
유지하고, strong trial의 경고 채널을 제거해 비용 감소로 인정하지 않는다.

[Green 최종 점검](pr392_interpretation_2026-10-09/GREEN_review.md),
[Red 최종 점검](pr392_interpretation_2026-10-09/RED_review.md),
[실행·검증 범위](pr392_interpretation_2026-10-09/VALIDATION.md)에 연결한다.
