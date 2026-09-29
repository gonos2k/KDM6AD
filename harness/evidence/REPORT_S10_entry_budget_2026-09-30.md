# S10 combined opt-in candidate: one native mass–volume–heat update

**S10 remains OPEN.** This follow-up measures the stage-2 graupel update at
step 1, loop 1, substep 0, `(j,i,k)=(84,117,17)` in the existing combined
midpoint, exact-zero-rate and entry-volume mp237 candidate. It does not isolate
which earlier candidate block produced the density or approve 400 kg m⁻³ as a
physical policy. The generator-preparation manifest says `PREPARED_NOT_RUN`;
the [run receipt](S10_entry_budget_run1/receipt.json) and [single raw row](S10_entry_budget_run1/selected_row.txt)
are the execution evidence.

The new overlay logs 41 defined REAL4 operands and states after the actual
mass, volume and temperature stores. It reads `rhox` only when the preceding
ProgB assignment flag is set. Removing its three blocks restores the earlier
entry-candidate source exactly. The canonical private `.F`, host object,
archive and generated module were not changed. This was an isolated
one-object build with `-ffp-contract=off`, using the retained 5 km input,
20 s step, one rank/thread and local `en0` MPI interface.

Logging OFF and ON both completed with saved times 0 and 20 s. The two
histories have identical SHA-256 `55d7162e…bc505c`, and strict comparison
finds **254/254 common variables raw-bit equal** in each frame. That SHA also
matches the earlier, separately built entry candidate. There is exactly one
`S10BUD` row in the ON run and none in the OFF run. These are bounded
noninterference and between-build value results, not a new physical approval.

| Quantity | Before REAL4 | After REAL4 | Decoded context |
| --- | --- | --- | ---: |
| Graupel mass `qg` | `2F3C4DF1` | `37E758D6` | 1.7126191e-10 → 2.7578713e-5 |
| Bulk volume `brs` | `2AF1079A` | `32ECE63B` | 4.2815474e-13 → 2.7578713e-8 |
| Temperature `t` | `43881776` | `43880646` | 272.18329 → 272.04901 K |

The current-call `rhox` was assigned (`43C80001`, 400.0000305 kg m⁻³), and
`dtcld=20 s`. The applied `pgdep` is −8.5630955e-12 per second. Binary32
arithmetic gives **exact zero** for the isolated sub-budgets of old mass plus
`pgdep*dtcld` and old volume plus `(pgdep/rhox)*dtcld`. These are decomposed
checks, not separate executed stores: Fortran sums all rates before updating
each state once. The positive `paacw=1.3789356217e-6` and paired
`baacw=1.3789356323e-9` dominate those full sums. Their
rate ratio is approximately 1000, following the executed
`baacw=paacw/denr` expression.

Replaying the full logged stage-2 expressions in source order reproduces five
stored REAL4 words exactly:

```text
qg_after   37E758D6
brs_after  32ECE63B
xlf        48A9CAD0
xlwork2    40D8624F
t_after    43880646
```

The heat expression includes `paacw` twice, exactly as the current source
does; this arithmetic replay does not determine whether that duplication is
the intended physical attribution. `xlwork2=6.76200056` and the source
temperature store reproduce the measured temperature change. This is a
**local applied update**, not a column water or enthalpy state-function budget.

The moment ratio after this update is about 1000 kg m⁻³, while the logged
`rhox` is the approximately 400 kg m⁻³ diagnostic from the earlier ProgB
call. The density output is not recomputed during this store; subsequent
re-slope/clamp behavior and a physical mixed-density rule remain to be
validated. Neither this arithmetic closure nor the completed 20 s forecast
resolves the particle-number basis, native seven-call Python/C++ parity,
the candidate's AD path, independent radiative accuracy or liquid-observation
acceptance.
