# S10 first-fatal graupel budget (2026-09-29)

Source: `harness/evidence/REPORT_S10_fatal_budget_2026-09-29.md` and its two
raw REAL4 rows. The native mp237 exact-zero-only variant stopped at step 1,
`(j,i,k)=(84,117,17)`, before an unassigned `rhox` could be read.

The pre-store graupel mass was `0x2F3EB97A`, with zero stored bulk volume.
The applied `pgdep` times 20 s has the exact negative REAL4 word
`0xAF3EB97A`;
`paacw` simultaneously creates new graupel mass, with a positive `baacw`
volume rate. This separates a defined new-particle volume source from the
undefined density needed to remove the old trace mass. It does not choose a
physical density, close a whole-column budget, or approve S10.

Related: [[KDM6AD]] and [[KDM6AD Mathematical Microphysics Operators]].
