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
six levels; twenty-three produced a usable pair. Re-run against the CANONICAL
density -- `mu_d |d(eta)| / g` from `MU`+`MUB` and `DNW`, the layer mass WRF's
own hydrostatic relation makes exact, times `(1+qv)` -- rather than the
thermodynamic estimate the first pass used (owner review §10.2).

Both readers, side by side, because they are different quantities:

| reader | columns | median | p25 | p75 | min | max |
|---|---|---|---|---|---|---|
| recovered endpoints | 23 | 2.2889 % | 1.2518 % | 2.8537 % | 0.1333 % | 5.6691 % |
| **actual `XFER`** | 23 | **2.0664 %** | 1.2422 % | 2.8566 % | 0.1256 % | 5.6766 % |

| | land (`xland` = 1) | sea (`xland` = 2) |
|---|---|---|
| recovered | 2.6012 % (n = 5) | 1.9983 % (n = 18) |
| actual `XFER` | 2.6042 % (n = 5) | 1.8717 % (n = 18) |

**The single column's 1.88 % was on the low side of a distribution spanning a
factor of forty**, and the domain-wide coefficient estimate of 1.92-1.98 % sits
just below the sample median under either reader. The interquartile range is
1.24-2.86 %, so any one column says little about the next.

### The two readers agree in the middle and not in the tail

Per column, `|recovered - XFER| / XFER` has a median of **0.13 %** and a maximum
of **42.86 %**. The medians differ by 0.22 points and one column differs by
nearly half, which is what the review predicted: where the legacy residual is
small, the endpoint-recovered ratio and the emitted-transfer one are not
interchangeable. That is the argument for printing both rather than replacing
one with the other -- a median is exactly the statistic that would have hidden
it.

The published figure was **2.19 % on 22 columns, recovered reader,
thermodynamic density.** It is superseded by the table above; the first version
before that said 2.31 %, which is the UPPER MIDDLE value of an even sample and
not its median.

### One column rejected, and why

`(j, i) = (145, 233)` carries two negative `ni` cells at levels 6 and 7. The
manifest generator refuses negative prognostic input unless told to allow it,
so the column never reached a build. It is reported here rather than dropped
silently: a sample that discards its awkward members is not the sample it
claims to be.

**And this is not an unbiased sample of the state.** The columns are taken at
even intervals along a row-major list of those carrying `QNRAIN` deeply enough,
which spreads them spatially and balances nothing -- not land against sea, not
moisture-gradient quantile, not rain intensity, not the size of the legacy
defect. It is a deterministic spatial sample of one state, and a
regime-stratified one would be a different experiment.

## The sign is not a distribution

**Arm N's dry residual is negative in 23 of 23 columns, under BOTH readers.** Legacy over-delivers
number across an interface; Arm N removes that and lands slightly on the other
side. The closed form says why -- the remaining term is
`(1+qv_upper)/(1+qv_lower) - 1`, and `qv` decreases upward in every one of these
columns, so the term is negative in all of them. A magnitude that varies by
forty times and a sign that does not is what a mechanism looks like.

## What this does and does not establish

It establishes that the size measured on one column is typical of that state's
columns to within the spread reported here, and that the mechanism's SIGN is
uniform across them.

It does not widen the ceiling. These are 23 columns of ONE case at ONE time, so
it is a sample of that atmosphere and not of atmospheres. It is not a forecast
impact, and `mstep = 1`, first call, f32 throughout.

## Reproducing

    python3 harness/g33_real_column_batch.py <wrfout> --columns 24 \
        --json harness/evidence/g33m_real_column_batch_v1.json

The per-column results are committed beside this note.
