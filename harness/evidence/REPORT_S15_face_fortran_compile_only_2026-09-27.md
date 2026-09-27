# S15 bounded Fortran overlay compile-only check

**Disposition: COMPILE-CHECKED, NOT NATIVE-CAPTURE-READY. S15 remains OPEN.**
The disposable overlay preprocesses and compiles, but no model process ran and
no six-row native event stream has been measured.

The source path is now explicit. `solve_em.F::scalar_tile_loop_1` calls
`rk_scalar_tend`, which dispatches to `advect_scalar` or
`advect_scalar_pd` and emits producer face/prefix records. The later
`solve_em.F::scalar_tile_loop_2` calls `rk_update_scalar` and emits the consumer
RK records. Both owner-5 calls receive the same step/RK/tile identity. This
corrects the earlier plan's single-path wording; the old RK-store discovery
remains valid for the operands it recorded.

The macro-gated overlay is built from these read-only private source pins:

| Source | SHA-256 |
| --- | --- |
| `dyn_em/solve_em.F` | `d66e9db1bba8f37e3f46d30c2fd74bdf8def411adf233376a69e0b401c6d3d1f` |
| `dyn_em/module_em.F` | `7695bfb05a7f99763334a6e69523bbcc1de0f2c659177a18c10a6e1cf530a0c7` |
| `dyn_em/module_advect_em.F` | `58253bdbeb188dd47ed0579fcd2891086be1889b75c0c7d3696c9ad1d213559d` |

With `KDM6AD_S15_FACE_CAPTURE` undefined, WRF preprocessing produced byte-
identical output for all three files. The matching preprocessed SHA-256 values
were `d6cc9d34512f2c231fe4ef886576f3a2304a5693dae848eb6e0174d97733c855` for
`solve_em.F`, `7695bfb05a7f99763334a6e69523bbcc1de0f2c659177a18c10a6e1cf530a0c7`
for `module_em.F`, and
`53fd3a21702032573c2190b3f5b076af81dc8d18f3f3ef3ccebd0ff2cc152e80` for
`module_advect_em.F`.

With the macro enabled, GNU CPP 15.2.0 produced the three compile inputs. Their
SHA-256 values, in `module_advect_em.F`, `module_em.F`, `solve_em.F` order, were
`68e791466ba76667ef6b794b3d51f711e4574b8bdf6bd55df62e6bb5885a03cb`,
`4b9868f4145bf8d5f67f58696a70f0d41561dd421ba5b4a00112431d2d8ff09d`, and
`dc1f6d1a619a7e34c440839b4fab55fd9da84ff667751094995b33858d8173ed`.
Focused GNU Fortran 15.2.0 `-fsyntax-only` checks passed in dependency order for
all three touched modules. The command used the host's configured free-form,
line-length, endian, compatibility, optimization, and module-search settings;
the ten WRF module search directories were taken from the pinned private
installation. Preprocess receipt SHA-256 values are
`f81cb9c1a0f41df3be90bab976ff7f873f19b2a103861fd809e02e4bb2bab910` (macro
off) and `85b9efea6a55ddaec1898b88c055433206ecbc819db3086840887cf57b12b2e4`
(macro on). The compile-only receipt SHA-256 is
`cda6af692d87e926fb3bd01493dc71116ae87b3412a3c6f8ffa666f7eddf3406`.

The path-redacted command forms were:

```text
cpp-15 -P -nostdinc -xassembler-with-cpp -traditional-cpp -I <host>/inc
  -DEM_CORE=1 -DNMM_CORE=0 -DNMM_MAX_DIM=2600 -DDA_CORE=0 -DWRFPLUS=0
  -DIWORDSIZE=4 -DDWORDSIZE=8 -DRWORDSIZE=4 -DLWORDSIZE=4
  -DMAX_DOMAINS_F=21 -DMAX_HISTORY=25 -DCONFIG_BUF_LEN=65536 -DNMM_NEST=0
  <configured WRF macros> [-DKDM6AD_S15_FACE_CAPTURE] <pinned .F input>

gfortran -O2 -ftree-vectorize -funroll-loops -w -ffree-form
  -ffree-line-length-none -fconvert=big-endian -frecord-marker=4
  -fallow-argument-mismatch -fallow-invalid-boz -fsyntax-only
  -J <scratch>/mods -I <scratch>/mods -I <10 configured WRF module dirs>
  <macro-on preprocessed .f90 input>
```

One initial Apple `cpp` setup invocation failed before processing a source file;
that diagnostic is preserved outside the repository and is excluded from the
compile count. The focused Fortran compile count is **3 attempted, 3 passed, 0
failed**. GNU CPP processed three pinned sources in macro-off and three in
macro-on mode.

The Fortran check wrote two module files in scratch output and zero object
files. It did not link, install, or run the host. Scratch commands, preprocessed
inputs, and compiler diagnostics stay outside the public tree; no private source
text or raw event operands are published.

The synthetic parser checks exact six-key coverage, source-ordered axes,
ordinary versus positive-definite dispatch, PD limiter record shape, duplicate
and unknown tags, and producer/consumer identity. They are synthetic protocol
checks only. A same-executable macro-off control, native capture, output
noninterference comparison, and the six actual producer/consumer rows remain
required before S15 can advance.
