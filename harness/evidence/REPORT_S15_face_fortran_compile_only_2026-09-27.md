# S15 bounded face overlay preprocessing and syntax checks

**Disposition: PREPROCESS/SYNTAX CHECKED, NOT NATIVE-CAPTURE-READY. S15 remains OPEN.**
No executable was linked or run. No six-row native event stream or cause
measurement exists.

The overlay now latches `KDM6_S15_NATIVE_CAPTURE_LOG=1` once in the shared
`solve_em` step path and passes the same step/RK/owner/tile identity through
both source paths: producer `scalar_tile_loop_1 -> rk_scalar_tend ->
advect_scalar[_pd]`, and consumer `scalar_tile_loop_2 -> rk_update_scalar`.
This corrects the earlier plan's single-path wording; the prior RK-store
discovery remains valid for the consumer operands it recorded. The instrumentation
is macro-gated under `KDM6AD_S15_FACE_CAPTURE`; macro-off identity was checked
through the configured WRF `.F.o` suffix sequence, not a standalone CPP pass.

The source pins remain:

| Source | SHA-256 |
| --- | --- |
| `dyn_em/solve_em.F` | `d66e9db1bba8f37e3f46d30c2fd74bdf8def411adf233376a69e0b401c6d3d1f` |
| `dyn_em/module_em.F` | `7695bfb05a7f99763334a6e69523bbcc1de0f2c659177a18c10a6e1cf530a0c7` |
| `dyn_em/module_advect_em.F` | `58253bdbeb188dd47ed0579fcd2891086be1889b75c0c7d3696c9ad1d213559d` |

The generated, macro-gated overlay source hashes for this candidate are:

| Generated overlay source | SHA-256 |
| --- | --- |
| `module_advect_em.F` | `13a2ec4b44c56efe6f4fd62488e3c18643f50a622eebfd674faa2142295e158d` |
| `module_em.F` | `7a768de4a72733409ce73bac8f34b84d1216a254d11948a9cfd5650c95289d9a` |
| `solve_em.F` | `f8d57b06e60dbebf966267606a26a984f3172f5dfbfa84b3c0303b92b1d008e7` |

For all three pinned sources, the configured suffix sequence was executed in a
disposable shadow: comment-cleaning `sed`, GNU CPP, `standard.exe`, then GNU CPP
with the configured traditional mode. Macro-off final `.f90` files were
byte-identical between pinned source and overlay. Their SHA-256 values, in
`module_advect_em.F`, `module_em.F`, `solve_em.F` order, were
`1f6d10ba7b44870fb6ac324cea8a613758db0a6991dafa46c9b9afd8231495dc`,
`e00d4b4131e179c2e59aa2cf282965bed1aef5c449202405e93b2e43e8e9e804`, and
`2155b1c46883d23434bc7bd0f90f9e2570e764beeba159ae26ab1d759851a22d`.
Macro-on final `.f90` SHA-256 values in the same order were
`6b2c541fc62ec0cd7f56d243bf68dc4692c782371752ec033187318db1c36bd7`,
`53207a03dba5b3a42edb43891368f09318a59d44ced480f8ef982184a9e0034e`, and
`f2b6748ea4b2fc02881a085bd33f8d1fdcd3a2aac233d6ca7492fd25d0694a36`.

GNU Fortran 15.2.0 syntax-only checks passed in dependency order for
`module_advect_em`, `module_em`, and `solve_em`: **3 attempted, 3 passed, 0
failed**. No object files were produced. The private receipt SHA-256 is
`afee12b9f034ecd2b8c1772f83bc844e2febe8727896effcd990d958c94de05e`.
It records full redacted-at-publication argv, working directories, file hashes,
tool identities, and zero object output. Tool SHA-256 values are GNU CPP 15.2
`da93121aee7a566976e57fcebdc19f5b3cdd3aaa94469ff4bde61ff44f199e03`, GNU
Fortran 15.2 `0019c2383f399c1ba6aed1dc060191e793caf963c1066d254194883581098bb2`,
`sed` `c22008f570205b508cd80adecc06c5332aead6b45228ca436bf1615c39adf0f6`,
`standard.exe` `21848b3d6e1680a2221753f06afef1c2d3043b542cf7ac0062c542470786cf19`,
and `configure.wrf` `490a164e853e4d1f28ff79c9dfc36843d00db9c8bd6aaae6bd47afd70ffc9292`.
The receipt, intermediates, and diagnostics remain outside the public tree.

The runtime logger has hard caps of 18 `S15AX`, 2 `S15PD`, and 6 `S15RK`
records; exceeding any per-tag cap stops the instrumented process. The strict
stream extractor reads incrementally and rejects unknown `S15*` tags, full
stdout above 1 MiB, lines above 64 KiB, face output above 64 KiB, and legacy
output above 1 MiB or 100,000 records. It uses bounded `readline`, hashes the
same streamed bytes used for parsing, and rechecks the source. Source and
output paths use descriptor-relative no-follow parent walks; the input must be
a regular file whose pre-open and post-open identities match. Output creation
is exclusive, and rollback unlinks relative to the retained parent descriptor.
The parser independently enforces the declared six-key schedule and exact
18/2/6 record counts.

Synthetic tests cover stream separation, exact event counts, size limits,
unknown tags, symlinked source/output paths, FIFO timeout, parent-swap rollback,
unterminated oversized lines, and producer/consumer transition contracts.
They are protocol checks, not native evidence. The separate
`sc_tend` operand is recorded but has not been attributed numerically against
the runtime producer. A macro-off same-executable control, captured six-key
producer/consumer records, stream repeatability, and output noninterference
checks remain required. No physical cause or graupel-policy conclusion is
claimed.
