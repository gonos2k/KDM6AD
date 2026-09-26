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
stderr receipt, checks the required KDM6 source/object paths and archive-member
coverage, and verifies the observed loader's executable and dylib identities.
Run it as `python harness/verify_s9_source_build_manifest.py MANIFEST.json
--root BUILD_ROOT` with the `jsonschema` Python package installed. It hashes the
recorded artifacts and extracts the six KDM6 members from `libwrflib.a` for
byte comparison. File mtimes remain supporting chronology only, never proof
of origin.

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
| `libtorch/build/libkdm6_c.2.0.0.dylib` | `82c9fffe18c1fcbcb41aeec85b5430ce103b57b285089953ecdea7341dc1103e` | Jul 17 23:42:16 | Build-tree library bytes. |
| `libtorch/install/lib/libkdm6_c.2.0.0.dylib` | `7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7` | Jul 17 23:44:04 | Installed bytes differ from the build-tree hash; no install receipt explains the difference. |

All six listed objects predate the active scheme source witnesses by mtime;
only `module_mp_kdm6.o` and `module_mp_kdm6_cons.o` are directly paired with
those two dated scheme sources here. The archive member hashes independently
match their corresponding listed `phys/*.o` hashes for all six objects.
This identifies which object bytes are in the present archive; it does not
identify which source bytes or compiler commands produced them.

The intended lineage is a converging build graph, not a serial
source → archive → dylib chain:

```text
Each KDM6/KDM6AD/bridge/driver Fortran source
  → its preprocessed source → its own object ─────────────┐
                                                          ├→ libwrflib.a → wrf.exe
C++ entry sources → their objects → build-tree dylib ─────┤
  → installed dylib ──────────────────────────────────────┴→ Mach-O dependency
                                                             → observed dyld resolution
```

`phys/Makefile` lists the KDM6 objects in the physics object set, declares the
wrapper dependencies, and compiles the KDM6 Fortran objects with
`-ffp-contract=off`. `main/Makefile` links `libwrflib.a` into `wrf.exe`.
The KDM6AD wrapper rules depend on the corresponding KDM6 module object for
Fortran module/build ordering. Each wrapper, ABI shim, and dispatch object is
compiled from its own source; a dependency rule does not make one object the
producer of another.
`configure.wrf` links `$(KDM6AD_PREFIX)/lib/libkdm6_c.dylib`, while the WRF
binary records `@rpath/libkdm6_c.2.dylib` and several RPATHs. Static Mach-O
inspection records candidate loader paths only. No process was launched, so
the census does not observe which dylib dyld resolved. The installed
`libkdm6_c.dylib`/`libkdm6_c.2.dylib` aliases point to the versioned installed
file, but this symlink identity is not a runtime resolution receipt.

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
4. Capture SHA-256 for every source/config input, preprocessed KDM6 source,
   dependent `.mod`, KDM6 and bridge/driver object, archive and relevant
   archive member, build/install dylib, and WRF executable. Record tool binary
   identities and versions, exact flags, environment, symlink targets,
   Mach-O install names/RPATHs, and the output location. The verifier must
   check every source-to-output edge, not infer one from matching mtimes.
5. Only after both manifests pass structural and byte-edge verification may a
   separately authorized native comparison run the declared one-rank,
   one-thread fixture and compare saved times and numeric fields. Record that
   result as bounded fixture evidence; do not convert it into universal
   equivalence, approval, or a revised historical Gate A result.

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
- `static_macho_only` can document install names and RPATHs but cannot satisfy
  `resolves_to`. A full source/build/install/runtime lineage claim requires an
  observed loader receipt tied to the exact executable hash and resolved
  dylib hash.
- A source/build lineage pass is separate from owner approval, scientific
  acceptance, raw-bit parity, JVP/VJP validation, and native fixture results.

## Provenance of this plan

The plan was prepared in an isolated public worktree from `origin/main` at
`1956acd` (2026-09-26). Canonical `host/` inputs were read-only. No private
source, object, archive, dylib, executable, or run input was modified, and no
native compile, link, or model run was performed. The pre-edit Graphify query
returned unrelated cached wiki nodes. A code-only `graphify update .` created
the worktree graph, but the subsequent query still returned unrelated wiki
nodes; semantic refresh for this new Markdown plan was unavailable because
`OPENAI_API_KEY` is unset. Dependency statements above were checked against
the source census, local Makefiles, archive member identities, and Mach-O
records.
