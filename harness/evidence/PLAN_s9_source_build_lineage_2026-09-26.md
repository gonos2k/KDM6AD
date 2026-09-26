# S9 source-to-build lineage contract and bounded control plan

## Status

This is a prospective evidence contract. It does not change the historical
Gate A pin, approve the `rhox` edit, or certify any host artifact. No build,
link, or model process was run for this plan.

The accompanying
[`s9_source_build_manifest.schema.json`](s9_source_build_manifest.schema.json)
defines the minimum machine-readable record. JSON Schema checks record shape;
[`verify_s9_source_build_manifest.py`](../verify_s9_source_build_manifest.py)
adds semantic and byte checks. It requires exactly the six relation types,
rejects duplicate edges and unknown or path/hash-mismatched artifact references,
binds each edge to exactly one correctly typed build step and retained stdout or
stderr receipt, checks all six KDM6 Fortran object paths, all fourteen CMake
core C++ translation units, both static archive member sets, and the bridge
object's separate shared-library link. It parses loader-capture content and
checks the pinned collector and `mpirun -n 1 <wrf.exe>` allowlist.
Run it as `python harness/verify_s9_source_build_manifest.py MANIFEST.json
--root BUILD_ROOT` with the `jsonschema` Python package installed. It hashes the
recorded artifacts and extracts members from both `libwrflib.a` and
`libkdm6.a` for byte comparison. Because this checkout has no independent
signed loader-execution attestation, a complete graph remains
`unverified_loader`; the verifier rejects `lineage_gate.status: proven` even
when a local receipt claims runtime resolution. File mtimes remain chronology
only, never proof of origin.

## Current evidence and exact build graph

PR [#270](https://github.com/gonos2k/KDM6AD/pull/270) merged the 2026-09-25
read-only census. It establishes the following current identities in the
canonical private tree, without tying them to one another through build
receipts:

| Node | SHA-256 | mtime (JST) | What the evidence says |
| --- | --- | --- | --- |
| Active `phys/module_mp_kdm6.F` | `fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5` | Sep 5 18:34:23 | Current bytes; the historical pin differs by the one deleted `rhox(i,k) = max(rhox(i,k),0.0)` read. |
| Active `phys/module_mp_kdm6_cons.F` | `4f0103c8a8321b8e854d3500f4ae567755e41eb78746fac54519eca2686a6648` | Sep 5 19:11:51 | Current source witness; historical Gate A report separately records `364a1319…`. |
| `phys/module_mp_kdm6.o` | `9c103f267d61582c45a9d7e2dfd6753a3c0d2d165bf47c241f7c4729eca90721` | Aug 23 00:18:32 | Predates its active source by mtime. |
| `phys/module_mp_kdm6_cons.o` | `415799b05c05133f08cd2ae13c9e199c31138145b927e0b77ef6cf894ec0bcf1` | Jul 17 21:57:07 | Predates its active source by mtime. |
| `phys/module_mp_kdm6ad.o` | `2cd5f0ba4bd0887e3efe85a04f75e064ed44248d50a1cb31a17a14fc50718ee1` | Aug 23 00:18:34 | Listed wrapper object; its input/source lineage has no retained compile receipt. |
| `phys/module_mp_kdm6ad_cons.o` | `144b09a86e07b4de3fd89f638eaa0d39a01fc0e0799aae343d44f761959cd13f` | Jul 17 21:57:08 | Listed wrapper object; its input/source lineage has no retained compile receipt. |
| `phys/kdm6_iso_c.o` | `a3273b3a929bd5e79e33450ae37f5414fc65961bb178f2cec184e062cfa6049f` | Jul 17 19:25:45 | Listed ABI shim object; its input/source lineage has no retained compile receipt. |
| `phys/module_microphysics_driver.o` | `a89608fd8dcda6bbb71713efdd9da9e5eeec1585bb3cc1b08161c80e171a081e` | Aug 23 00:18:35 | Listed dispatch object; its input/source lineage has no retained compile receipt. |
| `main/libwrflib.a` | `722f83c058ea1c43d5f23cc497aed1b218f33f90828a0e1dc51c6fe30203deba` | Aug 23 00:21:51 | Contains the same bytes as the two listed stale scheme objects and the listed KDM6AD bridge/driver objects. |
| `main/wrf.exe` | `676223e8d61d23456d4ac83713bff0283ea08b1e71776b7f8885b062d97f801b` | Aug 23 00:21:51 | Predates both active scheme source files. `run/wrf.exe` and `test/em_real/wrf.exe` are symlinks to this file. |
| `libtorch/build/libkdm6.a` | `22015aba2e2eab4e6ccca8610a317caf2eebf8374abab64314d51bde62bad56c` | Jul 17 23:42:01 | CMake static core archive; its fourteen named members each match the corresponding `CMakeFiles/kdm6.dir/src/*.cpp.o` bytes. |
| `libtorch/install/lib/libkdm6.a` | `4f083272ea3efb7a4f2cbfccbba94463f232117b3d9529bc6a73b13038a40409` | Jul 17 23:44:04 | Installed static archive; the same fourteen members match those build object bytes. The whole-archive hash differs from the build archive; no install receipt is retained. |
| `libtorch/build/libkdm6_c.2.0.0.dylib` | `82c9fffe18c1fcbcb41aeec85b5430ce103b57b285089953ecdea7341dc1103e` | Jul 17 23:42:16 | Build-tree library bytes. |
| `libtorch/install/lib/libkdm6_c.2.0.0.dylib` | `7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7` | Jul 17 23:44:04 | Installed bytes differ from the build-tree hash; no install receipt explains the difference. |

All six listed objects predate the active scheme source witnesses by mtime;
only `module_mp_kdm6.o` and `module_mp_kdm6_cons.o` are directly paired with
those two dated scheme sources here. The archive member hashes independently
match their corresponding listed `phys/*.o` hashes for all six objects.
This identifies which object bytes are in the present archive; it does not
identify which source bytes or compiler commands produced them.

The CMake archives were also checked read-only on 2026-09-26. Both contain
exactly the fourteen `kdm6` core members named in `libtorch/CMakeLists.txt`,
and every member extracted from both build and install archives matches its
`libtorch/build/CMakeFiles/kdm6.dir/src/*.cpp.o` file. The archive-level hashes
still differ (`22015a…` build, `4f0832…` install), so the member check proves
payload equality for these fourteen objects while an install receipt remains
absent. Two of the fourteen source/object pairs are stale by mtime: active
`libtorch/src/cold.cpp` (`9ee34fc1…`, Jul 18 12:44 JST) is newer than
`CMakeFiles/kdm6.dir/src/cold.cpp.o` (`bd8c7835…`, Jul 17 23:42), and active
`libtorch/src/sedimentation_conservative.cpp` (`38adc7f9…`, Jul 21 16:43) is
newer than `CMakeFiles/kdm6.dir/src/sedimentation_conservative.cpp.o`
(`59daf628…`, Jul 17 21:56). The archive members match those older objects.
Their July 17 archive mtimes also predate the Aug 23 WRF executable; neither
mtime nor matching members reconstructs the executable link command.
The ordered `ar -t` inventory contains fifteen physical entries in each
`libkdm6.a` (one `__.SYMDEF` plus fourteen objects) and 376 entries in the
current `libwrflib.a`, including one repeated member name. The schema retains
the full ordered name/hash multiset; the verifier compares it with parsed
physical archive entries so an unlisted extra or duplicate cannot pass.

The CMake source establishes two distinct targets: fourteen `src/*.cpp`
translation units form the STATIC `kdm6` target; `kdm6_c` is a SHARED target
whose direct source is the C ABI bridge and which links `kdm6`. CMake installs
both libraries. The WRF Fortran objects take a separate archive branch:

```text
14 libtorch/src/*.cpp sources → 14 objects → libkdm6.a ─┐
                                                       ├→ build libkdm6_c → installed dylib ─┐
kdm6_c_api.cpp → bridge object ────────────────────────┘                                      │
                                                                                              ├→ WRF Mach-O dependency
KDM6 Fortran sources → own objects → libwrflib.a ─────────────────────────────────────────────┴→ wrf.exe
                                                                                                 → loader target UNVERIFIED
```

`phys/Makefile` lists the KDM6 objects in the physics object set, declares the
wrapper dependencies, and compiles the KDM6 Fortran objects with
`-ffp-contract=off`. `main/Makefile` links `libwrflib.a` into `wrf.exe`.
The KDM6AD wrapper rules depend on the corresponding KDM6 module object for
Fortran module/build ordering. Each wrapper, ABI shim, and dispatch object is
compiled from its own source; a dependency rule does not make one object the
producer of another.
`configure.wrf` links `$(KDM6AD_PREFIX)/lib/libkdm6_c.dylib`, and WRF records
`@rpath/libkdm6_c.2.dylib` plus Torch dependencies. A read-only check matched
all fourteen build and installed `libkdm6.a` members to their CMake object
files. That proves member-byte identity only; compile and install receipts do
not tie those objects to current source bytes. Static Mach-O records candidate
loader paths only. No WRF process was launched and dyld resolution remains
unobserved. `kdm6` also links `${TORCH_LIBRARIES}`; `libtorch`, `libtorch_cpu`,
and `libc10` are separate dynamic dependencies, not members of `libkdm6.a`.
The future manifest must retain their exact link/load identities as external
inputs. `@rpath` and `otool -L` records alone do not prove their loaded paths.

Gate A is still intentionally unchanged and still fails the current legacy
source SHA pin. The historical pin is
`9354141b9e93aceb4a1c35e06bf673a5d4d916028877c0f84f729a301876b7dc`; the
current active source is `fc0a72…`. A source-pin report reproduces the active
bytes by deleting only the historical `rhox` pre-read line, but records no
explicit owner approval and no executable-level noninterference check.

## Smallest auditable isolated rebuild and historical control

When a native-build slot is available, make two private disposable host copies
from the same recorded host revision and use the same public checkout, build
configuration, compiler, linker, dependencies, flags, environment, fixed
inputs, and destination layout. Keep both copies and their build/install
prefixes separate; never reuse the canonical host tree's objects, archive,
install directory, executable, or run directory.

1. **Historical control:** restore the single pinned line in a copy of the
   active legacy source and require its SHA-256 to equal the unchanged Gate A
   value `9354141b…` before invoking the build. This is the historical source
   control, not a new pin.
2. **Current-source arm:** use the active source unchanged and require its
   SHA-256 to equal the recorded `fc0a72…` witness. All other source files,
   including the conservative source, must have matching hashes across arms.
3. Materialize source-only copies with generated build outputs excluded, then
   configure each independently and run `apply_kdm6ad_config.sh`. Confirm the
   fresh build directories contain no inherited `.o`, `.mod`, `.a`, executable,
   or KDM6AD build/install output before compiling. This forces both arms to
   rebuild the same full dependency closure. Capture expanded preprocessing,
   compile, archive, dylib build/install, and final link argv plus stdout and
   stderr.
4. Capture SHA-256 for every source/config input, preprocessed KDM6 Fortran
   source, all six KDM6 Fortran objects, all fourteen CMake `kdm6` objects,
   the bridge object, both archives and every listed member, build/install
   static/shared libraries, and the WRF executable. Record tool identities,
   exact flags and commands, environment, symlink targets, Mach-O install
   names/RPATHs, and output locations. The verifier must check each
   source-to-output edge, not infer one from matching mtimes.
5. After both manifests pass structural and byte-edge verification, a scoped
   one-rank, one-thread comparison can run the declared fixture and compare
   saved times and numeric fields. Record the result as bounded fixture
   evidence; it does not establish universal equivalence or revise the
   historical Gate A result.

This is the minimum defensible paired build for attributing an observed
between-arm difference to the one source line. A single rebuild of the active
tree could establish a new current-source build lineage, but it could not
isolate that line's effect against its historical control. A one-object
recompile followed by linking against the present archive would retain the
unproven pre-existing dependency closure and is therefore insufficient for
the paired comparison.

## Fail-closed rules

- Missing source/config hashes, exact commands, tool identities, object or
  archive-member hashes, library install receipt, executable hash, or link
  output makes the lineage `unproven`.
- Any recorded edge whose input digest does not match the upstream artifact or
  whose output digest does not match the retained artifact makes the lineage
  `failed`; do not repair a mismatch by changing the historical pin.
- `static_macho_only` records candidate install names and RPATHs only.
  `unverified_loader` records the expected installed dylib while keeping the
  `resolves_to` edge OPEN. A pinned collector checks actual argv, environment,
  exit code, dyld output bytes, executable hash, and loaded dylib path/hash;
  its unsigned local receipt still cannot promote the lineage gate to proven.
  Proven status needs an independent trusted execution attestation, which this
  workspace does not currently define.
- Collector JSON is a path-redacted projection: argv and cwd use aliases, and
  only allowlisted loader/thread environment keys are serialized, with
  path-valued settings replaced by digests. Exact command paths, allowlisted
  raw values, absolute dyld output, and stdout/stderr are written only under
  ignored `host/s9-captures/`; the public projection records their digest, not
  their local path. A regression test injects user paths and AWS credential
  variables and scans the serialized projection.
- A source/build lineage pass is separate from owner approval, scientific
  acceptance, raw-bit parity, JVP/VJP validation, and native fixture results.

## Provenance of this plan

The plan was first prepared in an isolated public worktree from `origin/main`
at `1956acd` (2026-09-26), then the S9 branch was rebased onto `origin/main`
at `9ac2b1d` after PR #283 merged (2026-09-27). Canonical `host/` inputs were
read-only. No private
source, object, archive, dylib, executable, or run input was modified, and no
native compile, link, or model run was performed. Read-only hash checks
confirmed all fourteen `libkdm6.a` members match their build objects in both
the build and install archives. The pre-edit Graphify query returned unrelated
cached wiki nodes. A post-edit code-only update rebuilt the graph; Graphify
`explain` now resolves `verify_manifest_semantics()` and the C ABI bridge.
HTML output was skipped because the graph exceeds the visualization node
limit. Semantic extraction for this Markdown plan remains unavailable because
no Gemini/OpenAI API key is configured. Dependency statements above were
checked against the source census, current CMake/Makefiles, archive member
bytes, and Mach-O records.
