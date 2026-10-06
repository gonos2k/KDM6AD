---
title: Bounded source-only research candidate acceptance (2026-10-06)
type: source
date_modified: 2026-10-06
---

The [execution report](../../harness/evidence/REPORT_research_candidate_2026-10-06.md)
and [user recipe](../../docs/RESEARCH_CANDIDATE.md) accept one existing fp64
selector-2/dry-number native-column configuration from a clean PR #377 clone,
a new Python environment and a freshly built installed library. Two native
runs match raw-bit; three input/overwrite failures reject. CTest executes 19
tests including both Fortran targets, and the installed ABI exports 11 symbols.

The clean-workspace work reproduced mixed Torch library discovery and an
incomplete private-test profile predicate. Explicit dependency paths and the
complete profile prerequisite fix those verification boundaries without
changing physics or loosening numerical criteria. The public-only Python suite
reports 1,628 passed / 87 skipped; the separate ambient-RTTOV run and failed
pre-fix run remain individually attributed. These counts overlap.

This is a local source-only candidate, not a published or licensed distribution.
The native forecast is supplied externally; KMA/RTTOV provisioning, physical
policies, observation/prior calibration and operational approval remain separate.
Original PR #370–#377 evidence is preserved.
