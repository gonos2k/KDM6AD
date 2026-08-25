# What a green CI actually certifies, measured

The harness suite is the campaign's regression gate, and `g33-harness-ci` is a
required check. This measures what that check EXECUTES, because "the suite
passes" and "CI proves the suite passes" are different claims and only the
first one has ever been made with numbers.

## The measurement

CI run `32790296549` (branch `harness/g33-provenance-shown`, the PR #168 head),
read from the job log rather than from a local run:

    1928 passed, 357 skipped

So **15.6% of the suite does not execute in public CI**. That number alone is
not interesting; where it concentrates is.

Per-file, skipped-in-CI over collected (`pytest --collect-only`), everything at
100%:

| file | tests | CI |
|---|---|---|
| `test_g33_ncmin_locality.py` | 124 | 0 run |
| `test_g33_cap_interface.py` | 27 | 0 run |
| `test_g33_fortran_build.py` | 25 | 0 run |
| `test_g33_density_control.py` | 20 | 0 run |
| `test_g33_metric_trajectory.py` | 16 | 0 run |
| `test_g33_ice_density_matrix.py` | 7 | 0 run |
| `test_g33_probe_pipeline.py` | 5 | 0 run |
| `test_g33_real_column_density.py` | 4 | 0 run |
| `test_g33_column_separability.py` | 4 | 0 run |

**232 tests are dark in CI**, in nine files that run entirely or not at all.

## The consequence that matters

Being dark is survivable when another CI-visible file also exercises the module.
Cross-referencing each dark module against every other test file, six have no
second reference anywhere in `harness/tests/`:

    g33_fortran_build.py        g33_probe_pipeline.py
    g33_density_control.py      g33_real_column_density.py
    g33_ice_density_matrix.py   g33_column_separability.py

For those six, **a change merges with every required check green and no test
file that references them having run.** That is a STATIC-reference argument
and not a dynamic one: a transitive import, a helper, or a subprocess could
still touch them. Saying "nothing executed it" would need coverage.py or an
import trace in CI recording executed lines per module, which is not done
here. What is measured is that no test file naming them ran.

This is not hypothetical. Neutering `_expect_universe` in
`g33_ncmin_locality.py` (return `None` at the top of the body) is caught locally
by its own test file: 3 failed of 124, in 306 s. That file is one of the nine.
The same mutation reaches a green PR.

Three modules are better off than the count suggests: `g33_ncmin_locality`,
`g33_cap_interface` and `g33_metric_trajectory` ARE referenced by CI-visible
files (`test_g33_identity`, `test_g33_refine_experiment`, `test_g33_refine_manifest`,
`test_g33_factorial`, `test_g33_refine_analyze`), so a signature break there
still fails CI. Their behaviour is unguarded; their interface is not.

## Why each skip happens, and why none is fixable in this CI as configured

Every one of the 357 traces to one of three causes, all structural:

1. **The local-only Fortran leg** — 209 skips, gated on
   `shutil.which("gfortran") is None or not REF.is_file()`, where `REF` is
   `host/KIM-meso_v1.0/phys/module_mp_kdm6.F`. `host/**` is gitignored and not
   distributed; it cannot be on a CI runner. Already recorded in
   `g33-harness-ci.yml`'s own closing note.
2. **Evidence bundles** — ~70 skips reading "no v3/v4/v6 bundle on this host".
   Bundles are RUN ARTIFACTS. `git ls-files | grep bundle` returns only source
   files (`g33_bundle_io.py`, its tests, one finding) — no bundle data is
   committed, so there is nothing for CI to find.
3. **Host data** — `netCDF4` and the LC05 state file, same category as (2).

**The Fortran gate was checked for over-breadth and is not over-broad.** A
module-level `pytestmark` that skips pure-Python tests along with the ones that
shell out would be a real and cheap defect — and the codebase already applies
the alternative elsewhere ("bundle not on this host -- structural half runs
regardless"). An AST pass flagged `test_g33_column_separability.py` as 4 tests
touching nothing Fortran. Reading them refutes it: all four go through `_run`
or `_tiled`, which `subprocess.run` `fortran_build.sh` and `refine_build.sh`.
The pass only scanned test-function bodies, so helpers named `_run`/`_tiled`
were invisible to it. The other four files are 27/20/7/4 Fortran-touching with
zero pure tests.

## What this does and does not license

It does NOT say the six modules are wrong, or that the local evidence is weaker
than claimed — the suite that certifies them runs, in full, on the owner's host,
and that is where the Fortran leg's evidence has always been produced
(`test_g33_fortran_build.py` + committed evidence, not CI).

It says the SENTENCE "CI is green" must not be offered as evidence about those
six. For them the load-bearing artifact is a local run, and a local run has to
be cited as one.

## Not open

- Making the Fortran leg run on a PUBLIC HOSTED runner. It needs a gitignored
  source tree, and that is a property of the runner, not of the problem. NOT
  foreclosed, and a process question rather than a technical one: a self-hosted
  required check, a minimal public reference kernel or stub, a sanitized
  deterministic artifact, or an owner-host attestation JSON pinned to the PR
  head SHA. This measures the current configuration; it does not argue that no
  configuration could do better.
- Splitting a structural half out of the five Fortran files. Measured above:
  there is no structural half to split.
