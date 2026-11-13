---
title: Native host atomic catalog consumer correction
type: source
date: 2026-11-13
---

# Native host atomic catalog consumer correction

The [v2 catalog patch](../../harness/evidence/native_host_execution_successor_2026-11-13/atomic_catalog_consumer_patch_v2.json) separates a source line that explains a measurement group (`context_location`) from a checked use of a particular value (`consumer`). The historical 191-atom draft used `consumer.location` for context in some entries. The compact patch and SHA-pinned parent deterministically materialize the full v2 catalog, then verify only two same-function source uses: `dep_sum_c` enters `xlwork2_cold`, and `t_new` enters the returned `CoordinatorState`. The other 189 atom consumers and 19 proposed-mask consumers remain unverified.

This is a source relationship correction for the [[native-host-capture-preflight-2026-11-12|selected host-column preflight]], not evidence that any of the 191 atoms was emitted or that its live derivative was measured. The successor remains `DRAFT_BLOCKED`; its execution-plan field-catalog, build, DSO, loader and watchdog pins are empty. A pinned [source archive and patch](../../harness/evidence/native_host_execution_successor_2026-11-13/producer_source/README.md) reconstruct the isolated macro-gated source without changing operational `libtorch/`. That source passed two isolated synthetic CTests in a private build; its DSO was loaded without a KDM call. JVP/VJP record readers and a Python fake ABI adapter are synthetic-tested, but selectors are caller supplied and registered execution remains blocked; graph-mode primal checkpoints remain absent. Output noninterference and actual graph derivatives remain unverified. Scientific and physical-unit statuses remain `INCONCLUSIVE`.

A first private static audit found direct hook fragments for 45/191 draft atoms. The expanded [public source audit](../../harness/evidence/native_host_execution_successor_2026-11-13/hook_coverage_summary.json) now maps 107/191 atoms to curated source fragments; all 19 proposed masks have only partial fragments. These counts are source coverage, not emitted records or measured derivatives; all 28 requirement groups remain blocked.

The historical G33 overlay and old source SHA checks still read their unchanged operational source. The isolated batch5 patch separately reproduces that source when its research macro is OFF; neither static check verifies capture ON. The test-only intermediate JVP/VJP entries recheck effective ATen thread counts and restore the caller's floating-point environment; their graph results remain synthetic evidence only.
