---
title: Native QNC flux and limiter trace — 2026-10-27
type: source
date: 2026-10-27
---
# Native QNC flux and limiter trace

Four corrected full-domain 20-second host runs from the same READY40 state
compare control and the earlier alpha=0.25 T/Q proposal, each with trace off
and on. Within each input, ACK and all 652 checkpoint variables / 322,426,586
numeric elements match bitwise. One 77-row scalar-QNC trace per trace-on run
joins its final RK1 and RK3 tendencies to the same run's `ADVECT_TEND` words.

At native `(221,63,6)`, the first recorded control/candidate difference is
after RK1 Y flux. RK3's positive-definite limiter is active in both cases:
`FLUX_OUT > PH_LOW`, with outgoing scales about 0.79922950 and 0.79922843.
Recorded post-limiter faces and cumulative Z→X→Y tendency are consistent with
the applied path. The final RK3 QNC remains positive in control
(`+3.4425406456`) and becomes negative in alpha=0.25 (`−3.8143992424`).

This is not a closed domain number budget or an identified physical cause.
The executed positive-definite routine has no `qmin` or `ieva_corr` term;
those belong to a different monotonic routine. The target `PH_LOW` has a
source-compatible binary32/FMA replay, but the actual instruction sequence
and complete neighboring shared-face ledger were not recorded. Raw NC units
are not certified. The alpha
proposal remains inadmissible; the four runs performed zero RTTOV/optimizer
calls, accepted updates and second assimilations. An earlier V1 capture and a
pre-step plan failure are preserved separately from the selected comparison.

See [detailed trace report](../../docs/NATIVE_QNC_FLUX_LIMITER_TRACE_20261027.md)
and [public evidence](../../harness/evidence/native_qnc_flux_2026-10-27/README.md).
