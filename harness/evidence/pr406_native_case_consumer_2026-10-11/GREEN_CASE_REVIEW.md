# Green review: PR406 native case consumer

## Disposition

Green review found the v2 intake, capture adapter, driver, packet report, and
case checklist consistent with the demonstrated scope below. No actionable
internal inconsistency remains in the reviewed paths. The disposition is
bounded to receipt linkage, one same-date native-core replay, case admission,
and synthetic adapter boundaries; it is not a scientific acceptance review.

## Receipt linkage and preserved history

The original `intake_native_case.py` remains byte-identical to the v1 source
pinned by the historical v1 manifest (SHA-256
`c8dac976132f6ec88bd3080896a275a7b6fd1c56ad51071cae99484c24050780`). The
corrected consumer is `intake_native_case_v2.py`. Actual PR397 producer
`run_identity.json` and `experiment_valid.json` omit run IDs. V2 requires an
explicit completion-receipt path and SHA for every ready case; it checks the
receipt's run ID and directory, binds both producer-receipt hashes, requires
launcher status zero and a completed valid 1x1 run, and rejects an embedded
producer run ID if it disagrees. It does not edit producer receipts or infer
archive identity from a basename.

Synthetic regressions cover the historical missing-ID receipt fallback,
missing completion receipt, changed receipt hash, wrong receipt run ID,
identity run-ID disagreement, and invalid completion/control metadata. V2
focused consumer/adapter tests passed 24 tests. The portable oracle contract
facade passed 14 tests; it covers portable case, receipt, pending and L1B
contracts, not private native data or analysis execution.

## Demonstrated data paths

The fresh v2 Jul19 record is `CORE_REPLAY19_V2_INTAKE.json` with comparison
receipt `CORE_REPLAY19_V2_COMPARISON.json`. It uses the pre-existing PR397
completion record. It selected only saved frame index 0 at
`2025-07-19_05:55:40`. All 70 common array keys compare exactly against the
same-time first slice of the historical PR395 eight-frame fixture; 42
time-dependent arrays require that singleton-versus-first-slice comparison.
The v2 NPZ contains 71 arrays, including one additional background dry-density
array, and has SHA-256
`e8976c92ff3b08327822bba8aeab49a7f123f453afd134c1bc5febdc2fd580b3`.

This is a same-date core-intake readiness replay. The case has no bound L1B
observation: `load_bound_intake` rejects it with the default
`require_observation=True`, and accepts it only with the explicit readiness
override `require_observation=False`. The PR397 completion receipt itself
records launcher exit 0 and `model_completed=true`, but also outer-harness exit
120 with an unconfirmed cause and `science_accepted=false`; the replay does not
resolve or override those recorded limitations.

The fresh v2 July20 and July21 cases retain their own nominal background times
and original PR403 result/payload/metadata bindings. Both return
`PENDING_NATIVE_INPUT`; neither opens a forecast or creates a private NPZ. The
first ready date can proceed independently when its native archive is
available. Neither new-date native state/forcing nor a July20/21 analysis has
been demonstrated.

## Adapter/driver consistency

The adapter and driver import v2. The adapter checks case/run/time identity,
the selected native state and forcing against the preserved State/Forcing
objects, positive f32 `[39]` dry mass, native pressure geometry, original L1B
payload/result/reader metadata, DQF0 channel values, and the declared 2.5 km
point radius. The driver refuses a noncanonical AMI template before creating
output, uses the established one-step 20-second T/Q contract, and carries the
observation slot as a local model slot rather than claiming a saved host frame.
Its tests use synthetic NetCDF and receipts, then stop before M, H, or the
optimizer. Thus they verify intake/admission wiring, not new-date RTTOV or
geophysical analysis.

The user-owned assessment remains 79/100 on the same rubric. External SST,
MLS, VIIRS and L2 products remain deferred; no external model or reanalysis
input was introduced. The checked source graph now includes the v2 intake,
adapter, and driver symbols; the semantic fragment alongside this review
records the evidence relationships and bounded limitations.

## Validation record

Focused local command, with one-thread environment:

```sh
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_THREAD_LIMIT=1 VECLIB_MAXIMUM_THREADS=1 \
  /private/tmp/KDM6AD-research-rc-20261007/env/bin/python -m pytest -q \
  harness/evidence/pr406_native_case_consumer_2026-10-11/test_native_case_intake.py \
  harness/evidence/pr406_native_case_consumer_2026-10-11/test_case_analysis_adapter.py
```

Result: **24 passed**. The portable contract command
`.../env/bin/python -m pytest -q oracle/tests/test_native_case_consumer_contract.py`
returned **14 passed**. `/opt/homebrew/Caskroom/miniforge/base/bin/ruff check`
on the v1/v2 consumer, both test modules, adapter, and driver passed;
`python3 -m py_compile` for changed Python modules and `git diff --check` also
passed. The exact Jul19 replay, comparison, pending cases and receipt SHA
bindings are recorded in the packet JSON receipts. No model integration, H/M,
optimizer, new-date native read, or satellite-data acquisition was run here.

The Graphify update rebuilt the structural graph (18,005 nodes / 30,919 edges),
and a focused query now returns the v2 intake/adapter/driver nodes and their
producer-to-consumer functions. Documentation semantics are captured in
`graphify-out/pr406-green/semantic.json` because the generated source graph
does not encode these bounded evidence/qualification relationships by itself.
