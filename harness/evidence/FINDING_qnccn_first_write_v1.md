# The first divergence: a CCN profile written over memory bounds into an unexchanged halo

Owner authorisation, 2026-08-23, to instrument the deployed tree. The question
was the one `FINDING_qnccn_divergence_locus_v1` mapped but could not answer:
where does `QNCCN` first differ between decompositions?

## This is a RE-discovery, and the fix already exists

Before anything below: the repository tree's kernel revision `9354141b` --
the SHA-pinned reference every fixture result uses -- **already carries the
fix**, with a comment that names the defect:

> np>=2 nondeterminism root-fix: TILE bounds only (its:ite/jts:jte/kts:kte).
> The previous ims:ime/jms:jme sweep read delz(=dz8w) in the HALO region, which
> dynamics never writes (dz8w is tile-computed) -> uninitialized heap; the
> garbage-seeded halo NN varied run-to-run (ASLR/heap state) and leaked into
> the trajectory under domain decomposition (np2/np4 runs were not bitwise
> reproducible; WSM6 control was). Tile-interior values are IDENTICAL to the
> old loop (z_sum is a per-column recurrence), so np1 results are unchanged.

So the mechanism below was found, understood and corrected before this campaign
looked at it. What this finding adds is a direct measurement of it, and one
operational fact: **the DEPLOYED binary does not have the fix.** Its revision
`a06c954b` still loops over memory bounds, and every MPI result in this campaign
was produced by it (`FINDING_two_wrf_trees_v1.md`).

It also refines the comment in one place. The comment attributes the
non-reproducibility to varying heap garbage; measured here, the halo `delz` is
**deterministically 0.0000**, which is why the same-`np` repeats in
`FINDING_mpi_repeatability_v1.md` came back bit-identical while `np = 1` and
`np = 2` still differ. Both can hold on different hosts or allocators; on this
one the garbage is a stable zero.

## The site

`module_mp_kdm6.F`, run tree revision `a06c954b`, at `itimestep == 1`:

    do j = jms,jme            ! MEMORY bounds, not tile bounds
      do i = ims,ime
        z_sum = 0.0
        do k = kms,kme
          z_sum = z_sum + delz(i,k,j)
          if (xland(i,j)==1) then
            nn(i,k,j) = (5000.*exp(-0.4*z_sum/1000.)+100.)*1.e6
          else
            nn(i,k,j) = (150.*exp(-0.35*z_sum/1000.)+10.)*1.e6
          endif

`nn` is `QNCCN`. The loop covers the whole MEMORY window -- patch plus halo --
rather than the tile it was called for.

## The measurement

A probe compiled out unless `-DKDM6_QNCCN_PROBE` is set, writing `nn`, `delz`
and `xland` over the memory window immediately after that block, once per tile,
tagged with `its`/`jts`. One 20-second step at `np = 1` and `np = 2`.

The tile structure alone is informative -- **`np = 1` is already two tiles, not
one**:

| | memory j | tiles (jts..jte) |
|---|---|---|
| `np = 1` rank 0 | -4..288 | 2..142, 143..281 |
| `np = 2` rank 0 | -4..148 | 2..71, 72..141 |
| `np = 2` rank 1 | 135..288 | 142..212, 213..281 |

Comparing the full `k x i` slab at every global `j`:

    rows where nn differs AT THE WRITE:   7   (j = 135..141)
    rows where delz differs AT THE WRITE: 6   (j = 135..140)

and `j = 135..141` is exactly **rank 1's halo**: its memory starts at 135 and
its patch at 142.

## What is there

| j | `nn` differs | `delz` differs | `delz` at np=1 | at np=2 |
|---|---|---|---|---|
| 134 | no | no | 408.74 | 408.74 |
| **135** | **yes** | **yes** | 409.18 | **0.0000** |
| ... | | | | |
| **140** | **yes** | **yes** | 408.32 | **0.0000** |
| 141 | yes | no | 408.14 | 408.14 |
| 142 | no | no | 409.20 | 409.20 |

**Rank 1's halo `delz` is zero.** The halo has not been exchanged when the block
runs, and the block reads it anyway because it loops over memory bounds. `z_sum`
accumulates zeros, so the profile is evaluated at zero height and `nn` is written
wrong in those rows. At `np = 1` there is no such row: the single rank's memory
halo lies outside the domain and its interior is all owned.

This is the FIRST divergence, and it is not `ncmin`
(`FINDING_arm_l_mpi_null_v1.md` shows that cannot fire here at all).

## What this does NOT yet explain

The seed is seven rows. The difference in the OUTPUT after that same step spans
`j = 72..212`, a hundred and forty rows. So something carries the halo seed into
the interior between the write and the end of the step, and this finding does
not show what. The obvious candidate -- a later halo exchange propagating the
bad values back -- is a candidate and not a measurement.

`j = 141` differs in `nn` while its `delz` matches, which the zero-halo account
does not cover either. It was sampled at one `(k, i)`; a column with zeros at
some other level would explain it and has not been checked.

## What was refuted along the way

That the block's memory-bound loop produces different values everywhere. It does
not: 276 of 283 rows are bit-identical at the write, including every row across
the tile boundaries at `j = 71/72`, `141/142` and `212/213`. The defect is
confined to the unexchanged halo, and the first hypothesis -- that the
decomposition changes the profile broadly -- was wrong.

## Provenance

The probe is instrumentation: compiled out without its macro. The kernel,
`configure.wrf` and the deployed `wrf.exe` were restored and verified after
every build and every run. The legacy rebuild of this tree is bit-identical to
the deployed binary, so the toolchain is deterministic
(`FINDING_two_wrf_trees_v1.md`).
