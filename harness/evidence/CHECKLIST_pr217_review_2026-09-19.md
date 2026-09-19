# PR #217 follow-up — rate resolution checklist

Baseline: merged `c5d1a218217ef3d691e7f6441da92e91c227b9b6`.
Scope: selected process-rate and state sensitivities through the first-order
GK2A–RTTOV chain. Previous state-resolution, alpha-zero primal and asymmetric
channel checks remain closed in their declared scope.

| Order | Task | Acceptance evidence | Status |
| --- | --- | --- | --- |
| 1 / B1 | Rate output-spacing gate | Reuse state spacing rule for selected rates; equal nonzero AD/FD at one spacing cannot produce aggregate verified status; preserve state-specific results | Verified locally |
| 2 / B2 | Actual consumer regression | Reproduce before/after with real attribute_process and injected diagnostic rate; zero/resolved and finite/primal/branch precedence remain correct | Before/after reproduced; consumer regression passed |
| 3 / B3 | Applied amount to final response | Reuse existing active applied-path evidence; distinguish a resolved applied derivative from a final response erased by a subsequent boundary | Evidence inventory; representative coverage remains open |
| 4 / B4 | Actual auxiliary/unit/transport evidence | Retain source requirements for actual RTTOV auxiliaries, physical number units and nonzero M1 transport | Open; prior evidence reused |
| Final | Review and checks | Green/Red independent review, focused execution and graph refresh | Green/Red passed; results below |

## Direct pre-change reproduction

The unchanged real `attribute_process` consumer was run with the normal warm
fixture and a diagnostic-only praut injection. All physical model calculations
remained real KDM; the injected diagnostic rate is an intentionally synthetic
negative control, not a claim of a faulty physical rate.

At epsilon=1e-4, r_minus=1e-5 and r_plus=nextafter(1e-5,+inf), AD=FD=spacing
=8.470329472543003e-18. State resolution fields are empty, alpha-zero primals
match, yet aggregate status is `verified_selected_direction`.

Local reproduction script/results:
`graphify-out/pr217-review-20260919/rate_resolution_probe.py` and `before.json`.

## Preserved scientific boundaries

- The selected freeze NC→NCCN return diagnosis retains the original epsilon=1e-4
  mismatch and independently resolved larger-epsilon comparisons. It is not
  blanket physical number conservation or proof of every internal branch.
- An active applied-process derivative may be nonzero even when a downstream
  evaporation/reclassification/cap makes a final-state derivative zero. Do not
  require artificial nonzero final responses from every species.
- Actual observation auxiliaries, physical number-unit contracts, nonzero M1
  transport and N1 sensitivity convergence retain their existing open gates in
  the main hydrometeor sensitivity checklist. No f32 or ABI change is needed.

## B3 — selected downstream-zero check

Extended the existing CCN-return regression to include post-evaporation nc in
both VJP and genuine forward-AD vectors. Its derivative is zero while incoming
nc and outgoing nccn derivatives are the same nonzero value. The exact applied
return identity and unchanged recorded branches are already checked. Thus a
zero final NC response has an identified downstream cause, not an independence
claim. This is one selected boundary; representative process coverage remains
open. Focused execution: 1 passed, 18 existing Torch deprecation warnings (1.64s).

## Baseline CI recheck

Queried check-runs for the **merge commit c5d1a218**, not the PR head. All five
are now completed/success: port run35416662022 (Linux and macOS), oracle
35416662069, harness35416662014 and changed-path detection. This closes the
previous pending-CI observation for that baseline, not for this follow-up.

## Independent before/after comparison

Re-ran the same injected real consumer after the rate-spacing change: aggregate
status is now `unresolved_output_resolution`; AD, FD and spacing retain the
exact value 8.470329472543003e-18, state resolution fields remain empty, and
alpha-zero primal equality remains true. Stored in `after.json` beside the
pre-change result.

Loaded the baseline module directly from git c5d1a218 and compared all 18
process/regime combinations against the modified module. State/rate AD and FD
mappings, state-field classifications and aggregate classifications are
unchanged. Artifact: `graphify-out/pr217-review-20260919/matrix_comparison.json`.
This preserves selected fixture evidence, not all possible numerical inputs.

## Final verification

- Reused `_fd_ulp_bound` for selected process rates; no new tolerance or scale
  multiplier. One shared field classifier preserves finite/primal/zero/branch/
  resolution/agreement precedence with the existing rate and state tolerances.
- JSON exposes rate spacing bounds, unresolved names and individual statuses;
  Markdown displays unresolved rate names and points to JSON for exact detail.
- Related five-file tests: **55 passed, 18 existing Torch deprecation warnings**
  (6.46s). Separate CLI consumer: **1 passed** (0.88s).
- Green and Red independently reviewed the final change and ran process/CLI
  checks: **22 passed**, overlapping the above tests; do not add this count.
- `git diff --check` passed. No physics, f32 or ABI changes. B3 is selected
  boundary evidence; broader representative coverage and B4 remain open.
