---
title: Native TH/QV activation upper-boundary sweep
type: source
date: 2026-11-10
---

# Native TH/QV activation upper-boundary sweep

The [evidence packet](../../harness/evidence/native_activation_upper_boundary_cpp_ad_2026-11-10/README.md) follows the saved native column and 20-second f64 call under initial TH16 and QV16 directions. TH is potential temperature, with physical temperature `TH*pii`. Across 190 full-call forwards, separate bisections for supersaturation `0.48` and observed activation fraction `1` terminate on the same adjacent input words for each axis. The adjacent final NC16 gaps are 1,019 output ULP for TH and 90 for QV. A recorded fraction of `1` does not prove which minimum operand supplied it, because the pre-minimum power value was not captured. The endpoint differences are numerical diagnostics, not a mathematical continuity proof.

Four strict interior sides have AD/VJP results and 16 same-branch one-sided FD evaluations. Each side has at least one resolved NC scale with signal-relative residual below `10^-6`. The smallest QV fraction-`1` NC difference instead has relative residual `0.00226` and absolute mismatch about `0.86` output ULP; it is not evidence of `10^-6` relative accuracy. Side responses do not establish a unique derivative at the cap.

This is one native column, two initial directions and selected f64 branches; unrecorded branches, operational f32, physical budgets, whole-host AD and GK2A–RTTOV cost sensitivity remain open. Scientific and physical-unit statuses remain `INCONCLUSIVE`. Public CI replays saved private runner evidence rather than rebuilding the executable.

The one-sided FD replay binds each nominal step to its exact f64 endpoint coordinate and word and checks distinct positive represented gaps, rejecting duplicated endpoints relabeled as different steps.

Full replay rejects nonfinite boundary payload values and derived FD diagnostics before acceptance, even if another scale passes.

Replay requires the actual TH/QV interior inventory of four AD points and 16 one-sided FD calls, and derives the corresponding call counts from retained data. Terminal bisection trace observations match the bracket endpoints by recorded raw f64 values; repeated evaluations at the same input word, including seeds shared by the two searches, must have matching recorded observations.
