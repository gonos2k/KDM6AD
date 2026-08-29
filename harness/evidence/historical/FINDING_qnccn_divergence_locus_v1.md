# Where `QNCCN` first diverges: a band, and one row that does not

`FINDING_real_mpi_decomposition_v1` found that one 20-second step at `np = 2`
changes exactly ONE field against `np = 1` -- `QNCCN` -- and declined to name a
mechanism. The review asked for the first divergence to be localised rather than
described through ten-minute statistics. This is that map, from the runs already
taken.

## The decomposition

From `rsl.error.*`, `np = 2`:

    domain   jds..jde = 1..283
    patch 0  jps..jpe = 1..141
    patch 1  jps..jpe = 142..283

so in the 0-based output array, patch 0 is rows 0..140 and patch 1 is 141..281.

## The map

`QNCCN` differs in 687 086 of 2 573 532 cells (26.70 %), over 232 of 234
west-east columns and all 39 levels. The south-north extent is a BAND, not a
boundary line: rows 71 through 211, with rows 0-70 and 212-281 untouched.

And inside that band exactly one row is clean:

| row | differing cells | patch |
|---|---|---|
| 70 | 0 | 0 |
| 71 | 6 018 | 0 |
| ... | | |
| 140 | 5 577 | 0 (its last row) |
| **141** | **0** | **1 (its FIRST row)** |
| 142 | 5 681 | 1 |
| ... | | |
| 211 | 1 912 | 1 |
| 212 | 0 | 1 |

**Row 141 is the first row of the second patch, and it is the only row inside
the band that agrees with the single-tile run.** Its neighbours on both sides
differ in more than five thousand cells each.

At `np = 4` there is no such hole: rows 1 through 280 all differ, with no
interior gap.

## What this rules out and what it leaves

Its terminal footprint is **not boundary-confined**: the difference covers 140
rows on both sides of the split, not a halo-width strip. That was written here
as "not a boundary artefact", which does not follow and turned out to be wrong:
`FINDING_qnccn_first_write_v1.md` measures the FIRST write and finds the seed in
exactly seven rows, all of them rank 1's halo. A wide terminal footprint does
not refute a boundary origin -- it only says something carries it inward.

It is **not roundoff propagation**: the relative difference runs from -98 % to
+4900 % with a median of +22.6 % over 450 000 distinct values. `QNCCN` is being
given substantially different values, not perturbed ones.

It is **not simply "wherever cloud is"**: only 12.2 % of the differing cells
carry `QCLOUD > 0` and 10.4 % carry `QNCLOUD > 0`, while `QNCCN` itself is
non-zero everywhere in both runs.

What remains is a specific fingerprint: a broad band, spanning both patches,
with the first row of the second patch alone agreeing. Naming the site needs
instrumentation -- the first write that changes `QNCCN`, with the rank and tile
bounds beside it -- and that instrumentation belongs in the RUN tree, which is
the one this campaign has not been able to build in
(`FINDING_two_wrf_trees_v1.md`).

## Not claimed

No mechanism. `ncmin` is still not named: it gates cloud droplet number, and
`QNCLOUD` was unchanged at `np = 2` while `QNCCN` alone moved.

One case, one initial time, one step, and the map above is of that step.

## The `ncmin` candidate is ruled out for these runs

This case sets `ncmin_land = ncmin_sea = 10`, verified in the saved namelist of
every MPI run in this campaign. With the two equal, every column asks for the
same threshold and the scalar holds what the array would have held -- so
`ncmin` is identical under every decomposition and cannot produce a difference
between them. Confirmed directly: an Arm L binary is bit-identical to legacy at
`np = 1` on this case. See `FINDING_arm_l_mpi_null_v1.md`.
