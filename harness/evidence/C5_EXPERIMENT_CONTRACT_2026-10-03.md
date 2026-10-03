# Fixed liquid-case observation experiment

Freeze the previously input-selected sea column (71,101), native frame 20 s,
and its existing 39 layers. The candidate is the current opt-in dry-specific
number interpretation: `N=rho_d*n_d`, `C=rho_d*q_d`, unchanged volume-coordinate
10/10 cutoffs and unchanged source coefficients. Fixed forcing and an NC-only
direction imply `delta qv=delta rho_d=0`; this direction is compatible with the
observation bridge's fixed dry-air measure. No original threshold calibration
or general coupled qv Jacobian is inferred.

Use the retained 00:00 GK2A slot and its input-matched pixel. Record the 20 s
nominal model/observation offset and 0.674 km displacement. Geometry is modeled
from that pixel and the documented nominal orbit, not measured ephemeris.
Preserve the native center pressures, T/Q and hydrometeors. Source-backed
REAL(4) interface reconstruction is not raw P8W measurement. Above-top T/Q and
otherwise unavailable gas profiles are separately identified reference inputs.

Run the nine thermal channels (8–16), solar disabled, IREMIS sea emissivity,
same-case skin/near-surface inputs, BT-seeded K and stored radiance quality.
Keep the existing quality flags: observation quality and radiance quality must
both be zero. Zero accepted channels cannot validate a cost. Report the
unaltered Huber diagnostic with its explicitly declared scale; do not fit an
error model, masks or thresholds to the resulting residuals.

For `delta nc=0.01*nc`, compare the optical-map tangent/K contraction and VJP
with independent value-only endpoints at `h=1e-4`. Report channel differences,
vector max-norm relative discrepancy and output quantization. The bounded NC
diagnostic uses the existing 1e-5 FD relative criterion and a 1e-12 duality
criterion, requires a nonzero NC-to-BT tangent on radiance-supported channels and unchanged BASE/plus/minus
radiance quality. These numerical gates are frozen before the next BT/K
execution; they do not establish physical accuracy. Numerical failure
must remain failure. Return-branch evidence from NCCN does not certify optical
or microphysics branches.

Compare the same immutable inputs with the separate thermal DOM solver at
16, 32 and 64 streams. Report angular convergence and Delta-Eddington differences
for BT and the NC direction. Do not invent a radiative-accuracy threshold or
present shared optical-property tables as an independent physical model.
No full S11, forecast skill, parameter identification, cycling, deployment or
operational approval follows from this single conditional experiment.
