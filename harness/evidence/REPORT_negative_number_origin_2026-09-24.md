# Native localization of the retained mp237 negative number cells

## Measured causal path

This trace follows the **original, unnormalized mp237** from PR233. It is
separate from the normalization-only experiment. All 11 negative QNCLOUD,
QNRAIN and QNICE history cells at 40 s lie on east/north mass-grid edges.
A first read-only trace located their appearance across `flow_dep_bdy`.
That routine copies an inward cell on outflow, so a second trace added the
11 donor cells. Neither trace modifies a physics/dynamics assignment.

The measured chain for each final negative is:

1. The inner donor becomes negative across the scalar `rk_update_scalar` call.
2. `flow_dep_bdy` sees positive outward normal velocity and copies that exact
   donor value to the boundary cell. It does not numerically create the negative.
3. The inner donor is negative immediately before microphysics and nonnegative
   afterward; some species are also newly generated, so this is not exclusively
   a clipping measurement.
4. The boundary value remains negative across microphysics and to solver exit,
   exactly matching the saved 40-s history value.

One QNICE donor (pair 9) first goes negative at time step 2, RK stage 1
(-7.581973271442166e-9), later changes, and ends with -1.0833765800597275e-16.
The other ten donors first go negative at step 2, RK stage 3. This is a first
occurrence **among the 22 traced cells and recorded boundaries**, not a search
for the globally earliest negative anywhere in the domain or within every
upstream flux calculation.

## Why the boundary retains the value

For this case `specified=True`, `nested=False`, `have_bcs_scalar=False`,
`spec_zone=1`, `scalar_adv_opt=1`, `polar=False`. Thus the scalar file-specified
boundary-tendency branch is not executed; zero values found in wrfbdy number
fields are **not evidence of active zero forcing** in this path.

The generic flow-dependent boundary routine runs instead. At east/north edges,
positive outward coupled velocity selects the adjacent interior donor.
The source copies the donor without arithmetic. The recorded donor, velocity
sign, receiver and paired grid indices confirm this for all captured stages.

The microphysics driver shrinks its active bounds by `spec_zone` for a specified
boundary (private `module_microphysics_driver.F`, around 864 and 934–941).
Consequently these outer mass-grid cells are excluded from the KDM call, while
the paired donors are included. They are physical boundary points, not a
mistaken identification of arbitrary ghost cells. No final scalar boundary-file
reset runs for this non-nested case. This explains how an inner negative that
is subsequently removed can still be present at the edge in history.

## Native numerical replay and fused operations

The trace includes 1188 records: 22 cells, two time steps and 27 stage checkpoints
per step. It includes both ordinary scalar RK calls and the stage-3
`rk_update_scalar_pd` preparation. The latter modifies `scalar_old` and clears
`scalar_tend`; it must not be omitted merely because it is called “PD.”

For the ordinary update, define binary32 values

    M_old = c1*(mu_old+mu_base)+c2
    M_new = c1*(mu_new+mu_base)+c2
    n_new = (M_old*n_old + dt*tendency)/M_new.

The RK1 stored reference is the current pre-call scalar; subsequent stages use
`scalar_old`. Interior tendency includes advective tendency times map factor
plus the stored scalar tendency; the outer specified strip excludes the
advective contribution at this particular update.

The **retained host module_em object uses fused multiply-add instructions**.
It matches the member of the linked archive, SHA-256
`7be51c5276e3e28cefe6482377b9fb9d7e8cb3d1db972efbf2ad2b24137348c2`.
Disassembly contains `fmla` for both metric evaluation and the numerator.
This is an existing general-host object; the KDM module's `-ffp-contract=off`
contract was not changed.

An initial unfused binary32 source-expression replay differed in 10 of the 132
ordinary updates, including a near-zero sign difference. After accounting for
the observed fused operations, an exact-rational, round-once binary32 witness
reproduces **all 132 ordinary and 44 PD output stores bit-for-bit**. A local
system `fmaf` cross-check agreed; the public replay uses standard Python integer/
rational arithmetic, not a platform-specific native library. Its tests include
a double-rounding counterexample and subnormal/tie cases.

This is not permission to enable FMA in the KDM parity path. It demonstrates
why the executed host object, rather than an assumed expression rounding order,
is required to explain these stored values.

## The negatives are not all final-addition roundoff

For eight of the eleven final inner negatives (four cloud-number and four
rain-number cells), the last RK3 update has `scalar_old=0`, stored scalar tendency
0, and a negative advective tendency. Its negative result is not cancellation
between two large stored-number terms at the final addition.

For example, cloud-number donor (Fortran i=233,j=124,k=12) enters this RK3 call
with current intermediate state 24926.619140625 but `scalar_old=0`.
The advective tendency is -140.56446838378906; the mapped, time-integrated term
is -2744.953369140625 and the denominator is 96180.03125, producing
-0.028539743274450302. The current intermediate value is not the stored reference
used in this RK3 formula.

The three ice-number cells retain positive stored references and differ in their
cancellation. In pair 10 the negative tendency exceeds the storage term by about
6.17% of that tendency term, despite the final number value being small. Pair 9
is highly cancellation-sensitive: independently rounded products would cancel
to zero, whereas the actual fused numerator yields the measured tiny negative.

These observations localize and numerically reproduce the update. They do not
identify all upstream advective face fluxes/limiter decisions, establish a
physical number basis, or justify classifying every negative as harmless
roundoff. No blanket clipping, advection-option change or general WRF repair is
introduced. Whole-host positivity remains **not approved**.

## Noninterference and coverage

Both the boundary-only trace and the extended donor trace complete the same
40-s case through the repository runner. Each has the retained PR233 complete
history hash `7d2afb3236ea6ea53a1df5c75f17b2b1da27f963ace697a8a912eda871c0f750`:
253 numeric fields and Times at 0,20,40 s match, with matching variable sets,
shapes, types, input hash records and effective namelists.
Only an isolated `solve_em` object was recompiled; existing KDM and other host
objects were linked. Removing the read-only instrumentation restores the exact
source. One earlier incomplete compile was stopped to add the required PD
checkpoint; this was not a native experiment. Actual completed trace runs: two.

The public JSON includes the measured checkpoint operands, source/build hashes,
paired donor/receiver coordinates and history targets. Stage payload meanings
are explicit: FLOW records reuse slots for donor value, velocity and coordinates;
only the value slot is meaningful in the simple state checkpoints.
Public replay checks recorded arithmetic and evidence, not private file
re-authentication or a new host execution. It does not localize all negative
cells in the **normalized** trajectory, which has a different final cell set.

## Remaining decision

The missing location/propagation measurement is now available for the original
mp237's selected 11 final negatives. The next repair investigation can focus on
the upstream scalar transport/limiter budget at the paired donors and boundary
scheduling, with the number-unit contract kept explicit. This result neither
closes operational transport P1 nor authorizes a default change. It does not
add an RTTOV run or an approved liquid observation; that gate remains 0/9.
