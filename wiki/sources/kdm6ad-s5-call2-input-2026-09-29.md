---
title: S5 second calc_ww_cp caller inputs
source: harness/evidence/REPORT_S5_call2_input_witness_2026-09-29.md
---

# S5 second calc_ww_cp caller inputs

After the selected first-call `calc_ww_cp` differences were removed in a
local one-object no-vectorization mp237 run, the second call still received
different state values. At i=117, `mu_2` differences reproduce the measured
all three differing selected `MUU(117,119)/MUU(118,193)/MUV(117,158)` bits
under the original f32 source order; `u_2/v_2` also differ.
At i=234, one captured `v_2` word is the only differing direct input to the
selected first `DIVV` expression. The whole-host MPI history still differs,
so S5 remains open. See the [run report](../../harness/evidence/REPORT_S5_call2_input_witness_2026-09-29.md).
