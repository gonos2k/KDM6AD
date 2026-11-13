---
title: Native host atomic catalog consumer correction
type: source
date: 2026-11-13
---

# Native host atomic catalog consumer correction

The [v2 catalog patch](../../harness/evidence/native_host_execution_successor_2026-11-13/atomic_catalog_consumer_patch_v2.json) separates a source line that explains a measurement group (`context_location`) from a checked use of a particular value (`consumer`). The historical 191-atom draft used `consumer.location` for context in some entries. The compact patch and SHA-pinned parent deterministically materialize the full v2 catalog, then verify only two same-function source uses: `dep_sum_c` enters `xlwork2_cold`, and `t_new` enters the returned `CoordinatorState`. The other 189 atom consumers and 19 proposed-mask consumers remain unverified.

This is a source relationship correction for the [[native-host-capture-preflight-2026-11-12|selected host-column preflight]], not evidence that any of the 191 atoms was emitted or that its live derivative was measured. The successor remains `DRAFT_BLOCKED`; its execution-plan field-catalog, build, DSO, loader and watchdog pins are empty. The private macro-gated sidecar passed one isolated synthetic CTest for value-only metadata and copy-out. An isolated instrumented DSO then built and loaded without any KDM call. Output noninterference and graph-connected JVP/VJP remain unverified. Scientific and physical-unit statuses remain `INCONCLUSIVE`.

A private static audit found direct hook fragments for 45/191 draft atoms and partial source fragments for 16/19 proposed masks. Those counts are source coverage, not emitted records or measured derivatives; all 28 requirement groups remain blocked. The audit itself is not part of public replay.
