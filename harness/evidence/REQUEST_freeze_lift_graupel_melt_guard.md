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

## What must NOT be done

**Clamping the denominator.** `max(rhox, eps)` turns a negligible melt into a
large bulk volume, which is the failure mode `ProgB_param`'s `[100, 900]` clamp
exists to prevent. The divisor is not small; it is absent.

## Acceptance

    the four land columns that fail   0 non-finite at 5, 10, 15, 20, 30, 60 s
    every arm on the gradient fixture bitwise unchanged
    the 23-column batch              medians unchanged within the screen

The last is the load-bearing one: cells in the window carry `qg <= 1e-9`, so a
correct fix must not move any published number. If it does, it changed more
than the division.

## Not asked

What to do with the leftover `qg` below `qcrmin`, and whether the number and
volume fields should be zeroed with it. That is a modelling decision about a
threshold's meaning, and this request is deliberately the smaller one: stop
dividing by a quantity the code declined to compute.
