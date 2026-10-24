# Selected-column norm_actual observation-cost coupling

The [QR stage investigation](LOCALIZED_ICE_BUDGET_AD.md) retains the original main
map and documents its budget defects. This experiment evaluates the candidate's
existing numerical map; it does not adopt it operationally or correct the
transport defects.

## Preserve the B512 map through a one-column protocol

`BatchTargetKernel` provides the selected map `P K E`: it copies the immutable
full `[12,B,L]` and `[4,B,L]` background, injects only target-column inputs,
runs the full batch backend, and returns that column. JVP scatters the target
directions into zero full buffers and selects the result. VJP scatters the
output cotangent, runs the full transpose and selects the input adjoints.
This preserves actual cross-column coupling and shared scheduling, even though
the cost reads one profile. It does not replace the forward with B1.

Owner-bound recorded handles retain the full backend record; value-only,
foreign and closed handles are rejected by derivative calls. Close is
idempotent. A backend without timestep metadata is bound to20seconds; any
different timestep must be declared by the backend and match the adapter.
The adapter exposes `levels`, `dt`, and the joint state/forcing
keyword expected by the existing dry-number and finish wrappers. It is not a
full-host transition. Independent affine tests include deliberate cross-column
coupling and compare dense-matrix, FD and transpose results.

## Reuse the established observation chain

Native checkpoint controls are moist-theta perturbation, QV, total MU and
interface PH, with native hybrid coefficients/PHB fixed. Only native theta_m
and QV directions are evaluated here; MU/PH remain fixed. Scalar continuous
prep is checked against the original endpoint packet with the already declared
scalar/vmap agreement envelope. The selected kernel keeps the other511 packet
columns fixed.

The number receipt uses the captured B512 request as its explicitly labeled
input-trace artifact, not a nonexistent target `MP_INPUT` sample. Four kernel
volume operands are conjugated to a newly derived dry-mass coordinate with
live native DEN. Original host units are still unknown/not migrated. The
baseline dry control is defined once; trials do not reinterpret the saved
volume numbers with their perturbed density. Under T/Q-only directions the
native prep dry density is geometry-dependent and fixed, avoiding the NN-floor
crossing that can accompany unconstrained live-DEN geometry controls.

Existing `MicrophysicsObservationState`, `KernelFinish`, native profile/cloud
builders, live case writer, actual RTTOV-K and Huber cost are reused. They
retain initial-state finish dependence, all relevant cleanup, post-finish EOS,
live center/interface pressure, Exner/T/Q, cloud mass/number and direct
RTTOV P/P_HALF K paths. No RK/retained-memory/optimization/HVP contract is added.

## Spatial/surface/time assumptions

Both targets use their actual mapped seven-channel KO BT from the pinned
full-grid observation bundle. They do not reuse the old (156,21) BT. Target
native latitude/longitude, elevation and checkpoint skin/near-surface states
are overlaid; native winds are rotated using native sine/cosine map angles.
Q2 follows the existing explicit dry-mixing-ratio to moist-ppmv conversion.

The old RTTOV template supplies structure and declared fixed salinity/foam/
FASTEM/fetch, spectral emissivity, trace-gas and upper-reference assumptions.
It is not labeled a fully target-native surface. Thermal channels10–16 use
solar=false. Nominal slot00:00, scene header00:00:33 and model endpoint00:00:40
remain distinct; per-pixel UTC and independent navigation are unverified.

The [evidence](../harness/evidence/norm_actual_observation_2026-10-24/REPORT.md)
reports one admitted column and one coefficient-domain rejection. A zero cost
from an all-zero quality mask is not a fit or a derivative certificate.
