---
title: Native activation minimum operands
type: source
date: 2026-11-10
---

# Native activation minimum operands

The [evidence packet](../../harness/evidence/native_activation_operands_cpp_ad_2026-11-10/README.md) records the actual live C++ operands of the fraction and activation-rate minima for the same selected native column and f64 TH/QV sweep as #575. Across 189 observed events, the fraction's pre-minimum power is below one in 104 and above one in 85; none is exactly one. The 85 fraction-one observations therefore have a strict `pow>1` value comparison. At the separate rate minimum, the raw activation rate is below the cap in 104 events and exactly tied in 85. A rate-operand value tie does not identify a tie derivative rule: both relevant operand JVPs are zero at the selected strict interior points.

The separately reconstructed EPS-clamped base is diagnostic and is not the `safe_pow` tensor used by physics. The isolated test-only execution preserves the parent outputs and derivative records, and public replay checks the saved evidence rather than rebuilding the private archive. This one-column f64 sweep has no observed first-minimum value tie, does not prove continuity or a unique derivative at a tie, and supplies no new host capture. Operational f32, physical budgets, whole-host AD and GK2A–RTTOV cost sensitivity remain open; scientific and physical-unit statuses remain `INCONCLUSIVE`.

The replay verifies 197 operand observation objects, including eight bracket endpoint summary copies; these represent 189 distinct operand-bearing forward events, not 197 calls. Each of the four strict points has a resolved same-side pow-operand difference below `10^-5` relative residual. The tied rate-minimum sides have unresolved FD changes and do not measure its tie subgradient.

The 189 events use 105 distinct TH16/QV16 inputs; 84 were evaluated twice. Replay now requires each repeated input's new operand record to match in type and f64 bits. Its portable pow negative test constructs the rejected value from the current runtime `math.pow`, preserving the declared 16-ULP allowance across simulated library offsets.
