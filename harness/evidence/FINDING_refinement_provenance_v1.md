# The refinement bundle is now reproducible, and the reproduction was run

Owner review §9. The refinement experiment recorded provenance that could not
support a reproduction attempt, and no attempt had been made.

## What was wrong

| field | was | why it fails |
|---|---|---|
| `compiler` | `"GNU Fortran (Homebrew GCC 15.2.0) 15.2.0"` | a string the caller typed. Two hosts print it and produce different numbers. |
| `compile_commands` | `[]` by default | no caller passed any, and an empty list is indistinguishable from a build nobody recorded |
| members | parsed by a BEGIN-line regex | a truncated, duplicated or ragged member entered the manifest unchallenged — precisely what the strict reader rejects |
| findings | not linked | a finding citing a table nobody can tie to the run it came from is unreviewable |

## What is recorded now

The **build** writes it, because the build is the only place that knows it
(`harness/g33_build_provenance.py`, called from `refine_build.sh`):

```
compiler_path        /opt/homebrew/bin/gfortran
compiler_sha256      0019c2383f399c1ba6aed1dc060191e793caf963c1066d254194883581098bb2
compiler_version     GNU Fortran (Homebrew GCC 15.2.0) 15.2.0
compile_commands     7, logged as the build compiled them
build_script_sha256  + module_sha256 + fixture_sha256
repo_commit          tree_dirty
```

`_member()` now goes through `g33_refine_analyze.read()`, so a member that would
fail analysis cannot enter the manifest. Absent provenance is `null`, not `[]`.

## The reproduction, actually run

Rebuilt from `29c5119` on a clean tree and re-ran all six members against the
committed streams of `kdm6ad-g33m-refine/fortran-legacy-dtcld`:

| member | committed | rebuilt | diff |
|---|---|---|---|
| n3, n6, n12, n24, n48, n96 | 155 lines | 335 lines | **0 removed, 0 changed, 180 added** |

In all six, `diff`'s edit script is **insertion-only** — the committed stream is
an in-order subsequence of the rebuilt one, so **every committed record
reproduces bit-identically**. The 180 additions are 144 `INITIAL` and 36
`FORCING` records that the driver gained after those streams were written.

The bundle was refreshed to the rebuilt streams. That is not a cosmetic change:
without `FORCING` there is no ρΔz, so the old streams could not support the
column water budget, the moist-enthalpy and operator ledgers, or the fallout
diagnostic-trust table. The manifest went from 4 members to the 6 present.

## Limits

- **One host, one compiler.** Reproduction on a different machine is untested;
  the digests are what would make that test meaningful, not evidence that it
  passes.
- **The reproduced set is the 155 records that existed.** The driver's newer
  `INITIAL`/`FORCING` output has no committed predecessor to compare against.
- **`tree_dirty` is recorded, not refused.** The decision-bundle producers
  refuse a dirty tree; this experiment producer records the flag instead.
  Deliberate — an experiment run from a working tree is still worth keeping, and
  `decision_eligible` is a constant `False` — but it is a real difference in
  strictness between the two artifact classes, and it is the owner's call
  whether the experiment path should refuse too.
- Provenance makes a run reproducible. It says nothing about whether the run
  answers the question.
