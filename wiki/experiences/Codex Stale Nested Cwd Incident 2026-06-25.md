---
title: Codex Stale Nested Cwd Incident 2026-06-25
type: experience
instance_of: Experience
page_kind: experience-page
date: 2026-06-25
date_created: 2026-06-25
date_modified: 2026-06-25
tags:
  - codex
  - workflow
  - path-hygiene
relations:
  - predicate: derived_from
    target: "[[Codex Canonical Worktree Decision 2026-06-25]]"
    rationale: "The incident record preserves why the canonical worktree decision was needed."
---
# Codex Stale Nested Cwd Incident 2026-06-25

## Context

KDM6AD-k 작업 중 사용자가 `/Users/yhlee/KDM6AD-k`가 세션 디렉토리인지, 그리고 `/Users/yhlee/KDM6AD/KDM6AD-k/wiki`가 왜 존재하는지 점검을 요구했다. 조사 결과 현재 Codex 세션 메타데이터와 기본 cwd가 `/Users/yhlee/KDM6AD/KDM6AD-k`를 가리키는 반면, 최근 실제 코드와 wiki 작업은 `/Users/yhlee/KDM6AD-k`에 축적되어 있었다.

이 문제는 단순 표시 문제가 아니라, KG ingest와 wiki 편집이 잘못된 루트로 들어갈 수 있는 작업 안전성 문제이다.

## Attempted

- 세션의 기본 `pwd`, Codex session metadata, user-provided environment context, turn context의 cwd 기록을 확인했다.
- `/Users/yhlee/KDM6AD-k/wiki`와 `/Users/yhlee/KDM6AD/KDM6AD-k/wiki`의 역할을 비교했다.
- canonical root에 최근 논문 페이지, KDM6/KDM6AD 코드 비교, 발표자료 검토, KG 로그가 누적되어 있음을 확인했다.
- stale nested path가 비어 있지 않고 별도 대형 tree임을 확인하여 즉시 삭제하거나 이동하지 않았다.

## Outcome

작업 기준을 `/Users/yhlee/KDM6AD-k`로 정정했다. Canonical `AGENTS.md`, `wiki/hot.md`, `wiki/log.md`에 경로 정정 기록을 남겼고, stale nested path에는 작업 금지 안내 파일을 추가했다.

현재 스레드 안에서 세션 메타데이터 자체를 소급 수정할 수는 없으므로, 이후 명령은 explicit `workdir=/Users/yhlee/KDM6AD-k`로 실행해야 한다.

## Root Cause

이전 Codex 세션 또는 환경 컨텍스트가 `/Users/yhlee/KDM6AD/KDM6AD-k`를 workspace root로 기록했고, 현재 대화가 그 metadata를 계속 이어받았다. 반면 사용자가 의도한 최신 프로젝트 루트와 실제 KG/wiki 작업 루트는 `/Users/yhlee/KDM6AD-k`였다.

즉 원인은 코드 구조 자체가 아니라, 세션 메타데이터가 과거 nested path를 authoritative cwd처럼 제공한 데 있다.

## Resolution

- Canonical project root: `/Users/yhlee/KDM6AD-k`
- Canonical wiki root: `/Users/yhlee/KDM6AD-k/wiki`
- Stale nested path: `/Users/yhlee/KDM6AD/KDM6AD-k`
- 현재 스레드에서는 모든 명령에 명시적 workdir을 부여한다.
- stale nested path에는 stop instruction과 marker를 두었다.
- 완전 차단이 필요하면 사용자 승인 후 stale nested tree를 보존 이동하고 symlink로 대체한다.

## Lesson

Codex의 세션 cwd는 프로젝트의 단일 출처가 아니다. KDM6AD-k처럼 코드, wiki, Zotero ingest, Graphify 산출물이 함께 누적되는 프로젝트에서는 첫 명령 전에 canonical root와 KG root를 확인하고, 의심스러우면 모든 명령을 절대경로 workdir로 실행해야 한다.

이 사건의 운영상 결론은 [[Codex Canonical Worktree Decision 2026-06-25]]에 따른다.
