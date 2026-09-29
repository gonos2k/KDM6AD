---
title: S5 one-object no-vectorization native follow-up
source: harness/evidence/REPORT_S5_novec_native_oneobject_2026-09-29.md
---

# S5 one-object no-vectorization native follow-up

A strict same-`.f90` compile-option pair ran mp237 for 20 s on the retained
5 km input in local 1×1 and 2×1 layouts. Disabling vectorization only in
`module_big_step_utilities_em.o` removes the selected first-call `calc_ww_cp`
differences at i=117/234, with raw-bit-equal logging-OFF/ON histories.
The complete host still has 28 differing saved variables. At selected call 2,
mass/map intermediates differ at i=117 and flux-derived intermediates differ
at i=234. This does not locate the earliest whole-domain producer or approve
the compiler option as a default. See the [run report](../../harness/evidence/REPORT_S5_novec_native_oneobject_2026-09-29.md).
