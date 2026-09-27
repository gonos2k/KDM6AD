# S2 opt-in C++ dry-number operator

The [Python oracle reference](REPORT_S2_oracle_dry_number_2026-09-28.md)
converts host dry-specific QN fields to volume number inside one KDM6 step.
The C++ core now has a separate `dry_number` overload for the same declared
representation. Existing C++ overloads, `PhysicsOptions` layout and C ABI
entry points retain their signatures and default calculation.

For positive entry density, the opt-in path computes
`rho_d = rho_m / (1 + qv_entry)` as a live tensor. It converts `nccn`, `nc`,
`ni` and `nr` to volume number before the coordinator and divides the four
outputs by the same entry density afterward. `CoordinatorForcing.den` stays
moist for air properties; `dend` carries dry density for paired DSD moments,
q/bg sedimentation, q-specific rates and number-source conversion. Melting
and contact freezing keep separate moist-air and mass-moment density inputs.
The existing numeric number thresholds are treated as volume concentrations.

The new direct C++ test uses the same three-level synthetic input as the
oracle test. Its rain-number outputs agree with the pinned oracle values
within `1e-4` relative; JVPs of all four number outputs agree with independent
central differences within `1e-5` of the derivative scale (with unit floor). A basic
conservative-interface combination produced finite outputs; its full
conservation and AD behavior are not established by that check. The existing
`kdm6_fn` options overload and its explicit-false overload produced exactly
the same 12 output fields in the test.
Six focused CTests passed: `dry_number`, `melt_freeze`, `coordinator`,
`autograd_endtoend`, `conservative_interface` and `c_abi`.

The G33 diagnostic overlays for `runtime.cpp` and `coordinator.cpp` were
re-derived against the changed canonical sources. Their source hashes were
repinned only after the overlay verifier established macro-OFF textual
identity, macro-ON in-order source inclusion, and no textual production-value
mutation finding. The related focused harness tests passed (**251 passed**).
These are static overlay checks; no new instrumented A/B run is claimed.

The isolated local build used the repository CI's
`-DKDM6_SUBSTEP_DUMP` compile definition. A first build without that flag
stopped at the pre-existing `kdm6_dump_on` reference in `coordinator.cpp`,
whose declaration is guarded by that macro. This is a build-configuration
limitation, not evidence about the new S2 arithmetic.

The C ABI has no S2 unit selector and the private mp137 caller still copies
host QN fields directly. It also initializes the timestep-one CCN profile in
volume units, so that caller must adapt the profile before using this new
boundary. No new mp137 host trajectory, full C++/oracle field parity,
threshold calibration, density-forcing derivative, physical accuracy or
observation acceptance is claimed. S2 and default-path approval remain OPEN;
no deployment work is part of this change.
