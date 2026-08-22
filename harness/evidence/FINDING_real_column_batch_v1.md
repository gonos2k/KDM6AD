# Twenty-two real columns, not one

`FINDING_real_column_replay_v1` ran ONE column of the operational case and found
Arm N leaving 1.88 % of the legacy dry defect, against a domain-wide coefficient
estimate of 1.92-1.98 %. One column is an instance -- which is why that
fixture's ceiling is STRUCTURAL_ONLY -- and a single agreement can be a
coincidence.

`g33_real_column_batch.py` runs the same experiment over a sample. The fixture
data are compile-time constants, so each column is a separate manifest, a
separate generation and two separate builds; the tool restores the committed
column when it finishes, including after a failure.

## The distribution

Twenty-four columns selected evenly from those carrying `QNRAIN` over at least
six levels; twenty-two produced a usable pair.

| | columns | median | p25 | p75 | min | max |
|---|---|---|---|---|---|---|
| all | 22 | **2.19 %** | 1.13 % | 2.84 % | 0.14 % | 5.47 % |
| land (`xland` = 1) | 5 | 2.63 % | | | | |
| sea (`xland` = 2) | 17 | 1.98 % | | | | |

**The single column's 1.88 % was on the low side of a distribution spanning a
factor of forty**, and the domain-wide coefficient estimate of 1.92-1.98 % sits
just below the sample median. The interquartile range is 1.13-2.84 %, so any one
column says little about the next.

The first version of this table said 2.31 %, which is the UPPER MIDDLE value of
an even sample and not its median: with 22 columns the median is the mean of the
11th and 12th, 2.19 %. A small difference and the wrong name for it.

**And this is not an unbiased sample of the state.** The columns are taken at
even intervals along a row-major list of those carrying `QNRAIN` deeply enough,
which spreads them spatially and balances nothing -- not land against sea, not
moisture-gradient quantile, not rain intensity, not the size of the legacy
defect. It is a deterministic spatial sample of one state, and a
regime-stratified one would be a different experiment.

## The sign is not a distribution

**Arm N's dry residual is negative in 22 of 22 columns.** Legacy over-delivers
number across an interface; Arm N removes that and lands slightly on the other
side. The closed form says why -- the remaining term is
`(1+qv_upper)/(1+qv_lower) - 1`, and `qv` decreases upward in every one of these
columns, so the term is negative in all of them. A magnitude that varies by
forty times and a sign that does not is what a mechanism looks like.

## What this does and does not establish

It establishes that the size measured on one column is typical of that state's
columns to within the spread reported here, and that the mechanism's SIGN is
uniform across them.

It does not widen the ceiling. These are 22 columns of ONE case at ONE time, so
it is a sample of that atmosphere and not of atmospheres. It is not a forecast
impact, and `mstep = 1`, first call, f32 throughout.

## Reproducing

    python3 harness/g33_real_column_batch.py <wrfout> --columns 24 \
        --json harness/evidence/g33m_real_column_batch_v1.json

The per-column results are committed beside this note.
