# Localized B512 ice-variant budget and first-order checks

This follows the [completed domain comparison](NATIVE_DOMAIN_ICE_FACTORIAL.md).
The source packet, 39 native levels and original B=512 blocks stay fixed. Two
blocks (34 and 40) are traced in `norm_actual` and `raw_actual`, using the same
frozen v6 experimental executable; every trace-on response matches the previous
trace-off response byte-for-byte. No whole-domain repeat or host integration
is performed. Measurements are in the
[report](../harness/evidence/localized_ice_budget_ad_2026-10-24/REPORT.md).

## Stage accounting

`analyze_localized_ice_stage.py` verifies the controller, packet, executable,
request/response echoes, source chunks and verified trace buffers. It requires
one subcycle and the captured native ordering: water stages bottom-first, ice
recurrence records top-first. Every observed DEN/DELZ agrees with the actual
request. Weighted changes use rounded binary64 `(q_after-q_before)*(DEN*DELZ)`
terms followed by `fsum`, with species/level order explicit. Inventories are
also displayed, but differences of large column inventories are not used to
compute small stage changes.

The main sedimentation state update changes QR/QS/QG; ice changes QI. QV/QC
remain bit-identical across the sedimentation transition in these four blocks.
`pre_sed`, `post_sed`, `post_micro`, the raw response and a separate offline
uniform interior cleanup distinguish their changes. The common surface record
contains total precipitation once; snow/ice and graupel are subsets. Actual
bottom ice departure uses applied outflow, not bottom net depletion. Both ice
bottom departure and its reported increment are zero in these blocks, so this
is not validation of a nonzero ice-ground conversion.

These observations localize the two selected residuals to the main QR state
change/surface accounting. They do not record main-rain internal departures and
arrivals, nor certify a closed physical budget. The fixed request measure is
not an RK mass measure or a map-area integral. Raw code-flux dimensions and
historical number units remain conditional.

## The differentiated operator

The isolated diagnostic C ABI library reuses the frozen v6 core archive and
an existing state+forcing bridge object. It is relinked into a new path; no
physics translation unit or operational install is rebuilt. Fresh processes
select `KDM6_ICE_FACTORIAL_MODE=norm_actual`, `physics_variant=0`,
`dry_number=0`, dt20, ncmin10/10. The full batch remains in every forward and
finite-difference trial. ABI dimensions **im=1, kme=39, jme=512** match each
C-order `(B,L)` field block; im=512/jme=1 would be a different packed layout.

`verify_localized_ice_ad.py` returns 17 field blocks:

- 12 **raw kernel state** outputs, including dry theta and raw number operands;
- the existing five thermo-finish outputs: `T_NEW_AFTER`, `H_RATE`, `QV_RATE`,
  `QC_RATE`, `TH_PHY_M_T0`.

It does not return a fully cleaned 12-field host state. The finish uses only
TH/QV/QC cleanup. Uniform cleanup of the other hydrometeors belongs to the
separate value ledger. No precipitation seed, surface-flux derivative, water
closure derivative, native prep/EOS/profile/RTTOV derivative or RK/memory
consumption derivative is added here. `H_RATE` is moist-theta memory K/s.

For raw kernel `y=K(s,F)`, thermo cleanup `z=Z_T(y_TH/QV/QC)`, and finish
`r=R(s_TH/QV/QC,z)`, the combined JVP is

\[
\delta y=K_s\delta s+K_F\delta F,\qquad
\delta r=R_s\delta s_T+R_zZ_y\delta y_T.
\]

The VJP sums the raw-state cotangent and cleanup/finish pullback before the
kernel VJP, then adds the finish's direct old-state cotangent. This retains
the subtraction term in `(q_new-q_old)/dt`; an identity-kernel test requires
zero tendency tangent and cancellation of old/new-state adjoints.

## Direction families and boundaries

The first `raw` sweep is preserved with failed gates. Its cloud-mass direction
varies QG with BG fixed; its number direction includes NN exactly at its lower
entry clamp. A centered FD can cross those clamps although JVP/VJP remain
transpose-consistent. An actual full-B512 one-sided probe confirms NN behavior:
at NN=1e8, JVP and inward FD equal the seed, outward FD is zero, central FD is
half. This is a selected clamp-side Jacobian, not a classical two-sided
Jacobian at the boundary.

A separately versioned `entry_interior_pairs` sweep keeps the **same base**:

- active QC/NC, QR/NR, QI/NI and QG/BG mass-direction components vary by matching
  fractional amounts, preserving entry moment ratios to rounding;
- the number-only direction still contains NC/NI/NR, while its NN support is
  restricted so the entire epsilon envelope stays strictly inside the entry
  `[1e8,2e10]` interval;
- T/Q, four independent forcing directions (DEN, PII, P, DELZ), and their mixed
  direction are also tested.

These are frozen, target-local test directions, not an operational control
transform or a proof that every downstream limiter stays interior. Paired QG/BG
can be tangent at density 900; a normal derivative there is not certified.
Returned NN at the floor alone cannot distinguish a tie from a deeply clipped
smooth plateau. Native base values are neither shifted nor relabeled as
physically qualified number concentrations.

Every direction must pass a full-array JVP/VJP dot check and a common epsilon
where **all 17 fields** meet their predefined FD tolerances and the explicit
thermo cleanup/heating masks are unchanged. The KDM's other internal limiter
and schedule signatures are not exhaustively captured. All failed epsilon
trials are retained. Off-target products are observed zeros for these vectors,
not a universal locality claim. First-order evidence does not certify HVPs,
identifiability, unrestricted raw-coordinate derivatives or forecast skill.

The numerical map and derivative evidence here are fp64 research calculations;
operational f32 rounding and Legacy parity are separate contracts. Archived
directions are replayed as stored, rather than requiring cross-platform
transcendental seed regeneration to be bit-identical.
