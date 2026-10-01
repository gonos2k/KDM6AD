# Isolated NCCN return-arithmetic candidate

Baseline: `f88bb977` (PR #349). Main's production runtime, defaults, ABI and the
column runner are unchanged. This PR supplies an **experimental patch**, focused
boundary checks, and measured baseline/candidate results. It does not adopt the
patch or approve physical number units, observations or operations.

## Bounded result

The unchanged external-path command still fails with the original library and
exits 1. With the separately built candidate library, the **same input-selected
column, direction, h=1e-4 and thresholds** passes and exits 0. All 12 field FD
checks pass; NCCN JVP and FD are both zero. The other 11 forward field arrays are
bit-identical to the baseline. Two clean-worktree candidate executions have
identical metadata and all 14 NPZ arrays are raw-identical. The second execution
uses the same library; it is not an independent second build or host forecast.

The retained column is zero-based `(3,272)`, frame 1, 39 native levels. It was
selected by maximum input ice before observing the numerical result in PR #348;
it was not replaced with an easier column. The command reconstructs an offline
snapshot, not exact native host-staged operands. No new native or RTTOV run was
performed. [Run receipts](nccn_return_candidate_runs_2026-10-01.json) retain the
source/library/input hashes, unmodified configuration and all numerical checks.
[Baseline failure arrays](nccn_return_baseline_failed_2026-10-01.npz) and
[candidate pass arrays](nccn_return_candidate_passed_2026-10-01.npz) include the
actual inputs, endpoints and AD results.

## Candidate and numerical limits

With the same entry density `rho_d = rho_m/(1+qv_entry)`, capture the actual live
`N_in = rho_d*n_in` tensor before kernel updates. The candidate returns

```
delta = N_out - N_in
n_out = n_in + delta/rho_d       if abs(delta) <= 0.5*abs(N_in)
n_out = N_out/rho_d             otherwise
```

The patch changes only the opt-in dry-number **fp64 NCCN return** in Python and
C++. Other number fields and f32 arithmetic are unchanged. It adds no new ABI
selector, process limiter or detached AD path. `delta` includes all executed
CCN changes, including entry clamps; it is not a new independent measurement of
one physical process.

At zero change, the incremental expression preserves the input exactly without
an unnecessary multiply/divide round trip. The [level-10 scalar fixture](nccn_return_level10_2026-10-01.json)
rebuilds both density and volume entry for each qv endpoint and reproduces both
saved direct-return hex words. The old minus endpoint differs by 1 binary64 ULP,
producing FD 0.002384185791015625 at h=1e-4. The failed record is preserved.

Plain increments are insufficient near complete removal: one declared boundary
case yields a plain-increment residual `0x1.0000000000000p-21`, while direct
return gives `0x1.2492492492492p-22`. The fallback retains the latter.
The arithmetic switch itself can differ by **1 ULP** around the half-change
threshold. The tests explicitly record a crossing-stencil FD mismatch; they do
not certify smoothness or relax a failed gate. Same-branch analytic/FD checks
are separate. These limits are a reason to keep this a candidate experiment,
not silently replace the production map.

## Nonzero change and checks

The actual retained-column pass is an inactive NCCN identity witness, not an
active CCN-process derivative certificate. A separate [synthetic warm three-layer
kernel probe](nccn_active_return_probe_2026-10-01.json) uses real C++ kernel
updates, nonzero NCCN changes, 1% NCCN/qv/nc directions and a signed NCCN-only
VJP seed. Baseline FD relative error is 5.17e-11 and duality 1.69e-16;
candidate values are 7.71e-11 and 3.39e-16. This is a declared synthetic kernel
case, not another native weather observation or full-Jacobian certification.

The local environment is Python 3.10.11 / Torch 2.13.0; the new library was
built with AppleClang 21, Release, and `-ffp-contract=off`. The same linked
Torch installation is used for both local libraries; this is not certification
of other platforms.

Local executed checks: 11 boundary tests; 9 existing runtime/runner tests on the
patched oracle; freshly built C ABI target, 1 test. Focused tests cover zero,
nonzero additions/removals, analytic JVP/VJP, near/full removal and threshold
sides/crossing. They are distinct test sets, not independent meteorological
cases. Current main CI and these local candidate checks must not be conflated.

## Reproduction

Use a separate checkout at `f88bb977`; do not patch the operational install.
Apply `harness/nccn_return_candidate.patch` from this PR and build the existing
`kdm6_c` target in a new build directory with the usual Torch CMake prefix:

```sh
git apply /path/to/nccn_return_candidate.patch
cmake -S libtorch -B /path/to/candidate-build -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH=/path/to/torch/share/cmake
cmake --build /path/to/candidate-build --target kdm6_c test_c_abi -j 4
ctest --test-dir /path/to/candidate-build -R '^c_abi$' --output-on-failure
```

Use the [existing command](../../docs/NORMALIZED_DRY_COLUMN.md) with external
retained-input and library paths, frame 1 / i 3 / j 272. The baseline library
produces failure; the candidate library produces the bounded pass. Always choose
a new result directory. Both library hashes and applied patch must identify the
numerical map; the selector/dry-number options alone do not identify this
experimental return arithmetic. The local clean candidate source commit is
`963e7d7`; it is not an adopted main revision. Exact baseline plus the published
patch reproduce its source changes. The retained NetCDF and original baseline
binary remain private local inputs; they are not included in the public clone.

Run public scalar tests from the repository root:

```sh
python3 -m pytest -q oracle/tests/test_nccn_return_candidate.py
```

The active-kernel probe is a small developer helper, not a new product entry
point; `harness.nccn_active_return_probe.probe(library_path)` returns its result.
The [three-item checklist](CHECKLIST_pr349_followup_2026-10-01.md) is closed for
this isolated diagnostic scope. S2/S8, general branch accuracy, production
adoption, host/MPI/restart and observation approval remain unresolved.
