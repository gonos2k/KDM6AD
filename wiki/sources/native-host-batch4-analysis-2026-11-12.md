---
title: Selected host-column output screening and shared capture plan
type: source
date: 2026-11-12
---

# Selected host-column output screening and shared capture plan

The [saved analysis packet](../../harness/evidence/native_host_batch4_analysis_2026-11-12/README.md) extends the [[native-host-shared-screening-2026-11-12|#586 bounded same-column screening]] to 28,548 output rows and 4,212 NC second-forward rows without another KDM run. It separates equal-word unresolved outputs, distinct output words under recorded-mask stability, and the two PII mask-crossing cases. It provides field-scale, absolute, relative and output-ULP diagnostics, but no general retrospective derivative pass threshold or whole-Jacobian claim.

For NC=0, the center-to-`+h` and `+h`-to-`+2h` outputs remain distinct observations; the NC16 first-forward estimate grows roughly with inverse step while the saved JVP stays finite. Upper PII crosses recorded masks at `h=10⁻⁴` on one side; both `h=10⁻⁵` endpoints keep recorded masks, yet one step alone cannot establish a two-step accuracy verdict. The [prospective gate](../../docs/NATIVE_HOST_OUTPUT_FD_GATE_V1_20261112.md) and [single-build capture plan](../../docs/NATIVE_HOST_BATCH4_COMMON_CAPTURE_20261112.md) fix the next input/operand/ledger inventory before further model calls.

The [number-measure note](../../docs/NATIVE_HOST_NUMBER_MEASURE_GATES_20261112.md) links the active host Registry and direct mp137 raw packing to the four number fields, while keeping dry/ moist mass, volume thresholds and same-call process budgets unresolved. The conditional water residual from #586 is arithmetic on one f32 B=1 call, not an approved physical conservation verdict. Isolated joint state+forcing AD and the installed Legacy DSO remain separately attributed; host-coupled forcing and GK2A–RTTOV cost derivatives remain open.

The one-hour ice-census test optimization reuses a hash- and plan-bound result inside one pytest session while preserving separate wrapper metadata and ten-minute prefix checks. It changes test cost, not the production replay or scientific result.
