---
title: Codex Canonical Worktree Decision 2026-06-25
type: decision
instance_of: Decision
page_kind: decision-page
date: 2026-06-25
date_created: 2026-06-25
date_modified: 2026-06-25
tags:
  - codex
  - workflow
  - path-hygiene
relations:
  - predicate: decided_for
    target: "[[KDM6AD]]"
    rationale: "KDM6AD-k code and wiki work must resolve to the canonical root before any edit."
  - predicate: supersedes
    target: "[[Codex Stale Nested Cwd Incident 2026-06-25]]"
    rationale: "The incident is operationally resolved by canonical root pinning and stale-path guardrails."
---
# Codex Canonical Worktree Decision 2026-06-25

## Context

현재 Codex 세션 메타데이터와 셸 기본 `PWD`는 `/Users/yhlee/KDM6AD/KDM6AD-k`를 가리킨다. 그러나 최근 KDM6AD 코드 검토, 논문 ingest, Obsidian vault/wiki 갱신, Graphify 갱신이 실제로 축적된 작업 루트는 `/Users/yhlee/KDM6AD-k`이다.

이 불일치를 방치하면 같은 이름의 두 디렉토리에 코드, wiki, graphify 산출물이 분산된다. 특히 KG 기록은 누적성과 링크 일관성이 핵심이므로, 한 번 잘못된 디렉토리에 기록되면 이후 논문 계보, KDM6/KDM6AD 코드 비교, 자료동화 확장 기록의 근거 사슬이 분리된다.

## Decision

KDM6AD-k의 canonical project root는 `/Users/yhlee/KDM6AD-k`로 고정한다.

모든 Codex 작업, KG 작업, Graphify 갱신, wiki 편집은 명시적으로 `/Users/yhlee/KDM6AD-k`를 기준으로 수행한다. 현재 세션의 기본 cwd 또는 세션 메타데이터가 `/Users/yhlee/KDM6AD/KDM6AD-k`를 가리켜도 이를 권위 있는 작업 루트로 보지 않는다.

`/Users/yhlee/KDM6AD/KDM6AD-k`는 stale nested path로 취급한다. 해당 경로에는 `AGENTS.md` stop instruction과 `DO_NOT_WORK_HERE.md` marker를 두어, 도구가 낡은 세션 메타데이터를 따라 들어가더라도 즉시 canonical root로 되돌아오도록 한다.

## Rationale

KDM6AD-k는 코드, 논문 KG, Obsidian vault, Graphify 산출물이 함께 진화하는 프로젝트이다. 이 프로젝트에서는 단순히 "어느 디렉토리에 코드가 있는가"보다 "어느 디렉토리가 현재 지식과 검증 기록의 단일 출처인가"가 더 중요하다.

`/Users/yhlee/KDM6AD-k/wiki`에는 최근 논문별 페이지, KDM6 계보, KDM6AD 미분가능 미세물리 수학 독해, 발표자료 적대적 검토, KDM6/KDM6AD 코드 비교가 축적되어 있다. 반대로 `/Users/yhlee/KDM6AD/KDM6AD-k/wiki`는 과거 세션 경로의 흔적이며 canonical KG로 쓰지 않는다.

세션 메타데이터는 현재 대화 중간에 사용자가 수정할 수 있는 프로젝트 파일이 아니므로, 이 세션 안에서는 명시적 `workdir=/Users/yhlee/KDM6AD-k` 고정과 stale path guardrail이 현실적인 통제 수단이다.

## Alternatives Considered

1. 현재 Codex 세션 cwd를 그대로 신뢰한다.
   - 기각. 세션 cwd가 stale nested path를 가리키는 것이 이미 확인되었고, 그 경로를 따르면 KG와 코드 기록이 분산된다.

2. `AGENTS.md` 경고만 둔다.
   - 부분 채택. 경고는 유용하지만, 명령 실행 시 명시적 workdir 고정이 없으면 여전히 낡은 cwd에서 탐색하거나 기록할 수 있다.

3. `/Users/yhlee/KDM6AD/KDM6AD-k`를 다른 이름으로 이동하고 `/Users/yhlee/KDM6AD-k`로 향하는 symlink로 대체한다.
   - 가장 강한 current-thread hard-stop 대안이다. 다만 nested tree가 비어 있지 않고 약 12GB 규모로 확인되었으므로, 명시적 승인 없이 실행하지 않는다.
   - 승인 시 절차는 다음과 같다.
     ```bash
     mv /Users/yhlee/KDM6AD/KDM6AD-k /Users/yhlee/KDM6AD/KDM6AD-k.stale-20260625
     ln -s /Users/yhlee/KDM6AD-k /Users/yhlee/KDM6AD/KDM6AD-k
     ```

4. 새 Codex 세션을 `/Users/yhlee/KDM6AD-k`에서 시작한다.
   - 향후 세션 메타데이터 수준의 위험을 제거하는 가장 안전한 방법이다. 현재 스레드에서는 과거 metadata가 남아 있으므로, 계속 작업한다면 explicit workdir과 guardrail을 병행한다.

## Consequences

- KG와 wiki의 canonical 위치는 `/Users/yhlee/KDM6AD-k/wiki`이다.
- 현재 세션에서 `pwd`나 환경 컨텍스트가 stale nested path를 보일 수 있으므로, 편집·검색·빌드·Graphify 갱신은 항상 명시적 경로로 실행해야 한다.
- `/Users/yhlee/KDM6AD/KDM6AD-k`에 새 산출물이 생기면 우선 stale-path 오작업으로 의심하고 `/Users/yhlee/KDM6AD-k` 반영 여부를 확인해야 한다.
- symlink hard-stop은 경로 혼동 가능성을 가장 강하게 줄이지만, 기존 12GB tree 이동을 수반하므로 별도 승인 전에는 보류한다.

## Verification

- Canonical wiki: `/Users/yhlee/KDM6AD-k/wiki`
- Canonical AGENTS policy: `/Users/yhlee/KDM6AD-k/AGENTS.md`
- Stale nested guard: `/Users/yhlee/KDM6AD/KDM6AD-k/AGENTS.md`
- Stale nested marker: `/Users/yhlee/KDM6AD/KDM6AD-k/DO_NOT_WORK_HERE.md`

## Links

- [[Codex Stale Nested Cwd Incident 2026-06-25]]
- [[KDM6AD]]
- [[KDM6]]
- [[KDM6AD Literature Claim Map]]
