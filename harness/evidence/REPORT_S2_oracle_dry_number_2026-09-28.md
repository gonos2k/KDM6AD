# S2 opt-in dry-number Python oracle

The [native mp37 experiment](REPORT_S2_dry_number_optin_2026-09-28.md) converts
host QN values from number per kg dry air to volume concentration at the
microphysics boundary. This change adds the same *declared representation* to
the Python oracle with `dry_number=True`. The default remains unchanged.

For positive entry density, the oracle computes
`rho_d = rho_m / (1 + qv_entry)`, converts all four input QN fields to volume
number, and converts the four outputs back with the same entry `rho_d`.
The conversion is in the Torch graph, so a qv perturbation also changes the
number conversion. The first-step CCN profile must already be in the host's
dry-specific units when passed to this entry point; this one-step oracle does
not implement the host's timestep-one profile initializer.

The existing coordinator `dend` field carries dry density for mass/number
moments and q/bg sedimentation in this opt-in path. `den` remains moist density
for fall-speed factors, viscosity, thermal conductivity, and vapor diffusion.
Melting and contact freezing now receive both densities where one function
uses both roles. With `dry_number=False`, `dend` and `den` are the same input
tensor as before. Number threshold and cap numeric values are treated as
volume concentrations, matching the stated assumption of the mp37 experiment.

Focused validation: the new three-level liquid-column test compares qv
directional JVPs of all four number outputs from the public handle with
independent central differences through the full one-step oracle. It also rejects invalid dry density and use
of the old moist-density water-budget ledger or unlabelled internal-number
diagnostic trace with this variant. The new test
and the directly affected runtime, coordinator, melt/freezing, handle and
parameter tests passed together: **101 passed**. These are synthetic oracle
checks, not additional native meteorological cases.
For one three-level synthetic state, the default output arrays before and
after this change had the same raw-byte SHA-256
`4bc8c4687dca927d07ccde16f32d4efe04223cdd661b3e4cc69812672212dd7d`.

This is an oracle reference slice. The C++/ABI and private mp137 caller do not
select this representation yet; no cross-tree equality, in-host AD, physical
coefficient calibration, full water budget, RTTOV or accepted observation
result follows. S2 and the operational/default-path decision remain OPEN.
