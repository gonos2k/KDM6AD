# The fixed-dry-mass arm is Arm N_d, and the remaining residual is the harness's

The review asked for an arm that weights by a dry layer mass frozen at call
entry instead of by the evolving `q(i,k)`, and for the column-3 window residual
to be predicted before that arm is built. Both are done; the second changes what
the first is for.

## Within a call, the snapshot is already what runs

Inside `kdm62D` the first write to `q` is at line 2799 (`q = q + work2*dtcld`,
the condensation update). The number transfer Arm N_d edits is at 1222 and
1307, inside the outer sub-cycle loop that begins at 934. For `loops = 1` --
which is the harness (`delt = 5 s`) and the operational call (`delt = 20 s`,
both under `dtcldcr = 120 s`) -- the sedimentation statement therefore sees `q`
**exactly as it was at call entry**. A call-entry snapshot would be bit-identical
to the current edit. It is not built because it would be the same arm.

`loops > 1` (a call longer than 120 s) is the one case where the two differ;
it is not a configuration this campaign runs.

## And in production the snapshot is the canonical dry density

The host forms the density it hands to microphysics as

    rho(i,k,j) = 1./alt(i,k,j) * (1. + moist(i,k,j,P_QV))

(`module_big_step_utilities_em.F:4856`), with `alt` the dynamics' inverse DRY
density. So `den/(1+q)` at call entry is `1/alt` -- not an estimate of the dry
density but the quantity the dynamics conserves -- and Arm N_d's weight

    den(k+1) dz(k+1) (1+q(k))          rho_d(k+1) dz(k+1)
    --------------------------   ==   ------------------
    den(k)   dz(k)   (1+q(k+1))        rho_d(k)   dz(k)

is the canonical dry layer-mass ratio exactly. **Arm N_d already is the
fixed-dry-mass arm the review describes**, for every call the operational
configuration makes.

## So where does the column-3 residual come from

From the harness, not the arm. The 12-call window holds `den` and `delz` as
FIXED forcing while `q` evolves from call to call. But if dry air is conserved
and `q` changes, `rho_m = rho_d (1+q)` must change with it -- the forcing the
harness supplies is inconsistent with the conservation law the window-initial
ledger encodes. Against a ledger built from what each call was actually given:

| column | window-initial ledger | per-call ledger `den/(1+q_call)` |
|---|---|---|
| 1 | 2.882e-07 | 2.883e-07 |
| 2 | -9.812e-08 | -9.813e-08 |
| **3** | **6.641e-04** | **-1.123e-06** |

Column 3 closes to roundoff against the measure consistent with its inputs, in
all twelve calls. The 6.6e-04 is the gap between the two ledgers, and
`FINDING_arm_nd_closure_v1` already predicts it to 0.17 % from the moisture-ratio
mismatch. It is the cost of a harness that advances `q` without advancing
`den`.

## What a window-initial arm would need, and why it is not built here

To close the window-initial ledger over a multi-call harness window, the kernel
would have to weight by a dry mass the harness fixes at `t = 0` -- a quantity
the kernel cannot know. It has to be passed in, which changes `kdm62D`'s
argument list, which is a call-shape change outside the 2026-08-22 freeze-lift
("two lines"). `REQUEST_freeze_lift_arm_nd_window.md` asks for it, and says
what it would show: exact algebraic closure of the window-initial ledger in the
harness, and nothing about production, where the host already supplies the
dynamics-consistent `den` every call.

## Not claimed

That the harness is wrong to hold `den` fixed: it was built to isolate the
operator, and fixed forcing is how it does that. What this establishes is which
of the two ledgers that isolation makes closable, and that Arm N_d closes it.
