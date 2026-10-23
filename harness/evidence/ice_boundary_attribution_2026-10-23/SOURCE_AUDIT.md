# Ice sedimentation source contract

Read-only source audit for the legacy ice-trace investigation, 2026-10-23.
The graph query was low-recall and returned unrelated interface nodes; the
contracts below are checked against the active Fortran source and matching
oracle/C++ implementations. No source or model was changed or run for this
memo.

## Source identity

The active private host file is
`/Users/yhlee/KDM6AD-k/host/KIM-meso_v1.0/phys/module_mp_kdm6.F`, SHA-256
`fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5`.
Matching public sources checked:

| Source | SHA-256 |
| --- | --- |
| `libtorch/src/runtime.cpp` | `4a56110c91b7495aea0542531eb809a048bb7994747cea2be826f9a2f6e26f7a` |
| `libtorch/src/coordinator.cpp` | `9253e1741cb8926f98fc088c56579a015472ea43b7ef0b365ef2c42bd2660152` |
| `libtorch/src/sedimentation.cpp` | `1fd41e6dff2f99cf80cf9f318245cb50cb2d107d2f9053f8c65802f6b4037c2a` |
| `oracle/kdm6/runtime.py` | `e505c3a1d42fb2880d0ce3d65381488a06528de8d4133b39d4e9a573cef997ac` |
| `oracle/kdm6/coordinator.py` | `05981b7a19c8d4fe262cb8080b14ddf3b4eb5c027b58604803b2e0b80764a0bd` |
| `oracle/kdm6/sedimentation.py` | `0e2b866f1a71937fbc2cf9ff382ced8bd0e439c732992b494b2ea2251f806f89` |

## Legacy ice velocity handoff

At `module_mp_kdm6.F:1158-1185`, `slope_kdm6` first fills `work1(4)` and
`workn(2)` with the raw ice terminal-velocity terms. The code divides these
two arrays by `DELZ` at lines 1171 and 1173, then selects per-column
`mstep_i = max_k max(NINT(max(work1(4),workn(2))*dtcld+0.5),1)` at 1177-1179.
This uses the normalized `vt/DELZ` basis.

The main rain/snow/graupel subcycling follows. Its final in-loop `slope_kdm6`
recomputes all velocity work arrays at lines 1263-1265; the following
normalization loop divides only slots 1-3 and `workn(1)` at 1267-1273. It
leaves the ice slots 4 and `workn(2)` raw. The subsequent ice loop consumes
those raw values on its first substep in `falk = DEN*QI*work1(4)/mstep_i` and
`falkn = NI*workn(2)/mstep_i` at 1284-1285. After each ice substep the source
re-slopes and divides the ice slots by `DELZ` at 1324-1339, so later
substeps consume normalized values. When `mstep_i=1`, the whole ice transport
uses the raw handoff while its substep count was selected from normalized
values.

This establishes the executed legacy basis/order. It does not alone prove
that the recomputed numerical `vt_i` changed during the main loop: QI/NI are
not main-loop sedimentation fields. The finding is the raw-versus-normalized
handoff state, not a measured numerical difference between those two
velocity arrays. `runtime.cpp:596-604` computes ice mstep from normalized
work; `coordinator.cpp:2803-2809` deliberately retains raw work in the
default `Legacy` variant and only the separate normalized variant divides
it. The Python runtime/coordinator follows the same explicit legacy handoff
at `runtime.py:653-685` and `coordinator.py:2682-2706`.

This basis difference also limits dimensional claims about the forensic trace.
`slope_kdm6` produces `vt_i` and `vtn_i` (`module_mp_kdm6.F:3846-3857`);
`work1_i/DELZ` is the rate-like value used for mstep, while the default first
ice substep consumes raw `vt_i`. Thus trace fields named `falk_qi` in
kg m-3 s-1 and `out_attempt_qi` in kg/kg describe physical units only for a
normalized-velocity calculation. For the raw legacy handoff treat them as
algebraic values in the executed map, not a dimensional flux certificate.
`DEN*DELZ*QI` remains a defined fixed-measure state accounting diagnostic,
but `raw_falk*DELZ*dt` is not thereby a validated physical surface export.

For the selected `dt=20` case the captured ice substep count is 1, so the
Fortran and C++/Python upper-bound behavior does not affect this trace. Do not
generalize the count formula to large `mstep_i`: the active Fortran source
shown here only lower-bounds `numdt_i`/`mstep_i` at 1 (`:1177-1185`), whereas
the C++/Python port clamps its per-column mstep to 100 (`runtime.cpp:596-600`,
`runtime.py:670-672`).

## Departure, arrival, and boundary measures

Fortran uses bottom-first WRF indexing. In its ice loop, `k=KTE` is the top
cell; it has no above-cell arrival and applies `QI_after=max(QI_before-
falk*dtcld/DEN,0)` at lines 1280-1290. Interior `k=KTE-1...KTS` uses a
stored `falk(k+1)` produced from the above cell's pre-update state. Local
departure is `dqi(k)=min(falk(k)*dtcld/DEN(k), QI_before(k))`; the arrival
attempt is `falk(k+1)*DELZ(k+1)/DELZ(k)*dtcld/DEN(k)`. Critically, its cap is
`QI(k+1)` after the above cell was updated, lines 1294-1308. The same
pre-update stored-falk / post-update-reservoir cap applies to number at
1303-1307. C++ matches this at `sedimentation.cpp:243-285`; the Python oracle
matches at `sedimentation.py:390-427`.

For ice mass mixing ratio `QI` in kg water per kg dry air, use the fixed
call-entry layer measure `W_k = DEN_k * DELZ_k * QI_k` in kg m-2. For the
upper source `u` and lower receiver `l`, define

```
D_u = DEN_u * DELZ_u * dqi_u
A_l = DEN_l * DELZ_l * dqi_above_l
G_u = D_u - A_l
```

where `dqi_u` and `dqi_above_l` are the actually capped departures and
arrivals, not the uncapped attempts. With no upper boundary inflow,

```
column_delta_QI + actual_bottom_outflow + sum(interior G_u) = 0
```

up to floating-point reduction error. The applied bottom departure is
`DEN_bottom*DELZ_bottom*out_applied_QI_bottom` (the source's `dqi` at KTS).
The bottom state net depletion is instead
`DEN_bottom*DELZ_bottom*(QI_before-QI_after)`; because the bottom update also
adds the applied arrival from the layer above, this net depletion equals the
departure only when that arrival is zero. The stored bottom diagnostic is
raw accumulated `falk_qi * DELZ_bottom * dtcld`; if the local departure cap
binds, it can exceed the applied departure. Under the default raw-velocity
handoff, its dimensional interpretation is additionally conditional as
described above. Keep this diagnostic-minus-applied-departure gap separate
from the bottom net state change and internal interface gaps.

For `NI`, the KDM equations imply a volume-number coordinate: the ice DSD
uses `PIDNI*NI/(DEN*QI)` and its limiting inverse writes
`NI=DEN*QI*lambda^DMI/PIDNI` (`module_mp_kdm6.F:1578-1589`). Thus the
kernel-coordinate layer inventory is `NI*DELZ` (# m-2), with number
departure `DELZ_u*dni_u` and arrival `DELZ_l*dni_above_l`. However the host
Registry labels transported QNI as `# kg-1`, and the KDM wrapper copies NI
through unchanged (`module_mp_kdm6.F:385-388, 426-428`). No producer conversion
is visible here. Therefore this is a conditional kernel-coordinate number
ledger, not certification of the original host payload's physical basis. A
physical per-dry-mass column inventory would instead weight NI by
`DEN*DELZ`; the source does not establish that this is the basis supplied to
the KDM kernel.

## Counterexample and scope

The post-update cap can be a real deficit even with equal density and layer
thickness. For two layers with `DEN=1 kg m-3`, `DELZ=1 m`, upper `QI=1`,
lower `QI=0`, and `falk*dtcld/DEN=0.8`, the upper leaves `QI=0.2`; the lower
arrival is then capped to 0.2 although the source already lost 0.8. The
column loses 0.6 kg m-2 with no bottom outflow. The analogous volume-number
example loses 0.6e6 m-2 for upper `NI=1e6 m-3` and `falkn*dtcld=0.8e6 m-3`.

The source equations support interface-by-interface accounting and point to
the sedimentation stage. They do not attribute a captured native residual to
a unique limiter or prove that the raw-velocity handoff alone caused it.
Any source trace is value-only instrumentation; it does not change the
operational physics map or its JVP/VJP. It does not certify the full host/RK
cycle, HVPs, physical host NI units, or conservation outside the measured
column and call.
