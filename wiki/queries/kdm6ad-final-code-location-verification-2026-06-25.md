---
title: KDM6AD Final Code Location Verification 2026-06-25
type: query
instance_of: Source
page_kind: source-page
date_created: 2026-06-25
date_modified: 2026-06-25
tags:
  - kdm6ad
  - code-verification
  - path-hygiene
  - parity
relations:
  - predicate: about
    target: "[[KDM6AD]]"
    rationale: "Verifies where the current reviewed KDM6AD implementation and KG records live."
  - predicate: supported_by
    target: "[[Codex Canonical Worktree Decision 2026-06-25]]"
    rationale: "Uses the canonical worktree decision as the path authority."
---
# KDM6AD Final Code Location Verification 2026-06-25

## Summary

정밀 확인 결과, 현재 최종 검토 대상으로 삼아야 하는 KDM6AD-k 코드와 KG/wiki 기록은 `/Users/yhlee/KDM6AD-k`에 있다. `/Users/yhlee/KDM6AD/KDM6AD-k`는 같은 이름의 stale nested tree이며, 일부 C++ 핵심 파일은 동일하지만 wiki/KG와 최근 테스트·문서·oracle 수정 상태가 canonical tree와 다르다.

또한 SS strict bitwise gate는 `klfs_lc05_fcst.202507190000`의 `frame index 1`이다. 이 gate에서 mp37 vs mp137은 `254 common, 253 BITWISE-MATCH, 0 DIFFER, Times non-numeric`으로 `STRICT BITWISE PASS`가 재현된다.

## Location Verdict

- Canonical project root: `/Users/yhlee/KDM6AD-k`
- Canonical wiki root: `/Users/yhlee/KDM6AD-k/wiki`
- Stale nested path: `/Users/yhlee/KDM6AD/KDM6AD-k`
- 작업 결론: 이후 코드 검토, KG ingest, Graphify update, 논문 작성용 근거 정리는 `/Users/yhlee/KDM6AD-k` 기준으로 수행해야 한다.

## Evidence

- `/Users/yhlee/KDM6AD-k/AGENTS.md`가 canonical root를 `/Users/yhlee/KDM6AD-k`로 명시한다.
- `/Users/yhlee/KDM6AD-k`에는 `graphify-out/graph.json`, `wiki/index.md`, `wiki/log.md`, `wiki/papers/_index.md`가 존재한다.
- `/Users/yhlee/KDM6AD/KDM6AD-k`에는 `wiki/index.md`와 `wiki/log.md`가 없고, stale path guard 파일인 `DO_NOT_WORK_HERE.md`가 있다.
- 파일 수 기준으로 canonical tree는 13,310개, stale nested tree는 7,931개로 확인되었다. 둘 다 약 12GB이므로 stale nested tree는 비어 있는 alias가 아니라 별도 tree이다.
- Graphify query를 `/Users/yhlee/KDM6AD-k`에서 실행했을 때 [[KDM6AD]], `module_mp_kdm6ad`, `kdm6ad()` 및 host wrapper 노드가 canonical graph에서 검색되었다.
- `libtorch/bridge/kdm6_c_api.cpp`, `libtorch/src/runtime.cpp`, `libtorch/src/coordinator.cpp`는 canonical tree 안에 있고, `kdm6_step_ad_c`, `kdm6_handle_vjp_c`, `kdm6_handle_jvp_c`, `value_only`, `diag_rhog` 경계 주석을 포함한다.
- `oracle/tests/test_cpp_parity.py`는 canonical tree에서 `libtorch/build/test_autograd_endtoend`를 가리키며 f32 mirror regression bound를 사용한다. stale nested tree의 같은 파일은 이전 경로와 더 강한 f64/ULP 서술을 갖고 있어 현재 검토본이 아니다.

## Verification Run

- `ctest --test-dir libtorch/build --output-on-failure`: 16/16 passed.
- `/opt/homebrew/Caskroom/miniforge/base/bin/pytest oracle/tests/test_cpp_parity.py -q`: 1 passed.
- `/opt/local/bin/python3 -m pytest`는 pytest 미설치로 실패했다. 이는 코드 실패가 아니라 interpreter 환경 문제이다.
- Existing host SS run artifacts under `/Users/yhlee/KDM6AD-k/host/KIM-meso_v1.0/test/.../runs/` both have `exit_code=0` and end with `SUCCESS COMPLETE WRF`.
- Documented strict bitwise command, with explicit frame index `1`, passes:
  ```bash
  python3 host/KIM-meso_v1.0/run/strict_bitwise_nc.py \
    host/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS/runs/mp37_final_1min_hist0_20260624_194512/klfs_lc05_fcst.202507190000 \
    host/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS/runs/mp137_final_1min_hist0_20260624_194620/klfs_lc05_fcst.202507190000 \
    1
  ```
  Result: `254 common, 253 BITWISE-MATCH, 0 DIFFER, 1 non-numeric`; `STRICT BITWISE PASS`.

## Parity Gate Clarification

기존 wiki의 "SS step-1 strict bitwise pass" 표현은 맞다. 단, comparator에 frame index를 생략하면 기본값이 마지막 공통 프레임이므로 documented gate와 다른 비교가 된다.

`klfs_lc05_fcst.202507190000`의 frame별 재비교 결과:

- frame 0: 254 common variables, 253 numeric bitwise matches, 0 differences, 1 non-numeric. PASS.
- frame 1: 254 common variables, 253 numeric bitwise matches, 0 differences, 1 non-numeric. PASS. This is the documented SS step-1 gate.
- frame 2: 254 common variables, 234 numeric bitwise matches, 19 differing numeric variables. FAIL.
- frame 3: 254 common variables, 202 numeric bitwise matches, 51 differing numeric variables. FAIL.

따라서 현 시점에서 정직한 표현은 "SS step-1 frame index 1 strict bitwise pass"이다. "last common frame" 또는 "all frames" pass라고 쓰려면 별도 장기/다중-step parity gate를 정의하고 검증해야 한다.

추가로 명시적 historical pair들을 모두 frame index `1`에서 재검증했고, gate/relink/kstandalone/final pair가 모두 `STRICT BITWISE PASS`였다.

## Consequences

- `/Users/yhlee/KDM6AD-k`가 최종 검토 코드의 위치라는 판단은 유지된다.
- [[KDM6AD Forward Parity]]의 host-level claim은 "SS step-1 frame index 1 strict bitwise pass"로 써야 한다.
- 논문이나 발표에서 "all frames" 또는 "last-frame forecast bitwise parity"라고 쓰려면 fresh host rerun과 별도 다중-step gate 정의가 필요하다.

## Links

- [[Codex Canonical Worktree Decision 2026-06-25]]
- [[Codex Stale Nested Cwd Incident 2026-06-25]]
- [[KDM6AD Forward Parity]]
- [[KDM6AD Automatic Differentiation ABI]]
- [[kdm6-vs-kdm6ad-code-comparison-2026-06-25]]
