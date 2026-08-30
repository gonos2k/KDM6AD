# Freeze-lift request: a stage probe inside one dynamics step, one file

**GRANTED 2026-08-30**, and the scope below was then revised by the owner --
stages 0, 3a/3b, the halo-exchanged and tendency field sets, the ownership keys
and the instrument control were all added after the grant. The work follows the
revised text; the first pass, which predated it, is corrected in
`FINDING_i_seam_first_write_is_rk_step_prep_v1`.

## What is asked

Permission to build and run an instrumented copy of **one file** --
`dyn_em/solve_em.F` in the campaign tree -- that emits five fields at named
points inside the first time step, and to keep the generator that writes that
copy.

The canonical file is `dyn_em/solve_em.F`, 5 002 lines,

    sha256  d66e9db1bba8f37e3f46d30c2fd74bdf8def411adf233376a69e0b401c6d3d1f

in `~/KDM6AD+/KIM-meso_v1.0/`, the tree that built the deployed `f54ef3c9`. It
is **never edited**. A generator reads it, verifies its
SHA against a pin, inserts `#ifdef KDM6_G33_DYN_DUMP`-guarded emission at
unique whole-line anchors and writes a throw-away patched copy -- the same
protocol §5.1 rule the microphysics overlay already follows
(`make_fortran_overlay.py`). Nothing outside the `#ifdef` changes.

Every point the probe needs is a call site in that one file:

| # | stage | anchor in `solve_em.F` | what is dumped |
|---|---|---|---|
| 0 | **dynamics step entry**, before the RK loop | immediately above `Runge_Kutta_loop:` (L573) | state |
| 1 | **RK-stage entry** (each `rk_step`) | top of the `Runge_Kutta_loop` body (L573) | state |
| 2 | after `rk_step_prep` | L652 | state + halo-exchanged set |
| 3a | **before** `HALO_EM_A` | just above `HALO_EM_A.inc` (L703) | halo-exchanged set, owned + halo |
| 3b | **after** `HALO_EM_A` | just below `HALO_EM_A.inc` (L703) | halo-exchanged set, owned + halo |
| 4 | after `rk_tendency` | L876 | state **and tendencies** |
| 5 | after `relax_bdy_dry` (specified boundary) | L934 | state **and tendencies** |
| 6 | after `rk_addtend_dry` | L962 | state |
| 7 | each acoustic sub-step | `small_steps:` (L1261), after `advance_uv` / `advance_mu_t` / `advance_w` | state |
| 8 | RK stage end | end of the `Runge_Kutta_loop` body | state |

Stage 0 is separate from stage 1 because `Runge_Kutta_loop: DO rk_step = 1, rk_order`
(verified at L573) is the entry of **each RK stage**, not of the timestep. Without
stage 0 a difference created before the loop cannot be seen.

Stages 3a and 3b are both needed: without the pre-exchange dump there is no way to
separate "the halo arrived wrong" from "the halo was right and a later stencil
diverged".

**Fields.** State: `u_2`, `mu_2`, `ph_2`, `t_2`, `w_2`. Tendencies at stages 4 and 5:
`grid%ru_tend`, `grid%rv_tend`, `rw_tend`, `ph_tend`, `t_tend`, `mu_tend` (names read
from the `rk_tendency` call at L876). Halo-exchanged set at stages 2/3a/3b: the fields
`HALO_EM_A` actually moves, which the Registry declares as
`8:ru,rv,rw,ww,php,alt,al,p,muu,muv,mut,rho` -- an **8-point** stencil, so both
directions, and a field set that does NOT intersect the five state fields above. A
probe that dumps only `u_2`/`ph_2`/... around the exchange cannot see a halo defect at
all, because those arrays are not what the exchange writes.

**Region and volume.** `i` within 16 columns of each i patch boundary plus the eastern
lateral-boundary zone, all `j`, all `k`, the FIRST time step only, and every record
carries its own index keys (below), so the earlier `5 x 117 x 282 x 40` arithmetic is
an order-of-magnitude bound on volume, not the comparison schema. Adding the tendency
and halo sets roughly triples it; still bounded, and small beside the 29 GB the case's
`runs/` already holds.

### What each dumped word must carry

A bare value at a global index cannot be compared at a patch boundary, because the
same global cell exists as an owned value on one rank and as a halo copy on its
neighbour. Assembling those into one global array silently picks one of them and can
either hide a halo mismatch or count a duplicated halo as a physical difference. Each
record therefore carries:

```
rk_step, acoustic_substep, stage_id, field, stagger (M/X/Z),
rank, global_i/j/k, local_i/j/k, ownership (owned | west-halo | east-halo),
raw_f32_word
```

`U` is x-staggered, `W` and `PH` are z-staggered and `MU` is 2-D, so the stagger is
part of the key, not an assumption.

Two comparisons are then separable, and both are wanted:

- within `np=4`: `X(left rank, east halo) == X(right rank, west owned)` and its mirror
  -- this is a halo-content check that needs no `np=1` run at all;
- `np=1` vs `np=4`: **owned cells only**.

### The dump must be shown not to make the difference it looks for

The A/B/C plan checks that the overlay is inert when the macro is OFF. That is not the
configuration the measurement runs in. Several hundred MB of rank-local I/O inside the
first step can change rank progress, MPI arrival order and memory behaviour, and the
thing being measured is a bit difference between two decompositions.

So: buffer the raw words in memory during the stages, flush rank-local after the first
dynamics step ends, and use no collective I/O. Then compare the final state of a
dump-ON run against a dump-OFF run **at the same decomposition** and require raw-bit
identity. That is a control on the instrument, not a new gate.

## Why

`SCIENCE_STATUS.md` has one open statement left in the MPI section:

> The instantaneous first-write support, and whether it is set by halo width,
> stencil reach or a patch-local boundary update.

Everything reachable by running more decompositions has been run. Cutting j is
bit-identical (0 of 197 fields, raw-word), cutting i differs in 77, the
difference bands on the i patch boundaries one band each, its RELATIVE HALF-PEAK
core stays within 1-6 columns and does not grow, and its one-ULP envelope advances at
3.5-4.5 times the sound speed. Another processor grid adds nothing now. What is
missing is not another comparison of OUTPUTS -- it is where inside the step the
first difference is written.

The decision the probe makes is mechanical:

| first stage at which `np=1` and `4x1` differ | reading |
|---|---|
| right after the halo exchange | the exchanged field set, width or content |
| after the x-direction tendency | stencil reaching past what was exchanged |
| after the lateral-boundary update | eastern-zone handling, a separate source |
| only inside the acoustic sub-steps, growing each | numerical domain of dependence, no single site |

## Prediction

Falsifiable, and recorded before the build:

1. The first difference appears **at or before stage 4** (`rk_tendency`) --
   before any acoustic sub-step.
2. **Soft hypothesis, not an acceptance criterion:** it is confined to within about
   three columns of a patch boundary at the stage where it first appears. The 1-6
   column figure it leans on is a RELATIVE HALF-PEAK support, which narrows when a
   boundary peak grows on an unchanged surround as readily as when the difference
   concentrates, so a wider first-difference band would not refute the probe -- it
   would refute this width estimate.
3. `U` differs no later than `PH`. This is a **hypothesis, not a derived
   dependency**: `ph_1`/`ph_2` are prognostic in the small step, updated alongside
   `u`, `w`, `t` and `mu`, so `PHB` being bit-identical says only that the base-state
   geopotential matches -- it does not make `PH` a diagnosed consequence of `U`.
   `W -> PH`, `MU`/pressure coupling `-> PH` and the vertical acoustic update are all
   open paths. `U` is prioritised because the decomposition cuts the x-staggered
   direction, and the ordering is what the probe tests.
4. The eastern band is **absent through stage 4 and first present immediately after
   stage 5**. It may persist or change at stage 6 -- a difference created at stage 5
   normally survives into stage 6 unless something cancels it, so requiring its
   absence there would be a self-refuting prediction.

If instead the difference is zero at every stage of the first RK step and only
appears in a later one, prediction 1 is refuted and the site is elsewhere.

## What it would NOT show

That the difference is a defect. A core order-fixed in j and not in i may be
ordinary; the probe locates the write, it does not judge it.

That the probe finds the first WRITE. It brackets the first OBSERVED difference
between two named call boundaries; the write itself may be anywhere inside that
bracket.

That the located stage is the ORIGIN rather than the first place the probe
looks. The anchors are call boundaries, so a difference created inside
`rk_tendency` and one created inside a routine it calls both report at stage 4.
Narrowing further would need anchors inside those routines, which this request
does not ask for.

Anything about `mp_physics`. The microphysics kernel is untouched, and running
the probe with `mp_physics = 0` -- a namelist value, not a code change -- would
separate dynamics from physics feedback if the stage evidence is ambiguous.

## Scope -- INCLUDED

- `dyn_em/solve_em.F` in the campaign tree, through a generated throw-away copy.
- One preprocessor macro, `KDM6_G33_DYN_DUMP`, guarding every added line.
- One generator in `harness/`, and the A/B/C discipline that already exists.

## Scope -- EXPLICITLY EXCLUDED

- Editing the canonical `dyn_em/solve_em.F`, or any other dynamics file.
- `phys/module_mp_kdm6.F` and every frozen kernel file.
- Any change to computation, order, or loop bounds outside the `#ifdef`.
- Making the instrumented build the deployed binary, or changing `f54ef3c9`.
- New gates, new provenance layers, new authority documents. The result is one
  finding and one row in `SCIENCE_STATUS.md`.

## Acceptance gates

**A == B, and the evidence for it already exists.** A is the deployed
`f54ef3c9`. B is the overlay compiled WITHOUT the macro. B must reproduce, byte
for byte, the forecast output of the runs already on disk --
`mp37_lin3_1min_hist0` and `mp37_lin3_1min_hist0_np4_4x1`, one minute, four
frames, `np = 1` and `4x1`. No new fixture is needed and the comparison is the
raw-word one already written for the j-cut check.

**C emits only inside the `#ifdef`.** With the macro and no dump environment
set, C's output must also be byte-identical to A -- the emission is conditional
on a sealed environment as well as the macro, exactly as the C++ A/B/C gate
requires.

**The diff is auditable.** `diff canonical overlay` must show only added lines,
every one inside an `#ifdef KDM6_G33_DYN_DUMP` block, and the generator must
refuse a canonical whose SHA is not the pin.

## Cost

The Registry is untouched, so no `clean -a`: the `dyn_em` objects and a relink.
Two one-minute runs, about 80 s each, and about 800 MB of dumps.
