---
title: Synthetic capture runner closure and field contract
type: source
date: 2026-11-13
---

# Synthetic capture runner closure and field contract

The [runner closure report](../../docs/NATIVE_HOST_RUNNER_CLOSURE_20261113.md) addresses two synthetic budget-runner defects after [[native-host-gate-receipt-2026-11-12|#589]]: a second termination signal could interrupt TERM→KILL cleanup, and initial validation or final receipt storage could exceed the budget while a completed status survived. The revised adapter records repeated signals, attempts full group cleanup, accounts for every planned call and measures from before asset validation through final durable completion. A separate completion marker binds the receipt and plan hashes; failures or overruns leave no valid marker. These are synthetic stub tests, not a KDM execution.

The future receipt-to-FD adapter requires 45 call-specific condition assets with the **#586 captured** 1,170 Boolean and 195 schedule key inventory. It assembles selected and diagnostic endpoints with 21 represented JVP payloads but remains `NOT_ELIGIBLE` because source/build/loader provenance and live intermediate tangents are absent. A public-only source archive maps seven planned categories to 28 measurement requirements and 19 proposed masks; every new measurement is `BLOCKED`, and the current adapter rejects additional masks until a reviewed successor contract exists.

The 45-input `SPEC_ONLY` plan and physical-unit status have not changed. An `EXECUTION_READY` successor, isolated DSO, actual ABI producer and independently checked same-call assets must precede NC/PII/applied-budget claims. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.
