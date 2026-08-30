# The i-cut difference is one band per i patch boundary, and a fourth band that is not on one

`FINDING_seam_is_i_specific_v1` measured that cutting i produces the
decomposition difference and cutting j does not, and left open what in the
i-split produces it. A difference made AT a patch boundary and a difference
made everywhere reach the same 77 fields, so the field count cannot separate
them. Collapsing the differing cells onto each axis can.

Deployed binary `f54ef3c9`, `mp_physics = 137`, one minute (three 20 s steps),
frame 1 against the `np = 1` run. Patch bounds read from each rank's
`rsl.error.*`, not assumed:

    4x1   i patches  1..59 | 60..117 | 118..176 | 177..235   boundaries after i = 59, 117, 176
    2x2   i patches  1..117 | 118..235                       boundary  after i = 117
    1x4   i patches  1..235                                  no i boundary

## One interior band per i boundary, centred on it

| grid | field | interior bands | peak i | distance to its boundary |
|---|---|---|---|---|
| `4x1` | `PH` | **3** | 59, 118, 174 | 0, +1, -2 |
| `4x1` | `T` | **3** | 59, 117, 175 | 0, 0, -1 |
| `4x1` | `W` | **3** | 52, 124, 165 | -7, +7, -11 |
| `2x2` | `PH` | **1** | 118 | +1 |
| `2x2` | `T` | **1** | 118 | +1 |
| `2x2` | `W` | **1** | 124 | +7 |
| `1x4` | `PH`, `T`, `W` | **0** | -- | -- |

The count of interior bands is the count of i patch boundaries. `PH` and `T`
peak on the boundary within two columns; `W`, the vertically staggered field,
peaks within eleven and carries the widest band.

**The j axis has no structure.** Every differing field differs across 280 of
282 j rows (282 of 282 for `W`), in a flat profile, in BOTH i-cut grids --
including `2x2`, which also has a j boundary at 141/142. A j cut leaves no
footprint even when it happens beside an i cut.

**And the control is empty.** `1x4` differs in no i column and no j row, in all
three fields. The bands above are measured against a comparison that returns
nothing when the domain is not cut in i.

## The bands are wider than anything could have carried them there

Interior bands are 34 to 44 columns wide -- a half-width of 17 to 22 columns,
85 to 110 km at `dx = 5 km` -- after three time steps, 60 s. Filling that from
a one-column seed by propagation would need 1400 to 1800 m/s. The sound speed
is about 340 m/s and the winds are two orders below it, so the band is not the
seam difference being advected or propagated outward.

What remains is the numerical domain of dependence: an RK3 step with acoustic
sub-steps applies many multi-cell stencils per time step, and three time steps
of those reach far further than the flow does. This finding does not measure
that; it measures that propagation cannot be the explanation.

## The fourth band

Both i-cut grids carry one more band, and it is not on a patch boundary:

    4x1   PH  i 216..233   peak 230      nearest i boundary 176, 54 columns away
    2x2   PH  i 214..233   peak 232      nearest i boundary 117, 115 columns away
    2x2   W   i 213..234   peak 227      nearest i boundary 117, 110 columns away

The case runs with `specified = .true.` and `spec_bdy_width = 5`, so the
eastern lateral-boundary zone is `i = 230..234`. The band peaks inside it and
trails west by about the same distance the interior bands spread.

**The western zone (`i = 1..5`) carries no band, in either grid.** In both
decompositions a rank owns the western zone without owning the whole domain,
exactly as one owns the eastern zone, and only the eastern one differs. The
pure j cut, whose every rank owns the full i extent and therefore both zones
whole, differs in neither.

So cutting i perturbs the eastern boundary zone and not the western. Nothing
here says why, and the asymmetry is the finding, not an explanation of it.

## What this settles, and what it does not

**Settled: the difference is local to the i patch boundaries, not global.** A
reduction whose order changed with the decomposition would not band; it would
perturb the domain. The i-split difference is anchored at the boundaries, one
band each, plus the eastern boundary zone.

**Not settled: what at an i patch boundary produces it.** A halo width, a
stencil that reaches past what is exchanged, a boundary-zone update applied per
patch -- none is measured here. The band's CENTRE is on the boundary; its
mechanism is not identified.

**Not settled: whether it is a defect.** As in
`FINDING_seam_is_i_specific_v1`: a core exact under a j cut and not under an i
cut is an asymmetry that wants explaining, and this narrows where to look.

**Scope.** One case, one build, one host, `mp37`, `235 x 283 x 40` at 5 km, one
minute, three fields, `np = 4`. Frame 1 only -- the first step is not resolved
separately, because the runs that cut i at one 20 s step on this binary
(`2x3`, `3x2`) wrote no forecast file.

## Provenance

Runs `mp37_k1m_1min_hist1_{1x1,np4_2x2,np4_4x1,np4_1x4}_20260829_10*`, binary
`f54ef3c962a1d6a0`, comparator attribution gate applied on every pair. Measured
with `harness/g33_mpi_divergence.py --frames 1 --footprint PH,T,W`.

## Resolved at one step: the seed is halo-wide and the integration spreads it

The bands above are measured after three time steps, which is why their width
could not be read as a mechanism. Re-run at ONE 20 s step, `4x1` against
`np = 1`, same binary, same runner, both runs made for this purpose:

| field | one step (1 x 20 s) | three steps (60 s) | growth per step | width at zero steps |
|---|---|---|---|---|
| `PH` | 17, 18, 18 | 38, 41, 42 | 11 | **7** |
| `T` | 15, 14, 16 | 34, 37, 40 | 11 | **4** |
| `W` | 19, 20, 20 | 38, 43, 44 | 11.5 | **7.5** |

Each row is the three interior bands. The width grows by about eleven columns
per time step -- five to six on each side -- and the two-point extrapolation to
zero steps leaves four to eight columns, which is two to four columns each side
of the boundary. **That is the halo scale.** The difference is created within a
few columns of the i patch boundary and everything wider is the integration
carrying it outward.

Eleven columns per step is 55 km in 20 s, about 2 700 m/s, roughly eight times
the sound speed. Nothing propagates that fast here; this is the numerical
domain of dependence of one RK3 step with its acoustic sub-steps, not a signal
moving through the fluid.

**The eastern band checks that reading.** It sits against the domain edge and
can only spread west, and it grows at half the interior rate:

    PH  east band   width  8 at one step -> 18 at three steps   (5 per step)
    T   east band   width  8            -> 17                   (4.5)
    W   east band   width 11            -> 22                   (5.5)

A band free on both sides grows at eleven columns per step; one with a wall on
one side grows at five. If the widening were physical it would not care; a
stencil reaching outward from a seed does exactly this.

At one step `4x1` differs from `np = 1` in **28** of 197 fields, against 77 at
one minute. `FINDING_np4_seam_is_rounding_v1` reports 28 at one step for an
i-cut on the arm-C binary, so the two binaries agree on the first-step count.

**Still not settled: what within those few columns.** A halo exchanged too
narrow for the stencil that reads it, a stencil reaching past what is
exchanged, or a boundary-zone update applied per patch all fit a seed of this
width. Naming which needs a probe at the boundary, not another decomposition.

**Provenance for this section.** Runs
`mp37_step1_0min20s_hist0{,_np4_4x1}_20260830_2052*`, made on binary
`f54ef3c962a1d6a0` with the current runner `397b5076`, `experiment_valid` true,
requested grid matching actual, `wrf_exe_sha256` stable across each run. They
were made rather than reusing the 2026-08-29 one-step runs because the runner
changed after those (PR #181 removed the copy-drift gate), and the comparator
refuses a pair whose runners differ -- correctly, since it cannot know the
change was to provenance plumbing and not to what ran.

The case directory `host/lc05_da_run/` had `wrf.exe` symlinked to
`676223e8`, whose `module_mp_kdm6.o` is older than its `.F`, rather than to the
deployed `f54ef3c9`. It was corrected before these runs.

