# PR393 심층 검토 해소 — 실행 및 검증 범위

- 공개 JSON 두 개만 쓰는 포화잔차 reader를 독립 출력 경로에서 재생했다. 네 호출의
  clamp/cap 비활성 조건·적용량·endpoint를 확인하고 공개된 두 번째/세 번째 분모와
  잔차 비율을 재현했다. 기존 native forecast·NPZ·RTTOV를 다시 읽거나 실행하지 않았다.
- 실제 `compute_qs_water`의 네 scalar AD를 해석 미분과 대조했다. 최대 상대차
  2.14e−15. 이는 scalar 열역학식 확인이며 KDM 전체/RTTOV Jacobian은 아니다.
- 설치된 Torch 2.13.0의 1변수 LBFGS 합성 probe는 [0,1] closure 뒤 ValueError·x=1
  잔류·step 결과 없음으로 끝났다. 사용자 검토의 Torch 2.10.0 실험과 별도 근거다.
  callback은 closure마다 zero_grad를 수행한다. 예상 ValueError만 기록하며 다른 예외를
  삼키는 생산 처리나 retry는 추가하지 않았다. probe 소스 해시는 결과와 일치한다.
- 관리용 점수 합계와 소수점 한 자리 환산을 확인했다. 49/75, 53/75, 54/75가 각각
  65.3%, 70.7%, 72.0%. 영역별 배점은 제공된 검토자 판단이며 독립 검정값이 아니다.
- 새 JSON 파싱·receipt/source hash·구문·ruff F821/F822/F823·whitespace 및 로컬
  Markdown 링크 확인을 수행했다. 생산 `oracle/kdm6`, `libtorch`, `run_ss_case.py`는
  c543b98c와 비교해 변경하지 않았다. 기존 179 passed/2 skipped를 재시험하지 않았다.
- 새 목표 case의 copied namelist, 80개 symlink, 입력/실행파일/라이브러리 및 소비 소스의
  식별을 확인했다. 79개 curated 정적 링크는 존재/크기가 과거 manifest와 일치하지만
  실제 파일별 접근은 관찰하지 않았다. 현재 case는 PREPARED_NOT_LAUNCHED다.
  전체 WRF source build attestation은 제한된 상태이며 추가 hash gate로 만들지 않았다.
- Green/Red 최종 검토에서 과거 빌드 head 표현 하나를 수정했다. 현재 runtime load,
  정상 종료, actual Times, 새 분석 결과는 아직 확보하지 않았다.

재현할 때 저장 receipt를 덮어쓰지 않고 새 출력 경로를 지정한다:

```sh
/opt/local/bin/python3 harness/evidence/pr393_satadj_residual_2026-10-09/analyze_residual.py --output /tmp/pr393-residual-new.json
/opt/local/bin/python3 harness/evidence/pr393_optimizer_failure_2026-10-09/inspect_failure.py --output /tmp/pr393-optimizer-new.json
```

독립 scalar thermo 확인은 다음 값·소스만 소비한다:

```python
import json, sys, torch
sys.path.insert(0, "oracle")
from kdm6.thermo import compute_qs_water, default_thermo_params
r = json.load(open("harness/evidence/pr393_satadj_residual_2026-10-09/RESULT.json"))
p = torch.tensor(r["selected_column_from_partition_receipt"]["p_Pa"], dtype=torch.float64)
for row in r["five_second_calls"]:
    t = torch.tensor(row["post_activation_reconstruction"]["T_K"], dtype=torch.float64, requires_grad=True)
    qs = compute_qs_water(t, p, params=default_thermo_params())
    actual = float(torch.autograd.grad(qs, t)[0])
    expected = row["water_saturation"]["dqsdT_kgkg_per_K"]
    assert abs(actual - expected) / abs(expected) < 1e-13
```

Code graph와 문서 semantic은 별도 갱신한다. query가 일부 일반/오래된 노드만 찾은
영역은 소스/receipt로 직접 확인했고 coverage 한계를 유지한다. raw graph는 ignored
`graphify-out/`에 보관하고 5,000노드 초과 시각화는 생략한다. 에이전트 token 사용량은
런타임이 제공하지 않아 정밀 비용을 주장하지 않는다. 모델/재분석을 새로 취득하지 않았다.

c543b98c의 기존 5개 성공 CI는 그 head의 근거다. 이 후속 문서·reader를 반영하는
새 PR-head CI는 별도 확인하며 native 목표실행이나 실제 분석의 완료와 합산하지 않는다.
