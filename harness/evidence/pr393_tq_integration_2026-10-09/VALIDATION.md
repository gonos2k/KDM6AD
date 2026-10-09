# T/Q 연결 경로의 실행 검증 범위

검토 입력은 e6198816이며 새 helper/test는 그 head에 없던 추가 파일이다. 작업 중
PR393이 b679431b로 병합돼 후속은 그 main을 기반으로 한다. UTC 검증일은 2026-10-09,
JST 기준 최종 실행은 2026-10-10이다. 파일 날짜는 제공된 검토의 날짜를 유지한다.

- 최종 집중시험 **12 passed**: singleton all-sky/empty-clear, 물리 clear 배경의
  cloudy trial 직접 QC 수반, 7/7 배경·strict trial, parameter sigma0, 초기 T/Q만
  제어, positive obs_time, H/M ncmin/xland 일치, 39층 synthetic shape, 이전 clear
  factory/.2-all-active prior, 비영 혁신·component totals, 대표 전체 방향 검사.
- 관련 CVT/dual 구성 **84 passed**, 43 existing deprecation warnings. 이는12개를
  포함한 subset이며 합산하지 않는다. 해당 실행 후 FD 허용오차를 엄격하게 조정했고
  변경한 한 방향 시험과 최종 집중12개를 재실행해 통과했다. 나머지72개와 adapter
  계산 소스는 이 조정에서 바뀌지 않았다. 전체 pytest·native를 로컬에서 실행하지 않았다.
- 작은 대표 방향은 AD .24124595381474626, FD .2412459533784883, abs차4.36e−10,
  relative차1.81e−9. h=1e−4, rel tolerance2e−8/abs1e−9. 두 실제 pure-Torch KDM
  step과 CVT·Jb를 사용했지만 H는 합성이다. actual RTTOV/native derivative 사례가 아니다.
- 공개 weak-cloud/비용 receipt의 prior 산술을 독립 대조했다. 23.122695533170 총량과
  13.035224% 감소는 저장 what-if 조건부 비교이며 최적화 수락 또는 forecast 개선이 아니다.
  +6% qv의 Jb 계산은 가능하지만6/7 지원이므로 고정7채널 후보로 인정하지 않는다.
- py_compile·ruff F821/F822/F823·JSON/source hash·Markdown 링크·whitespace 확인.
  Green/Red는 H 라우팅·매개변수 고정·슬롯 배경·J component·호출량 의미를 대조했다.
  source/hash는 [RESULT.json](RESULT.json)과 [FD_result.json](FD_result.json)에 연결된다.
- 기존 run_fulldomain_analysis·da_dual·물리식·solver·operational build/install의 기본
  계산을 변경하지 않았다. 단일-column 연구용 조립 함수만 추가했다. 실제 production
  설정으로 helper를 호출하면 configured H가 RTTOV를 실행하므로 pool과 fresh case_root,
  원자료·설정·실행 attribution은 caller가 관리해야 한다.
- 새 목표 native case는 prepared/not launched 상태를 유지한다. 실제 관측·분석 결과,
  P8W/native interface 정체, QA/시간/시차/footprint·R1/R2 승인을 확보한 것은 아니다.

실행 명령:

```sh
/opt/local/bin/python3 -m pytest -q oracle/tests/test_da_single_column.py
/opt/local/bin/python3 -m pytest -q oracle/tests/test_da_single_column.py oracle/tests/test_da_cvt.py oracle/tests/test_da_dual.py oracle/tests/test_dual_normalized_policy_guard.py oracle/tests/test_internal_prior_controls.py
```

graphify code refresh와 문서 semantic은 별도로 수행한다. raw graph는 ignored
graphify-out에 두고 5,000노드 초과 시각화는 생략한다. 기존 query coverage가 일반적인
call node만 제공한 부분은 소스를 직접 확인한다. exact agent token cost는 제공되지
않아 주장하지 않는다. PR-head CI는 별도 post-push 근거이며 작은 시험 수와 합산하지 않는다.
