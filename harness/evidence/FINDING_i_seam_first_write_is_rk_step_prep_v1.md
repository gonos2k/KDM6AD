# The first owned-cell difference is `ww`, written by `rk_step_prep`, before the halo exchange

Under the freeze-lift `REQUEST_freeze_lift_dyn_first_write_probe.md`, a probe was
placed inside the first RK stage of the first time step, `np = 1` against `4x1`
(i patch boundaries after 59, 117, 176), on the deployed binary's tree.

## The instrument is inert, and the tree is as it was found

`dyn_em/solve_em.F` (pinned `d66e9db1`) was never edited. A generator wrote a
throw-away copy adding one `#define` and 142 lines, every one inside an
`#ifdef KDM6_G33_DYN_DUMP` block -- audited by deleting the guarded regions and
comparing with the canonical byte for byte. Emission is gated a second time on
`KDM6_G33_DYN_DUMP_DIR`.

    instrumented binary, DUMPING, np = 1   0 of 197 f32 fields differ from f54ef3c9
    instrumented binary, DUMPING, 4x1      0 of 197
    canonical source rebuilt afterwards    wrf.exe == f54ef3c9, bit for bit

The last line is the control the request asks for and also shows the build is
deterministic: the overlay was the only difference, and it is gone.

## The first pass looked in the wrong place

A first version of this probe dumped only the prognostic set -- `u_2`, `t_2`,
`ph_2`, `w_2`, `mu_2` -- and reported the first difference after
`small_step_prep`, with the halo exchange, `rk_tendency` and `relax_bdy_dry` all
clean. The owner's revision of the request named the fault: `HALO_EM_A` moves
`ru, rv, rw, ww, php, alt, al, p, muu, muv, mut, rho`, **a set that does not
intersect the five dumped fields**, so the probe could not have seen a halo
defect and its stage-3 silence meant nothing.

Re-run with the exchanged set and the `rk_tendency` outputs added, the site moves
three stages earlier. The conclusion below replaces that one.

## Where the difference first appears

Owned cells, raw-word comparison. Total differing (field, column) pairs:

| stage | point | differences |
|---|---|---|
| 0 | before the RK loop | **0** |
| 1 | RK-stage entry | **0** |
| 2 | after `rk_step_prep` | **2** -- `ww` at i = 59 and 176 |
| 31 | before `HALO_EM_A` | 2 -- the same `ww` |
| 32 | after `HALO_EM_A` | 2 -- the same `ww` |
| 4 | after `set_phys_bc` | 0 |
| 5 | after `rk_tendency` | 26 -- `ru_tend` `rv_tend` `rw_tend` `ph_tend` `t_tend` |
| 6 | after `relax_bdy_dry` | 29 |
| 7 | after `small_step_prep` | 22 -- `u_2` `t_2` `w_2` first differ here |
| 8-12 | acoustic sub-step | 24, 24, 50, 82, 85 |

**`ww` after `rk_step_prep` is the first, and it is two columns.** At stage 2
every other field of the exchanged set -- `ru`, `rv`, `rw`, `php`, `alt`, `al`,
`p`, `rho`, `muu`, `muv`, `mut` -- is identical, and so is the whole prognostic
set. `ww` is the vertical mass flux.

**Stage 2 precedes the exchange.** `rk_step_prep` is at L652 and `HALO_EM_A` at
L703, so the difference exists before any halo is moved in this step.

## The halo exchange delivers what it declares

Within `4x1` alone, comparing each rank's halo copy against the owning rank's
value of the same global cell -- a check that needs no `np = 1` run:

    muu, boundary 59|60, halo columns 53..66
      before the exchange (31)   53 54 55 56 57 58 59 60 61 62 63 64 65 66  all differ
      after  the exchange (32)   53 54 55 56       61 62 63 64 65 66        59, 60 now match

The exchange fixes **exactly one column on each side** and leaves the rest. That
is `HALO_EM_A` doing what the Registry declares: `8:` is the eight-point stencil,
which is a halo of width one. The columns beyond it are stale by design, and a
wider exchange elsewhere is what would refresh them.

So the halo arrives correct for the width it covers, and the first difference is
not something the exchange delivered wrongly -- it is already in an owned cell
before the exchange runs.

## The eastern band comes from `rk_tendency`, not the boundary code

The eastern columns 231-234 appear first at stage 5, in `ru_tend`, `rv_tend`,
`rw_tend` and `t_tend` -- one stage BEFORE `relax_bdy_dry`, which is stage 6.
The lateral-boundary update is not what makes them.

## The predictions, judged

The request recorded four, as revised by the owner.

1. *"The first difference appears at or before `rk_tendency`."* **HELD.** It is
   two stages before it, at `rk_step_prep`.
2. *"Confined to about three columns of a boundary."* **HELD**, and tighter: one
   column per boundary at the stage where it first appears.
3. *"`U` differs no later than `PH`."* **HELD as an ordering** -- `u_2` at stage
   7, `ph_2` at stage 11 -- but the first field to differ is neither: it is `ww`,
   five stages before `u_2`. The hypothesis was about the wrong pair.
4. *"The eastern band is absent through stage 4 and first present immediately
   after stage 5."* **HELD exactly.** Stage 4 clean, stage 5 carries it.

## What this does NOT show

**That `rk_step_prep` is at fault.** The anchors are call boundaries, so this
brackets the first OBSERVED difference between the RK-stage entry and the return
from `rk_step_prep`. The write is somewhere in that bracket, including inside
anything it calls.

**Why `ww` differs at 59 and 176 and not at 117.** The same two-of-three pattern
appeared in `u_2` at stage 7 in the earlier pass. Nothing here explains it, and a
data-dependent cancellation at one boundary is as consistent with the evidence as
a structural difference between the boundaries.

**That the stale halo beyond width one is harmless.** This shows `HALO_EM_A`
refreshes width one. Whether any stencil in the step reads those fields further
out without a wider exchange first is not measured.

**Anything about later RK stages, later steps, or `mp_physics`.** The probe
covers `itimestep == 1` and `rk_step == 1`; `mp_physics = 37` throughout and the
microphysics runs after the dynamics.

**A probe bug worth recording.** Stage 0 sits above the RK loop, where `rk_step`
is not yet assigned, and the first implementation tested `rk_step /= 1` there --
which silently dropped every stage-0 record. It was fixed and re-run; stage 0 is
measured, not argued from stage 1.

## Provenance

Canonical `dyn_em/solve_em.F` `sha256 d66e9db1...`, restored and rebuilt to
`f54ef3c9`. Instrumented binary `456c5941`. Runs
`mp37_{lin3,probe3}_1min_hist0{,_np4_4x1}` in the SS case, `experiment_valid`
true, requested grid matching actual, one minute, four frames, history every
20 s, `mp_physics = 37` in every archived namelist. Dumps 616 MB and 724 MB.
Overlay generator, record format and reader: `harness/g33_dyn_probe.py`.
