---
title: Native QNC seven-cell PD/RK3 state trace — 2026-10-27
type: source
date: 2026-10-27
---
# Native QNC seven-cell PD/RK3 state trace

Four full-domain host steps compare the historical control and alpha0.25
actual-wire T/Q inputs with seven-cell QNC tracing off/on. Same-input
checkpoints and ACKs are raw-bit identical across 652 variables and
322,426,586 numeric elements. The seven-cell V2 trace records PD preparation,
ordinary RK3, scalar-boundary-after and pre-microphysics stages, with 728
binary32 values per trace-on run.

PD changes `SCALAR_OLD` and clears `SCALAR_TEND` while leaving live QNC
unchanged. Ordinary RK3 consumes that prepared old buffer and the same-run
face-derived `ADVECT_TEND`; all seven cells' source-compatible outputs match
recorded QNC. Boundary-after and pre-microphysics QNC equal immediate RK3
output. The target is `+3.442540646` in control and `−3.814399242` in
alpha0.25 before microphysics. The final candidate checkpoint instead has
NC=0 with positive QCLOUD, so the earlier optical invalidity remains.

The pre-microphysics-to-checkpoint changes in other cells are an observed
interval, not a named-process attribution. Raw NC units, whole-domain number
conservation, candidate RTTOV cost and another assimilation remain open.
No emitted FMA instruction sequence is claimed.

See [report](../../docs/NATIVE_QNC_STATE7_TRACE_20261027.md) and
[source-bound packet](../../harness/evidence/native_qnc_state7_2026-10-27/README.md).
