# S8 mp337 native forward ABI evidence — 2026-09-25

**Status: OPEN.** This report verifies the production mp337 host wrapper's current
value-only forward entry/return and captured prognostic copyback on the retained
5 km case. It does not demonstrate a host JVP/VJP, normalized host handle, fp64
DA behavior, or derivatives through the host wrapper.

## Scope and execution

The test used the retained full-domain LC05 5 km case under the isolated public
worktree's private host copy; the ABI logger captured one selected tile call.
All three final arms used the same `wrf.exe`
(`1b4184f7f19805b543d409b31ab5dc00b5417e0173164d7b59afb9eb783ada0b`): an
mp237 reference, mp337 capture-off control, and mp337 capture-on. Each ran with
one MPI rank, one thread, fixed `dt=20 s`, `--minutes 0 --seconds 20`,
`--history 0 --history-s 20`; each exited 0 and reached `SUCCESS COMPLETE WRF`.
Each history contains exactly `2025-07-19_00:00:00` and
`2025-07-19_00:00:20`. `run_ss_case.py` receipts mark the runs valid and record
the same executable hash before and after execution.

The retained input hashes were `wrfinput_d01`
`5a9ae8da992028dbf3a2a7652eb61532c1efab2acea7ea0e393e4cac8fd4c970`,
`wrfbdy_d01`
`d46e5d7117c076956d130b4ff905fc34a5d53dbd5a0d9571311582b0a60c5e6c`,
`wrfchainp_d01`
`c8e300d2aa52f98c9060803438ab6f796bddd1e1cdd6b75a14e39a398cb0c4e3`, and
`namelist.input`
`064b6f5ea5683ee3dc68d408c08bf4cbf588be06dbc7d99bb3529be8ba61554a`.
The three run IDs are:

| Arm | Run ID | Forecast SHA-256 |
| --- | --- | --- |
| mp237 reference | `mp237_s8_mp237_ref3_0min20s_hist0_20260925_231535_p28391` | `6f0bf483632ff7ca2f5d00745fe7325e7a386f5610531f40e1dd68cee785a059` |
| mp337 capture off | `mp337_s8_mp337_control3_0min20s_hist0_20260925_231633_p29284` | `14dbf6067f552c2e1fbda3d8317f1492eb61639657e5f304bde0457a7d6837d2` |
| mp337 capture on | `mp337_s8_mp337_capture3_0min20s_hist0_20260925_231740_p34969` | `14dbf6067f552c2e1fbda3d8317f1492eb61639657e5f304bde0457a7d6837d2` |

`strict_bitwise_nc.py` passed for frame 0 and frame 1 on both mp337 control vs
capture and mp237 reference vs mp337 control. Each comparison found 254 common
variables, with all 253 numeric variables and `Times` bit-identical (254/254).
This establishes instrumentation noninterference for the captured mp337 call
and same-executable forward parity against mp237 for this bounded case only.

## ABI boundary capture and replay

The corrected source generator verifies source SHA before patching and verifies
that stripping the instrumentation restores the original wrapper byte-for-byte.
The generated mp337 wrapper (`host/KIM-meso_v1.0/phys/module_mp_kdm6ad_cons.F`)
source SHA-256 is
`d6da161aa87de298c70a5ecf965a173d9215176b68362c66815bb31ef5425d00`; the
unmodified mp337 wrapper SHA-256 is
`940adce388dff58495710349a62a79dcc66506f3017cc089756d8f3992b7e9bb`. The
separate mp137 wrapper is `module_mp_kdm6ad.F` (SHA-256
`c56499524c73bec4e5092e7aecfde244d072f9572733708226c7f6d743cc9e67`);
it is not the mp337 capture target. The static regression asserts the entry
dump follows assignment of all `ARGS`
fields and immediately precedes `kdm6_step_v2_c(ARGS)`, while the return dump
follows the C call and `RC` assignment but precedes error handling and host
copyback. It also fixes the expected call count and field schema. The test is
`harness/tests/test_s8_abi_capture_source.py`.

The private raw capture SHA-256 is
`ac543e94c6c9b9e5b3a099f6854c487a300dc3d6e568c3b5948599454d7801a6` (211,804,960
bytes). Its lossless gzip scratch copy is SHA-256
`30b8be6e4d1e19d3517ec05cd5984e81b6b0d65e956bd7192f098cf6bedbccdb` (59,248,645
bytes); both files remain only in ignored `graphify-out/s8_native/`. A zstd-19
trial was 57,359,361 bytes (SHA-256
`e946da40e81d211717fa3c71e20a4c43134b86d399658aab77c69e49eb589833`), about
1.9 MB smaller, so the local replay path uses gzip and Python's standard
library. Neither private capture representation is checked into the public
repository.

The local replayer validates compressed and decoded hashes/lengths, exactly
one call, dimensions `(232,39,139)`, 17 input, 16 C-return, and 13 host-copyback
f32 fields with expected byte lengths, ABI version 2, struct size 336, `dt=20`,
and variant/value-only metadata. The local replay with isolated library SHA
`a843ab775e53ebf61c38549dd5f32223d8e180ebefc07025b1cbad48df5935ff` returned
**RECORDED / LOCAL_VERIFIED**: one call, ABI v2/336, `(im,kme,jme)=(232,39,139)`,
`dt=20`, variant 1, `value_only=1`, `RC=0`, null handle before and after, exact
C-return replay and prognostic copyback. No handle is created and no host
derivative call is made. The run ID, forecast hash, and saved times are
provenance annotations derived from the private run receipts; those receipts
and arrays are not checked in, and the replayer does not cryptographically
authenticate the private host run.

The public repository contains only a 280-byte synthetic ABI framing fixture
with zero-filled array payloads at `harness/tests/fixtures/s8_synthetic_v2_capture.bin` (SHA-256
`9c4f2d9761d846351c8ec3ba89284b0cf31bb2b5ac26e39ce8e4b6ac9252c09a`). Its
metadata describes a toy `(1,1,1)` record; it contains no retained-case state.
The `.gitignore` exception applies only to this exact fixture path; captures
and other binary run outputs remain ignored.
Public tests use it to exercise framing, schema, truncation, duplicate,
relocation, altered-hash/metadata, and replay/copyback mismatch handling with a
stub C function. These tests do not reproduce the private native arithmetic
replay. The private receipt is
`harness/evidence/s8_private_replay_receipt_2026-09-25.json`; it records hashes
and pass results only, without private arrays. The public variant-1 f32
JVP/VJP/FD tests remain a separate synthetic/unit evidence stream.

Validation: the focused public tests pass 15/15, Ruff, `py_compile`, and
`git diff --check` pass. The actual private capture replayer was run locally
against the ignored gzip scratch and isolated C library; no host executable was
rebuilt or rerun for this packaging change.

## Invalid attempts and setup failure

Two earlier capture attempts are excluded from S8 evidence. Attempt 1 used
shadow source SHA `41657f2c6fa373285a546810be4a43b4cb1e737eee19b29eeee3437856429abd`
and executable SHA
`0932e544d755d6b0d861c364afd9ed3b235739a21b38139ada8bddbfd51f3c9c`; its entry
capture ran before the `ARGS` fields were assigned (`mp337_s8_mp337_capture_0min20s_hist0_20260925_224037_p75446`). Its raw
capture was overwritten by the later attempt before its SHA was saved, so no
raw capture hash is available for attempt 1. Attempt 2 used shadow source
SHA `472c5194c6a2e86e609ee9bd011cf3343b361ff9f93ea715294a1211bdbc0680` and
executable SHA
`765194825076370c8ae7e1692ac6a06f677ff47bdba9d9b0b120b3228cef6eb3`; its
return capture ran before the C call, so replay and copyback comparisons failed.
The attempt-2 raw capture SHA was
`fcdeab5917ccd2d4e1cb85f9932028dc658aa98577ad5a3e592fac26b982b0f8`.
Its run ID was `mp337_s8_mp337_capture2_0min20s_hist0_20260925_225831_p7281`.
Those attempts' runs and captures are not used in any pass claim. An initial
isolated link also failed with `ld: library 'System' not found`; this was a
pre-run setup failure, corrected by setting `SDKROOT` to
`/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX27.0.sdk`.
It is not a host-run result.

## Source/build provenance and remaining gate

The public C API source SHA is
`aed7e621260c955592cd9744ee8c91ad138fe39630987b13c94334a0cddc0cdc`; public
runtime and coordinator source hashes are
`6e6bb4a46f06defd0ec4f5505f44067a933d51abb1480a0a16aaff3bb3e339bc` and
`1832399675f5026ae8342ea61826d8b9ce8978bbcad63d95e0c2c9ef94316399`.
`libtorch/CMakeLists.txt` has SHA-256
`1944b92371b7df4c57cd587dafc2512184063f014bf2d1db81cf0cad044394a0` and
specifies C++17 with `-ffp-contract=off`. The tracked Fortran ISO C shim SHA is
`b70125eb5f28ab3644a0ba30c8dc9388b8245075b93006f0cc4fbc7dc7bf43a7`. The
private mp337 `module_mp_kdm6ad_cons.F` wrapper, microphysics driver,
Registry and physics Makefile hashes are
`940adce388dff58495710349a62a79dcc66506f3017cc089756d8f3992b7e9bb`,
`94db84c45b7422b62e04967cb3cd1362311abdb02fa3d374d881799c0bce7e84`,
`fd6f0413d2cb7f6d6fce48c05cc765295ad2628175d0b46628b2a3d8d3134a95`, and
`e9e1d95afccf0aa5c88668adb5b43ca835aada3eaaae1cd97f8f628bb6482893`,
respectively. The corrected capture module object linked into the isolated
archive has SHA-256
`5df10dc7a9f0fd0aa9bd55dfb3fd4838757b6155656f8ba2e3b1d9b6403aa862`.
The private host sources were in an isolated clone; the canonical private host
tree was not modified. The build used Xcode 27.0 (build `27A266a`), macOS SDK
27.0, GNU Fortran 15.2.0 and Homebrew clang 22.1.4. Compiler executable hashes
are clang `1590ac950a3d627817d09ade5cb60b2115f17a72182a3141e010b4bcc482a0c9`
and gfortran `0019c2383f399c1ba6aed1dc060191e793caf963c1066d254194883581098bb2`.
`SDKROOT` was
`/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX27.0.sdk`;
the WRF core build flags selected EM only (`WRF_EM_CORE=1`, other core flags
zero), and `apply_kdm6ad_config.sh` wired the isolated prefix before building.
The WRF executable linked the isolated `libkdm6_c` and Torch runtime, and
`otool -L` confirmed those loader paths. The public worktree was based on
`3781084c07654d8187c77e1966f8b966fbc5eb61` when the evidence was recorded;
the linked WRF `commit_version` was `ae2b4163ad8272d9dcc21c5c36853c19646bf775`.
The worktree rebase happened after the isolated host build; the exact linked C,
Fortran shim, wrapper, driver, Registry, Makefile, executable, and library
contents are therefore pinned by the hashes above rather than inferred from
the later branch HEAD.

The public variant-1 f32 handle tests from the S8 public ABI change establish
bounded live-handle JVP/VJP behavior, state-direction FD and duality evidence.
This native test establishes only the production value-only wrapper boundary.
The production caller still requests `value_only=1` and receives a null handle;
normalized `value_only=0` host lifecycle/derivative routing, full actual host
state-direction JVP/VJP and FD, branch/threshold behavior through the host, and
fp64 normalized DA remain unverified. The mstep schedule and its threshold
directions also remain unverified. S8 therefore remains OPEN.
