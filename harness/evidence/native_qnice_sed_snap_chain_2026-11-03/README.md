# Conditional native NI chain across conservative sedimentation and snap A/B

This packet reuses the fixed native 39-level call from [PR #524](../native_qnice_39_applied_2026-11-03/README.md)
and the snap-A local check from [PR #525](../native_qnice_snap_a_ad_2026-11-03/README.md).
It makes **no new host, C++ or RTTOV call**. The frozen parent capture and
executed C++ conservative-sedimentation/coordinator source snapshots are
checked by SHA-256 before analysis. The public Torch oracle from the current
checkout is the differentiable snap-A/B producer under test; the earlier
packet's archived oracle sources are pinned and their relation to the current
checkout is reported.

```bash
python harness/evidence/native_qnice_sed_snap_chain_2026-11-03/replay.py
python -m unittest discover -s harness/evidence/native_qnice_sed_snap_chain_2026-11-03 -v
python -O -m unittest discover -s harness/evidence/native_qnice_sed_snap_chain_2026-11-03 -v
```

The CLI ends with `NATIVE_QNICE_SED_SNAP_CHAIN_REPLAY_PASSED`. Its
[results.json](results.json) retains represented plus/minus inputs, four
selected C3 outputs, branch signatures, JVPs, independent sparse analytic
directions, weighted VJP contractions and finite-difference residuals.
The saved JSON is hash-pinned. Stable baseline fields are compared directly;
fresh derivative results are judged against the analytic map, branch checks
and stated tolerances rather than every saved reduction bit.

## Defined conditional map

The initial QI is the recorded post-entry-clamp 39-level state; initial NI is
the recorded conservative-ice-substep input. For one substep, the replay uses
the executed conservative source order with the **captured work1/workn speeds,
DELZ, DEND, mstep, gate and dtcld held fixed**. NI arrival comes from the
preceding level's capped actual departure; QI arrival uses the recorded
density/depth metric. Both departure caps are re-evaluated as QI/NI vary.

The captured D1 and D2–D4 NI rates are zero at all 39 levels and the
homogeneous-freeze mask is false. The conditional map holds these rates and
mask fixed. **Their real producer derivatives are not measured.** It then
applies the public ice-number snap function twice with the reconstructed QI,
transported NI and fixed captured density. The baseline NI handoffs through
every recorded intermediate store and final C3 input are checked as f64 raw
bits at all 39 levels.

The reconstructed post-sedimentation QI equals snap-A's recorded QI at
**38 of 39** levels. At native level 15, reconstruction gives
`6.109135817357022e−11` while recorded snap-A QI is zero. Its intervening
QI process is not attributed by this packet. The map fixes that one cell to
the captured zero and excludes it from every derivative target and seed.
Thus this is a **fixed-operand conditional chain**, not the executed host's
full QI/NI Jacobian. Baseline C3 NI is recovered at all 39 levels; derivative
claims concern only the causal support at native levels 20–23.

A later [same-call D1 QI capture](../native_qnice_d1_qi_2026-11-03/README.md)
attributes the level-15 **baseline** zero to complete D1 ice melt. This
historical conditional replay still uses its declared splice and does not
claim the D1 producer derivative.

## Selected directions

Each seed is a unit relative change in one recorded input: QI at native 21,
NI at native 21, or NI at native 23. The four output columns below are final
**C3-input NI directional derivatives** in the recorded numerical coordinate.

| Relative input seed | NI20 | NI21 | NI22 | NI23 |
| --- | ---: | ---: | ---: | ---: |
| QI21 | +1.0429468145871474 | 0 | 0 | 0 |
| NI21 | 0 | +0.1358895005804943 | 0 | 0 |
| NI23 | 0 | 0 | +171.31746311439238 | +116547.04977661459 |

With fixed speed and open caps, the independent sparse expectation is:

- NI21 retains `(1−workn21·dt)` in NI21 and sends
  `workn21·dt·DELZ21/DELZ20` to NI20 **before** snap A. Snap A's lower branch
  replaces NI20 using QI and density, so the final NI20 derivative from NI21
  is zero.
- QI21 sends its applied ice mass to QI20 through the density/depth metric.
  The lower snap-A branch converts that QI20 response into the positive NI20
  value in the table.
- NI23 retains `(1−workn23·dt)` in NI23 and sends the actual applied share to
  NI22. Both cells pass their NI through the recorded snap decisions.

The replay checks these analytic values against Torch JVPs, selected weighted
VJPs and centered differences at `h=1e−3`, `1e−4`, `1e−5`. Difference
denominators use the **represented input endpoints**. All affected transport
cap and snap-A/B signatures remain the same at the checked endpoints. At
native 20, snap B is only `0.002466248950440786` above the lower lambda
bound at baseline; its positive margin is checked again at each endpoint.
Native-20 NI is exactly zero **at sedimentation entry**, an unchanged cap tie
for the three selected directions; it becomes positive after arrival and
before snap A. Other dry zero ties outside the causal support are frozen.

`scientific_status: INCONCLUSIVE` and `physical_unit_status: INCONCLUSIVE`.
The QNICE producer/restart basis, speed/reslope and intermediate-rate
sensitivities, native full-process JVP/VJP, operational f32, and RTTOV response
remain open. The conditional map is a source-ordered test at actual captured
values, not evidence that a perturbed host trajectory would follow it.

A later [ice-speed producer derivative packet](../native_qnice_ice_speed_ad_2026-11-03/README.md)
recomputes `work1_qi` and `workn_qi` for selected QI/NI directions and
reports the added producer path separately. Its other frozen assumptions
and physical-unit limits remain in force.
