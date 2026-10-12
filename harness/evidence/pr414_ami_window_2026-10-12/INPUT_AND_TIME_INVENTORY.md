# Actual dates, inputs and clocks (2026-10-12)

Only observation date **2025-07-19** has completed real native–AMI analyses:
original clear centre (j86,i48), the V4 replay of that same centre, and natural
QC column (j103,i48), including its declared budget comparison. These are one
initialization/date, not separate independent weather events. Jul20/21 have
nine-channel L1B decoding only; their native analyses remain pending.

## Original actual Jul19 method

The normal retained native producer initialized at **2025-07-19 00:00 UTC**,
ran 358 min, and terminated at **05:58 UTC**. Its eight actual saved states span
**05:55:40–05:58:00 in 20 s increments**. Initial analysis background is
**05:55:40**, lead 5 h 55 min 40 s. The original analysis used one f64 KDM local
20 s transition to nominal **05:56** (lead5h56m), supplied forcing fixed, then
actual all-sky RTTOV/KMA BT, initial T/Q controls, fixed physical parameters,
seven AMI channels10–16, scale1K/bias0, normalized Huber delta1, one initial
prior, L-BFGS, accepted-point audit and full-gradient/state checkpoint.
It is not full host cycling, host dynamics adjoint, or independently verified
atmospheric truth. Native39 centres/40 interfaces are preserved; the27-layer
upper reference extension, gases and surface/optical assumptions are declared
H inputs, not newly acquired model states.

AMI filename nominal label is **202507190556**. Actual source metadata has
scene acquisition raw **20250719_055656** (OBT05:56:56), mission planned UTC
**2025-07-19T05:50:00Z**, and unresolved synchronization/epoch numbers.
Actual scene/pixel UTC is unverified/null. The original research matchup uses
filename nominal time as model UTC **by an explicit assumption**; planned UTC
and raw OBT are not relabelled actual pixel time. New window receipts retain
all three scenes' distinct metadata and the same nominal hypothesis.

## Jul19 requested ten-minute window

Use the already validated natural-QC saved background **05:55:40**, not a new
native run. Observe actual separately acquired scenes at nominal
**05:56,06:06,06:16**. On dt20s these are indices **1,31,61**, total61 steps
(1220s). One initial T/Q/prior is fitted jointly to21 channel–time terms.
The21 costs have equal1K scale and additive Huber weights; temporal observation
error independence/covariance is an exploration assumption, not calibrated R.
Forcing, pressures/interfaces, surface and optical background density are held
from that initial native column. The later states are **local KDM states**,
not saved06:06/06:16 host forecasts. This extends the existing conditional
experiment from20s to20m20s; it does not establish the accuracy of held forcing
or reproduce transport/PBL/dynamical host tendencies. The initial producer's
05:58 termination limits its saved host states, not this separate local window.

## Additional search and requirements

Coordinator:96 sibling/temp roots,217 filename matches,212 distinct physical
NetCDF metadata reads (Times/dimensions/attributes/variables only). Green/Red
also inspected additional user/home/project/volume paths; overlaps are not
summed as distinct files or independent evidence. Detailed audit inventory is
in ignored `graphify-out/other-native-search-20261012/`; metadata-only reads do
not certify valid weather arrays, normal termination or producer lineage.

| Found candidate | Metadata | Admission |
|---|---|---|
| canonical `host/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS/klfs_lc05_fcst.202507190000` | Jul19 hourly00–12,5km39layers,MP137 | candidate; lacks separate completion/run-identity receipts; not used for this window |
| sibling `KIM-meso/KIM-meso_v1.0/run/wrfout_d01_2025-12-23_21:00:00` | 5km39layers,MP8,one initial frame | different producer/physics lineage; not silently substituted |
| other WRF/KSCM candidates | ideal/2023 dates or different grids/levels | not the required current native series |

No new Jul20/21 current-lineage native pair was confirmed in searched paths.
This is scoped absence, not an assertion about all institutional archives.

For another native-backed date, the needed materials are: normal run identity,
producer effective initialization/stop and completion proof; an actual saved
39-layer State with native centre/interface pressures and surface; its supplied
forcing and declared hold/time sequence; native location/sea/ice metadata;
matching AMI L1B scene/channel/calibration/navigation/QA/source receipt; the
existing RTTOV executable/coefficient/optical and reference inputs. Earlier
initialization is allowed if valid time/lead and integration coverage fit.
No external model/reanalysis or additional satellite/L2 acquisition is used.
For full-host ten-minute forecast/cycling claims, actual admitted host states
and their time-specific forcing/surface/pressure coverage would additionally
be needed; the local window does not manufacture them.
