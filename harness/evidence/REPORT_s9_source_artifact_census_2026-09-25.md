# S9 source, object, executable, and install census

## Finding

The historical Gate A pin remains unchanged and fails against the active
private source for the documented one-line `rhox` cleanup. The current private
source witness passes its separate provenance script, but the available host
objects, WRF executable, and installed C ABI library do not authenticate a
build from that source witness. This read-only census does not approve the
cleanup, recertify the old pin, or establish runtime parity.

The public evidence change is based on `origin/main` at `eb1287f6` (#266). The
private artifacts were read from canonical host checkout
`/Users/yhlee/KDM6AD-k` at `0aa2c30b6c8673f1c1a032d6a7f9b277d45440e1` with
unrelated documentation and AGENTS edits present.

## Source and historical gate

The unchanged Gate A report is present at
`harness/evidence/gate_a_scope_report.json` with SHA-256
`cff6cb64f36f818f4eeb655ab8e5ffe3423195bdd4509b88bf4c128d0564dbd2`. It records
the historical hashes `9354141b9e93aceb4a1c35e06bf673a5d4d916028877c0f84f729a301876b7dc`
for `module_mp_kdm6.F` and
`364a1319d0099bdb474a752a2a017defaf008babbe85dd03da872c603b2e7e3e` for
`module_mp_kdm6_cons.F`, and a passing historical scope check. The separate
2026-09-24 [source-pin lineage report](source_pin_lineage_2026-09-24.json)
documents the current legacy source as
`fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5`, exactly
the historical source with the single
`rhox(i,k) = max(rhox(i,k),0.0)` read removed. The active conservative source
is `4f0103c8a8321b8e854d3500f4ae567755e41eb78746fac54519eca2686a6648`.
Read-only replay of `harness/check_cons_fortran_scope.py` against the canonical
private files returned `pass=false`, with the sole failure being the old legacy
SHA pin; all four structural clusters and both handoff-block checks matched.
The replay did not pass optional `--legacy-wrapper`, so the legacy wrapper's
SHA pin is outside this result.
The replay saw checker commit `0aa2c30b6c8673f1c1a032d6a7f9b277d45440e1-dirty`
because unrelated local documentation and AGENTS changes are present, while
the checker source hash remained the expected
`2d2dea356422987099b4a8449f55c9c4d62fd949b7ab0f4e527990aa39753f8f`. The pin
is not changed here.

On 2026-09-25, `sh host_fortran/check_source_provenance.sh` passed all seven
current active-source witnesses, including the two hashes above. That script
binds active source bytes to its local witness only; its provenance notes
explicitly do not bind those bytes to object, executable, or library outputs.
`host_fortran/` remains a historical review archive. Its legacy source hash
`31302e886595670c…` is neither the historical pin nor the active host source.

## Available artifact identities

The read-only inspection found these artifacts in the canonical private tree:

| Artifact | SHA-256 | Modification time (JST) |
| --- | --- | --- |
| Active `phys/module_mp_kdm6.F` | `fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5` | 2026-09-05 18:34:23 |
| Active `phys/module_mp_kdm6_cons.F` | `4f0103c8a8321b8e854d3500f4ae567755e41eb78746fac54519eca2686a6648` | 2026-09-05 19:11:51 |
| `phys/module_mp_kdm6.o` | `9c103f267d61582c45a9d7e2dfd6753a3c0d2d165bf47c241f7c4729eca90721` | 2026-08-23 00:18:32 |
| `phys/module_mp_kdm6_cons.o` | `415799b05c05133f08cd2ae13c9e199c31138145b927e0b77ef6cf894ec0bcf1` | 2026-07-17 21:57:07 |
| `phys/module_mp_kdm6ad.o` | `2cd5f0ba4bd0887e3efe85a04f75e064ed44248d50a1cb31a17a14fc50718ee1` | 2026-08-23 00:18:34 |
| `phys/module_mp_kdm6ad_cons.o` | `144b09a86e07b4de3fd89f638eaa0d39a01fc0e0799aae343d44f761959cd13f` | 2026-07-17 21:57:08 |
| `phys/kdm6_iso_c.o` | `a3273b3a929bd5e79e33450ae37f5414fc65961bb178f2cec184e062cfa6049f` | 2026-07-17 19:25:45 |
| `phys/module_microphysics_driver.o` | `a89608fd8dcda6bbb71713efdd9da9e5eeec1585bb3cc1b08161c80e171a081e` | 2026-08-23 00:18:35 |
| `main/wrf.exe` (same bytes in `run/` and `test/em_real/`) | `676223e8d61d23456d4ac83713bff0283ea08b1e71776b7f8885b062d97f801b` | 2026-08-23 00:21:51 |
| `libtorch/build/libkdm6_c.2.0.0.dylib` | `82c9fffe18c1fcbcb41aeec85b5430ce103b57b285089953ecdea7341dc1103e` | 2026-07-17 23:42:16 |
| `libtorch/install/lib/libkdm6_c.2.0.0.dylib` | `7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7` | 2026-07-17 23:44:04 |

The WRF executable and listed objects predate the active Fortran source files
by mtime. The build-tree and installed dylibs also have different hashes. These
facts establish that the present artifacts are not a retained current-source
build record; timestamps alone cannot identify the source bytes used at an
earlier compilation.

`otool -L main/wrf.exe` records `@rpath/libkdm6_c.2.dylib`. Its load commands
include both `@loader_path/../../../libtorch/install/lib` and the absolute
`/Users/yhlee/KDM6AD-k/libtorch/install/lib` RPATH. This identifies the static
loader search route to the installed dylib in this local tree; the local
`libkdm6_c.dylib` symlink resolves through `libkdm6_c.2.dylib` to
`libkdm6_c.2.0.0.dylib`. No process was started, so this is not an observation
of dyld's runtime resolution. No
executable manifest connects the active Fortran source, compiler command and
flags, object hashes, executable hash, and the dylib bytes actually loaded.

## Approval status and bounded next experiment

The 2026-09-24 lineage report and bounded provenance review found the edit
rationale and later source hash witnesses, but no explicit owner approval or
attributable change record for the undefined-read cleanup. A passing current
source witness and a structurally matching Gate A replay are not that approval.
S9 therefore remains **OPEN**. The approval record and executable lineage are
independent missing evidence; neither should be inferred from the other.

After the S5/S10 native-run queue clears, a minimal isolated experiment can
bound the cleanup's effect on a declared fixture: build two fresh host trees
from the same host revision, compiler/toolchain, flags, inputs and configuration;
use the pinned legacy source in one and the current source with only that line
deleted in the other; retain the conservative source and every other source
byte-identical. Keep each build, install prefix, executable and linked dylib in
its own directory. Record source and toolchain manifests, compiler/link
commands, object/executable/library SHA-256 values, dyld linkage details, and
the hashes of fixed initial/boundary inputs. Run both through
`harness/run_ss_case.py` with one MPI rank and one thread, then compare saved
times and every numeric field with `harness/strict_bitwise_nc.py`. This could
show raw-bit equality or a measured difference for those inputs and that build;
it cannot prove universal semantic harmlessness, grant source approval, or
replace the historical pin.

## Scope

Commands were limited to source-hash witnessing, Gate A scope replay, SHA-256
and mtime collection, and static Mach-O load-command inspection. No source,
pin, install, object, executable, or namelist changed. No build or native run
was made. The [2026-09-24 ice-normalization
report](REPORT_ice_normalization_2026-09-24.md) remains evidence for its distinct
measured experimental variant; it does not close this source/build certification
gap.
