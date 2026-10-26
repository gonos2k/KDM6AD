# Native upstream QNC RK trace — 2026-10-26

This follow-up traces the ordinary host RK update that feeds KDM. It uses the
same native full-domain 00:00:40 READY checkpoint for two states: control and
the previously proposed alpha=0.25 T/Q state. Each state has an independent
trace-off/on pair of 20-second runs. Each run ends
at 00:01:00 / timestep 3. This is an observed state transition, not a forecast
or a new assimilation cycle.

## Executed comparison

Four actual steps were run: control V4 trace-off/on and alpha0.25 V6-controller
trace-off/on, all with the same V4 executable. The two off/on pairs match each
other byte-for-byte in ACK and across 652 checkpoint variables / 322,426,586
numeric elements. The endpoints also match the earlier control and alpha0.25
checkpoints. Each step made two KDM wrapper entries; total: 4 host steps, 8
KDM entries, 0 RTTOV calls, 0 optimizer calls, and 0 accepted analysis updates.
The replay is offline arithmetic and makes 0 model calls of any kind.

The measured `PRE_MICROPHYSICS` QNC words match the same run's KDM `MP_INPUT`
words bitwise at both selected locations. The first witness, native
`(i,j,k)=(221,63,6)`, begins from the same READY QNC value, 13,605,366, in both
runs. The regular RK stages are:

| Boundary | Control | Alpha 0.25 |
| --- | ---: | ---: |
| RK1 QNC | +3,424,469.25 | +3,424,466.5 |
| RK2 QNC | −1,918,020.375 | −1,917,976.75 |
| RK3 QNC / pre-microphysics | **+3.4425406456** | **−3.8143992424** |

Both cases have a negative RK2 intermediate. The positive-def preparation before
RK3 gives the same `SCALAR_OLD=22,714,292` in both; the RK3 numerator changes
from `+310,889.0625` to `−344,470.9375`. The recorded combined tendency changes
from `−102,553,681,920` to `−102,553,714,688` (difference `−32,768`); with
`DT_RK=20`, the rounded `dt*tendency` term shifts by `−655,360`. A
source-order binary32 replay with an exact-FMA-contraction candidate reproduces
the output words. The compiler instruction sequence was not captured, so this
is not evidence that the executed machine used FMA.

At `(91,94,4)`, READY QNC is already zero while QC is positive, so this is an
inherited QC/NC mismatch. RK3 gives QNC `+0.02228504047` in control and
`−0.17183831334` at alpha 0.25. The negative pre-microphysics QNC values are
the actual f32 KDM inputs; the KDM clamp returns zero while QC remains positive
at these failed profiles.

## Interpretation and limits

The RK update is the first measured boundary at `(221,63,6)` where the control
and alpha0.25 QNC signs differ. This locates an applied state change; it does
not identify a named physical cause. The upstream interval includes analysis
application, host preparation, dynamics and other physics. In particular, the
combined `ADVECT_TEND` operand is not decomposed here. Raw QNC units are not
certified, and the `POSITIVEDEF` setting does not guarantee a nonnegative final
stored QNC in these runs.

The execution used a private compiled snapshot of `mediation_integrate.F` to
apply the selected T/Q state; the canonical active host source does not contain
that experimental hook. Runtime namelist readback confirms MP137 with
`NO_MP_HEATING=0`, `USE_THETA_M=1`, `USE_Q_DIABATIC=0`, RRTMG LW/SW 4/4,
PBL 11, CU 37, LSM 2, `MP_ZERO_OUT=2`, and `MP_ZERO_OUT_ALL=0`.

The alpha0.25 proposal remains inadmissible on the fixed observation support.
No candidate cost, accepted update, second assimilation, or forecast/cycling
result is established. R5 physical admissibility and a justified repair remain
open; no NC floor or observation-mask change was introduced.

## Reproducibility

The [public evidence README](../harness/evidence/native_upstream_nc_2026-10-26/README.md)
links the actual execution receipts, source/build identities, traces and
[analysis](../harness/evidence/native_upstream_nc_2026-10-26/analysis.json).
The public replay validates hashes and reproduces that analysis without model
calls:

```sh
python3 -m harness.evidence.native_upstream_nc_2026-10-26.replay
```
