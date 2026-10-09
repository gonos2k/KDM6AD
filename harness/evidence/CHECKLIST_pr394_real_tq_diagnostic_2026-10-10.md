# PR394 후속 — 실제 RTTOV 연결 진단과 미완료 범위

이번 진단은 과거 launcher exit1 실행의 작은 cached checkpoint를 사용했다. 입력의
역사적 invalid 상태는 유지한다. 새 정상 target native–독립관측 사례가 아니다.

| ID | 확인 | 결과 / 상태 |
| --- | --- | --- |
| KEEP1 | helper 구성 종결 | all-sky·parameter pin·T/Q controls·strict S·window pullback 근거 유지; 재설계 없음 |
| INPUT1 | 원래 입력을 재사용했는가 | 37KB checkpoint·immutable case_00. q8d5 원본과 q3b2 재사용 scratch를 분리. 큰 forecast 미조회/미해시 |
| BASE1 | 실제 baseline H가 같은 계산인가 | 10–16 실제 channel 파일·p/p_half/T/Q·기체/표면/기하 일치. 7/7 Q-good·기존 BT/Jo와 차이0 |
| ANALYSIS1 | 새 helper 실제 M/H/dual 연결 | 기존 zero control·max_iter1로 정상 반환. Jb=.02141671856, Jtheta0, Jo26.45074405369, 합계26.47216077225 |
| SUPPORT1 | 같은 목적함수와 수락점 audit인가 | final trace와 합계 일치, 7채널·동일signature·RQ0·all-sky 유지 |
| CONTROL1 | 초기 제어와 parameter가 의도대로인가 | th/qv만 비영 증분 norm, 다른 State의 증분 norm0·parameter sigma0. th norm은 온위 K이며 물리 T norm 아님 |
| FAILURE1 | 준비 실패를 수락 결과로 오인했는가 | 잘못된 direct-H cfg·params/capture 등 setup 문제 수정. 실패 receipt 보존. 두 capture 실패는 실제 H probe를 했으나 분석 미반환 |
| COUNT1 | 실행 횟수의 의미 | 최종 analysis trace의 성공callback3/window2/audit1/logicalH4. 별도 baseline H·실패probe를 포함하지 않음. 실제 child launch 수는 미계측 |
| PROV1 | 실행 소스·metadata 정정 추적 | baseline driver hash와 analysis hash 분리. 원래 raw write 별도미보존; metadata 수정 전 형태는 deterministic reconstruction로만 기록 |
| PHYS1 | 실제 증분·구름반응의 물리 해석 | 전체 반환 State/slot QC-NC·physicalΔT/relativeqv·RH 미보존. 추가 replay하지 않고 미기록으로 표시 |
| RUN1 | 새 정상 목표 native 실행 | 준비case 미실행·기존 실행범위 응답 대기. 역사적실패 원인을 영구 선행조건으로 삼지 않음 |
| SCI1 | 새 independent science case | R1/R2·QA/UTC/parallax/footprint·전체물리수지·확장 OPEN, 관리72% 유지 |

[REPORT](pr394_real_tq_diagnostic_2026-10-10/REPORT.md),
[RESULT](pr394_real_tq_diagnostic_2026-10-10/RESULT.json),
[Red](pr394_real_tq_diagnostic_2026-10-10/RED_review.md)에 근거/한계를 연결한다.
actual iteration1에서 비용이 낮아졌다는 것은 forecast·구름 복원·calibrated B/R의
승인이 아니다. 새 유효 사례에서는 accepted initial/slot 상태를 private checkpoint로
보존하고 증분·수직구조·QC/NC·분석증가량과 적분수지를 같은측도로 연결해야 한다.
