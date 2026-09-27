---
title: KDM6AD S15 upstream attribution plan
type: source-note
date_modified: 2026-09-27
---
# S15 upstream attribution plan

The public step-2 S15 report records 87,937 owner-5 QIB transition occurrences
and six replayable first-event rows, but the probe ends at the RK store and
does not capture upstream Y/X/Z face operands. Its 258 melt rows all have
`rhox_valid=0`, so they do not establish melt thermodynamic attribution.

The next bounded plan calls for six source-scheduled owner/RK/tile witnesses
from advection faces through source-ordered directional contributions,
`advect_tend`, separate `sc_tend`, and the RK store. The producer and consumer
are reached through separate loops: `scalar_tile_loop_1` calls `rk_scalar_tend`,
which dispatches to ordinary or positive-definite advection; the later
`scalar_tile_loop_2` calls `rk_update_scalar` for the consumer. The overlay must
propagate the same identity through both owner-5 callsites. RK1/RK2 ordinary
advection is kept distinct from RK3 positive-definite dispatch, which depends
on the active configuration and observed branch. The six repeatability
coordinates have a separate ordered projection and SHA-256 pin; they do not
define the expected schedule. The implementation checklist and private source
anchors are in [the public plan](../../harness/evidence/S15_UPSTREAM_ATTRIBUTION_PLAN.md).

This corrects the plan's earlier single-path wording. It does not invalidate the
prior owner-5 RK-store discovery, which remains evidence for the operands it
actually captured; no upstream face values were present in that discovery.

The standalone synthetic contract checks identities and record shape, plus
binary32 accumulation of directional terms. A macro-gated runtime overlay now
shares the capture latch and step/RK/owner/tile context across both producer
and consumer paths. The configured WRF suffix preprocessing chain and focused
Fortran syntax checks pass, with macro-off preprocessed byte identity. Its
bounded extractor separates face/RK records from legacy S15 records and fails
closed on unknown tags or size/path violations. These are implementation and
compile checks only; no executable was linked or run. Full face-divergence and
RK-store numerical replay remain OPEN acceptance gates.

The [candidate report](../../harness/evidence/REPORT_S15_face_fortran_compile_only_2026-09-27.md)
records the checks. The separate `sc_tend`
operand is captured as a consumer input but is not yet numerically attributed
to the producer.

This note records a future measurement contract, not native evidence. S15
remains OPEN; no physical cause or graupel policy is assigned.
