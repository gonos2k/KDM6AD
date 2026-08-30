# The decomposition difference is made by cutting i, and not by cutting j

`FINDING_seam_direction_and_1x4_crash_v1` measured `2x2` and `4x1` against
`np = 1` and could not run `1x4` -- the only pure j-cut, and it called that
"exactly the case that could have separated them and is the one missing".
`FINDING_segv_localised_to_flow_dep_bdy_qnn_v1` then located the crash in
`share/module_bc.F`'s `flow_dep_bdy_qnn` and fixed it. `1x4` runs on the
deployed binary, so the control exists now, and it separates them.

## The measurement

Deployed binary `f54ef3c9` throughout, `mp_physics = 137`, one case, one host.
Of 197 f32 time-varying fields, against the `np = 1` run of the same length:

| grid | seams | np | horizon | fields differing |
|---|---|---|---|---|
| `1x2` | 1 j-seam, no i-seam | 2 | one 20 s step | **0** |
| `1x3` | 2 j-seams, no i-seam | 3 | one 20 s step | **0** |
| `1x4` | 3 j-seams, no i-seam | 4 | one 20 s step | **0** |
| `1x4` | 3 j-seams, no i-seam | 4 | one minute | **0** |
| `4x1` | 3 i-seams, no j-seam | 4 | one minute | **77** |
| `2x2` | 1 i-seam and 1 j-seam | 4 | one minute | **77** |

Cutting the domain in j is bit-exact at every rank count tried. Cutting it in i
is not, and adding a j-seam to an i-seam adds nothing to the field count.

## The zero is a measured zero

An empty comparison also reports 0, so the same tool, the same binary, the same
baseline run and the same frame produce the difference when the grid cuts i:

    1x1 vs 4x1  frame 1   77 fields   T 11.37 % of cells, conditional p99 8.9e-04
    1x1 vs 2x2  frame 1   77 fields   T  5.01 % of cells, conditional p99 1.8e-03
    1x1 vs 1x4  frame 1    0 fields   T  0.00 %, domain p99 0.000e+00

Frame 0 is identical in all three, so each pair starts from the same state.

The comparator's attribution gate ran on every pair (`experiment_gate.applied`
true): the runner digest and `wrf_exe_sha256` agree, and the only recorded
differences are `namelist` and `proc_grid`, which is what `--expect
decomposition` allows.

## What it changes

**`FINDING_seam_direction_and_1x4_crash_v1`.** Its open item is closed: `1x4`
runs, and its table's missing row is 0.

**`FINDING_np4_seam_is_rounding_v1`.** It read the identical `2x2` and `4x1`
counts as "what a rounding-scale seed amplified by the flow looks like, and not
what a defect tied to a particular seam looks like -- a geometry-specific fault
would make three i-seams differ from one." That inference is now incomplete
rather than wrong. The count is indeed direction-independent AMONG grids that
cut i; a grid that does not cut i differs in nothing. The magnitudes it
measured stand, and its conclusion that direction does not matter does not.

**The site.** `FINDING_np4_seam_is_rounding_v1` traced the difference upstream
to `PH` with `PHB` bit-identical. This adds that whatever produces the `PH`
difference is exercised when the i-extent is split across ranks and not when
the j-extent is.

## What this does NOT settle

**That it is a defect.** A core whose reductions are order-fixed in j and not
in i is possible, and this measures the asymmetry rather than explaining it.
What it removes is the reading that the difference is direction-blind rounding:
rounding that came from summing in a different order would not care which axis
the patches are cut along.

**The first step, on the i side.** The j-cuts are exact at the first 20 s step
AND at one minute. The i-cuts here are measured at one minute only: the two
one-step runs on this binary that cut i (`2x3`, `3x2`, `np = 6`) completed with
`exit 0` but wrote no forecast file, so there is nothing to compare.
`FINDING_np4_seam_is_rounding_v1` reports 28 of 197 fields after one step for
an i-cut, on a DIFFERENT binary (`arm C`), which is consistent and is not this
binary.

**How far the j-exactness holds.** Rank counts 2, 3 and 4, one minute, one
case. A larger j-cut, a longer forecast or another case are not measured.

**Anything about `nproc_x > 1` in general.** One domain shape, `235 x 283 x 40`
at 5 km. The i and j extents are not equal, and the patch dimensions differ
between `4x1` and `1x4` along with the direction.

## Provenance

Binary `f54ef3c962a1d6a0` (kernel `9354141b`), recorded in each run directory
as `wrf_exe_sha256` with a before/after pair that agree, so the binary did not
change under the run. Runs, all under the SS case's `runs/`:

    mp37_k1m_1min_hist1_1x1_20260829_100735_p58212
    mp37_k1m_1min_hist1_np4_2x2_20260829_100835_p63063
    mp37_k1m_1min_hist1_np4_4x1_20260829_100907_p63527
    mp37_k1m_1min_hist1_np4_1x4_20260829_100941_p65752
    mp37_k20_0min20s_hist0_1x1_20260829_100337_p46495
    mp37_k20_0min20s_hist0_np2_1x2_20260829_100426_p47676
    mp37_k20_0min20s_hist0_np3_1x3_20260829_100459_p48706
    mp37_k20_0min20s_hist0_np4_1x4_20260829_100528_p52304

Each records `requested` and `actual` proc grid and they match, so WRF used the
decomposition the run asked for rather than one of its own choosing.

Compared with `harness/g33_mpi_divergence.py --expect decomposition --frames 1`.
