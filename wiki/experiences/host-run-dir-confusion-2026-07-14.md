---
title: host-run-dir-confusion-2026-07-14
type: experience
date_modified: 2026-07-14
---
# Host run-dir confusion (2026-07-14)

Lesson from a session that repeatedly conflated three different WRF cases under
`host/`, and once deleted a `wrfinput_d01` by running an ideal-case script.

## What happened

- While probing the host for the PR1-B OpenMP diagnostic, the run directories
  were treated as interchangeable. They are not:
  - `host/lc05_da_run/` = the **5 km** [[LC05 5km SS Case]] — the real-time DA target.
  - `host/KIM-meso_v1.0/run/` = a **100 km ideal** experiment (`ideal_case 7`).
  - `wrfinput_d01.37` there = an **old 1 km** experiment IC copy.
- `run_parity.sh` was run in `KIM-meso_v1.0/run/`; its `rm -f wrfinput_d01` +
  a crashed `ideal.exe` deleted that dir's `wrfinput_d01`.

## Impact

- **No real loss.** The deleted file was the disposable 100 km ideal IC
  (gitignored). The real 5 km IC (374 MB, `DX=5000`) is symlinked from the
  external `ss_real_case_…/SS/` and was never touched.

## Lessons

1. **Real-time DA = 5 km = `host/lc05_da_run/`.** Verify with
   `ncdump -h <wrfinput> | grep ':DX'` (5 km ⇒ `DX = 5000`) before acting.
2. **Never use the ideal scripts (`run_parity.sh` / `run_kdm6ad.sh`) for the real
   case** — they `rm -f wrfinput_d01` and need `ideal.exe`. Run `wrf.exe` directly
   on the existing 5 km `wrfinput`.
3. `/Users/yhlee/KDM6AD` (no `+`/`-k`) is a stale sibling — a red herring; see
   [[Codex Canonical Worktree Decision 2026-06-25]].

Provenance: this session (2026-07-14); codified in `docs/HOST_RUN_LAYOUT.md`.
Related: [[WRF KIM-meso Host]], [[LC05 5km SS Case]].
