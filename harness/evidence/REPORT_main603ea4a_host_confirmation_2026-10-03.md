# Exact `603ea4a` private-host confirmation

The exact merged source was freshly built and linked into the existing isolated
mp337 wrapper. Two 40 s normal forecasts completed with selector 2, dry-number
1, one local MPI rank on en0 and all thread limits 1. The existing fp64 AD/FD
probe was disabled in both. Only the existing read-only S1 tile logger changed
between OFF and ON; no new instrumentation or solver was added.

OFF/ON files are byte-identical to each other and to the archived N5.3 candidate
forecast: SHA-256 `be0edb894d1ddc5996f925cf01d56d1d882b53d6ed0295566edac2cb60f31308`.
All 253 numeric variables and `Times` match at actual saved 0/20/40 s frames.
Energy output files also match. The ON logger reports both tiles at both calls.

The [compact receipt](main603ea4a_host_confirmation_2026-10-03.json) records
source, fresh library, wrapper/ISO objects, executable and run configuration.
The installed library SHA-256 is
`b1ffad40b1b14d356744069cecfb976d18c51062cb74f046ec7d1704156f7172`;
the executable is
`a1a0c4b394e8141ea65b23da4d47cc8fde927115cb4667ecf1a4f8e567cabefa`.
Its first rpath resolves the dependency into the isolated fresh prefix. No
operational library or executable was replaced. Existing non-wrapper host
objects/archives were reused; this is not a complete host rebuild or historical
source-pin certification. One link attempt failed without the saved SDKROOT;
the recorded successful link includes that environment.

Tracked libtorch build inputs equal commit
`603ea4a681faf3822915cbf4f9f6f2c61cd758cf`. An untracked follow-up checklist was
present outside libtorch and was not consumed by CMake. The receipt does not
call the entire working directory clean. The full private receipt is retained
as `host_confirmation_603ea4a_2026-10-03.json`, SHA-256
`53e61f522400566956938e5b0302f63408553a5b9895fccf1e1efac665e11435`.

This closes the requested exact-main link/normal-forecast lineage check. It is
not a new native fp64 derivative experiment: with the probe disabled, the
forecast runs the f32 path. Previous supported-state fp64 directions, masks and
C ABI replay remain separately attributed evidence. No number-unit/calibration,
RTTOV, observation, MPI decomposition, restart or operational approval follows.
NCCN arithmetic stays frozen. Scientific work now proceeds through S2 before
size/optics and S11; release/deployment remain deferred.
