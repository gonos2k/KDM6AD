# Freeze-lift request: a stage probe inside one dynamics step, one file

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

| # | stage | anchor in `solve_em.F` |
|---|---|---|
| 1 | dynamics step entry | `Runge_Kutta_loop:` (L573) |
| 2 | after `rk_step_prep` | L652 |
| 3 | **after the x-direction halo exchange** | `HALO_EM_A.inc` (L703) |
| 4 | after `rk_tendency` | L876 |
| 5 | after `relax_bdy_dry` (specified boundary) | L934 |
| 6 | after `rk_addtend_dry` | L962 |
| 7 | each acoustic sub-step | `small_steps:` (L1261), after `advance_uv` / `advance_mu_t` / `advance_w` |
| 8 | RK stage end | end of the `Runge_Kutta_loop` body |

Fields: `U`, `MU`, `PH`, `T`, `W`. Region: `i` within 16 columns of each i patch
boundary plus the eastern lateral-boundary zone, all `j`, all `k`, the FIRST
time step only. That is about 117 i columns, so 5 x 117 x 282 x 40 x 15 stages
x 4 B ~ 400 MB per run and ~800 MB for the pair -- bounded, and small beside the
29 GB the case's `runs/` already holds.

## Why

`SCIENCE_STATUS.md` has one open statement left in the MPI section:

> The instantaneous first-write support, and whether it is set by halo width,
> stencil reach or a patch-local boundary update.

Everything reachable by running more decompositions has been run. Cutting j is
bit-identical (0 of 197 fields, raw-word), cutting i differs in 77, the
difference bands on the i patch boundaries one band each, its half-maximum core
stays within 1-6 columns and does not grow, and its one-ULP envelope advances at
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
2. It is confined to within **about three columns** of a patch boundary at the
   stage where it first appears, consistent with the 1-6 column half-maximum
   core already measured downstream.
3. `U` differs no later than `PH`. `PH` is a diagnosed consequence -- `PHB` is
   bit-identical and `PH` is not -- and `U` is the field the C-grid stores on
   the i-face that the split cuts.
4. The eastern band appears **only at stage 5** and not at stages 3, 4 or 6,
   keeping it the separate source family the finding already treats it as.

If instead the difference is zero at every stage of the first RK step and only
appears in a later one, prediction 1 is refuted and the site is elsewhere.

## What it would NOT show

That the difference is a defect. A core order-fixed in j and not in i may be
ordinary; the probe locates the write, it does not judge it.

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
