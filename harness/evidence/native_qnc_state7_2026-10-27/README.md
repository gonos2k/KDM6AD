# Native QNC seven-cell PD→RK3 state trace — 2026-10-27

This packet follows the [PR459 shared-face capture](../native_qnc_shared_face_2026-10-27/README.md).
The witness is native one-based `(i,j,k)=(221,63,6)` plus its six face
neighbors. Each run uses the original **234×282, 39-level full-domain MP137
host**, starting at the same READY 00:00:40 and ending at 00:01:00. Control
and the historical rejected alpha0.25 T/Q candidate each ran trace off/on.

## Executed comparison

All four 20-second host steps finished. Within each input, trace-off/on
checkpoints and ACK bytes match exactly; the raw-bit comparator checked
**652 variables and 322,426,586 numeric values**, with zero mismatches.
Endpoints also equal the earlier PR459 same-input checkpoints. The alpha0.25
case used the same 117,172 effective T/Q grid-level pairs as the earlier
candidate; it is not a newly accepted analysis. The host used one MPI rank,
one thread and two tiles. Runtime readback retains `SCALAR_ADV_OPT=1`, RK3,
scalar h/v orders 5/3, MP137, `NO_MP_HEATING=0`, RRTMG4/4, PBL11 and CU37.
The [four compact run plans](receipts/plans) contain no private paths. Each
plan's SHA joins its run result and pins the historical source plan, READY40
checkpoint, private build/executable/DSO, expected endpoint, one requested
step and trace mode. Offline replay checks these bindings and the rank/thread
receipt.
The forward's nonadiabatic processes were enabled. The new private build
changes only `solve_em.o`; [exact source/build hashes](SOURCE_RESOLUTION.md)
and [run receipts](receipts/execution_summary.json) identify the executed
path separately from this packet's zero-call offline replay.

## Seven-cell state connection

Each trace-on run records **728 native binary32 values over seven cells**:
RK1/RK2 ordinary before/after, RK3 positive-definite preparation before/after,
final ordinary RK3 before/after, scalar boundary handling after, and
microphysics entry before. The source trace records the model
`itimestep=3` and its own `DT_RK=20 s` separately.

At all seven cells:

- `RKSCALAR_PD_BEFORE/AFTER` leaves live QNC unchanged, prepares `SCALAR_OLD`
  and clears `SCALAR_TEND`.
- Prepared `SCALAR_OLD`, live QNC and zero tendency match the subsequent
  ordinary RK3 inputs bit for bit. The same run's PR459 final face-derived
  tendency equals ordinary RK3 `ADVECT_TEND` bit for bit.
- The recorded old/new mass and RK operands reproduce prepared old state and
  ordinary QNC output under explicit source-compatible binary32/FMA
  arithmetic candidates. **7/7 cells pass each transition in each case**.
  The emitted FMA instruction sequence is not identified.
- Ordinary RK3 output QNC equals the value after conditional scalar boundary
  handling and before microphysics at all seven cells. This *does not* mean
  the final checkpoint after all physics has the same NC.

| Target QNC, legacy raw coordinate | Control | Alpha0.25 |
| --- | ---: | ---: |
| Ordinary RK3 / microphysics entry | +3.442540646 | **−3.814399242** |
| Final 00:01:00 checkpoint | +3.442540646 | **0** |
| Final checkpoint QCLOUD, kg/kg dry | 6.3834101×10⁻⁵ | 6.3858613×10⁻⁵ |

For the target, both inputs start final RK3 with prepared
`SCALAR_OLD=22,714,292` and `SCALAR_TEND=0`; their `ADVECT_TEND` and new
mass factor differ. A source-compatible contraction gives numerators
`+310,889.0625` and `−344,470.9375`, yielding the observed opposite QNC
signs. The negative alpha value is carried unchanged through the measured
boundary/pre-microphysics stages. The final checkpoint's zero NC with positive
QC remains an invalid mass–number pair for the current observation bridge.

The final checkpoint QNC differs from microphysics-entry QNC in six control
cells and all seven alpha cells. This packet measures that **interval** but
does not assign those changes to one named microphysics, cleanup or later
host process. It does not certify raw NC physical units, an applied domain
number budget, an admissible analysis, or RTTOV candidate cost.

## Offline reproduction

From the repository root:

```sh
python3 -m harness.evidence.native_qnc_state7_2026-10-27.replay
```

This verifies the packet files and source pins, compares the target's older
upstream record, replays the new seven-cell PD/RK3 chain and reproduces
[analysis.json](analysis.json) byte for byte. It makes zero host/KDM/RTTOV/
optimizer calls. Earlier evidence packets and their source hashes remain
immutable. Private generated host Fortran, executable and checkpoints are
excluded; their SHA attribution appears in receipts.
