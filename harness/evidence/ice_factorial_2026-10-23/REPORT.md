# Ice-only factorial and full-domain preparation — 2026-10-23

Base: `f694051c6d32d4ce867a3363d17c119b1cf998ab` (#435 merge on the feature
branch). This change first corrects the source-audit bottom-departure sentence;
the #435 numerical captures/results and its completed milestones are unchanged.

## Completed one-column experiment

The same 39-layer #435 request was evaluated with raw/normalized first ice
handoff crossed with Legacy/actual-departure arrival. Main rain/snow/graupel
sedimentation remains Legacy. A private, four-TU overlay and known research
archive were used; no operational source, ABI, install or default was changed.
The alternate arms intentionally change the experimental ice map.

There were **nine CLI calls**: unset baseline, then trace off/on for each arm.
All four off/on response pairs are byte-identical. `raw_cap` and unset baseline
match the old response SHA `93a357b011bab8724a1ff84ce278927abc24f88d9b5f42e1d10f94fa3949cf8d`.

| Arm | QI state change + bottom departure | Raw total water change | Applied total water change |
| --- | ---: | ---: | ---: |
| raw_cap | -1.2979597722250025e-3 | -1.2985492047658913e-3 | -1.299094197388839e-3 |
| norm_cap | -4.260488185124349e-20 | -8.285370684791286e-7 | -2.6329908538302776e-6 |
| raw_actual | -1.199620578517985e-19 | -5.894325409404607e-7 | -6.698501538209663e-7 |
| norm_actual | -4.25784120717404e-20 | -8.285370684791286e-7 | -2.6329908538302776e-6 |

All entries are nominal state-inventory kg/m2. QI bottom arrival/departure are
zero for this column. Raw work/attempted-flux units and NI host payload basis
remain conditional. Counterfactual ice balances are at roundoff scale, while
later microphysics/cleanup residuals remain. The experiment does not certify
physical water closure of the full kernel.

`norm_cap` and `norm_actual` have identical full returned states at this point;
their recurrence is not generally equivalent. The QI interaction is
-0.0012979597722250023 kg/m2. Raw-actual and normalized-actual heating profiles
differ (maximum H_RATE difference about 4.84041e-4 K/s), showing why preserving
an inventory alone cannot select the velocity treatment.

The result JSON stores all four returned state/finish profiles, field ledgers,
stage changes and factorial contrasts. Full request/response and trace files
support public arithmetic replay. No new RTTOV call, optimization or alternate-
map JVP/VJP/FD validation was performed, and no candidate was selected.

## Completed full-domain preparation, not execution

- Genuine MP137 endpoint checkpoint: `2025-07-19_00:00:40`, SHA
  `7a353f1fa4f6636864ac169c9ee8d16869d1f38c8e998762c19659404cbb9c8e`.
- Full native grid: 234x282 columns, 39 mass/40 interface levels, including
  stored edge cells. No external/reanalysis or historical MP37 KO substitution.
- Prepared binary64 packet: 129 chunks, 65,988 unique columns, zero missing or
  duplicates, 330,922,260 bytes. Stored dtypes/values/hashes were reread; 387
  samples matched the public 1-D prep within its declared fp64 comparison gate.
- Explicit source checks: MP_PHYSICS=137, USE_THETA_M=1,
  HYPSOMETRIC_OPT=2, nonhydrostatic, exact grid and actual Times.
- Raw negative NC=1, NI=6, BG=2 are counted and retained. Physical number-basis
  admission is false; no numerical correction of saved inputs is hidden.
- Standalone batch tool compiled against the experimental archive. Eight tiny
  B=1/B=2 duplicated-column calls match state/precipitation bits across all four
  arms. This is a transport smoke, not new regional output.
- Dry-run plan checks every chunk hash/shape/index. It specifies 512 columns
  per batch (last 452), 129 batches per arm, 10 single-thread workers per arm,
  arms sequentially. A fake-protocol parallel test exercises stable orchestration
  without KDM calls. **Full-domain KDM calls: zero.**

The full-domain packet is a new endpoint-initialized offline split-physics
experiment, not an actual next-MP snapshot or host forecast/cycle. Fixed
batching is part of its map identity because global substep maxima depend on
batch composition. Boundary cleanup/RK/radiation/RTTOV are outside this plan.
Prepared data stays private; public inventories and hashes identify it.

## Evidence map

- `native39_factorial.json`, `campaign/`: executed same-column four-arm result,
  original off/on response bytes, direct ice transfers and full water-stage data.
- `overlay_build_receipt.json`: original/experimental source and build identity;
  default operational map unchanged, experimental ice map deliberately varies.
- `full_domain_preparation.json`, `post_preparation_source_preflight.json`:
  offline endpoint packet and post-write/source validation.
- `full_domain_readiness.json`, `batch_plan.json`: bounded execution/resource
  plan, complete coverage, no full-domain execution or timing claim.
- `full_domain_run_configuration.json`: explicit dt=20 s and namelist-bound
  ncmin_land=ncmin_sea=10, fixed chunks and 10 single-thread workers. Public
  local paths are redacted; the actual private command configuration is ready
  but has not been executed.
- `../ice_factorial_batch_smoke_2026-10-23/`: standalone batch build and tiny
  protocol smoke receipts, plus the fixed four-arm full-domain dry-run plan.

The earlier unpublished f32 storage draft was rejected during parent review.
The final packet preserves fp64 prep outputs, performs post-write readback and
checks the reread values against the 1-D map. No draft data enters the plan.
Two earlier batch-tool prototype/rebuild rounds used another 16 sample calls
before the final eight-call capture; those raw files stay private and are not
mixed into the final smoke results. Including the nine-call factorial, there
were 33 single-column/duplicated-column sample calls and zero full-domain calls.

## Local validation

The focused factorial, packet preparation and batch tests pass, including
public response/accounting replay, a nonzero-bottom-arrival witness with
nonuniform weights, exact binary64 packet storage, source-option mutation
rejection, and bounded parallel orchestration using a fake executable.
The full local Harness completed with **2,672 passed, 59 skipped,
309 deselected** before the final extra public batch/sample replay test;
that added check also passes in the final focused suite. Native compilation
and packet generation are local evidence, separate from public arithmetic CI.
