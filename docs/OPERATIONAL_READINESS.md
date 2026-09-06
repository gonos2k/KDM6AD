# Operational readiness and remaining acceptance evidence

**Unattended real-observation assimilation, host writeback, and repeated forecast
cycling remain NO-GO.** Research/regression use and supervised, isolated shadow
experiments are distinct uses; an accepted LC05 evidence artifact is not an
operational approval. Conservative-interface release/default-DA promotion remains
on HOLD under its existing scientific gates.

This checklist incorporates the operational review of PR #213 (`15aaefe1`) and
was checked against PR #214's merged source (`30edd837`). Prior local numerical
resolutions remain closed. In particular, process lifetime does not require a
change to the operational f32 map, f64 microphysics map, window adjoint, or ABI.

## Checklist

| ID | Disposition | Completion evidence required |
|---|---|---|
| O1 — external-call lifetime | Code fixed; bounded regression evidence below | Positive finite timeout, owned POSIX group termination, direct-child reaping, early-wrapper-exit rejection, fresh output and failure diagnostics |
| O2 — timeout routing | Code fixed; bounded regression evidence below | Explicit LC05 CLI → full-domain clear/all-sky → live runner limit; shard-spec propagation; finite default for other live callers |
| O3 — workspace ownership | Code fixed; bounded regression evidence below | Unique LC05 run namespace and temporary all-sky cases; nonblocking exclusive ownership around live case write/run/parse |
| O4 — target deployment | OPEN | Pin OS, host/port source and configuration, compiler flags, libtorch, installed and actually loaded library hashes, MPI/threads, RTTOV executable/coefficients; rebuild and execute that combination |
| O5 — actual observation conditions | OPEN | Pin UTC, channels, coordinates, calibration, units, geometry and surface for the declared product. Prohibit reference-fixture substitution in a future operational entry point; verify representativeness for any allowed time offset |
| O6 — complete cycle and host application | OPEN | Stage and verify a candidate tied to UTC/grid/background hash; apply once, read back values/units/budgets, restart/forecast, proceed to next cycle. Test retries and duplicate inputs without applying increments twice |
| O7 — whole-job failure and resource budget | OPEN | Supervisor-enforced overall deadline, worker death/cancellation, detached descendants, memory/disk exhaustion, late/missing observations, no runnable residual tasks; target-scale wall time and peak resources |
| O8 — scientific acceptance | OPEN | Independent withheld observations/times/weather regimes and forecast-space evaluation; distinguish legacy-equivalence risk acceptance from promotion of changed physics |

O1–O3 address the reviewed public execution boundary. They do not close O4–O8.
Target OS/product selection and deployment measurements have not been supplied
for this change. The historical 12-hour MPI parity result remains attributed to
its recorded source/binary/configuration; it is not recertified by a port-only
CI run or by these Python changes. Linux port CI does not certify the private
macOS host build hook on Linux: see [host integration](HOST_INTEGRATION.md).

## External RTTOV execution contract

`run_rttov_k`, `run_rttov_direct`, and `make_live_run_k` use **300 seconds per
external invocation** by default. `timeout=None`, booleans, nonpositive and
nonfinite limits are rejected before rewriting a case. LC05 accepts
`--rttov-timeout SECONDS`; full-domain and shard callers accept `rttov_timeout`.
The selected value is execution metadata, not a performance measurement or a
claim that a 300-second forecast cycle is feasible.

The common runner starts `sh run.sh` in its own POSIX session/process group.
It writes stdout/stderr to files rather than pipes, waits with the selected
limit, sends SIGKILL to the owned group on every exit, and waits up to five
additional seconds to reap its direct child. A wrapper that exits while group
members remain is rejected even with exit code zero. Fresh target existence and
the original parser/profile-count checks still apply. Timeout and nonzero exit
propagate; there is no retry using an uncontrolled calculation or a skipped cell.
These are the distinct POSIX primitives described by Python's
[subprocess API](https://docs.python.org/3.13/library/subprocess.html) and
[process-group signalling API](https://docs.python.org/3.13/library/os.html#os.killpg).

The supported wrapper must keep descendants in the owned group and wait for
them. This is **not** containment of a deliberately detached session, forced
death of the Python worker, an uninterruptible OS operation, or a time limit on
input preparation/parsing/minimization. Orphan descendants' wait status belongs
to the OS reaper. O7 requires a target supervisor/container/scheduler acceptance
test for those broader cases; do not infer whole-cycle guarantees from O1.

`run.stdout.log`, `run.stderr.log`, and execution-failure `run.failure.txt` are
written in the prepared case. Log recording is best effort if the filesystem
itself fails; the original exception still propagates. All-sky disposable cases
retain a small failure record outside the large temporary case before cleanup.
Failed runs do not produce an accepted analysis artifact. Disk quota, retention,
and arbitrary wrapper output volume remain deployment responsibilities.

Live closures acquire an advisory POSIX lock beside the canonical case path
before write/run/parse. An overlapping caller is rejected. The lock inode is
retained after release to avoid an unlink/reopen race; put both case and lock
inside a disposable workspace when cleanup is required. LC05 allocates a unique
run child beneath `CASE_ROOT` and records the actual namespace. Filesystem lock
semantics on the target shared filesystem are part of O4/O7 validation. Low-level
`write_rttov_case` users still own their write/execute lifecycle.

## Meaning of existing inputs and gates

The historical LC05 runner remains a case-specific stress experiment, with its
fixed observation slot, input assets, iteration settings and explicit 300-second
representativeness allowance. It is not a generalized operational cycling CLI.
Geometry and surface inputs already propagate through the underlying clear and
all-sky APIs; omission uses and reports the reference fixture. Their availability
does not establish that the historical runner used actual location-specific
conditions. Its full-domain analysis supports observation time 0 or 1 of a
single fixed-forcing microphysics step.

`evaluate_artifact_gates`/`accepted=True` assess evidence consistency: descent,
innovations, finite/physical-state diagnostics, final audit and the declared
conservation mode. They do not approve timing, host writeback, observation
representativeness or forecast skill. The public runner ends at report/NPZ
production. A successful C ABI return is required before caller-owned buffers
can be committed to host state; error returns are not a rollback guarantee.

M1 applied ten-minute transfers, M2 first-negative QIB operands, the particle
number unit contract, D4 operation ordering, and actual forecast impact remain
separate open scientific work in [Science status](../harness/evidence/SCIENCE_STATUS.md).
O–A or objective reduction on assimilated observations does not close O8.

## Verification record

On macOS, Python 3.10.11 / PyTorch 2.13.0 / NumPy 2.2.6, the local oracle
returned **1,110 passed / 26 skipped**. The focused lifecycle/parser run had
35 passes, and the caller/related regression run had 25 passes. These subsets
are included in the full count; do not add them to it.
After that full run, one additional LC05 reader-failure regression passed:
two invocations sharing a case root retain distinct run namespaces and release
both output locks. It is not included in the 1,110 count.

The existing RTTOV case-writer suite returned **57 passed**, including actual
clear/cloud executable calls, reference BT, and differentiation through the
real K matrix. It is also part of the full oracle count. This is fixture-based
live-library validation, not an operational real-observation assimilation,
WRF/MPI cycle, forecast-skill comparison, or target-scale performance result.

Independent Luna xhigh GREEN and RED agents reproduced surviving descendants
before the fix. The RED post-fix probe confirmed group cleanup on timeout and
early wrapper exit, nonzero/freshness rejection, interruption cleanup, spawn
and log-open errors, successful parsing, and separate-closure ownership.
It also deliberately detached one synthetic child: that child escaped the
group and was explicitly cleaned by the probe. This observation supports the
O7 limitation, rather than a claim to arbitrary process-tree containment.
Raw source snapshots, probes and logs remain outside the wiki under
`graphify-out/operational-boundary-20260906/` in the development checkout.
