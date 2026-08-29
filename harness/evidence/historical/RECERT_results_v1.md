# Recertification carried out: seven of eight, and two verdicts of my own that were wrong

`RECERT_after_two_ccn_fixes_v1` classified 17 binary-dependent findings and
listed 8 as RECERTIFY. This carries that out on `f54ef3c9` (kernel `9354141b` +
corrected `share/module_bc.F`) and corrects two verdicts in that inventory which
were assigned without reading the finding -- the failure mode this campaign has
been catching all along.

## Two verdicts in the inventory were wrong

**`ccn_destroys_valid_input_v1` STANDS; it was listed RECERTIFY.** Its argument
is that `start_em.F:1778` initialises the CCN profile only when there is nothing
there (`ccn_max_val < 1.0`, "initialization of ccn not already done") while the
kernel's `itimestep == 1` block has no such guard and so destroys valid external
input. The tile-bounds fix does not add the guard: `ccn_max_val` appears **0**
times in the now-deployed `9354141b` and 4 times in `start_em.F`. The claim is
untouched.

**`ccn_overwrites_microphysics_v1` is RESOLVED, not RECERTIFY.** Its mechanism is
that `kdm6` is called once per TILE and "each run rewrites `nn` over the whole
MEMORY window", so a later tile clobbers the microphysics an earlier tile already
computed. Tile bounds is exactly the removal of that: each run now writes only
its own tile. Its unexplained row `j = 142` goes with the mechanism.

Two more are sharpened rather than changed. `middle_rank_crash_v1` stands
**strengthened**: it excluded the CCN block by construction -- Arm C, the block
deleted entirely, still crashed `1x3` -- and concluded "two separate defects
touching the same decomposition machinery". Both are now named.
`provenance_complete_melt_run_v1` stands **with a caveat**: `9354141b` leaves
`rhox` itself alone, changing only the `diag_rhog` export and the reflectivity
`cmg1d`, so its structural melt-arm claims hold; its identification of a specific
failing column came from a ten-minute trajectory on `a40bd80f` and would have to
be re-taken before being re-quoted.

## The recertifications

### `real_mpi_decomposition_v1` -- half of it is now zero

One step, `history_interval_s = 20`, of 197 f32 fields:

| | t = 0 | t = 20 s | worst |
|---|---|---|---|
| `np = 2` vs `np = 1` | 0 of 197 | **1 -> 0** | -- |
| `np = 4` vs `np = 1` | 0 of 197 | **28 -> 28** | `REFL_10CM`, **1.917e+00** relative |

The `np = 4` row reproduces the recorded worst-field magnitude to all four
digits, which is both the result -- neither CCN fix touches the i-seam -- and a
check that this pipeline measures what the original one did.

### `qnccn_divergence_locus_v1` -- the band does not exist

`QNCCN` differing cells at `np = 2`, 20 s: **687 086 of 2 573 532 (26.70 %) ->
0**. South-north rows touched: 141 -> **0**.

### `mpi_trajectory_growth_v1` -- the early footprint halves, the ten-minute state does not move

| field | t | cells differing, was -> now | median at 10 min |
|---|---|---|---|
| `T` | 1 min | 8.75 % -> **5.01 %** | |
| | 10 min | 86.01 % -> **82.80 %** | 9.16e-05, unchanged |
| `QVAPOR` | 1 min | 22.76 % -> **11.52 %** | |
| | 10 min | 94.54 % -> **93.70 %** | |
| `RAINNC` | 10 min | 25.71 % -> **25.39 %** | |
| `REFL_10CM` | 1 min | 4.76 % -> **1.73 %** | |
| | 10 min | 11.17 % -> **11.14 %** | |

Removing the `QNCCN` seed roughly halves the one-minute footprint and leaves the
ten-minute state where it was. The i-seam dominates the trajectory; the CCN
defects dominated only its opening.

### `mpi_growth_is_not_distinguishable_v1` -- the `np = 4` arm is unchanged

Differing fields against the `np = 1` baseline, of 197:

| minute | recorded `np = 4` | now | recorded 1 ULP |
|---|---|---|---|
| 1 | 77 | **77** | 104 |
| 2 | 78 | **77** | 103 |
| 5 | 75 | **75** | 102 |
| 10 | 106 | **106** | 106 |

The conclusion holds. **The 1-ULP arm was not re-run**: it is `np = 1`
throughout and involves no decomposition, and the perturbation is applied
identically to both of its runs, so the CCN fixes shift its baseline and its
perturbed run together. That is an argument, not a measurement, and it is the
one gap in this item.

### `seam_magnitude_and_provenance_pair_v1` -- structure stands, the tail shrank

Per common field, `r_f = log10(E_4x1 / E_2x2)` over relative L2 at one minute:

| | recorded | now |
|---|---|---|
| fields differing, `2x2` / `4x1` | 77 / 77 | 77 / 77 |
| common | 76 | **76** |
| only one grid | `SNOWH` / `TML` | `VIS_SFC_CAPPED` / `TML` |
| median `r_f` | +0.038 (1.09) | +0.098 (1.25) |
| median \|`r_f`\| | 0.177 | 0.137 |
| p90 \|`r_f`\| | **1.017** | **0.541** |
| max \|`r_f`\| | **3.074** (`SNOW`, 1185x) | **2.203** (`RAINNC`, 160x) |

Its structural finding -- the two cuts reach the same NUMBER of fields and reach
them differently, and the field sets are not identical -- stands. The tail it
corrected upward is now itself smaller: the p90 halves and the extreme drops from
a factor of 1185 to 160.

### `unwritten_set_is_decomposition_dependent_v1` -- the residual is zero

Its 9 971-cell, 0.387 % `QNCCN` residual was measured on a tile-bounds binary,
which is the ring the kernel does not reach. The same comparison on `f54ef3c9`
is 0 of 197 fields.

## The one item not carried out

`ccn_onetime_reference_v1` compares the CCN arms against Arm C -- the kernel with
its `itimestep == 1` block deleted. That needs a variant binary, and building
variants beside the deployed tree is what left the stale `.f90`/`.o` this
campaign found. It is left for the owner to schedule, with that hazard stated:
after any variant build, force a recompile and confirm the deployed binary
reproduces its recorded hash before taking a measurement.

## Runs

All on `f54ef3c9`, `mp_physics = 37`, adaptive stepping off, provenance recorded
per run: `1x1`/`1x2`/`1x3`/`1x4`/`2x2` at 20 s, `1x1`/`2x2`/`4x1`/`1x4` at one
minute, `1x1`/`2x2` at ten minutes. Determinism was verified on this binary --
`np = 1` and `1x4` each repeat bit-identically.
