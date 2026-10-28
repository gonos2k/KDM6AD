---
title: Native QNC failed-layer applied-face preflight — 2026-10-28
type: source
date: 2026-10-28
---
# Native QNC failed-layer applied-face preflight

Following [[native-qnc-applied-face-guard-2026-10-28]], four accepted
full-domain READY40→60 s host steps recorded the final RK3 QNC applied-face
and state operands at the 54 liquid failure layers. Trace off/on ACK and
checkpoint hashes match within control and α=0.25, and both endpoints equal
the established PR #471 results. The new trace is passive; no correction
was applied.

With saved f32 inputs interpreted exactly, the low-order plus source amount
is positive at all 54 layers in both cases. The applied correction produces
a negative exact numerator at 7 control and 48 α layers. At the other 6 α
layers the exact numerator is positive while the stored RK3 NC is negative.
Control stores positive NC and α stores negative NC at all 54 layers; QC is
positive and the pair is unchanged across scalar boundary handling. Every
selected layer has a source-compatible face tendency and RK output, but the
executed FMA instruction sequence is not identified.

This means a positive exact-face guard would also change selected control
cells, and six α layers require a separate f32 rounding condition. The
calculation is a numerical RK-coordinate diagnostic, not a physical
particle-number conservation result. The Registry, KDM and RTTOV number
bases still need a shared contract before physical interpretation.

See the [report](../../docs/NATIVE_QNC_DOMAIN_PREFLIGHT_20261028.md) and
[hash-bound packet](../../harness/evidence/native_qnc_domain_preflight_2026-10-28/README.md).
