# S10 exact-zero deposition guard: native stopping witness

**S10 remains OPEN.** An isolated mp237 variant now bypasses `pgdep/rhox`
only when the applied `pgdep` numerator is exactly zero. It preserves the
other graupel-volume terms in their source order. For nonzero `pgdep`, it
requires the preceding `ProgB_param` call to have assigned a finite, positive
`rhox` before retaining the original quotient. It does not choose a substitute
density, change the operational default, or alter the other `rhox` consumers.

The variant uses the safe S10PAIR logger from [PR #318's bounded pair
trace](REPORT_S10_stage2_pair_2026-09-29.md). Its generator pins the private
mp237 source and emits a removable opt-in block. Six focused Python tests and
Ruff pass. The generated Fortran compiled and linked into an isolated WRF
executable. The same-executable logging-OFF/ON comparison was **not** possible:
the first logging-OFF native 20-second attempt stopped before the selected
S10PAIR event. No completed guarded trajectory or new history parity is
claimed.

The first-fatal record comes from step 1, `ProgB` site 5, loop 1, preceding
substep 0, `(j,i,k)=(84,117,17)`. The guard saw nonzero `pgdep` and an
unassigned `rhox` from that call, then stopped before the division. It never
read or printed the undefined density.

| Defined quantity at the failing consumer | REAL4 word | Value |
| --- | --- | ---: |
| Applied `pgdep` | `AD189462` | −8.673147269822046×10⁻¹² |
| Current graupel mass `qg` | `37E758D5` | 2.7578711524256505×10⁻⁵ |
| Current graupel volume `brs` | `00000000` | 0 |
| `qcrmin` | `3089705F` | 9.999999717180685×10⁻¹⁰ |
| `brs_min` | `26901D7D` | 1.0000000036274937×10⁻¹⁵ |

The current `qg` is **after** the stage-2 mass store, whereas the preceding
`ProgB` density gate saw its earlier input. Comparing this current mass to
`qcrmin` does not establish that the earlier gate should have been active.
The assignment bit independently records that it was inactive. Source audit
shows the mismatch: `ProgB` assigns `rhox=qg/brs` only when its input
`qg>qcrmin` or `brs>brs_min`, while the `pgdep` producer can run for a
smaller positive graupel mass. Its negative applied rate here therefore
reaches a consumer without a defined current-call density.

The exact-zero branch remains a valid local bypass for a zero numerator, but
the native stop proves that bypass alone cannot complete this 20-second
trajectory. It is an explicit invalid-state detector, not an accepted S10
repair. A physical rule for nonzero deposition/sublimation when the
graupel mass-volume pair is below `ProgB`'s activation threshold is still
needed, followed by the same-run value, moment-budget and derivative checks.
Using `denr`, a fixed midpoint, or suppressing `pgdep` would each select a
different physical algorithm; the present evidence does not justify one.

Source checks have separate scopes. Removing the opt-in blocks restores the
S10PAIR overlay exactly and then the canonical source exactly. WRF's
macro-OFF preprocessed file is **not** byte-identical to the pair-only file:
inserted blank lines shift a generated `wrf_error_fatal3` diagnostic location
literal. That source-pin failure is retained and is not called a parity pass.
The failed run's [compact receipt](S10_exact_zero_guard_run1/diagnostic_receipt.json)
and [single S10ZF row](S10_exact_zero_guard_run1/first_fatal_row.txt)
identify the source, generated overlay, object/executable, input, failed run
and absent completed-history comparison. Their SHA-256 values are
`89b9b4b84d1d83f9ecf81f74a3a2332b6718866253d993169767f3faedbc3b31`
and `da3cb3deb821748edc2f291034fc905705fa855a43962dad1003f7dba6844b92`,
respectively.
