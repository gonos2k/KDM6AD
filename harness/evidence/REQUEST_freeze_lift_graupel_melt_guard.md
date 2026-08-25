# Freeze-lift request: one existence test for graupel, in the melting block

## What is asked

In `module_mp_kdm6.F`, make the graupel-melting block ask the same question
`ProgB_param` asks before dividing by the density it produces. One condition
changed, in `legacy` and `cons` and therefore in every generated arm.

## Why

`FINDING_thirty_second_step_overflows_v1` measures a non-finite `brs` on real
columns at the OPERATIONAL 20 s call step, and locates it exactly:

    ProgB_param (line 1325, before the melt):
        if (qrs(i,k,3).gt. qcrmin .or. brs(i,k).gt. brs_min) then
            rhox(i,k) = qrs(i,k,3)/brs(i,k)     ! then clamped to [100, 900]

    the melting block (line 1400):
        if (qrs(i,k,3).gt. 0.) then             ! a DIFFERENT threshold
            ...
            brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))

`rhox` is zeroed per sub-step and computed only under the first condition, so in
`0 < qg <= qcrmin` with `brs <= brs_min` it is exactly `0` while the melt runs.
Measured operands at the failing cell, from the stream's own stage dump:

    qg  = 8.29644e-13    ( > 0, and <= qcrmin = 1e-9 )
    brs = 9.21827e-16    ( <= brs_min = 1e-15 )
    t   = 286.117 K

`pgmlt` is already capped at `-qrs(i,k,3)`, so no mass is created; the failure
is the division alone.

## Scope

- `qcrmin` and `brs_min` are already in scope at the melt; no new state.
- The two BASES only (`module_mp_kdm6.F`, `module_mp_kdm6_cons.F`); every arm is
  generated from them, so no variant is hand-edited.
- No change to `pgmlt`, to the mass or temperature updates, or to `ProgB_param`.

## The density is NOT undefined, which changes what the fix is for

The measured operands give

    qg / brs = 8.29644e-13 / 9.21827e-16 = 899.9997

and `ProgB_param` clamps `rhox` to `[100, 900]`. **The failing cell's graupel
density is at the top of the valid range**, not undefined or degenerate. The
division fails only because `ProgB_param` DECLINED TO COMPUTE it -- the absolute
amounts are below `qcrmin` and `brs_min` -- and not because there is no density
to compute.

This request is therefore a SAFETY patch and not a physics decision. Aligning
the melt's existence test with the density's removes the division by zero and
leaves the trace graupel in place, unmelted, with its latent heat and rain-mass
transfer also skipped. That is a defensible branch and it is not the only one:

    G1  skip the melt entirely, as asked here
    G2  compute rhox wherever qg > 0 and brs > 0 -- which at this cell gives
        899.9997 and lets the full melt proceed as physics
    G3  a complete-melt branch: pgmlt is already capped at -qg, so set
        qg = 0 and brs = 0 directly and never divide

The owner review asks for the three to be compared on the failing columns
against mass, enthalpy and `qg = rho_g * b_g` consistency before one is adopted.
This request does not settle that and should not be read as settling it.

## What must NOT be done

**Clamping the denominator.** `max(rhox, eps)` turns a negligible melt into a
large bulk volume, which is the failure mode `ProgB_param`'s `[100, 900]` clamp
exists to prevent. The divisor is not small; it is absent.

## Acceptance

    the four land columns that fail   0 non-finite at 5, 10, 15, 20, 30, 60 s
    every arm on the gradient fixture bitwise unchanged
    every column that ALREADY produces numbers   bitwise unchanged

### The third criterion, corrected

This first read "the 23-column batch: medians unchanged within the screen",
which is **self-contradictory**. The four land columns that hit `-inf` are
REJECTED from the sample today. A fix that works makes them produce numbers, so
they JOIN the sample -- and they sit above the median, which is the
survivorship effect `FINDING_timestep_matrix_sample_v1` measures in the other
direction. **The median must move, and its moving is the fix working.**

What must not move is any column the window never fires in. Those are
bitwise-unchanged or the change reached past the division.

And even on a passing column "no published number moves" is not guaranteed by
the threshold argument alone. In the window the `nr` line at 1414 is guarded
OFF -- it asks `qg > qcrmin` -- but lines 1416-1419 run, so `qr`, `qg`, `t` and
`brs` do change there, and `qr` feeds later processes within the same call.
The rain-NUMBER ledger is what this campaign publishes and is the most likely
to be untouched; that is a prediction to check, not a property to assume.

## Not asked

What to do with the leftover `qg` below `qcrmin`, and whether the number and
volume fields should be zeroed with it. That is a modelling decision about a
threshold's meaning, and this request is deliberately the smaller one: stop
dividing by a quantity the code declined to compute.
