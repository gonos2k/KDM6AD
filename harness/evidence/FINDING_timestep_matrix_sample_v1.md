# The fraction is timestep-invariant per column, and the sample that survives is not the sample that started

The single-column timestep result (1.88-1.90 % across 5-30 s) is now measured
across the real-column sample. It holds -- and running the matrix changed WHICH
columns are in the sample, in a direction that must not be read as a timestep
effect.

## REGENERATED per step, so each step keeps its own sample

The table below conditioned every step on surviving 30 s, which cost four land
columns. With per-step verdicts each step reports the columns that ran it:

| call step | columns | median | failures |
|---|---|---|---|
| 5 s | **23** | 2.0664 % | 0 |
| 10 s | **23** | 2.0628 % | 0 |
| **20 s** (operational) | **21** | **2.0300 %** | **2** |
| 30 s | 19 | 1.9661 % | 4 |

**The operational step has 21 columns, not 19.** Two of them fail at 20 s and
the other two failures are 30 s only -- under complete-case all four vanished
from every step.

### And the failures are the same for both arms

| step | `legacy` | `nmass` |
|---|---|---|
| 20 s | 2 | 2 |
| 30 s | 4 | 4 |

Identical counts, which answers what per-arm recording was added for: the
overflow is a property of the OPERATOR, not something Arm N's correction
introduces or removes.

## Per column, across call steps (the superseded complete-case reading)

Nineteen columns that completed all four steps, Arm N's physical dry residual as
a fraction of legacy's, actual `XFER`:

| call step | median | p25 | p75 | min | max |
|---|---|---|---|---|---|
| 5 s | 1.9642 % | 0.8364 % | 2.7060 % | 0.1256 % | 5.6766 % |
| 10 s | 1.9671 % | 0.8289 % | 2.7099 % | 0.1385 % | 5.6698 % |
| **20 s** (operational) | **1.9678 %** | 0.8314 % | 2.7063 % | 0.1368 % | 5.7711 % |
| 30 s | 1.9661 % | 0.8242 % | 2.7068 % | 0.1344 % | 5.8211 % |

The median moves by 0.0036 points over a sixfold change in call step.

**Per column** -- the statistic immune to which columns are present -- the
relative spread across 5-30 s has a **median of 0.32 %** and a maximum of
16.06 %. So for most columns the fraction is a property of the state and not of
the step, and for one it is not.

## The survivors are not the starters

The matrix requires a column to run at every step, and four columns emit `-inf`
at 30 s (`FINDING_thirty_second_step_overflows_v1`). **All four are land**, and
all four sit above the median:

    (71,147)  2.2894 %      (88,130)  2.8573 %
    (82,145)  2.4704 %     (100,142)  2.9743 %

| sample | n | land | sea | all |
|---|---|---|---|---|
| one step, 5 s only | 23 | 2.6042 % (n = 5) | 1.8717 % (n = 18) | **2.0664 %** |
| matrix, must survive 30 s | 19 | (n = 1) | 1.8717 % (n = 18) | **1.9642 %** |

The land membership falls from five columns to one and the overall median falls
by 0.10 points. **That is a survivorship effect and not a timestep effect**, and
the two sample medians must not be compared as though the difference were
physical. The sea sub-sample is untouched, which is what identifies the cause.

## What to quote

For the SIZE of Arm N's remainder on this state: the 23-column figure,
**2.0664 % actual-`XFER` median** (`FINDING_real_column_batch_v1`), which does
not condition on surviving a step nothing in operations uses.

For its TIMESTEP DEPENDENCE: the per-column spread, **median 0.32 %**, which is
computed within a column and cannot be moved by which columns are present.

Not the 19-column median, in either role.

## Not established

That the four land columns would have been timestep-invariant. They are excluded
precisely because they cannot be run at 30 s; whether their fraction is stable
over 5-20 s is measurable and is not measured here.

Nineteen columns of one case at one time, `mstep = 1`, first call, f32. Two arms,
`legacy` and `nmass`; Arm N_d is not in this sample.
