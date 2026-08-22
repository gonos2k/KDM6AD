# Cycle checklist: the re-review of `main@2935fcd2` (PR #147)

The owner's re-review found the factorial finding's central claim mathematically
wrong and asked for a checklist worked one item at a time. This is it, with
where each item landed.

## 1. The factorial finding, corrected — PR #148

The claim "cross terms are at roundoff" / "the three defects do not interact"
was reproduced as FALSE before anything was changed:

    I_NC = 6.546e-20 - 7.540e-17 - 1.468e-01 + 1.703e-01 = 0.0235

13.8 % of baseline against an f32 epsilon of 1.19e-07.

What the first version observed was MARGINAL SELECTIVITY and reported as
ORTHOGONALITY. Different claims; the first does not imply the second. Withdrawn
and rewritten.

## 2. C's own invariant in the response vector — PR #148

N was scored on number closure and L on decomposition invariance, their own; C
only through its indirect effect on the ice-number residual. `cap_sink` is C's,
and with it in the vector C's main effect is the largest in the table:
`beta_C = -2.845`, moving the net cap term from +2.435 to -3.400.

## 3. Signed coefficients against a resolution scale — PR #148

`|R|` hides sign reversal and turns cancellation into apparent effect. Folded,
`cap_sink`'s coefficient reads 0.5 instead of -2.9.

The measured structure is selectivity plus a NAMED SATURATION:

    beta_C(R_ni)  = -5.865e-03
    beta_NC(R_ni) = +5.865e-03

Equal and opposite — masking, not coupling. C acts only where N has not already
removed the residual.

## 4. The physical (dry-air) basis — PR #149, and NO arm was needed

Arm N closes the OPERATOR's ledger, which is moist. Against the PHYSICAL measure
the remaining coefficient is

    eps = (1 + qv_upper)/(1 + qv_lower) - 1

purely the moisture jump, with no dependence on the density profile, and it
composes with the density term EXACTLY (max error 4.44e-16 over 2 507 544
interfaces).

Every stream in the archive that carries `qv` carries it UNIFORM in the column
-- spread exactly 0.0 across `armn`, `f64`, `migrate` -- so no published fixture
could ever have distinguished the two measures. On the real LC05 state Arm N
leaves a median -1.246e-04 against a legacy 8.557e-02: 0.33 % of it.

A dry-air arm would buy at most 7.08e-03 per interface. The freeze-lift it would
need can now be written against a number. **This cycle does not ask for one.**

## 5. The mstep > 1 matrix — PR #150

"mstep > 1 not re-run" understated it: no reader could measure it there. The
transport-only closure's guard went through `column()`, which needs one
sub-step, so the path whose docstring says "no recursion" was silently
mstep == 1 only.

With the guard put to `G33F CAPIN` instead (218/220 agreement where both can
see; mstep == 1 unchanged, bit for bit):

- Arm N drives the number residual to zero at mstep up to 10, against a legacy
  13.2 %. Its closure is not an mstep == 1 artefact.
- The N x C masking survives: `ni` runs 6.772 -> 5.359 -> 0.000.
- C does its own job on MASS at high mstep, which one sub-step could not show.

And the mass control in `FINDING_arm_n_closure_v1` could not detect what it was
controlling: `qr 1.412673e-16 == 1.412673e-16` is ~0 by construction in every
arm. Read out of the same bundles, Arm N moves `qv` by 1.429e-05 relative
(~120 ulp at f32). Arm N moves water, and it should.

## 6. The full-window factorial — PR #151

The legacy ice-number residual grows along the trajectory (0.1703 -> 0.2637),
the masking signature is preserved EXACTLY (`beta_C = -beta_NC = 2.2713e-02`),
and a term appears the first call could not show: `beta_L` on `R_ni` at
1.83e-05, because after call one the arms hold different states. That is why the
first call is the matched comparison and the window is not.

## 7. The LC05 actual-column factorial — **THIS BLOCKER WAS WRONG**

Every field the fixture generator needs is present in the real state EXCEPT the
one the experiment is about. Measured:

| state | QNRAIN | QNICE | QNCLOUD | QNCCN |
|---|---|---|---|---|
| `host/lc05_da_run/wrfinput_d01` (real 5 km) | 0 everywhere | 0 | 0 | 0 |
| `host/KIM-meso_v1.0/run/wrfout.37.ieee.nc` | 0 everywhere | 0.01 % nonzero | 0.05 % | 100 % |

The real analysis is a cold start whose double-moment number variables were
never initialised, and the completed run available here is the 100 km IDEAL
case, which develops no rain number. A factorial built on either would measure
N's subject as identically zero.

**Corrected 2026-08-22.** The table above is right about `wrfinput_d01` and
about the 100 km ideal run, and it drew the wrong conclusion from them, because
it never checked the real case's OWN forecast output. A twenty-second `mp37`
run of this case carries `QNRAIN` in 0.9 % of cells (max 1.93e+03), `QNICE` in
5.3 % and `QNCLOUD` in 4.3 %: the number fields spin up almost immediately. No
new model run was needed -- one produced in this campaign already had them.

What that unblocked is recorded in `FINDING_number_basis_gap_v1`: restricted to
interfaces that actually carry rain number, Arm N leaves a median 1.94 % of the
legacy defect rather than the 0.33 % the all-interface statistic reported.

What remains genuinely blocked is a real-COLUMN FIXTURE, and for a different
reason: the manifest requires the vertical anchor `p` to be the same profile in
every column, and real columns on terrain-following levels are not. The generator side is ready: fixtures are produced from a JSON by
`harness/g33_fixture_v1.py`, and every other field the schema requires is in
the file.

Note this is the same shape as the open `ncmin` sensitivity item, which needs a
spun-up double-moment state over mixed coast. One run would serve both.

## 8. Real MPI one-step, np = 1, 2, 4 — PR #153

Unaffected by item 7's blocker: decomposition invariance does not need a number
field. Run, and the result is the strongest of the cycle.

The control first: at `t = 00:00:00` all 197 f32 time-varying fields are
BIT-IDENTICAL across np = 1, 2, 4. Whatever separates the runs is made by the
step.

| | differing at t = 0 | at t = 20 s | worst |
|---|---|---|---|
| np = 2 vs 1 | 0 of 197 | 1 | `QNCCN`, 9.800e-01 relative |
| np = 4 vs 1 | 0 of 197 | 28 | `REFL_10CM`, 1.917e+00 relative |

After twenty seconds the forecast's precipitation and reflectivity depend on how
many MPI ranks it ran on.

The mechanism is NOT established. `ncmin` is the obvious candidate -- a scalar
assigned inside `do i = its,ite`, so only each tile's last column survives -- but
it gates `nci(i,k,1)`, cloud droplet number, which surfaces as `QNCLOUD`, and
`QNCLOUD` is unchanged at np = 2 where `QNCCN` alone moves. Naming it would be
the kind of inference this campaign has had to withdraw before.

## 9. The factorial cannot be PINNED — OPEN, and it is the structural lesson

A wrong claim survived a whole cycle because nothing gated it: the factorial
finding has no entry in `CLAIMS.yaml`, so no figure of it was ever read back.

Pinning it needs the publisher to carry a DECOMPOSITION axis -- `partition` is
single tile against `(2,1)`, and `g33_refine_experiment.py` hard-wires one tile
of `width` (`tiles=(width,)`). The driver already takes the tile spec; giving
the publisher the axis adds a manifest key, which is a schema change and
therefore a NEW TAG. A deliberate act with its own cycle, not a side effect of
correcting a sentence.
