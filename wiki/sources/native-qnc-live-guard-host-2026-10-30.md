# QNC live guard host pilot, 2026-10-30

선택한 액체 QNC donor 54개에 대해 저장 자료의 후보 탐색을 실제 `mp_physics=137` 한 스텝에 연결했다. 현재 상태의 제한 전 face와 RK 피연산자로 첫 통과 scale을 찾고, 동일한 반올림 face를 donor·receiver에 적용했다. 두 타일의 382개 캡처 셀을 검사한 뒤 실제 RK 단어도 확인한다. 이 실험은 좌표가 고정된 연구 변형이며 일반 제한기 규칙이나 미분 가능한 host map을 인증하지 않는다. [실행·재생 근거](../../harness/evidence/native_qnc_live_guard_2026-10-30/README.md) · [수치 및 수용 범위](../../docs/NATIVE_QNC_LIVE_GUARD_HOST_20261030.md)

Control·α 각각 trace off/on의 네 호스트 한 스텝이 완료됐고 각 쌍의 체크포인트 SHA와 ACK가 같다. Control은 38/14/2곳에서 0/1/2 ULP를, α는 25/21/6/1/1곳에서 1/2/3/4/5 ULP를 선택했다. 대응하는 변경 공유면은 87/310개이며, 새 face 단어는 양쪽 셀 기록과 일치한다. Control의 (M_0) 손실은 0, α는 액체 실패 53개 프로파일을 모두 회복하고 얼음 QI/NI **1개 프로파일·7채널**이 남았다.

정확 산술 면 잔차와 f32 RK 결과를 모두 검사했다. Raw NC 물리 단위와 전체 입자 수 보존, 이 변경의 JVP/VJP, 전체 RTTOV 비용은 인증되지 않았다. α가 원래 고정 support를 유지하지 못했으므로 분석 수용·두 번째 동화는 아직 없다. 다음 확인은 경계 donor QI의 subnormal 출처와 적용 규칙이다.
