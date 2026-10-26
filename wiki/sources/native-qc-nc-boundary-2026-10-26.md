---
title: Native QC-NC boundary trace V2, corrected three-case campaign
type: source
date: 2026-10-26
---

# Native QC-NC boundary trace V2 — corrected three-case campaign

The corrected V3 diagnostic campaign traces the no-new-analysis control and
historical α=1 and α=0.25 T/Q candidates. Each arm of an off/on pair ran one independent
40→60 s full-physics step from the original 00:00:40 restart. That restart
already carried prior unaccepted single-column T/Q diagnostic history;
“control” means no new T/Q command this step.

## Executions and noninterference

The execution ledger preserves two initial V2 control steps. Only the initial
on arm emitted a V2 stream, which included 18 storage-level-40 records; the off
arm had no V2 stream. The strict reader rejected the on trace; it remains in
engineering history and is not included in the corrected analysis. Six corrected off/on steps followed: control, α=1 and α=0.25. They
used the same corrected V3 executable and DSO. Across the campaign the ledger
records 8 host steps and 16 integrated MP137 wrapper entries, with zero RTTOV
or optimizer calls.

For each corrected pair, off/on ACKs are byte-identical and full final
checkpoint files match bitwise across all 652 serialized variables /
322,426,586 numeric values. Each pair reproduces its earlier full-physics
endpoint: control SHA `225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070`,
α=1 SHA `ff3c101e3b352594471ac5dfd0daab07c0daff3b6d406c88e2461283389978b5`, and
α=0.25 SHA `77be4282ef36a06ca59473fc69b21334eb719fdcdcea0d211d0238c40387657a`.
The full checkpoints and off/on receipts remain in the private research tree.

## Corrected V2 traces and selected states

The on-arm traces are `control_v3_on`, `alpha1_v3_on` and `alpha025_v2_on`;
all use the corrected V3 build. Each trace has two matched host/kernel CALL
headers. The six streams contain 6,318 finite QC/NC values total (3 runs × 3
columns × 39 levels × 2 fields × 9 stages). Every run has complete target-stage
coverage, exact REAL4→FP64 input widening and exact FP64→REAL4 output casting.
Each second tile remains represented by its header even though it owns no
witness. The α=0.25 run label retains its plan version; its executable and DSO
are the same corrected V3 build as the control and α=1 pairs.

Selected levels show why the READY state and a candidate endpoint must be kept
distinct. At `(i=155,j=25,k=19)`, READY already has QC>0, NC=0. Control and
α=0.25 output QC=NC=0; α=1 retains QC≈7.615×10⁻⁷ with NC=0. At
`(221,63,6)`, control MP_INPUT NC≈3.44254 and remains positive; α=1 MP_INPUT
NC≈12.15087 and output NC≈275,672.28; α=0.25 MP_INPUT NC≈−3.81440 and FP64
output NC=0 while QC remains positive. At `(91,94,4)`, READY already has
QC>0, NC=0. Control MP_INPUT NC≈0.022285 and retains it; α=1 and α=0.25 have
negative MP_INPUT NC and FP64 output NC=0 while QC remains positive. These are
raw stored coordinates; NC physical units are not certified.

`ZERO_OUT_PRE` is sampled after tile bounds are set and before the optional
zero-out branch. `MOMENTS_PRE/POST` sample caller QC/QNC immediately before and
after `moist_physics_finish_em`. The V1 thermodynamic trace is separate and
unchanged. READY-to-MP_INPUT changes span the intervening host evolution; these
stage observations do not identify advection or another process as the cause.

## Scope and evidence

R4 boundary measurement is complete for these three cases; α=0.5 is not in this
trace triad. The measurements preserve the previous inadmissible trial outcomes; they do not repair NC, change
M0, accept an update, evaluate candidate cost, or certify full-host AD. Raw NC
units remain uncertified. R5 candidate-preserving support/cost work and later
optimization remain open. The public packet contains V3 on-arm selected traces
and context arrays, not full checkpoints; off/on full-checkpoint comparisons
are bound by the private execution receipts. Build receipts pin executable, DSO,
objects and source inputs, but do not record builder-script hashes at execution
time. The later [build-producer provenance inventory](../../harness/evidence/native_qc_nc_trace_2026-10-26/receipts/build_producer_provenance.json)
identifies available script bytes without retroactively attesting that they were
the exact scripts used. The `solve_em.F` source reconstruction matches the old
object instruction/relocation bodies, with source-path strings differing; object
byte identity is not claimed.

- [V2 trace contract](../../docs/NATIVE_MOMENT_TRACE_V2.md)
- [Input manifest](../../harness/evidence/native_qc_nc_trace_2026-10-26/input_manifest.json), [analysis](../../harness/evidence/native_qc_nc_trace_2026-10-26/analysis.json), [execution ledger](../../harness/evidence/native_qc_nc_trace_2026-10-26/receipts/execution_ledger.json) and [off/on gate](../../harness/evidence/native_qc_nc_trace_2026-10-26/receipts/noninterference.json)
- [Control context](../../harness/evidence/native_qc_nc_trace_2026-10-26/data/control_v3_on/context_source.json), [α=1 context](../../harness/evidence/native_qc_nc_trace_2026-10-26/data/alpha1_v3_on/context_source.json) and [α=0.25 context](../../harness/evidence/native_qc_nc_trace_2026-10-26/data/alpha025_v2_on/context_source.json)
- [Build provenance inventory](../../harness/evidence/native_qc_nc_trace_2026-10-26/receipts/build_producer_provenance.json) and [archived V3 builder bytes](../../harness/evidence/native_qc_nc_trace_2026-10-26/execution_sources/build_private_host_v3_module_only.py.txt)
- [Strict trace reader](../../harness/native_moment_trace_records.py) and [stage analyzer](../../harness/analyze_native_moment_trace.py)
