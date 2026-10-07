---
title: Research recipe checkout alignment (2026-10-07)
type: source
date_modified: 2026-10-07
---

The [current recipe](../../docs/RESEARCH_CANDIDATE.md) now selects clean PR #378
30931e52 for build, native CLI and Python tests. The
[new executed receipt](../../harness/evidence/REPORT_research_candidate_revision_2026-10-07.md)
records a fresh build/install, 19 CTests, 11 ABI exports, two matching native
runs, three rejections and the public-only suite (1,628 passed / 87 skipped).
No test overlays or runtime/physics changes were used.

The separate October 7 acceptance witness is retrieved by an exact committed
blob and digest outside the clean source checkout. The prior October 6 witness
and its 4ce39d8-plus-test-overlays evidence remain unchanged and historical.
This closes the instruction/source-composition mismatch; it does not supply
second-user acceptance, distribution permission or scientific/operational approval.
