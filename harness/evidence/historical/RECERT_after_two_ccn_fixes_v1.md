# What the two CCN fixes cost the evidence base, item by item

`FINDING_segv_localised_to_flow_dep_bdy_qnn_v1` fixed two sites and moved every
`QNCCN`-dependent result. The deployed binary is now `f54ef3c9` (kernel
`9354141b` + corrected `share/module_bc.F`); the campaign's was `a40bd80f`
(kernel `a06c954b`, both sites defective). This is the inventory of what that
costs, taken over all 107 evidence files: 17 cite the deployed binary or the run
tree, and those are the ones at risk.

Three verdicts are used. **STANDS** -- the claim does not depend on the fixed
sites, or was measured on a binary whose identity is recorded and still means
what it said. **COMPLETED** -- the measurement stands and an open question in it
is now answered. **RECERTIFY** -- a number in it would come out differently on
`f54ef3c9` and has to be re-taken before it is quoted again.

## The two fixes are complementary, which resolves the apparent contradiction

`FINDING_ccn_bounds_collapse_v1` reports that the kernel's tile-bounds fix does
NOT collapse the decomposition difference (75 -> 49 at `np = 2`, 77 -> 77 at
`np = 4`), and this campaign measures 0 of 197 with both sites fixed. Those are
not in conflict. That finding's own mechanism explains why:

> The tile loops never reach the domain's outermost ring. `i = 1`, `i = 234`,
> `j = 1` and `j = 282` are written by the memory-bounds loop and not by the
> tile-bounds one, so under the fix they keep whatever `QNCCN` came in as.

That ring is exactly what `flow_dep_bdy_qnn` writes. Measured over the ring of
the one-minute `np = 1` frame:

| binary | ring cells at zero | ring median | interior median |
|---|---|---|---|
| `a40bd80f` both defective | **27.7%** | 9.992e+07 | 1.028e+08 |
| `4c899067` `module_bc` fixed only | 0.0% | 1.000e+08 | 1.028e+08 |
| `f54ef3c9` both fixed | 0.0% | 1.000e+08 | 1.027e+08 |

So the kernel owns the interior and the boundary routine owns the ring. Neither
fix alone suffices and the pair does. The "at least one other
decomposition-dependent site" that `FINDING_ccn_bounds_collapse_v1` inferred is
`flow_dep_bdy_qnn`.

Completing that finding's own table, one minute, of 197 fields:

| binary | `np = 2` | `np = 4` |
|---|---|---|
| deployed, memory bounds | 75 | 77 |
| + tile-bounds fix only | 49 | 77 |
| **both sites fixed (`f54ef3c9`)** | **0** | **77** |

## The inventory

| finding | verdict | why |
|---|---|---|
| `ccn_bounds_collapse_v1` | **COMPLETED** | Measurements stand. Its open second site is now named, and its table is completed above. |
| `qnccn_first_write_v1` | **COMPLETED** | Located the kernel site correctly. It is one of two; the boundary copy is the other. |
| `second_decomposition_defect_v1` | **STANDS** | Predicted "the tile-bounds fix leaves `np = 4` at 77 differing fields". Confirmed exactly on `f54ef3c9`. |
| `np4_seam_is_rounding_v1` | **STANDS** | Sizes the `delz` i-seam, which neither fix touches. `2x2`/`4x1` remain at 77. |
| `seam_direction_and_1x4_crash_v1` | **COMPLETED** | Its `1x4` row read "did not run". It now runs and is 0 of 197. `2x2`/`4x1` counts unchanged. |
| `middle_rank_crash_v1` | **COMPLETED** | The crash it describes is `flow_dep_bdy_qnn`; the mechanism is the sign of `(k - jms)`. |
| `middle_rank_hypothesis_refuted_v1` | **STANDS** | The refutation holds and now has a mechanism: the `j` memory origin, not the `j` band. |
| `real_mpi_decomposition_v1` | **RECERTIFY** | Its headline -- one field, `QNCCN`, at `np = 2` -- is 0 on `f54ef3c9`. The claim was true of its binary and is not true now. |
| `qnccn_divergence_locus_v1` | **RECERTIFY** | Maps a 687 086-cell `QNCCN` band that no longer exists. |
| `ccn_onetime_reference_v1` | **RECERTIFY** | A collapse test against a reference, on the old binary. |
| `ccn_destroys_valid_input_v1` | **RECERTIFY** | The overwrite of external `QNCCN` needs re-measuring against the corrected block. |
| `ccn_overwrites_microphysics_v1` | **RECERTIFY** | Same; the per-tile overwrite argument is about the loop that changed. |
| `mpi_repeatability_v1` | **STANDS** | Same-decomposition reproducibility re-verified on `f54ef3c9`: `np = 1` and `1x4` each repeat bit-identically. |
| `mpi_trajectory_growth_v1` | **RECERTIFY** | Ten-minute growth of a difference that is now zero in the j direction. |
| `mpi_growth_is_not_distinguishable_v1` | **RECERTIFY** | Compares `np = 4` growth to a 1-ULP perturbation; the `np = 4` baseline moved. |
| `seam_magnitude_and_provenance_pair_v1` | **RECERTIFY** | The `2x2`/`4x1` pair was produced by `a40bd80f`. Field counts are unchanged at 77, per-field magnitudes are not established. |
| `arm_l_mpi_null_v1` | **STANDS, narrowed** | Built from `a06c954b` and carried both defects, so its null is a null about `ncmin` only -- not a statement that the decomposition difference is accounted for. |
| `two_wrf_trees_v1` | **STANDS, extended** | The deployed/reference split it found for `module_mp_kdm6.F` also covered `share/module_bc.F`. Both are now closed: the deployed tree matches the reference for both files. |
| `unwritten_set_is_decomposition_dependent_v1` | **RECERTIFY, and explained** | Measured `QNCCN` at 20 s on a TILE-BOUNDS binary -- kernel fixed, `flow_dep_bdy_qnn` still defective -- and found a residual of 9 971 cells, 0.387 %, decomposition-dependent. That is the ring the kernel does not reach. With both sites fixed the same comparison is 0 of 197 fields. |
| `real_column_ncmin_exposure_v1` | **STANDS** | Reads `wrfinput_d01` directly rather than a forecast, so no deployed binary enters it. |
| `provenance_complete_melt_run_v1` | **STANDS** | Provenance machinery, not a `QNCCN` measurement. |

Everything not listed rests on the Fortran overlay fixtures, the oracle, or the
harness itself, none of which run the deployed binary.

## The graupel melt arms are not affected

They are generated from the repository tree's pinned kernel by textual anchor and
evaluated in the overlay fixtures, not by MPI runs. The one arm result that IS an
MPI result is `arm_l_mpi_null_v1`, narrowed above.

## A build hazard that outranks the list

The deployed tree held a `.f90` and `.o` that did not derive from their `.F`, so
any rebuild silently linked foreign objects -- the first fix binary did, and
every number taken on it was wrong. Before quoting any future rebuild, force a
recompile and confirm the binary hash: the toolchain here is bit-deterministic,
so unchanged sources must reproduce their recorded hash. `a40bd80f` does, which
is how the contamination was proved.

## What recertification costs

Each RECERTIFY item is a re-run of its own recipe on `f54ef3c9` plus its
comparison; the 20-second cases are about 17 s each and the ten-minute
trajectories are the only expensive ones. Nothing here needs a rebuild.
