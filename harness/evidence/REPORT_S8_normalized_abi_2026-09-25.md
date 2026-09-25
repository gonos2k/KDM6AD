# S8: normalized AD ABI preparation and native-forward plan

## Public ABI result

S8 remains **OPEN**. Public tests now exercise the conservative-interface v2
ABI's f32 graph and its Fortran ISO_C_BINDING mirror; no native mp337 case has
been run for this work.

On source base `e21ce235a83bf3c539e966ac4e3405d459b60ff0` (PR #271 merge; S14
closed in the checklist without changing these C++/Fortran ABI sources), the
`kdm6_step_v2_c` path accepts `physics_variant=KDM6_PHYSICS_CONSERVATIVE_INTERFACE`
and `value_only=0`, marks the 12 prognostic state fields as graph inputs, and
returns a live Float handle. The packed JVP/VJP routines transfer doubles at the
ABI boundary but cast directions/seeds to the handle's f32 dtype; this is
operational f32 derivative evidence, not fp64 DA evidence. `kdm6_step_ad_c`
remains a distinct fp64 Legacy entry and is not used by these tests. The
normalized Fortran host wrapper `module_mp_kdm6ad_cons.F` still calls v2 with
`value_only=1`, `physics_variant=1`; that host call returns no graph handle.

The C++ public ABI test in
[`test_conservative_interface.cpp`](../../libtorch/tests/test_conservative_interface.cpp)
uses a four-level mixed-ice fixture. It verifies bitwise forward equality
between `value_only=0` and `value_only=1`, nonzero packed JVP/VJP for qi/ni
directions, their dual identity, a centered value-only FD of a mass/energy
functional, and handle close/null behavior. The tested qi/ni directions affect
the DSD size/velocity path. Its direct slope signatures remain on the same
inactive/min/max limiter branch for each FD pair. A separate value-only case
brackets the executed `qi <= EPS` inactive branch; it makes no derivative claim
across the threshold. The test does not instrument or assert the runtime's
discrete `mstep` schedule.

At the selected f32 FD steps `eps = 0.5, 0.1, 0.02`, relative errors were
`1.245e-3`, `3.790e-2`, and `2.746e-1`. Smaller perturbations become dominated
by f32 rounding. The coarsest tested step is the best match for this fixture;
this is a fixture-specific finite-difference result, not a universal error
bound.

[`test_fortran_normalized_ad.f90`](../../libtorch/tests/test_fortran_normalized_ad.f90)
calls the same normalized v2 entry through the checked `bind(C)` struct. It
checks the live handle, packed qi/ni JVP/VJP duality, pointer-nulling close,
value-only null handle, and identical graph/value-only forward arrays. It does
not repeat the FD or threshold tests; those are in the C++ test.

## Build and test receipt

Build tree: `/tmp/kdm6ad-s8-build`; source worktree: `/tmp/KDM6AD-k-s8`;
compiler: AppleClang 21.0.0 and GNU Fortran 15.2.0; LibTorch came from the
configured Miniforge Python 3.9 installation. CMake used `Release` and
`-DKDM6_SUBSTEP_DUMP`; test targets retain assertions through `-UNDEBUG`.
Execution pinned OpenMP/MKL to one thread.

The following focused CTest targets pass on the rebased source (4/4, 3.59 s):

- `c_abi`
- `conservative_interface`
- `fortran_smoke`
- `fortran_normalized_ad`

Command: `OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_THREAD_LIMIT=1 ctest --test-dir /tmp/kdm6ad-s8-build -R '^(c_abi|conservative_interface|fortran_smoke|fortran_normalized_ad)$' --output-on-failure`.

The test build printed a missing optional `kineto_LIBRARY` warning from the
installed Torch package; both targets built and passed. No Python files changed,
so Ruff does not apply. The test evidence is public synthetic-fixture evidence;
it does not establish host dispatch, native boundary return values, number-unit
validity, physical accuracy, control gradients, mstep threshold behavior, or
fp64 normalized AD.

## Prepared native mp337 forward control/capture

This plan is **not executed**. S10 currently owns the native slot; wait for its
explicit release and root scheduling before any build or run.

The fixed canonical input is the retained LC05 SS case at
`host/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS`. The inventory report
identifies its `wrfinput_d01` SHA-256 as
`5a9ae8da992028dbf3a2a7652eb61532c1efab2acea7ea0e393e4cac8fd4c970` and paired
`wrfbdy_d01` as
`d46e5d7117c076956d130b4ff905fc34a5d53dbd5a0d9571311582b0a60c5e6c`.
These are the existing 2025-07-19 00 UTC, 5 km, 234×282×39 inputs described in
[`REPORT_retained_input_inventory_2026-09-25.md`](REPORT_retained_input_inventory_2026-09-25.md).
No alternate initialization or remapped grid is part of this test.

The active local host wrapper is
`host/KIM-meso_v1.0/phys/module_mp_kdm6ad_cons.F` (SHA-256
`940adce388dff58495710349a62a79dcc66506f3017cc089756d8f3992b7e9bb`); its
call uses v2, `physics_variant=1`, `value_only=1`, and closes the expected null
handle. Its Fortran mirror is
`host/KIM-meso_v1.0/phys/kdm6_iso_c.F` (SHA-256
`0aef23e61cd0e1a31eda0d9213f48c838a119f0c8e0de6dcf1e8da76af6b55b3`). The
host Makefile compiles the `.F` wrapper with `-ffp-contract=off`. Before the
run, rebuild/install `libkdm6_c` from the intended public source and verify the
installed library and `wrf.exe` link identity; the current local installed
dylib and executable hashes are inventory only and do not certify their source
chain.

The following hashes are an inventory for planning, not an executed build
receipt. The installed library and executable must be rebuilt or otherwise
authenticated before they can support an S8 claim.

| Input/source/artifact | SHA-256 |
| --- | --- |
| Public `libtorch/bridge/kdm6_c_api.cpp` at the source base above | `4d5fa1b59ebfce74ea1ee564f7aae972ec00c6e2f209a18e8317c7fa132cc8b3` |
| Public `libtorch/bridge/kdm6_c_api.h` | `de10863f16ebd8ddb4a24e21abca105beaa6b493567080ebd72915616a4c9403` |
| Public `libtorch/bridge/kdm6_iso_c.f90` | `b70125eb5f28ab3644a0ba30c8dc9388b8245075b93006f0cc4fbc7dc7bf43a7` |
| Private `module_mp_kdm6ad_cons.F` | `940adce388dff58495710349a62a79dcc66506f3017cc089756d8f3992b7e9bb` |
| Private `kdm6_iso_c.F` | `0aef23e61cd0e1a31eda0d9213f48c838a119f0c8e0de6dcf1e8da76af6b55b3` |
| Private `phys/Makefile` | `e9e1d95afccf0aa5c88668adb5b43ca835aada3eaaae1cd97f8f628bb6482893` |
| Private `module_microphysics_driver.F` | `94db84c45b7422b62e04967cb3cd1362311abdb02fa3d374d881799c0bce7e84` |
| Private `Registry.EM` | `fd6f0413d2cb7f6d6fce48c05cc765295ad2628175d0b46628b2a3d8d3134a95` |
| Retained `wrfinput_d01` | `5a9ae8da992028dbf3a2a7652eb61532c1efab2acea7ea0e393e4cac8fd4c970` |
| Retained `wrfbdy_d01` | `d46e5d7117c076956d130b4ff905fc34a5d53dbd5a0d9571311582b0a60c5e6c` |
| Retained `wrfchainp_d01` | `c8e300d2aa52f98c9060803438ab6f796bddd1e1cdd6b75a14e39a398cb0c4e3` |
| Current case `namelist.input` | `064b6f5ea5683ee3dc68d408c08bf4cbf588be06dbc7d99bb3529be8ba61554a` |
| Current case `wrf.exe` (not source-chain certified) | `676223e8d61d23456d4ac83713bff0283ea08b1e71776b7f8885b062d97f801b` |
| Current installed `libkdm6_c.dylib` (not source-chain certified) | `7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7` |

After S10 releases the slot, build a capture-capable shadow of the exact
wrapper, with a macro-guarded boundary logger and a runtime environment gate.
Verify that stripping the capture block reproduces the active wrapper
byte-for-byte. Do not edit the active private host sources. Then run
sequentially at np=1/thread=1 from the retained case with 20 s duration,
`--history 0`, and the existing `history_interval_s=20` setting:

1. `mp237` one-step reference.
2. `mp337` capture-capable binary with capture disabled (control arm).
3. The same `mp337` binary and build with capture enabled (capture arm).

The runner invocations are the matched forms
`python3 harness/run_ss_case.py --case host/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS --mp 237 --minutes 0 --seconds 20 --history 0 --history-s 20 --np 1 --label s8_ref`
and the same command with `--mp 337` and distinct control/capture labels. The
current retained namelist has `history_interval=60` and
`history_interval_s=0`, so pass the two keys explicitly and separately to
select 20-second output. Run these serially through the runner's case lock.

The capture record should include call count, ABI version/struct size, dimensions,
dt, selector, `value_only`, pre-call null handle, `RC`, post-call handle state,
hashes of all staged state/forcing arrays, all 12 C++ output arrays, and the
optional rain/snow/graupel increments plus `rhog_out`. At the host copy-back
boundary, hash the corresponding prognostic arrays and require raw-bit equality
with the C++ output buffers. Keep the capture disabled for the control arm in
the same capture-capable executable, then compare control and capture NetCDF
history bytes to establish instrumentation noninterference.

For each completed run, use `harness/run_ss_case.py` and its run verifier; check
the actual saved `Times` entries, expected to include the initial and 20 s
frames. Compare mp237↔mp337 and mp337 control↔capture with
`harness/strict_bitwise_nc.py` over all common numeric fields and `Times`.
Record the wrapper, ISO shim, Makefile, Registry, driver, C++ source, installed
dylib, executable, namelist, and input hashes with the run receipt. A successful
process exit alone is not a pass. This short case tests forward entry/return;
it does not exercise a derivative handle in the host wrapper.

The public source graph was refreshed after code edits and its affected-path
query links the new test to `main()`. The cached graph did not provide a complete
ABI-to-private-host dependency lineage. Full LLM document extraction was
unavailable, so the Graphify semantic fallback saved a focused S8 Q&A in the
local derived `graphify-out/memory/` store and linked it to the v2, JVP, VJP and
ISO_C_BINDING graph nodes. That derived memory is excluded from the source PR;
this report contains the reviewable evidence. The source references and private
hashes above were checked directly. S8 remains OPEN until the native host
evidence and remaining derivative-path criteria are reviewed.
