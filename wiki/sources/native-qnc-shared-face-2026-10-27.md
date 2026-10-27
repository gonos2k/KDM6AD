---
title: Native QNC shared-face trace — 2026-10-27
type: source
date: 2026-10-27
---
# Native QNC shared-face trace

Four native full-domain 40→60-second host steps compare control and the
historical alpha0.25 T/Q proposal with trace off/on. Each same-input pair is
bitwise identical across 652 variables and 322,426,586 numeric elements.
The one owned tile records the target `(221,63,6)` and six adjacent cells.

Each of six post-limiter faces has the same correction and low-order binary32
word from both sides. All seven cells' RK3 Z→X→Y tendency stages replay with
source-compatible f32/FMA candidates. This confirms applied local face reuse,
not an executed FMA instruction or a closed number budget: 30 perimeter face
incidences, physical NC units and domain boundaries remain open. Alpha0.25
still enters KDM with negative NC and is inadmissible on the fixed observation
support. No new RTTOV cost or second assimilation was run.

See [detailed report](../../docs/NATIVE_QNC_SHARED_FACE_TRACE_20261027.md) and
[source-bound packet](../../harness/evidence/native_qnc_shared_face_2026-10-27/README.md).
