# Oracle CI diagnostics

Profile the workflow's pure-Python Oracle selection from the repository root:

```sh
cd oracle
python ../harness/ci_diagnostics/profile_pytest.py --output /tmp/oracle-profile.json -- python -m pytest -rs -q
```

The wrapper appends `--durations=10` (configurable with `--durations`) and streams the pytest output, while recording wall, user and system seconds, peak RSS, and reported slow phases. `wait4` reports maximum RSS in bytes on macOS and KiB on Linux; the operating system determines how reaped descendants contribute, and this is not aggregate peak memory of concurrent processes. It forwards SIGINT/SIGTERM to the child process group and preserves its exit or signal status. On cancellation it allows a three-second grace period before killing the process group, then kills any remaining group members and bounds output draining. If the leader exits but an inherited pipe remains open, the wrapper kills the residual group and returns nonzero even for a successful leader; the report records both statuses and whether draining completed. The JSON report is written atomically after child termination. Forced termination of the profiler itself cannot produce a completed report.

`compare_workers.py` runs only the three slowest normal-mode suites recorded in #584, sequentially with one and two workers, using the evidence runner's API. It records individual outcomes, skip status, elapsed times, inputs and toolchain hashes; its local single-sample result is not a hosted Ubuntu benchmark or a full-suite claim. Its output files are non-overwriting; move or remove a previous experiment explicitly before rerunning.
