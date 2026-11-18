# Same-call native D1 ice-mass handoff

This packet closes the **baseline QI handoff** left open by the conditional
[sedimentation → snap A/B → C3 replay](../native_qnice_sed_snap_chain_2026-11-03/README.md).
It uses the same 2025-07-19 00:00:40 native input, one 20 s mp137 call,
column `(164,242)`, rank 0, tile 2, `runtime_call=2`, `one_step_call=2`,
`B=32248`, `b_zero=22617`, and 39 levels. The executable is byte-identical
to the PR #524 host executable; a newly built **isolated DSO** adds QI records
to the existing native capture. The active sedimentation variant remains
`KDM6_ICE_FACTORIAL_MODE=norm_actual` on the fp64 value bridge.

```bash
python harness/evidence/native_qnice_d1_qi_2026-11-03/replay.py
python -m unittest discover -s harness/evidence/native_qnice_d1_qi_2026-11-03 -v
python -O -m unittest discover -s harness/evidence/native_qnice_d1_qi_2026-11-03 -v
```

The CLI ends with `NATIVE_QNICE_D1_QI_REPLAY_PASSED`. It needs only public
files. `raw/native_qnice_applied_38424_runtime2.csv` contains 3,471 selected
rows: all 2,769 rows from the prior capture have **identical dtype and raw
word**; 702 new rows record post-sedimentation QI, D1 QI/T/amount/stores,
homogeneous-freeze QI/source/output, and D2–D4 QI amounts/stores. The host
trace's 39 value rows are also unchanged; its capture path header differs.

## Level 15 result

| Same-call stage | QI in the recorded C++ numerical coordinate |
| --- | ---: |
| After sedimentation and runtime cast | `6.109135817357022e-11` |
| D1 input | `6.109135817357022e-11` |
| D1 temperature | `275.62344271948496 K` |
| Applied `pimlt_qi` | `6.109135817357022e-11` |
| First D1 QI store; D1 output | `0` |
| After homogeneous freeze; snap A input | `0` |

The captured D1 `pinuc` and `pfrzdtc` terms are zero. The executed
`melting_torch` source selects `pimlt_qi=QI` for `T>273.15 K` and `QI>0`;
these two captured operands select that branch at level 15. Replaying the
executed `QI + pinuc − pimlt_qi`, then `+ pfrzdtc` stores gives zero in
f64 raw bits. The captured homogeneous-freeze mask is false. Thus D1's
complete ice melt explains the formerly unexplained baseline transition;
the recorded zero is no longer needed as an **unattributed baseline input**.
Across all 39 levels, the replay checks D1's simple ice-melt producer,
both QI stores, homogeneous-freeze QI arithmetic using its captured mask,
D2–D4 QI stores using captured process amounts, and the snap A/B/C3 QI
handoffs in raw f64 words. Only level 15 has a positive D1 ice-melt amount;
the captured homogeneous-freeze masks are false in this call.

## Execution and evidence limits

The same copied host executable and newly built isolated DSO ran capture-off
and capture-on. Both complete endpoint files hash to
`225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070`,
the same endpoint hash as PR #524. The public verifier checks pinned capture,
source snapshots, source-to-parent capture-only diff, object/build receipt,
private run/session receipts, and loaded-DSO path recorded by the runner.
Private executable/DSO and full checkpoints are **identified by hashes and
run records**, not redistributed or rehashed by public CI. The source/object
relation is the retained build record; this packet does not independently
recompile private binary bytes in public CI.

The D1 ice-melt amount is independently reconstructed from its captured QI
and T because that particular producer is a two-condition selection. The
other D1 melt terms, the homogeneous-freeze mask producer, and the D2–D4
process-rate producers are not independently replayed here. The prior
conditional derivative packets still hold their declared intermediate
rates/masks fixed and retain their level-15 splice; their **historical
computations are not retroactively changed**. A connected derivative replay
can now replace that splice with the measured D1 producer and verify
perturbed branch behavior separately.

`scientific_status: INCONCLUSIVE` and `physical_unit_status: INCONCLUSIVE`.
This is one f64 native call. It does not certify operational f32 behavior,
the QNICE production/restart unit, host-wide JVP/VJP, or RTTOV sensitivity.

The later [D1 conditional AD packet](../native_qnice_d1_ad_2026-11-03/README.md)
records QC/NC/T stores, replaces the level-15 splice in a **new** fixed-speed
baseline chain, and tests local D1 melt tangents. This historical packet's
baseline QI replay is unchanged.
