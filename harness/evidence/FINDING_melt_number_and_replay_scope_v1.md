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
