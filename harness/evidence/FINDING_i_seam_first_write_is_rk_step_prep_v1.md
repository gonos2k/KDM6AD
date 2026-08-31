# The first owned-cell difference is `ww`, written by `rk_step_prep`, before the halo exchange

Under the freeze-lift `REQUEST_freeze_lift_dyn_first_write_probe.md`, a probe was
placed inside the first RK stage of the first time step, `np = 1` against `4x1`
(i patch boundaries after 59, 117, 176), on the deployed binary's tree.

## The instrument is inert, and the tree is as it was found

`dyn_em/solve_em.F` (pinned `d66e9db1`) was never edited. A generator wrote a
throw-away copy adding one `#define` and 149 guarded lines, every one inside an
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

This is ONE field at ONE boundary and cannot carry a claim about the exchange as
a whole. The full table -- twelve fields, three boundaries, both directions --
is below, and it agrees; but the narrow measurement came first and the general
statement was made from it before the table existed.

## The eastern band is in `rk_tendency`'s output before `relax_bdy_dry` runs

The eastern columns 231-234 appear first at stage 5, in `ru_tend`, `rv_tend`,
`rw_tend` and `t_tend` -- one stage BEFORE `relax_bdy_dry`, which is stage 6.

What that supports is narrow: **`relax_bdy_dry` is not the FIRST producer of the
eastern-zone difference.** It does not put the band outside boundary handling
altogether. `rk_tendency` reads state that `set_phys_bc` has already touched, its
own stencils are boundary-aware, and the specified-boundary input is upstream of
all of it. Those remain candidates and none is measured here.

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

The first version of this section named the wrong array, and the mechanism it
proposed has since been measured and refuted. Both are recorded here rather than
edited away. Every line number below was checked against the PINNED canonical
(`dyn_em/.solve_em.F.canonical`, `d66e9db1`) and against `module_em.F`
(`7695bfb0`) and `module_big_step_utilities_em.F` (`27ce690b`), neither of which
carries any instrumentation. The working `dyn_em/solve_em.F` is an overlay while
a probe is deployed and its anchors sit at 578/661/719, not 573/652/703; citing
the working copy would have been wrong.

**`calc_ww_cp` does not read `grid%muu`.** It declares and fills its own:

| where | what |
|---|---|
| `dyn_em/solve_em.F:652` | `rk_step_prep` is called with `grid%u_2`, `grid%mu_2`, and separately `grid%muu` |
| `dyn_em/module_em.F:163` | `rk_step_prep` calls `calc_ww_cp ( u, v, mu, mub, c1h, c2h, ww, ... )` -- it passes `mu`, and no `muu` |
| `module_big_step_utilities_em.F:674` | `REAL , DIMENSION( its:ite+1 , jts:jte+1 ) :: muu, muv` -- a LOCAL array that shadows the name of the grid field |
| `module_big_step_utilities_em.F:699-700` | `MUU(i,j) = 0.5*(MUP(i,j)+MUB(i,j)+MUP(i-1,j)+MUB(i-1,j))` over `DO i = its, min(ite+1,ide)` |

So the `muu` in the divergence is rebuilt inside the routine from `mu` on every
call, is never exchanged, and is not the `muu` that `HALO_EM_A` moves. The
earlier claim -- "`muu` is in the `HALO_EM_A` set, and that exchange runs after
`rk_step_prep`" -- is true of the grid field and does not bear on `ww`.

What the divergence depends on, `module_big_step_utilities_em.F:747`, over
`DO i = its, itf` with `itf = MIN(ite, ide-1)`:

    divv(i,k) = msftx(i,j)*dnw(k)*( rdx*((c1h(k)*muu(i+1,j)+c2h(k))*u(i+1,k,j)/msfuy(i+1,j)
                                        -(c1h(k)*muu(i,j)  +c2h(k))*u(i,k,j)  /msfuy(i,j))     &
                                  + rdy*((c1h(k)*muv(i,j+1)+c2h(k))*v(i,k,j+1)*msfvx_inv(i,j+1)
                                        -(c1h(k)*muv(i,j)  +c2h(k))*v(i,k,j)  *msfvx_inv(i,j)) )

At the last owned mass column the `i+1` term needs `u(ite+1)` and, through the
local `muu`, `mu(ite+1)` -- both halo columns -- and `solve_em.F` 573 to 652
contains no `#include` at all, so nothing exchanges them first.

## That halo is current, measured: the mechanism is refuted

Group 4 dumps `u_2`, `mu_2`, `mub` and `msfuy` at stages 0 and 1 over the MEMORY
window, so each rank's halo copies come too, and `halo-vs-reference` compares
them against the single-patch value at the same global column, per rank.

    rank    owns        reads at i+1     halo columns that DIFFER from np=1
    0       1..59       60               63, 64, 65, 66
    1       60..117     118              53..56 and 121..124
    2       118..176    177              111..114 and 180..183
    3       177..235    (235 = ide)      170..173

**Every column the stencil actually reads -- 60, 118, 177 -- is bitwise identical
to `np=1`, in `u_2`, `mu_2`, `mub` and `msfuy`, at all three boundaries.** The
columns that differ are the ones beyond the width-3 halo the model fills, and
`mub` and `msfuy` are TIME-INVARIANT and differ at exactly the same columns,
which shows those columns are memory the model never wrote rather than stale
dynamics.

The denominator was checked rather than assumed: 60, 61 and 62 are PRESENT in
both dumps and equal, not absent and silently skipped. That check is why the
comparator now refuses a comparison whose coverage differs at all -- see below.

> The unexchanged-halo account is REFUTED. The inputs are current; the output is
> not.

## What is left is how the expression was evaluated, not what it read

With the i-direction inputs measured identical, one predictor survives, and it
is not about data at all. `itf = MIN(ite, ide-1)`, so each patch runs the `i`
loop a different number of times:

| patch | owns | `itf` | i-loop trips | `ww` differs at `itf`? |
|---|---|---|---|---|
| 0 | 1..59 | 59 | **59** | **YES** |
| 1 | 60..117 | 117 | 58 | no |
| 2 | 118..176 | 176 | **59** | **YES** |
| 3 | 177..235 | 234 | 58 | no |

Fifty-nine trips differ, fifty-eight do not, four of four. **This is a
correlation over two patches against two, not a result.** It is stated because it
is falsifiable in one run: a decomposition with a different trip-count set
(`nproc_x` = 2, 3 or 5) fixes which boundaries must differ, and the prediction
can be written down before the run.

Two inputs are still not in any group and must be closed before "the data are
identical" can be said without qualification: **`v_2` is dumped by no group at
all**, and neither are `msftx` and `msfvx_inv`. `rv` being identical in owned
cells at stage 2 constrains `v`, but it does not measure it.

## The same expression reads `j+1`, and the j cut measures zero

The `rdy` half of `:747` is the mirror of the `rdx` half. `muv` is filled at
`:706` as `MUV(i,j) = 0.5*(MUP(i,j)+MUB(i,j)+MUP(i,j-1)+MUB(i,j-1))` over
`DO j = jts, min(jte+1,jde)` -- `j`/`j-1` where `muu` used `i`/`i-1` -- and the
divergence reads `muv(i,j+1)` and `v(i,k,j+1)` where the x term reads `i+1`.

The stencil is symmetric; the measurement is 77 of 197 fields on an i cut and 0
on a j cut at every rank count. With the halo mechanism refuted this is no longer
a puzzle about communication: a j cut changes the `j` loop's extent, and the `j`
loop is the OUTER loop, whose trip count does not change how the inner `i` loop
is compiled or run. That is consistent with the trip-count correlation above and
is not evidence for it.

One candidate is closed by the archived namelist rather than left open: the case
is `specified = .true.` with `spec_zone = 1` and `relax_zone = 4`, no periodicity
in either direction, `e_we = 235`, `e_sn = 283`. The lateral boundary treatment
is the same kind in i and j, so the asymmetry is not a boundary-condition-type
asymmetry.

## `ww` at stage 2 is `calc_ww_cp`'s output, whatever it held before

Group 2 is not dumped at stages 0 and 1, so `ww` is first OBSERVED at stage 2 and
was not compared before it. The bracket still closes, from the source and from
the shape of the difference:

- `ww` is declared `INTENT(OUT)` at `module_big_step_utilities_em.F:666`.
- `calc_ww_cp` assigns `ww(i,1,j) = 0.` and `ww(i,kte,j) = 0.` over `DO i=its,ite`,
  then `ww(i,k,j)` for `k = 2, ktf` over `DO i=its,itf`. Every owned cell in
  `k = 1..kte` is written on every call.
- Measured: at i = 59 and 176 the difference occupies `k = 2..39` and 250-280 of
  282 `j` columns, with `k = 1` and `k = 40` exactly 0 in BOTH arms. The
  difference sits entirely inside the range the routine assigns, and the top
  staggered level `k = kde`, which the routine never touches, is untouched in
  both.

So the stage-2 owned value is this call's output regardless of what `ww` held at
stage 1, and no re-run is needed to say so. The recursion
`ww(i,k,j) = ww(i,k-1,j) - dnw(k-1)*c1h(k-1)*dmdt(i) - divv(i,k-1)` also explains
why one wrong column becomes a whole column of wrong levels.

## `HALO_EM_A` delivers width 1, at full scope

The earlier version of this claim rested on one field at one boundary. From the
same dumps, all twelve exchanged fields at all three interior i boundaries in
both directions, before (stage 31) and after (stage 32) the exchange -- 72
post-exchange comparisons of a halo copy against its owner:

    field   b59 pre/post   b117 pre/post   b176 pre/post      (WE = west col, east col)
    ru        XX   ==        XX   ==        XX   ==
    rv        XX   ==        XX   ==        XX   ==
    rw        XX   ==        XX   ==        XX   ==
    ww        XX   ==        XX   ==        XX   ==
    php       XX   ==        XX   ==        XX   ==
    alt       ==   ==        ==   ==        ==   ==
    al        ==   ==        ==   ==        ==   ==
    p         ==   ==        ==   ==        ==   ==
    rho       ==   ==        ==   ==        ==   ==
    muu       XX   ==        XX   ==        XX   ==
    muv       XX   ==        XX   ==        XX   ==
    mut       =X   ==        =X   ==        =X   ==
    '=' bitwise equal to the owner, 'X' differs

Every field, every boundary, both directions: equal after the exchange. Four
fields (`alt`, `al`, `p`, `rho`) already agree before it, and `mut` agrees on the
west side only -- both are facts about what the preceding code computed over the
halo, not about the exchange.

This says the exchange delivers what it declares. It does NOT say the exchange
sits in the right place: `calc_ww_cp` runs fifty lines before it and reads `u`
and `mu`, which `HALO_EM_A` does not carry at all.

## What this does NOT show

**That `rk_step_prep` is at fault.** The anchors are call boundaries, so this
brackets the first OBSERVED difference between the RK-stage entry and the return
from `rk_step_prep`. The write is somewhere in that bracket, including inside
anything it calls.

**Why `ww` differs at 59 and 176 and not at 117.** The halo account is refuted
and the trip-count correlation is 2 patches against 2. Neither explains it. The
same two-of-three pattern appeared in `u_2` at stage 7 in the earlier pass.

**That the data feeding `divv` are identical.** The i-direction inputs are
measured identical. `v_2` is dumped by NO group, and neither are `msftx` and
`msfvx_inv`. Until they are, "the inputs agree" is a statement about the x half
of the expression only.

**That the stale halo beyond width three is harmless.** Two different widths are
involved and they should not be conflated: the model carries `u`/`mu` correct to
width 3 at the RK-stage entry, from initialization and the previous step, while
`HALO_EM_A` refreshes width 1 for its OWN twelve fields. Whether any stencil in
the step reaches past the width it is given is still not measured.

**That the instrument was built the way the request specified.** The request
asked for a memory buffer during the stage and a rank-local flush after the first
dynamics step. The probe instead does `WRITE` then `FLUSH` at every stage. The
final-output control passed on both decompositions (0 of 197 fields x 4 frames
against `f54ef3c9`), so no invasiveness reached the forecast; but intermediate
timing was not preserved as asked, and the two are different claims.

**The domain-edge face of x-staggered fields.** The dump window ends at
`iu = MIN(ipe, ide-1)`, a mass-point bound applied to every field. For `u_2`,
`ru`, `muu` and `msfuy` the face at `i = ide` is therefore never compared. At the
INTERIOR patch boundaries this loses nothing -- WRF assigns those faces by the
same `ips..ipe` partition, so ownership is not mis-attributed, only the single
domain-edge column is uncovered. `GROUPS` now records each field's horizontal
stagger so this is visible rather than implicit.

**Anything about later RK stages, later steps, or `mp_physics`.** The probe
covers `itimestep == 1` and `rk_step == 1`; `mp_physics = 37` throughout and the
microphysics runs after the dynamics.

**A probe bug worth recording.** Stage 0 sits above the RK loop, where `rk_step`
is not yet assigned, and the first implementation tested `rk_step /= 1` there --
which silently dropped every stage-0 record. It was fixed and re-run; stage 0 is
measured, not argued from stage 1.

## Provenance

Canonical `dyn_em/solve_em.F` `sha256 d66e9db1...`, restored and rebuilt to
`f54ef3c9`. `dyn_em/module_em.F` `7695bfb0...` and
`dyn_em/module_big_step_utilities_em.F` `27ce690b...` carry no instrumentation;
every line cited from them was read from those files, and every `solve_em.F` line
was read from `.solve_em.F.canonical`, not from the working copy, which holds an
overlay whose anchors sit five and more lines lower.

First pass: instrumented binary `456c5941`, runs
`mp37_{lin3,probe3}_1min_hist0{,_np4_4x1}`. Group-4 pass: instrumented binary
`d1b46b8c`, runs `mp37_probe5_1min_hist0{,_np4_4x1}` (2026-08-31), dumps under
`dyn_dumps_probe5/{np1,np4}`, 1.3 GB. Both arms `experiment_valid` true,
requested proc grid matching actual, one minute, four frames, history every 20 s,
`mp_physics = 37` in every archived namelist. Overlay generator, record format
and reader: `harness/g33_dyn_probe.py`.

The group-4 probe, the `halo-vs-reference` comparator and the probe5 runs are the
work of a second session working the same tree; the halo table, the trip-count
count, the `ww` level profile and this document are this one's. The two arms
reached the refutation independently before comparing notes, which is the only
reason it is stated this plainly.
