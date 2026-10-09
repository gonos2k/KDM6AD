# Satadj/activation: contract for the bounded clear-state response

Baseline: PR391 `a85b39eb`; source `oracle/kdm6/coordinator.py::apply_satadj_step_torch`
and `oracle/kdm6/runtime.py::_kdm6_pure`. This is the local contract used to
interpret the new T/Q experiments, not a change to the process or a full S17
ledger. Operational f32 and the f64 research map remain distinct.

## Applied quantities and units

For one coordinator substep with duration `dtcld`, define the **applied**
activation mass `a=pcact*dtcld`, condensation/evaporation mass
`c=pcond*dtcld`, activated number `b=ncact*dtcld` and the actually transferred
complete-evaporation number `e=nc_evap`. `pcact` and `pcond` are mass mixing-ratio
rates; `ncact`, `nc`, `nccn` at this kernel boundary are volume-number quantities
(rate in m^-3 s^-1, inventory in m^-3) under the normalized dry-number contract.
The NC/NCCN State boundary numbers discussed here are instead per kg dry air.
This two-reservoir identity is not a budget for other number/volume moments.

Ignoring only inactive nonnegativity clips, the source applies:

```
delta_qv = -a-c
delta_qc =  a+c
delta_T  = (xl/cpm)*(a+c)
delta_nc =  b-e
delta_nccn = -b+e + reservoir_clip_departure
```

`pcact` is capped by available qv; `pcond` is capped by qv on condensation and
available qc on evaporation. `e` uses the source's exact complete-evaporation
equality gate. The final NCCN reservoir clip can create a signed numerical
departure and must be recorded separately rather than hidden in a number budget.
Earlier entry clamping and later DSD/floor/coalescence/other processes are
different stages, outside this isolated transfer identity.

At this stage, a water transfer check is
`delta_qv + delta_qc`; a latent-transfer check is
`delta_T-(xl/cpm)*(a+c)`, using the **actual entry coefficients and source
operation order**. These local checks do not replace a moist enthalpy state
function, boundary heat/work, or full-step heat closure. Applied number checks
must include `b`, `e` and the reservoir clip in the same volume basis. Universal
particle-number conservation across the whole microphysics map is not imposed.

## Tangent and attribution scope

Away from recorded activation/availability/evaporation/clip boundaries, the
directional identities use the same applied quantities and coefficients:

```
d(delta_qv) = -da-dc
d(delta_qc) =  da+dc
d(delta_T)  = d(xl/cpm)*(a+c)+(xl/cpm)*(da+dc)
d(delta_nc) = db-de
```

Independent directional differences must confirm the executed discrete map;
an observed finite perturbation crossing saturation is not that baseline's
local tangent. A JVP/VJP transpose check alone does not prove physical budgets.
State-to-state derivatives, this named stage and any later BT/cost path are
separate claims.

## Fixed forcing and measures

The local diagnostic keeps native pressure centers/interfaces and declares the
fixed `rho`, `pii`, `p`, `delz` forcing. The runtime dry density is
`rho/(1+qv_entry)` for each call; its qv derivative and finite change remain in
the executed operator. It is not silently replaced by a fixed optical or
inventory density. The optical/inventory reference, if used, is separately
declared. The 20/10/5-second study evaluates the same **constant physical-time
forcing**, with the same final physical time; it is not a host dynamics study.

For finite T/Q scenarios, first distinguish the changed initial inventory
`W(x0_perturbed)-W(x0_background)` from the integration departure
`W(xT)-W(x0_perturbed)`. Neither difference measures an unobserved model boundary
flux. Use the existing host dry-mass fields only under their captured measure;
rho_d*delz, host hybrid mass and volume-number inventories are not interchangeable.
Missing external/boundary/work terms remain unknown.

## Instrumentation boundary

The dry-number runtime refuses its unlabeled built-in budget and diagnostic
trace interfaces. That guard remains in place. Any temporary observation of
the satadj function is a separately identified **value-only** diagnostic,
recorded in kernel units and required to preserve returned outputs bitwise for
each captured scenario. Restore the original function afterward. AD/FD runs
use the unchanged, uninstrumented map. Such a capture does not claim that the
built-in dry-number trace/ledger is supported.
