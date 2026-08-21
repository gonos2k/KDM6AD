# The three defects violate three different invariants, and on this fixture they do not interact

The review's item 3 asks whether the three corrections add independently or
interfere: local `ncmin` changes which branch a column takes, that changes what
sediments, that changes what the interface transfer moves, and the number
correction changes the next call's field. Any of those could couple.

Eight arms, `g33_fixture_boundary_mapping_v1` (land/sea/land), `nsplit = 12`,
`rezero`, first call — the same initial state on every arm, so this is the
operator and not an accumulated difference.

| arm | N | C | L | \|R_nr\|/start | \|R_ni\|/start | partition |
|---|---|---|---|---|---|---|
| `legacy` | 0 | 0 | 0 | 3.685e-03 | 1.703e-01 | 45/144 |
| `nmass` | 1 | 0 | 0 | 1.936e-17 | 7.540e-17 | 45/144 |
| `lncmin` | 0 | 0 | 1 | 3.685e-03 | 1.703e-01 | 0/144 |
| `nmasslncmin` | 1 | 0 | 1 | 1.936e-17 | 7.540e-17 | 0/144 |
| `conservative` | 0 | 1 | 0 | 3.685e-03 | 1.468e-01 | 45/144 |
| `cons_nmass` | 1 | 1 | 0 | 1.936e-17 | 6.546e-20 | 45/144 |
| `cons_lncmin` | 0 | 1 | 1 | 3.685e-03 | 1.468e-01 | 0/144 |
| `cons_nmasslncmin` | 1 | 1 | 1 | 1.936e-17 | 6.546e-20 | 0/144 |

`partition` is the number of per-(split, global column, level) final states that
differ between the single tile and `(2,1)`.

## Reading it

**`R_nr` responds to N and to nothing else.** Every N=1 arm gives the identical
1.936e-17 whatever C and L are; every N=0 arm gives the identical 3.685e-03.

**Partition invariance responds to L and to nothing else.** Every L=1 arm is
0/144; every L=0 arm is 45/144.

**C moves only `R_ni`**, and only while N=0 (1.703e-01 -> 1.468e-01). With N=1
the ice residual is already at roundoff and C moves it from 7.5e-17 to 6.5e-20,
which is roundoff either way.

So on this fixture the cross terms are at roundoff: each defect violates a
different invariant and correcting one does not disturb another.

## What this is not

One fixture, one call, f32, `nsplit = 12`. It says the three corrections are
SEPARABLE AS OPERATORS here. It does not say they are separable in a
trajectory: the arms diverge after the first call precisely because their
fields differ, and coupling through fall speed, cap activation and the next
call's rates is exactly what a trajectory would expose. That measurement is
not in this finding.

## The first reading was wrong, and how

`nmasslncmin` initially read 4.664e-03 -- WORSE than legacy. It was the
analyzer: `NUMBER_CARRIES_DENSITY` was a set containing exactly `nmass`, so
every combined arm was read back with the thickness-only weight, which
reconstructs transfers that never happened. The same confusion -- an
ALGORITHM's property recorded as a fixed list -- had already cost one reading
earlier in this cycle, on the species table. It is asked of the arm's own name
now.

Worth keeping: an apparent INTERACTION is the reading most likely to be an
instrument artefact, because it is the one nobody has a prior for.
