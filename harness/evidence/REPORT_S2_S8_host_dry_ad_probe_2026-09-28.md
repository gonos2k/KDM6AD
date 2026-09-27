# S2/S8 selected mp337 dry-number fp64 AD probe

The [dry-number fp64 AD ABI](REPORT_S2_fp64_ad_dry_number_2026-09-28.md)
previously had only synthetic C/Fortran coverage. The additive
[`s2_fp64_host_dry_probe.patch`](../s2_fp64_host_dry_probe.patch) connects it
to the selected private mp337 host column without changing its value-only
forecast call. Apply the existing `s8_fp64_host_probe.patch`, then
`g33_fortran/s2_mp337_dry_number_optin.patch`, then this patch to a clean copy
of the canonical private `phys/` sources. This order is required: the inverse
order moves a function boundary and fails Fortran syntax, and the final patch
rejects that inverse composition. The ordered chain applied exactly and the
ISO mirror passed `gfortran -ffree-form -fsyntax-only`.

With `KDM6_S2_DRY_NUMBER=1` held fixed, the new branch calls
`kdm6_step_ad_number(..., physics_variant=1, dry_number=1)` only when the
existing exact-`1` S8 probe gate is enabled. Its one-column fp64 direction
contains entry `qi` plus 1% of entry `qv` and `nc`; it checks finite/nonzero
JVP and VJP norms and the `u=Jv` dual product. The normal f32 value-only
forecast output is not replaced by the probe output.

The isolated build used patched ISO/wrapper source SHA-256
`61eb023635e6792b4f92ec7a47115df8f0c46680babad2655db0ed4fde159933`
and `8bb3a706c72362f87a2e97786385b72c1b3dd44ff06bacc75050855c4fdd9258`.
Fresh objects precede the unchanged host archive in the link map. The
experimental executable SHA-256 is
`357ab81fe710b62deb4643bc255d63554ad6db8f100455b7dfea15dfcef42d62`;
its linked library SHA-256 is
`7a567013334c392555cc6d80bb720a1098bb138f56d99e9a0e9fbf6a1da16d1c`,
with the new AD-number symbol exported. The retained input identities and
actual preprocess/compile/link/run commands are pinned in a private local
receipt with SHA-256
`9f90c8290c136a781193785957150370c6f79f55ef496c37b3a38290e27238b4`.
Canonical private sources and operational installs were unchanged.

Two one-rank/one-thread 20-second runs used this **same executable** and saved
0/20-second frames. With S8 probe off there were no probe rows; with it on
there was exactly one `S2S8HAD_v1` row at global `(200,152)`. Its seven
reported norm/dot values were finite and nonzero, with relative duality
`2.4610124430467514e-16`. The off/on forecasts matched raw-bit for all
254 common variables at both frames, including `Times`, and shared forecast
SHA-256 `a218b7d756d32cd8c9f671e66fdec416ac55e4f4f39ba43dd9dd35984573e824`.

This measures one staged fp64 ABI step and its mixed direction. It does not
measure a pure number direction, independent native finite difference, or
the derivative of Fortran's timestep-one `NN` profile initialization. The
physical number thresholds and empirical coefficients, general host DA
routing, whole-host nonnegativity, RTTOV accuracy and accepted observations
remain open. No operational default or deployment changed.
