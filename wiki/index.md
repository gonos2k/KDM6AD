---
title: KDM6AD-k Wiki Index
type: meta
date_modified: 2026-07-14
---
# KDM6AD-k Wiki

## Start Here
- [[overview|Overview]]
- [[hot|Hot Cache]]
- [[log|Log]]
- [[papers/_index|KDM6AD 논문 페이지 색인]]

## Content
- [[sources/_index|Sources]] - 9 pages
- [[entities/_index|Entities]] - 4 pages
- [[concepts/_index|Concepts]] - 10 pages
- [[papers/_index|Papers]] - 42 pages
- [[procedures/_index|Procedures]] - 0 pages
- [[experiences/_index|Experiences]] - 4 pages
- [[heuristics/_index|Heuristics]] - 0 pages
- [[decisions/_index|Decisions]] - 2 pages
- [[queries/_index|Queries]] - 2 pages

## Sources
- [[kdm6-vs-kdm6ad-code-comparison-2026-06-25]] - Analysis note comparing mp37 KDM6 and mp137 KDM6AD implementation structure.
- [[kdm6-microphysics-zotero-survey-2026-06-25]] - Literature synthesis for KDM/WDM microphysics and KDM6AD manuscript positioning.
- [[kdm6ad-code-story-literature-review-2026-06-25]] - Reference-backed story for explaining the current KDM6AD code configuration.
- [[kdm6ad-kdm6plus-literature-set-2026-06-25]] - Curated KDM6+ Zotero collection ledger after removing non-KDM6 collected papers.
- [[kdm6plus-collection-mathematical-deep-ingest-2026-06-25]] - Mathematical deep ingest of KDM6+ papers for manuscript drafting.
- [[kdm6ad-20260610-presentation-adversarial-review]] - June 10 presentation review, including stale C-ABI status correction and adversarial manuscript cautions.

## Entities
- [[KDM6]] - mp37 Fortran reference microphysics scheme.
- [[KDM6AD]] - mp137 wrapper plus libtorch C++ differentiable port.
- [[WRF KIM-meso Host]] - Host model integration surface for mp37/mp137 dispatch.
- [[LC05 5km SS Case]] - the real 5 km (234×282) SS case; the single real-time DA target.

## Concepts
- [[KDM6 Literature Genealogy]] - KDM/WDM 계열 논문을 bulk microphysics, PSD, WDM6, graupel, AD, DA 계보로 연결하는 허브.
- [[KDM6AD Literature Claim Map]] - KDM6AD 원고 주장을 개별 논문 페이지와 연결하는 근거 지도.
- [[Bulk Microphysics Design Space]] - Literature-derived design axes for interpreting KDM6AD sensitivities.
- [[Differentiable Bulk Microphysics Research Gap]] - Gap between mature KDM/WDM schemes and parity-preserving AD implementations.
- [[KDM6AD Automatic Differentiation ABI]] - Packed fp64 state and handle-based VJP/JVP interface.
- [[KDM6AD Mathematical Microphysics Operators]] - PSD moment, tendency, sensitivity, and observation-operator math for KDM6AD.
- [[KDM6AD Differentiability Audit]] - Smoothness and adjoint-consistency criteria for KDM6AD derivative claims.
- [[KDM6AD Forward Parity]] - Operational requirement that mp137 mirror mp37 forward behavior.
- [[KDM6AD C ABI Hardening]] - thread fail-closed + additive ABI v2 + hidden-visibility 9-symbol export allowlist + SOVERSION 2 (abi-v2-hardened).

## Decisions
- [[Codex Canonical Worktree Decision 2026-06-25]] - Canonical project/wiki root를 `/Users/yhlee/KDM6AD-k`로 고정하고 stale nested path를 비작업 경로로 취급한다.
- [[Frozen-Code Freeze-Lift Protocol 2026-07-14]] - frozen dylib 변경은 scoped freeze-lift + owner host-parity gate 하에서만; PR1-B 계속 동결.

## Experiences
- [[Codex Stale Nested Cwd Incident 2026-06-25]] - Codex session metadata가 `/Users/yhlee/KDM6AD/KDM6AD-k`를 가리킨 사건과 정정 조치.
- [[abi-v2-hardened baseline 2026-07-14]] - abi-v2-hardened 봉인 + install-baseline tension(문서화된 parity는 pre-hardening dylib 기준).
- [[host-run-dir-confusion-2026-07-14]] - host/ 3개 케이스(5km 실사례·100km ideal·1km) 혼동 사고와 재발방지 규칙.

## Sources (recent)
- [[abi-v2-hardening-roadmap-2026-07-14]] - 2026-07-13/14 frozen-code hardening arc → abi-v2-hardened @ a53503e.

## Queries
- [[kdm6ad-differentiable-microphysics-zotero-kg-2026-06-25]] - Zotero/KG bridge for KDM6AD differentiable microphysics research.
- [[kdm6ad-final-code-location-verification-2026-06-25]] - `/Users/yhlee/KDM6AD-k`가 현재 검토 코드/KG 루트임을 확인하고 SS step-1 frame-index-1 strict bitwise gate를 재확인.
