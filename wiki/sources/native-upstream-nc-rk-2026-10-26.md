---
title: Native upstream QNC RK trace — 2026-10-26
type: source
date: 2026-10-26
---
# Native upstream QNC RK trace

Four full-domain 20-second host steps compared control with the prior alpha=0.25 T/Q proposal. Each case ran trace-off/on from the same READY checkpoint. Both pairs were bit-identical across 652 variables and 322,426,586 numeric elements; the trace records the upstream RK input to KDM.

At native `(221,63,6)`, both runs start with QNC 13,605,366. RK2 becomes negative in both. After the positive-def preparation, RK3 yields `+3.4425406456` in control and `−3.8143992424` at alpha 0.25. The source-order f32 arithmetic replay matches using an exact-FMA-contraction candidate, but the executed instruction sequence was not captured. The second point `(91,94,4)` was already QC-positive/NC-zero at READY; its later negative alpha result is an inherited mismatch.

This locates an applied host state transition, not a named-process cause: the interval includes analysis, host preparation, dynamics and other physics, and `ADVECT_TEND` is not decomposed. Raw NC units remain uncertified. The experiment made 4 host steps / 8 KDM entries, 0 RTTOV calls, 0 optimizer calls, and 0 accepted updates. Alpha 0.25 remains inadmissible on fixed support; no candidate cost, new assimilation, forecast or cycling result is claimed. The executed T/Q hook was in a private compiled snapshot absent from canonical active host source.

See [the detailed trace report](../../docs/NATIVE_UPSTREAM_NC_TRACE_20261026.md) and [public packet](../../harness/evidence/native_upstream_nc_2026-10-26/README.md).
