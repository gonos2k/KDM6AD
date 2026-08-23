# Freeze-lift request: a window-initial dry mass for Arm N_d, harness-only

## What is asked

One additional argument to `kdm62D` -- a dry layer mass `mdry(its:ite,kts:kte)`
-- and the use of its ratio in the two Arm N_d transfer lines in place of the
`den*(1+q)` form. A NEW variant, `nmass_dry_window`, generated; Arm N_d as it
stands is untouched.

This is a call-shape change, which is why it is asked for separately: the
2026-08-22 freeze-lift covered two lines inside the body.

## Why

`FINDING_fixed_dry_mass_arm_v1` shows that Arm N_d already weights by the
canonical dry density at every call entry, and that the column-3 residual it
leaves over the 12-call harness window (6.641e-04 of surface flux) is the gap
between the window-initial ledger and the per-call one -- a gap the harness
creates by advancing `q` without advancing `den`. The arm closes the per-call
ledger to -1.123e-06.

The window-initial ledger can only be closed by an arm that is TOLD the
window-initial dry mass. The driver has it (`inF`, the G33R INITIAL state) and
the kernel does not.

## Prediction

`FINDING_arm_nd_closure_v1` derives the residual as

    R = sum over calls, sub-steps, interfaces of  F_{u->l} * eps_{u->l}(t)
    eps_{u->l}(t) = (1+q_u^0)(1+q_l(t)) / [(1+q_l^0)(1+q_u(t))] - 1

and predicts column 3 to 0.17 %. With `mdry` frozen at the window-initial
`den/(1+q^0)`, every `eps` is identically zero. The acceptance criterion is the
same form as the original Arm N request:

    |R_window-initial| <= B_roundoff     in all three columns

against 2.882e-07, -9.812e-08 and 6.641e-04 today.

## What it would NOT show

Anything about production. There the host supplies `den = rho_d(1+q)` from the
dynamics every call (`module_big_step_utilities_em.F:4856`), so the per-call
and "window-initial" measures coincide at each call and Arm N_d is already the
canonical arm. This variant is a harness instrument: it separates the arm's
algebra from the harness's fixed-forcing artefact, and that is all.

## Scope

- Harness and `--algo` only. No default changes, no CLAIMS re-pointing.
- The driver passes `mdry` computed from the fixture's initial `rho`, `delz`
  and `qv`; the refine driver already reads all three.
- The owner may reasonably decide the prediction above is strong enough that
  the instrument is not worth a call-shape change. This request is written so
  that decision can be made against the number.
