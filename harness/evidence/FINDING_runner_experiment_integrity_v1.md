# The runner could lose an experiment four ways, and none of them would say so

`run_ss_case.py` is the instrument every MPI, perturbation and processor-grid
result in this campaign came out of, and it had no exclusive lock, no
before-run binary hash, a one-second output directory name, and no check that
WRF used the decomposition it was asked for. Each of the four fails quietly:
the run completes, writes a directory, and reports success.

## What each one loses

**Concurrency (the one that corrupts).** The runner rewrites `namelist.input`,
deletes the previous `rsl.*`/`wrfout_*`, runs, archives, and restores. Two runs
in one case directory interleave all five: each overwrites the other's
namelist, deletes the other's outputs, archives results produced under settings
it did not choose, and the second to finish restores a namelist the first had
already replaced. Nothing detects it afterwards -- the archive looks complete.

This repository has already paid for one shared-mutable-state race, the
compile-time fixture, and the answer there was an `O_CREAT|O_EXCL` lock. Same
answer here, with the same ORDERING lesson attached: restore, archive, and only
then release. Releasing first lets a waiter start while the outputs are still
in the case directory, where its own cleanup deletes them as stale.

**Binary identity.** `wrf_exe_sha256` was computed after `subprocess.run`
returned, so it recorded whatever `wrf.exe` was when the run ENDED. A binary
rebuilt or a symlink retargeted mid-run would be recorded as the one that ran.
Both hashes are now written with the resolved path, and disagreement is stated
in the file rather than resolved silently.

**Output directory.** The name resolved to one second and was created with
`exist_ok=True`, so two runs started in the same second with the same arguments
shared a directory and interleaved their archives. The lock makes that
impossible within one case directory; the PID and `exist_ok=False` make it loud
if it happens anyway.

**The decomposition.** `--proc-grid` pre-checked only that the two factors
multiply to `--np`. WRF prints what it actually chose, and a run whose grid is
not the requested one is a different experiment wearing the requested one's
directory name -- which matters exactly for the seam work, where the grid IS
the independent variable. `parse_proc_grid` reads it from `rsl.error.0000` and
the run records requested, actual, and whether they match. Absent lines record
as "not found", never as agreement.

## And the stale copy, which is why this list exists at all

The case tree keeps its own copy of the runner. It had fallen twelve lines
behind, so the binary-hash recording added one morning was not in the version
that ran that day. The copy warned and continued -- fail-open, and the warning
went to stderr before the output directory existed, so it was not in the run
either.

It now refuses by default and names the `cp` that fixes it; `--allow-runner-drift`
is the deliberate override. The comparison itself is recorded in the run as
`runner_sha256`, including the case where it could not be made: the canonical
path is one host's, and on a host without the repository there is nothing to
compare. That state is written as `uncomparable-no-repo-copy`, because "we did
not look" must not read as "we looked and it matched".

## What is NOT claimed

That any past run was corrupted by these. No evidence says two runs ever shared
a case directory or an output name, and the binary-hash window is narrow. The
claim is that the instrument could not have told us, and now four of the five
ways it could not tell us are closed.

The fifth is not closed here: the canonical runner path is still hard-coded to
one host, so on any other machine the drift check is skipped rather than
performed. The honest fix is a `--case-dir` argument on the canonical runner so
code location and run location separate and no copy exists to drift.
