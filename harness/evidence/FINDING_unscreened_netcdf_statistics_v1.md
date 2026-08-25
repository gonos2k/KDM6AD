# One gate covers the stream path and nothing covers the netCDF path

Two NaN defects were found in `g33_mpi_divergence.py` by reading it for what a
statistic could get wrong. Neither was a coincidence, and the rule that
predicts where they were is worth more than either fix.

## The rule

`g33_number_transport.py` refuses non-finite values at the boundary --
**"No NaN or Inf may enter a store (owner P0-5)"** -- after a NaN `XFER` once
parsed cleanly, made the matched residual NaN, and reached a JSON writer that
emitted a bare `NaN` token. Everything downstream of that gate is safe by
construction: a comparison like `abs(left - uncapped) > tol` cannot silently
read a NaN as "within tolerance", because a NaN never arrives.

**Nothing plays that role for netCDF.** Seven harness modules open a state or
forecast file directly, and the gate is not on that path.

## Where that leaves each of the seven

| module | input | what it does | exposure |
|---|---|---|---|
| `g33_mpi_divergence` | wrfout | statistics | **had two defects; fixed** |
| `g33_number_basis` | wrfinput | statistics | exclusion now explicit + counted |
| `g33_real_column_batch` | wrfinput | statistics | unscreened, **untested** |
| `g33_real_column_density` | wrfinput | statistics | unscreened |
| `g33_real_column_ncmin` | wrfinput | statistics | unscreened |
| `build_c4_evidence` | wrfout | exact comparison | safe by construction |
| `strict_bitwise_nc` | wrfout | raw-bit comparison | safe by construction |

The split is not about care taken; it is about the shape of the operation.
**An exact or bitwise comparison is NaN-correct in the safe direction** -- NaN
equals nothing, including itself, so a difference is reported rather than
hidden. **A statistic is not**: `abs(x - y) > 0` and `abs(d) > threshold` are
both False at a NaN, so a broken cell reads as an agreeing cell and every
count, fraction and percentile understates without saying so.

## The two that were real

`field_stats` reported `differing = 0` -- "the two decompositions agree
everywhere" -- for a field non-finite in one and finite in the other, which is
the one outcome a divergence tool exists to catch. `coverage()` called the same
field DIFFERENT, because `array_equal` is NaN-correct, so the two statistics in
one report contradicted each other exactly there.

`precipitation` counted a NaN column as not exceeding every threshold, so the
exceedance fractions understated with no census.

`reflectivity` needed no change, and the reason is the rule again: its physical
screen is `(x >= lo) & (x <= hi)`, NaN fails every comparison, and the cells
land in `outside_physical` where they are counted. It is screened, so it is
safe -- by the same mechanism, applied for a different reason.

Both fixes are verified no-ops on finite data: 200 randomised pairs for
`field_stats` and 50 for `precipitation`, agreeing with the old predicate on
every statistic compared.

## Not claimed

That the three remaining unscreened statistical modules are WRONG. Nothing
here says their inputs ever carried a non-finite value; it says they would not
report it if they did, and that no gate stands between the file and the
statistic. `g33_real_column_batch` is the one to look at first: it is 373 lines,
it produces evidence a finding cites, and it is one of only two harness modules
with no test reference anywhere.

That the netCDF path should get the store's gate. Refusing outright is right
for a store that must be citable later; a diagnostic that reads a forecast may
legitimately want to REPORT the broken cells rather than refuse the file. What
the fixes here do is the second thing.
