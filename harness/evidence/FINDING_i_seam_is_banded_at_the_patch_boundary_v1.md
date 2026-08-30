# The i-cut difference is one band per i patch boundary, and a fourth band that is not on one

`FINDING_seam_is_i_specific_v1` measured that cutting i produces the
decomposition difference and cutting j does not, and left open what in the
i-split produces it. A difference made AT a patch boundary and a difference
made everywhere reach the same 77 fields, so the field count cannot separate
them. Collapsing the differing cells onto each axis can.

Deployed binary `f54ef3c9`, `mp_physics = 37` (Fortran KDM6; the archived `namelist.input` in each run directory is the authority), one minute (three 20 s steps),
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

## Resolved at one step, on one matched pair

The bands above are measured after three time steps, so their width is mostly
spread and cannot be read as a mechanism. Two runs were made for this section
with the current runner -- `np = 1` and `4x1`, one minute, history every 20 s --
so steps 1, 2 and 3 come from ONE pair rather than from two experiments made a
day apart. That matters: the first version of this section compared 20 s widths
from these runs against 60 s widths from the 2026-08-29 runs, which were made
with the pre-#181 runner, while giving "the comparator refuses a pair whose
runners differ" as the reason for making new runs at all. The comparison
contradicted its own premise (owner review 8). Re-measured on the matched pair,
the widths are the same to the column, so the earlier numbers survive -- but
they are now measured rather than assumed.

### The support envelope grows; the relative half-peak core does not

`footprint()` counts cells where `x != y`, so its width is the outer envelope of
ANY difference. For `PH` that envelope's outermost column is **one ULP** on
every band and at every step, while the peak column is 4 512 to 96 932 ULP. The
envelope is a one-ULP fringe around something much smaller, and reporting only
its width would say the difference occupies forty columns when almost all of it
occupies a handful (owner review 5.2). Both are now reported.

`PH`, `4x1`, per band, columns:

| band (boundary) | measure | step 1 | step 2 | step 3 | per step |
|---|---|---|---|---|---|
| 1 (i = 59) | envelope | 17 | 27 | 38 | +10, +11 |
| | relative half-peak core | 6 | 1 | 4 | -5, +3 |
| 2 (i = 117) | envelope | 18 | 30 | 41 | +12, +11 |
| | relative half-peak core | 5 | 2 | 2 | -3, 0 |
| 3 (i = 176) | envelope | 18 | 31 | 42 | +13, +11 |
| | relative half-peak core | 6 | 3 | 1 | -3, -2 |

**The relative half-peak core does not grow.** It stays between one and six
columns at every step measured, while the envelope adds ten to thirteen columns
per step.

**What that does and does not establish (owner review 3.1).** The core above is the
set of columns whose per-column max |diff| is at least half *that step's* peak. It
is a support measured against a MOVING reference, so it narrows under two different
situations: the difference genuinely concentrating, or the boundary peak simply
growing faster than an unchanged surround. Synthetically, multiplying a single peak
by two on an untouched bump collapses this core from 15 columns to 1 while the width
holding 90% of the energy goes only 15 to 14 -- so "the core does not widen" cannot
by itself carry "the difference ENERGY stays localized".

What is established: the envelope's outer columns are a one-ULP fringe, the
per-column magnitude peaks within a few columns of the i patch boundary, and the
relative half-peak support does not widen. Whether the energy stays localized is
**UNMEASURED** here; `core_widths()` in `harness/g33_mpi_divergence.py` now reports
`l2_50` and `l2_90` beside `half_peak` from the per-column L2, and re-running the
footprint on the existing pairs closes it without new fixtures.

This replaces the two-point extrapolation the first version of this section
used. That fit reported an "effective width at zero steps" of 4 to 8 columns
and its `W` value, 7.5, was not reproducible from the per-band table (the
per-band intercepts are 9.5, 8.5, 8.0, median 8.5), and the per-band range
across all three fields was 2.5 to 9.5, not 4 to 8 (owner review 9.2). The
extrapolation is dropped rather than corrected: the core width measures the same
quantity directly, at three steps instead of inferring one before the first.

### The envelope's growth rate is not physical

Across the three interior bands and three fields the envelope adds **9 to 13
columns per step**, one outlier at 7 and one at 14. The envelope grows at BOTH
edges, so an edge advances at half that:

    edge rate   4.5 to 6.5 columns per step
                = 22.5 to 32.5 km per 20 s
                = 1.1 to 1.6 km/s, about 3.5 to 4.5 times the sound speed

The first version of this section read the whole-width rate as a propagation
speed and reported 2 700 m/s and eight times the sound speed, which is twice the
value the geometry supports (owner review 10). The qualitative reading is
unchanged: nothing in this flow propagates at even the corrected rate, so the
fringe advances by numerical domain of dependence, not by a signal in the fluid.

### The eastern band is consistent with one-sided expansion, and is not proof

The eastern band is pinned against the domain edge and can widen only westward.
It adds 4 to 7 columns per step -- one edge's worth, and comparable to one
interior edge:

    interior band   two free edges   9-13 columns per step of total width
    eastern band    one free edge    4-7

That is what one-sided support expansion looks like. It is NOT proof of a
stencil mechanism, and the earlier claim that "physical widening would not care
about the wall" was wrong: WRF's specified lateral boundary is an active region
with injected external data, a relaxation zone, one-sided tendencies and
inflow/outflow asymmetry, and physical and numerical widening alike are shaped
by it (owner review 11).

For the same reason the eastern band is NOT merged with the interior ones here.
It sits in the lateral-boundary zone and not on a patch boundary, and two source
families are kept apart until something measures them to be one:

    interior i-patch-boundary bands
    eastern lateral-boundary-zone band

### Field counts along the way

At one step `4x1` differs from `np = 1` in **28** of 197 fields, at two steps 71,
at three steps 77. `FINDING_np4_seam_is_rounding_v1` reports 28 at one step for
an i-cut on the arm-C binary, so the two binaries agree on the first-step count.

### Still open, and now stated as such

**CONFIRMED.** After one 20 s step the exact-difference support spans 14 to 20 i
columns around each interior i patch boundary; between steps 1 and 3 that
envelope widens by 9 to 13 columns per step while the relative half-peak core stays
within one to six columns and does not widen.

**OPEN.** The instantaneous first-write support, and whether it is set by halo
width, stencil reach, or a patch-local boundary update. Two to six columns is
compatible with all of them, and neither the exchanged halo width nor the
stencil radius has been read out of the source and compared. Naming which needs
a probe inside the step at the boundary, not another decomposition.

### Provenance for this section

Runs `mp37_lin3_1min_hist0{,_np4_4x1}_20260830_2114*` -- binary
`f54ef3c962a1d6a0` stable before and after each run, runner `397b5076` on both,
`mp_physics = 37` in both archived namelists, `experiment_valid` true, requested
grid matching actual, four frames at 0, 20, 40 and 60 s. The comparator's
attribution gate now also requires the two namelists to agree apart from
`nproc_x`/`nproc_y`, and it passed.

The case directory `host/lc05_da_run/` had `wrf.exe` symlinked to `676223e8`,
whose `module_mp_kdm6.o` is older than its `.F`, rather than to the deployed
`f54ef3c9`. It was corrected before these runs. Runs made through that case
before 2026-08-30 are attributable only by their own recorded `wrf_exe_sha256`.
