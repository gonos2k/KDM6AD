# 팀 재점검과 해소 결과

PR395 병합 main `e74cf3fa`를 기준으로 Green 두 경로와 독립 Red가 새 연구
도구의 producer→consumer 연결을 확인했다. 미세물리·AD·solver는 바꾸지 않았다.

주요 반례는 사용자 지정 intake 경로가 기본 경로 조회로 실패하는 경우,
receipt publication 후 정리 예외가 private checkpoint와 불일치를 만드는 경우,
그리고 masked QNCCN이 유한 fill 값으로 변환되는 경우였다. 모두 합성 입력과
한정 예외 주입으로 재현했고 현재 source에서 해소했다. 실제 새 예보의 선택
cell에 결측이나 해당 오류가 있다는 주장은 하지 않는다.

intake는 archive의 실행 namelist·producer hash/control을 읽으며 고정 dt를
effective flags에서 확인한다. 실제 launch처럼 CLI fixed_dt=false인 경우도
archived flags가 false/time_step20이면 통과한다. adaptive=true는 거부한다.
선택 hyperslab만 검사해 다른 열의 mask 때문에 사례를 거부하지 않는다.
기존 historical reader/source/수치 기록은 수정하지 않았다.

capture는 final trace의 signature/valid7과 mask digest를 보존한다. 실패가
helper 반환 전인지, 반환 후 검증/저장 중인지 구분하고 raw optimizer history
arrays를 public failure에서 제외한다. public success와 private checkpoint가
정리 오류로 분리되지 않도록 link commit 뒤 cleanup 정책을 보완했다.

검증 근거는 저장·제어·비용 기록 9개, 초기 비용 보고 2개, 저장 배열 대수 3개의
집중 합성 시험(총14개; 기존 시험 포함), file-backed 합성 netCDF
흐름, default/override main 구성과 mock capture 연결, publication fault injection,
import/구문/ruff/whitespace 및 독립 소스 점검이다. 이들을 native/M/RTTOV 실행이나
기상 사례 수로 계산하지 않는다. 이전에 닫힌 MPI/거리/소산/국소 미분을 반복하지 않았다.

현재 native PID99158은 그대로 적분 중이다. 수정 전 consumer 미실행을 확인해
대기 v2만 철회했고 새 source pins의 v3를 시작했다. 후속 비용·단위 수정 전에
consumer 미실행을 확인하고 v3만 철회했다. 새 검증 소스를 고정한 v4로 이어가며
모델을 중단/재시작하거나
과거 invalid checkpoint를 새 입력으로 사용하지 않았다. 정상 종료·실제8Times·
필수 필드 확인 뒤 한정 분석을1회 연결한다. 이 보고서 작성 시 실제 결과는 대기 중이다.

남는 제한은 physical matchup/per-pixel UTC/CTH datum/footprint와 과학적 채택이다.
QN number의 dry/ moist basis 등 기존 조건부 단위 근거는 새 mask 시험으로
독립 승인되지 않는다. intake의 literal current_worktree_head는 LIVE_START의
launch-time checkout을 뜻하며 현재 audit HEAD나 새 build를 인증하지 않는다.
소비자는 manifest hash와 고정10/10으로 연결하지만 ncmin의 nested provenance를
별도로 재읽는 것은 아니다. 실제 mismatch는 확인되지 않았다.

관리용 54/75(72%)는 유지한다. 새 도구의 조건부 통합/저장 오류와 기록 보완을
생산 물리식의 새 결함이나 독립 기상검증 완료로 확대하지 않는다.

[체크리스트](../CHECKLIST_pr396_team_audit_2026-10-10.md) ·
[Red](RED_review.md) · [Green capture](GREEN_capture_review.md) ·
[Green intake](../pr395_native_tq_intake_2026-10-10/GREEN_review.md) ·
[합성 실행 범위](SYNTHETIC_PROBE.json)

## 추가 검토의 비용·단위·해석 자료

품질 확인용 zero-mask probe 비용은 0이며 실제 초기 Jo가 아니다. 새 capture는
첫 zero-control closure의 Jb/Jtheta/Jo/Jtotal과 signature·7채널 지원을 보존한다.
분석 consumer는 이를 초기 비용으로 사용하고, 저장 probe BT와 실제 고정 mask의
Huber 합계로 대조한다. 원래 probe 비용도 별도로 남긴다. 모델·RTTOV 재호출 없이
기록 경로만 정정하며, 기존 비용·소스 기록을 덮어쓰지 않는다.

PH/PHB는 지오포텐셜 m² s⁻²로 표기한다. 원래 값은 변환하지 않는다. 반환 후
저장 실패의 단계 구분은 이 PR에서 이미 수정한 A6이며 새 결함으로 중복 집계하지
않는다. Native reader가 이미 계산하는 host eta 층별 건조질량도 float32 [8,39]와
첫 시각 [39]로 보존한다. 측도를 EOS rho×dz로 바꾸거나 닫힌 수지를 승인하지 않는다.

`diagnose_saved_state.py`는 완료된 capture·intake 해시를 확인한 뒤 저장 배열만
사용한다. 전체 host 05:56:00과 국소 KDM 슬롯의 차이, 온위/Exner 온도 분해,
첫 시각 host 질량을 고정한 분석·적분 물 변화 항을 계산한다. 추가 M/H 호출은 없으며
경계·외부 flux는 미측정으로 남긴다. 3개 합성 대수 검사는 실제 수치의 승인이나
native 사례가 아니다. 실제 분석 성공 후에만 진단을 연결하며 실패하면 원래 수락
분석 receipt는 보존하고 진단 실패로 기록한다.
