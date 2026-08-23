# Arm N_d told the window-initial dry mass closes the physical ledger in every column

Owner approval 2026-08-23 ("모든 작업 승인"), granting
`REQUEST_freeze_lift_arm_nd_window.md`. `nmass_dry_window` is Arm N_d with one
extra `kdm62D` argument, `mdry0(its:ite,kts:kte)`, which the driver fills once
from the window-initial state as `den/(1+qv^0)*delz` and never updates. The two
transfer lines weight by `mdry0(k+1)/mdry0(k)` directly. Generated, never
hand-edited; the argument is `optional` so the 3D wrapper's call still compiles.

## The prediction, and the measurement

`FINDING_fixed_dry_mass_arm_v1` predicted exact algebraic closure of the
window-initial ledger, because every `eps_{u->l}(t)` in the residual formula is
identically zero when the arm's measure IS the ledger's. Window-initial
physical ledger, 12-call window, `nr`, residual over surface flux,
`g33_fixture_moisture_gradient_v1`:

| arm | column 1 | column 2 | column 3 |
|---|---|---|---|
| `legacy` | 1.043e-02 | 1.053e-02 | 7.330e-02 |
| `nmass` | -1.817e-04 | -2.250e-04 | -1.856e-03 |
| `nmass_dry` | 2.882e-07 | -9.812e-08 | 6.641e-04 |
| **`nmass_dry_window`** | **-3.235e-07** | **2.680e-09** | **-5.048e-07** |

Column 3 goes from 6.641e-04 to -5.048e-07: three orders, to roundoff. **The
physical ledger closes over the whole window.**

Stated carefully: column 3 is the only column that tests this. In columns 1
and 2 all interior transfer happens on the first call, before `q` has moved, so
they close under any measure and say nothing about the arm
(`FINDING_arm_nd_closure_v1`, adversarial pass). One column, one test, and it
passes by three orders. The counterfactual chain is complete:

    legacy  ->  Arm N  ->  Arm N_d  ->  Arm N_d-window
    density term removed   moisture term removed   harness artefact removed

## The uniform-moisture control

`g33_fixture_boundary_mapping_v1`, where `qv` is uniform down each column at
`t = 0`, whole window, `nmass` against `nmass_dry_window`:

    3 of 144 final-state cells differ
    relative: median 2.34e-07, max 2.37e-07      (f32 epsilon 1.19e-07)
    per call: 8.3e-08, 9.1e-08, ... 6.6e-07

Against the current-`q` Arm N_d, which diverged from Arm N by 2.9e-03 on this
fixture from call 2 onward, the window arm stays within two f32 ulp for all
twelve calls. The request's criterion was stated as "bit-identical"; that is not
attainable between two different f32 expressions -- `den*(1+q0)*dz` rounded and
then divided is not the same bit pattern as `den*dz` divided -- and what the
measurement shows is the meaningful form: no measure effect, expression rounding
only.

## What this is, and is not

A harness instrument. In production the host supplies `den = rho_d(1+q)` from
the dynamics at every call, so `den/(1+q)` at call entry IS the conserved dry
density and Arm N_d already weights by it (`FINDING_fixed_dry_mass_arm_v1`).
The window arm exists to separate the arm's algebra from the harness's
fixed-forcing artefact, and it does: the artefact was the entire column-3
residual.

One fixture, f32, `mstep = 1`. Not a forecast impact.
