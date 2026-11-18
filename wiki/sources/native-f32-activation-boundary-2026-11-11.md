---
title: Native-column f32 activation boundary through C ABI
type: source
date: 2026-11-11
---

# Native-column f32 activation boundary through C ABI

The [evidence packet](../../harness/evidence/native_f32_activation_boundary_2026-11-11/README.md) runs the standard float32 `kdm6_step_c` on the saved `(203,149)` native column. All 624 stored state/forcing values are exact f32 widenings. With production-default controls and a single-column batch, the installed DSO and isolated capture DSO agree in raw f32 bits on the baseline and four terminal endpoints: 468 state, three precipitation and 39 RHOG words per call. The captured activation row is native level 16 at runtime call 1, substep 0. This is C ABI evidence, not a live WRF host-tile capture.

The sweep contains 36 axis/word samples and 35 distinct full-state inputs; the baseline is repeated across TH and QV axes and must match in operands and outputs. The TH transition is between f32 words `439ff9f0/439ff9f1`, and the QV transition is between `3befdf4f/3befdf50`. The two observed predicates, supersaturation at least 0.48 and selected fraction at least one, change across the same adjacent pair on each axis. At the fraction-one endpoints the actual pre-minimum pow operand exceeds one, while the separate raw activation rate equals its NCCN cap. These are value comparisons; the cap tie derivative rule is not identified.

Public replay checks source-order f32 arithmetic through the selected NC/NCCN update, stage-to-final-output raw links, finite values, represented input gaps and output-word resolution. Executed ops and C ABI source snapshots are pinned inside the packet; unavailable installed/capture DSO binary hashes are only cross-checked between saved receipts. The first failed standalone loader attempt was before any C ABI call and is retained as provenance. A sampled adjacent-word transition does not prove global uniqueness, mathematical continuity, or an f32 derivative. Physical budgets, full host parity/AD and GK2A–RTTOV cost sensitivity remain open; scientific and physical-unit statuses remain `INCONCLUSIVE`.
The recorded cloud-complete-evaporation mask is consumed by the checked NC/NCCN arithmetic; its upstream production is not independently reconstructed.
