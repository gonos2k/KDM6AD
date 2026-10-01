# S8 same-candidate column entrypoint

The external-path [column command](../../docs/NORMALIZED_DRY_COLUMN.md) now uses
one fixed selector-2/dry-number-1 fp64 map for graph forward, value-only forward,
JVP, VJP and independent centered differences. It saves inputs, XLAND, all
outputs, directions and both difference endpoints. The legacy case runner is
unchanged; no release or observation approval is added.

The retained selector-2/dry-number-1 5 km history at 20 s supplied the input.
Before inspecting operator outputs, columns were filtered for the command's
nonnegative/defined moment-pair domain, then selected by largest input `qi` sum.
There were 26,118 eligible columns; zero-based `(i,j)=(3,272)` was selected, with
39 native levels and XLAND=1. Native layers were preserved. The existing frame
reader's temperature, density and geometry reconstruction makes this an offline
snapshot call, not the host's exact staged microphysics input.

The library was freshly built from `fb42798` C++ sources using Release CMake,
AppleClang 21 and the local libtorch/PyTorch 2.13 installation, retaining
`-ffp-contract=off`. Its focused C ABI test passed. Runner and library core
sources at runner commit `8efff854` differ from that base only in the new user
entrypoint/docs/tests, with no `libtorch/` source changes. The saved
[result](normalized_dry_column_run_2026-10-01.json) pins the runner, input and
library hashes and reports `source_dirty=false`.

Two separate clean executions, including one from a detached checkout at that
commit, produced identical raw bytes for all 14 saved NPZ arrays and identical
JSON metadata. Both exited **1 / NUMERICAL_CHECK_FAILED**:

| Check | Result |
| --- | --- |
| Same-map graph/value-only forward | Raw-bit equal |
| Mixed-direction JVP/VJP | Finite/nonzero; relative duality 1.7898345673e-16 |
| Independent FD | Fails `nccn`; remaining field errors are at most 5.59e-8 relative, including two exact-zero fields |

At native level 10 (zero-based), `nccn` input, baseline and plus endpoint are
`0x1.445c8a0000000p+31`; the minus endpoint is one double ULP lower,
`0x1.445c89fffffffp+31`. JVP there is zero and the FD is 0.002384185791015625.
The local endpoint-spacing estimate divided by the difference width is
0.00476837158203125. This is consistent with an output-resolution limitation;
it is not a certified evaluation-error bound and does not relax the FD gate.
An independent scalar replay of `rho_d=rho/(1+qv±h*v_qv)` followed by
`(nccn*rho_d)/rho_d` reproduces both endpoint words at this selected level.
Thus the dry-number boundary roundtrip alone reproduces this local witness;
the entire operator's branch/derivative contract remains unverified.
The original failure remains preserved. No branch-certified FD or entire
Jacobian identity is claimed.

S8 remains OPEN for general DA routing, the full same-candidate derivative gate,
physical number/threshold policy and accepted observations. This evidence does
not replace the separate selector-1 in-host probe with selector-2 native AD.
