---
title: S13 call-entry heat coefficient lifetime
source: harness/evidence/REPORT_S13_entry_thermo_lifetime_2026-09-29.md
---

# S13 call-entry heat coefficient lifetime

Current private mp37/mp237 source computes `cpm(qv)` and `xl(t)` once before
the outer microphysics subcycle loop. Prior public Python/C++ runtimes
recomputed these two coefficients from the updated state each loop. Their
current paths now carry call-entry tensors through every one-step, including
the post-freeze `work1` calculation that uses entry `xl` and current
temperature. Other diagnostics remain state-dependent.

The selected two-loop C++ temperature changes under this correction, while
selected one-loop `th/qv` words remain exactly unchanged. The prior C++
one-step symbol and public C ABI remain present. This is a source-lifetime
fix, not a fresh historical Gate B comparison; S13's ULP-envelope failures
and other `xlf` consumers remain open. See the [run and validation report](../../harness/evidence/REPORT_S13_entry_thermo_lifetime_2026-09-29.md).

An explicit active-source Fortran selector subsequently reran A/B/C on the
current private mp37/mp237 modules and paired them with fresh C++ A/B/C. The
four-case **debug** comparison remains inconclusive at outer-loop-1 freeze `xlf`:
the selected temperature store rounds identically, but other consumers are
unresolved. The historical Gate A pin does not authorize these active source
hashes. See the [current-source follow-up](../../harness/evidence/REPORT_S13_current_source_fourleg_2026-09-29.md).
