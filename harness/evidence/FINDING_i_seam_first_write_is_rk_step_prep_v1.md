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

## Inside the bracket: the read that crosses the patch boundary

The first version of this section named the wrong array, and correcting it changes
what the measurements support. Every line below was re-checked against the pinned
source, with `file:line` so it can be checked again.

**`calc_ww_cp` does not read `grid%muu`.** It declares and fills its own:

| where | what |
|---|---|
| `dyn_em/solve_em.F:652` | `rk_step_prep` is called with `grid%u_2`, `grid%mu_2`, and separately `grid%muu` |
| `dyn_em/module_em.F:163` | `rk_step_prep` calls `calc_ww_cp ( u, v, mu, mub, c1h, c2h, ww, ... )` -- it passes `mu`, and no `muu` |
| `dyn_em/module_big_step_utilities_em.F:674` | `REAL , DIMENSION( its:ite+1 , jts:jte+1 ) :: muu, muv` -- a LOCAL array that shadows the name of the grid field |
| `dyn_em/module_big_step_utilities_em.F:699` | `MUU(i,j) = 0.5*(MUP(i,j)+MUB(i,j)+MUP(i-1,j)+MUB(i-1,j))` over `DO i = its, min(ite+1,ide)` |

So the `muu` in the divergence is rebuilt inside the routine from `mu` on every
call, is never exchanged, and is not the `muu` that `HALO_EM_A` moves. The earlier
claim -- "`muu` is in the `HALO_EM_A` set, and that exchange runs after
`rk_step_prep`" -- is true of the grid field and does not bear on `ww`.

What the divergence actually depends on, `module_big_step_utilities_em.F:747`, over
`DO i = its, itf` with `itf = MIN(ite, ide-1)`:

    divv(i,k) = msftx(i,j)*dnw(k)*( rdx*((c1h(k)*muu(i+1,j)+c2h(k))*u(i+1,k,j)/msfuy(i+1,j)
                                        -(c1h(k)*muu(i,j)  +c2h(k))*u(i,k,j)  /msfuy(i,j))     &
                                  + rdy*((c1h(k)*muv(i,j+1)+c2h(k))*v(i,k,j+1)*msfvx_inv(i,j+1)
                                        -(c1h(k)*muv(i,j)  +c2h(k))*v(i,k,j)  *msfvx_inv(i,j)) )

At the last owned mass column the `i+1` term needs `u(ite+1)` and, through the local
`muu`, `mu(ite+1)` -- both halo columns. Nothing refreshes them first:

- `solve_em.F` lines 573 to 652 contain no `#include` at all. The first is `#ifdef
  DM_PARALLEL` at 672 and `HALO_EM_A.inc` at 703.
- `inc/HALO_EM_A_inline.inc` moves `al, alt, mut, muu, muv, p, php, rho, ru, rv, rw,
  ww`. **`u`, `v` and `mu` are not in it.** The exchange fifty lines later cannot
  refresh what `calc_ww_cp` read: it carries the OUTPUT `ww`, not the inputs.

### What the measurements support, corrected

| link | status |
|---|---|
| `ww` differs at exactly the last owned mass column of each affected boundary at stage 2, and nowhere else | MEASURED |
| `u_2` and `mu_2`, the two inputs `calc_ww_cp` reads, are identical in every OWNED cell at stage 1 | MEASURED |
| `mub`, `msfuy`, `msfvx_inv`, `c1h`, `c2h` are time-invariant fields read from input | identical by construction, NOT dumped |
| `calc_ww_cp` reads `u(i+1)` and, through its local `muu`, `mu(i+1)` past the last owned column | source, `:747` and `:699` |
| nothing exchanges `u` or `mu` between the RK-stage entry and the call | source, `solve_em.F` 573-652 and the `HALO_EM_A` field set |
| rank 0's halo copy of `muu` differs before the exchange and matches after | MEASURED, but of `grid%muu`, which `calc_ww_cp` never reads -- it is evidence about the exchange, not about `ww` |
| the halo columns of `u` and `mu` that it reads actually differ | **UNMEASURED -- the missing link** |

The account is now one named measurement short, rather than half-supported by a
fact about a different array.

## The same expression reads `j+1`, and the j cut measures zero

The `rdy` half of `:747` is the mirror of the `rdx` half. `muv` is filled at `:706`
as `MUV(i,j) = 0.5*(MUP(i,j)+MUB(i,j)+MUP(i,j-1)+MUB(i,j-1))` over
`DO j = jts, min(jte+1,jde)` -- `j`/`j-1` where `muu` used `i`/`i-1` -- and the
divergence reads `muv(i,j+1)` and `v(i,k,j+1)` where the x term reads `i+1`.

The mechanism is symmetric in the source; the measurement is not. 77 of 197 fields
differ on an i cut, 0 of 197 on a j cut, at every rank count. **An unexchanged halo
read therefore cannot by itself be the explanation.** It is at most necessary.
Something outside this stencil breaks the symmetry.

One candidate is closed by the archived namelist rather than left open: the case is
`specified = .true.` with `spec_zone = 1` and `relax_zone = 4`, no periodicity in
either direction, `e_we = 235`, `e_sn = 283`. The lateral boundary treatment is the
same kind in i and j, so the asymmetry is not a boundary-condition-type asymmetry.

The discriminating experiment is a pair, not a single run: dump the HALO columns of
`u_2` and `mu_2` at stage 1 on BOTH the `4x1` and the `1x4` decomposition, and test

> the stage-2 `ww` difference appears at a patch boundary if and only if the halo
> `u`/`mu` that `calc_ww_cp` reads across it already differs at stage 1.

An i cut whose halo differs and a j cut whose halo does not would put the asymmetry
in whatever fills the halo, upstream of the dynamics entirely. Both differing would
mean the divergence cancels it in j, which is a claim about the two map-factor forms
in the expression above (`/msfuy(i+1,j)` against `*msfvx_inv(i,j+1)`) and would need
its own test. Neither is argued here.

**That experiment does not need a new freeze-lift.** Its anchor is stage 1, already
in `solve_em.F`, and the probe already dumps a group over the MEMORY window rather
than owned cells (`g33_dyn_probe.py`, the `grp == 2` branch). Putting `u_2` and
`mu_2` in a memory-window group is a field-list edit to `g33_dyn_probe.py` inside
the granted scope. Narrowing further -- between `calc_mu_uv` and `calc_ww_cp` --
is what would reach `module_em.F` and `module_big_step_utilities_em.F`, and that is
a separate request.

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
