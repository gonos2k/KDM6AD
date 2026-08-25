# What the melt arms inherit, and what the replay is not a replay of

Three scope facts that constrain how the graupel work may be cited. All three
were read off the pinned source and the replay generator, not inferred.

## 1. The defect window is exactly where the number update is switched off

`F:1412` gates the rain-number transfer:

    if(qrs(i,k,3).gt.qcrmin) then
      gfac = (rslope(i,k,3))*n0go(i,k)/qrs(i,k,3)
      nrs(i,k,1) = nrs(i,k,1) - gfac*pgmlt(i,k)
    endif
    qrs(i,k,3) = qrs(i,k,3) + pgmlt(i,k)
    qrs(i,k,1) = qrs(i,k,1) - pgmlt(i,k)

The mass moves unconditionally; the NUMBER moves only above `qcrmin`. And the
overflow window is `0 < qg <= qcrmin` — precisely the complement. So in the
window this campaign is studying, **rain mass increases and rain number does
not**, which moves `qr/nr`, the mean drop size, the fall speed and the
reflectivity that follows from them.

**This is legacy's structure, not something the arms introduce.** `g1`, `g3`
and `g4` all leave `F:1412` untouched, so none of them makes it worse and none
of them fixes it. It is a property of the base that any FINAL correction has to
decide about, and it is not a reason to prefer one arm over another.

What that means for the arms: a complete melt under `g3`/`g4` zeroes `qg` and
`brs`, so the graupel is gone as mass and as volume, while its particles are
never handed to rain as number. Whether that is right depends on what KDM6
intends a sub-`qcrmin` graupel population to be, which is a question for the
owner and not one the harness can measure.

## 2. The real-column replay does not carry a real graupel state

`g33_real_column_batch.py:102`:

    fields["bg"] = [f2b(0.0)] * K

The graupel bulk volume is **set to zero for every level**, not read from the
state. The state file carries no `brs`, so there is nothing to read — but the
consequence is that the replay's graupel is a reconstruction, not a measurement.

`brs` is one of the two operands of the defect (`rhox` is computed only under
`qg > qcrmin .or. brs > brs_min`), so this is not a peripheral field. It is one
of the two things the branch tests.

**Therefore.** The replay remains load-bearing for the rain-number work — `rho`,
`qv`, `nr`, `qr` and `delz` are all read from the real state, and Arm N's
~2.07 % remainder stands. It is **not** evidence about how often the graupel
defect fires in a forecast, and the exposure numbers must not be generalised
from it. That needs `brs`, the graupel number and `rhox` instrumented in a full
WRF run, or a history variable that records them.

## 3. Two modules answer "the real atmosphere's density" differently

`g33_real_column_density.profile` uses the thermodynamic estimate
`p / (Rd T (1 + 0.608 qv))`. `g33_number_basis.profile(basis="canonical")` uses
WRF's own hydrostatic relation `rho_d dz = mu_d |d(eta)| / g`, which assumes no
thermodynamics.

Measured against each other on the real 5 km state, the thermodynamic routes
differ from the canonical one by a **median 2.3e-03 and up to 31 %** — about
2500 times the difference between the two thermodynamic routes.

Not switched, because the published statistics of that module were taken on the
thermodynamic route and changing authorities silently would move cited numbers.
Instead the module now names its authority in its docstring **and in its
output** (`density_authority`), so a reader comparing a figure from each can see
they are not on the same basis. `g33_number_basis` is the one to call when the
model's own layer mass is the question.

## 4. And one wording correction on the crash

`1x3` crashes and `3x1` does not, which is strong. But the two differ in more
than the presence of a middle j-rank: decomposition orientation, patch
dimensions, array strides, halo direction, message topology and which ranks own
a physical boundary all change together. "The only difference is a rank with an
interior neighbour on both j sides" overstates a single-variable intervention
that was not performed. `2x3` against `3x2` at `np = 6` is the control that
would separate them.

Graded: **a supported decomposition SIGSEGVs — confirmed. Middle-j-rank
topology as the cause — strong candidate. KDM6 as the cause — open.**

## 5. Correcting my own scope on g4's negative volume

`FINDING`-adjacent, and it corrects PR #170's commit message rather than an
evidence file, because the claim never reached one.

That commit reported g4's partial-melt branch producing a negative bulk volume
at "raw density 2000, 50 per cent melt". The arithmetic is right and **the
state is unreachable.** Where `ProgB_param` computes `rhox` it also rewrites
`brs = qg/rhox` (F:3680), so by the time the melt runs,

    brs + pgmlt/rhox  =  (qg + pgmlt)/rhox  >=  0

for ANY density and ANY melt fraction. The normalisation removes exactly the
states that looked dangerous. Measured over the same f32 draws: 0 negatives
outside the window.

**Inside** the window `rhox` was never computed and `brs` was never normalised,
and there it is real: `qg = 1e-9` over `brs = 1e-16` gives `-5.55e-13` at a half
melt. So the floor is necessary, for a window-only reason and not the general
one. At the measured failing cell (`raw = 900`, exactly at the clamp) the value
is `+4.6e-16` at a half melt and exactly `0` at a complete one.

**And the same fact makes g4 exactly contained.** `rhox` at the melt already IS
the pre-melt density — `ProgB_param` runs at F:1325, and neither `qrs(i,k,3)`
nor `brs(i,k)` appears anywhere between there and F:1400. So g4 now REUSES it
where it is positive, which makes the expression literally legacy's, rather
than recomputing `qg/brs`, which agrees only to within 1 ULP (191 151 of 200 000
f32 draws exact, worst relative 7.6e-08). The floor is then the only remaining
difference outside the window, and it provably never binds there.

That is the containment property `g2` was asked for and does not have, stated
as a proof over all states rather than as a fixture that happens not to fire.
