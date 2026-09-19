# PR #215 review resolution — ordered checklist

Baseline: merged main `ca23480b6dc005771024ea161698ba64faa2e136`.
Scope: differentiable KDM hydrometeor processes through first-order GK2A–RTTOV
assimilation. This checklist resolves the 2026-09-19 review without reopening
already verified subcases or treating forecast skill/cycling as completion gates.

Work in the order below. Close only the stated acceptance condition with an
executed result or an explicit evidence boundary; do not infer completion from
code changes, test counts or unchanged divergence locations.

| Order / ID | Task | Acceptance evidence | Status |
| --- | --- | --- | --- |
| 1 / R1 | Cross-tree nonfinite rejection | NaN and ±Inf in either implementation's forward/VJP/JVP fail, including allowed-divergence slots; portable injection tests execute without a native build | Local verification passed; new-build CI pending |
| 1 / R2 | Bounded divergence regression | Smooth parity and known divergence remain distinct; allowed slots have finite, measured signed values/scales and magnitude regression; remove unconditional subgradient claims | Local verification passed; new-build CI pending |
| 1 / R3 | Independent LCC CI check | At least one CI job installs/imports pyproj and runs the existing synthetic 900×900 comparison without optional dependency skipping | Local check passed; CI pending |
| 2 / R4 | Process state coverage | Explicit checked/unchecked outputs; include deposition qi, riming qc/qi/nc/ni, freeze qc/qi/nc/ni in selected checks; retain unresolved FD/branch classifications rather than weaken tolerances | Pending |
| 3 / R5 | Melt→profile→BT/cost | Existing melt control and fixture, fixed-K mock, nonzero genuine forward AD/reverse AD/FD; state clearly synthetic, first order and separate from live RTTOV | Pending |
| 4 / R6 | Actual RTTOV auxiliaries | Source/applied pressure, upper profile, viewing geometry, surface and UTC; fixture substitutions remain explicitly partial | Open; existing asset inventory reused |
| 5 / R7 | Physical number and mass measure | Resolve host/kernel unit boundary before physical number-budget claims; distinguish process source/sinks from transport conservation | Open scientific contract |
| 5 / R8 | M1 nonzero applied transport | Matched-source binaries, nonzero departure/arrival, actual ledger and neutrality evidence; zero transport is insufficient | Open external prerequisite; existing Xcode license blocker retained |
| 6 / R9 | Refinement and representative coverage | Same final time, state/tangent/objective comparisons with actual subcycles and recorded branch changes; declare process×regime×control×output domain | Partial; N1 experiment is not convergence proof |
| M / R10 | Metadata and progress claims | PR #215 is merged; distinguish dated local/CI counts, avoid unsupported overall percentages | Corrected PR description; historical records retained |

## Evidence log

- Confirmed GitHub PR #215 is merged: `2026-09-19T00:28:42Z`, merge commit
  `ca23480b6dc005771024ea161698ba64faa2e136`. Historical open/CI-pending notes
  remain dated records; the PR description will be corrected.
- Follow-up branch: `codex/ad-gate-finiteness`. Small reused Green/Red teams use
  Luna high. Production f32 equations and ABI are outside this correction.

### R3 — independent projection dependency

- Pinned `pyproj==3.7.1` in oracle CI, mandatory version import and explicit
  LCC test invocation. Optional local importorskip is preserved; missing CI
  dependency fails before it can skip.
- Local isolated install `/tmp/kdm6ad-review-pyproj`, Python 3.10:
  `PYTHONPATH=/tmp/kdm6ad-review-pyproj:$(pwd) python3 -m pytest -q
  tests/test_gk2a_l1b.py::test_lcc_matches_pyproj_if_available`
  from oracle: **1 passed** (6.41s). The new Linux CI run is pending.
- PR #215 description now records its actual merge rather than saying open.

### R1/R2 — measured local comparison (before magnitude pinning)

RED executed the existing library without rebuilding. Artifact
`graphify-out/goal-ad-gate-finiteness-20260919/red/cross-tree-ad-gate-baseline.json`
records the fixture, seed, signed C++/oracle values and library SHA256
`e0576f0d29613ee4752e06d4887126e03f5d8b6089ad83d8052cd3cfea9d2cbe`.
The build cache is unavailable, so this is a measured artifact, not a newly
provenanced source build. New Linux/macOS CI must validate the source build.

Smooth dt=20 maximum symmetric relative errors: VJP `5.1521e-8`, JVP `4.9687e-8`.
At dt=300 VJP bg[0] is approximately `4.8909423e13` versus zero; JVP qc/qr/nc/nr
have sign-changing differences. Those differences are not AD parity or proof
of valid generalized derivatives. The previously allowed ni[0] is zero in
both products in this measurement.

### R4 — preflight only

`graphify-out/pr215-review-20260919/state-field-preflight.json` records the
previously unchecked cold-fixture donor/receiver fields. All added fields have
AD=FD=0 in this fixture. Their inclusion must be reported as a tested zero
response, not nonzero pathway evidence or structural independence. Freeze
retains its existing temperature output-resolution limitation.

### R1/R2 — correction verification

- C++ and oracle forward/VJP/JVP arrays are checked for finiteness. `_rel`
  rejects nonfinite operands before any footprint exception and uses scaled
  finite arithmetic to avoid overflow in sum/difference.
- Portable producer stubs inject NaN/±Inf through the real Python product
  boundaries; they do not claim to exercise the native ABI.
- Allowed dt=300 products retain explicit measured signed C++/oracle values
  and relative-error baselines, checked at rtol=1e-6, atol=1e-12. This is a
  numerical regression contract, not physical accuracy or subgradient parity.
  Both improvement and deterioration of the snapshot require review.
- Parent cross-tree file: **33 passed** (1.10s, including two real-library
  cases). Subsequent actual-footprint injection tests: **6 passed** (0.67s):
  finite1e300, sign flip and doubled magnitude on either side are rejected.
  The 31 portable tests in the first selection do not need a library.
- Green/Red review completed on the gate; duplicated allowed tables and a
  signed-zero bitwise requirement were not added. The one baseline table is
  the reviewed regression contract; the declared f64 absolute tolerance is
  retained. New source-build CI remains pending.
