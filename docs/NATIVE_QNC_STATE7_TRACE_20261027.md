# Native seven-cell QNC state carry through PD and RK3 — 2026-10-27

## Executed question

PR459 measured identical shared face words at target `(i,j,k)=(221,63,6)`
and its six neighbors. PR460 separated the weighted face expression from the
recorded tendency stores. This experiment follows the **same seven native
cells** from the final positive-definite scalar preparation into ordinary
RK3, conditional boundary handling, microphysics entry and the saved host
checkpoint.

Control and the historical alpha0.25 actual-wire T/Q state each ran one
trace-off and one trace-on 20-second full-domain host step from the same
READY40. The **four steps completed**. Each same-input off/on pair has
identical ACK and raw-bit final state across **652 variables / 322,426,586
numeric elements**. Both endpoints match the prior corresponding full-host
case. One-rank/one-thread execution used two tiles; the selected seven cells
are in the owner tile. The full forward retained nonadiabatic processes.
[The public packet](../harness/evidence/native_qnc_state7_2026-10-27/README.md)
binds raw values to the private build, executable, inputs and run receipts.
Four path-free run plans expose plan/source-plan digests and tie each arm to
the same build and READY40 state without publishing private checkpoint data.

## What the two scalar updates change

The final PD preparation receives `scalar_old` as its writable state and
`scalar_tend` as an input to consume. In this host call it passes `mu_1` as
both old and new mass arguments. It changes `SCALAR_OLD`, zeroes
`SCALAR_TEND` and leaves the live `QNC` state unchanged. The subsequent
ordinary RK3 update uses that prepared old buffer and forms the local
numerator with `ADVECT_TEND×MSFTY + SCALAR_TEND`, the RK time interval and
old/new mass factors. It writes the live QNC state.

All seven cells in both runs meet the following bitwise joins:

1. PD after `SCALAR_OLD`, live QNC and zeroed source tendency equal ordinary
   RK3 before fields.
2. The previous shared-face trace's final tendency equals the same run's
   ordinary RK3 `ADVECT_TEND`.
3. Source-compatible binary32/FMA arithmetic candidates reproduce PD's
   prepared old buffer and ordinary RK3's live QNC **7/7 per case**. This
   does not identify the executed compiler instruction sequence.
4. Immediate ordinary RK3 QNC equals the value after the selected scalar
   boundary operation and at microphysics entry **7/7 per case**.

At the target cell, the two calls share a prepared
`SCALAR_OLD=22,714,292` and `SCALAR_TEND=0`. Their final RK3 candidate
numerators are `+310,889.0625` (control) and `−344,470.9375` (alpha0.25)
under the matching arithmetic sequence. New mass factors are
`90,308.03125` and `90,308.046875`, giving the measured QNC sign split.

| Target QNC, legacy raw coordinate | Control | Alpha0.25 |
| --- | ---: | ---: |
| Before final ordinary RK3 | −1,918,020.375 | −1,917,976.75 |
| After ordinary RK3 / boundary / pre-microphysics | **+3.442540646** | **−3.814399242** |
| Final saved checkpoint | +3.442540646 | **0** |

The candidate's checkpoint QCLOUD is still positive, approximately
`6.3858613×10⁻⁵ kg/kg dry`, while NC is zero. Thus the earlier optical
profile rejection remains; this experiment did not evaluate candidate
RTTOV cost or accept an analysis.

## The later state interval and limits

At microphysics entry and the saved checkpoint, control NC differs in six
of seven cells and alpha0.25 NC differs in seven of seven. The trace locates
that later transition but does not attribute it to a named KDM process,
cleanup, transport or boundary operation. It does not certify raw NC units,
whole-domain particle-number conservation or forecast skill. The checkpoint
is a full-host 00:01:00 output; the satellite slot remains nominal 00:00,
so the saved endpoint is not a new time-matched assimilation cycle.

The next gate is a **physically justified number-moment correction** that
preserves shared-face application and local mass–number admissibility, then
passes the *entire fixed observation support* before any candidate RTTOV
cost or second assimilation is claimed. Current evidence narrows where to
act: the PD old-buffer preparation and final RK numerator can now be
distinguished from the subsequent checkpoint interval.
