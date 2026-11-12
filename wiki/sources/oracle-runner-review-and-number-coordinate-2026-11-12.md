---
title: Oracle runner review and native number-coordinate source contract
type: source
date: 2026-11-12
---

# Oracle runner review and native number-coordinate source contract

The [runner review batch](../../docs/ORACLE_RUNNER_REVIEW_BATCH_20261112.md) addresses #584's two nonblocking observations together: timeout cleanup now checks the entire process group after its unittest leader exits, and a small research-branch seed job supplies a possible shared pip-download cache. The existing required Oracle job name and suite registry remain; only the three identified private-asset skip IDs/reasons are allowed. Per-mode artifacts carry checked-out commit/tree, registry hash, Python/worker/timeout and run identity. A pytest wrapper records slow test phases, child CPU/RSS and elapsed time, with cancellations and surviving child groups failing closed. A narrow local 1-vs-2-worker comparison stopped at a 300-second timeout and is [preserved as incomplete evidence](../../harness/evidence/oracle_runner_worker_probe_2026-11-12/README.md); no speedup follows. Cache-hit and whole-job speed effects require later hosted measurements.

The [number-coordinate source review](../../harness/evidence/native_number_coordinate_contract_2026-11-12/report.md) finds active Registry `#/kg` labels for NC/NI/NR/NCCN and a direct legacy mp137 `c_float` handoff without entry `rho_d` conversion. The opt-in `dry_number=1` map is separate. Neither source path proves a physically approved basis for the historical raw selected-column words. The report pins the reviewed public source snapshots and requires private current-source matching only for an explicit local freshness check; scientific and physical-unit statuses remain `INCONCLUSIVE`.
