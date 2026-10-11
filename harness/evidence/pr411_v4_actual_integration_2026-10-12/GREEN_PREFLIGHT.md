# Green preflight: one retained Jul19 V4 integration

The single predeclared V4 call is ready to launch. I checked the bound case,
retained native arrays, original L1B binding, current source pins, 33 declared
execution assets, and the fresh output root. No model, RTTOV, optimizer or
native-model call was made for this preflight.

The V4 intake is observation-bound for the retained 2025-07-19 case at nominal
05:56 OBT/model time. The new producer is explicitly PR411; it uses the PR403
wire shape because unchanged V4 validates that format, and records that it is
not a historical PR403 run. Nine restored GK2A AMI LA files match their old
hashes. The result, case and private decode receipt all point to the same
hash-bound patch payload; the V4 intake has all seven analysis channels DQF0
and the original reader's GEOS/time metadata. Pixel UTC remains uncertified.
No other sensor, phase, L2, model or reanalysis input is bound.

The native input is the already completed 1x1 mp337 run, case
`PR411_JUL19_REAL_V4_INTEGRATION`, at column `(j=86,i=48)` with saved background
05:55:40 and a 05:56:00 local 20-second slot. The fresh V4 NPZ contains the same
71 arrays as the earlier Jul19 core intake. Its source native forecast and
run receipts are present; no native model launch is part of the proposed
command.

All six V4/legacy source bindings match `PREDECLARED.json`. All 33 external
fixture, executable, coefficient, hydrotable, and direct-library assets match
their recorded path, size and SHA-256. The paired GK2A AMI coefficient is
`rtcoef_gkompsat2_1_ami_o3co2.dat` (`73401691…b54a7b5`), and the selected
`rttov_test.exe` is `0909d289…bc7692fd`; both agree with the previous actual
Jul19 RTTOV asset receipt. The template's saved hydro files are initialized
for the fresh copy and then rewritten from the current State by the existing
cloud writer at each H call. The direct dylib hashes cover the non-system
linked libraries; `/usr/lib/libSystem.B.dylib` is provided by the OS and was
not file-hashed. No runtime loaded-library map is claimed.

The output root
`/Users/yhlee/KDM6AD-k/host/research_evidence/pr411_v4_actual_20261012/runs/PR411_REAL_V4_JUL19_20261012_01`
is absent. The planned command uses the pinned Python executable from
`PREDECLARED.json`, the V4 `run_case_analysis.py` entrypoint, bound
`INTAKE.json`, bound private NPZ, and the paired AMI template:

```sh
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_THREAD_LIMIT=1 VECLIB_MAXIMUM_THREADS=1 \
PYTHONPATH=oracle /private/tmp/KDM6AD-research-rc-20261007/env/bin/python \
  harness/evidence/pr407_native_saved_time_bound_2026-10-11/run_case_analysis.py \
  --intake-manifest harness/evidence/pr411_v4_actual_integration_2026-10-12/INTAKE.json \
  --intake-npz /Users/yhlee/KDM6AD-k/host/research_evidence/pr411_v4_actual_20261012/inputs/core_jul19_bound_v4.npz \
  --output-root /Users/yhlee/KDM6AD-k/host/research_evidence/pr411_v4_actual_20261012/runs/PR411_REAL_V4_JUL19_20261012_01 \
  --template-fixture /private/tmp/KDM6AD-viirs-native-run-20261007/comparison/results_failed_native_artifact_diag_055540_055800_retry2/case_00
```

It retains
the existing `max_iter=3`, default nominal `max_eval=3`, one spawned worker,
single-thread settings, 20-second local step, T/Q controls, fixed physics,
seven all-sky AMI channels, sigma 1 K, zero bias, prior and final audit. The
legacy `huber_delta_K` metadata label stays unchanged; normalized Huber
`delta=1` is dimensionless. Strong-Wolfe line search may exceed nominal
`max_eval`; do not expand the declared budget or retry, and record actual call
counters. The native `MPI`/WRF executable is not invoked.

The fixed run settings and source/asset hashes establish a bounded diagnostic
execution path. They do not establish strict convergence, pixel-time match,
IR133 upstream SRF identity, scientific acceptance or forecast skill.
