# Observation submission omission review

Reviewed 2026-10-09 against:

- `harness/evidence/REPORT_pr391_review_resolution_2026-10-09.md`
- `harness/evidence/CHECKLIST_pr391_review_resolution_2026-10-09.md`
- `harness/evidence/DECISIONS_pr390_followup_2026-10-09.md`
- `harness/evidence/pr391_observation_scope_2026-10-09/summary.md`
- `harness/evidence/pr391_observation_scope_2026-10-09/receipt.json`

## Result

No material observation-scope omission found in the main report, checklist, or
decision update. Each keeps the physical matchup and R2 open. The report's
observation section links the detailed summary; the decision update restates
the fixed candidate and the still-open clock, QA, parallax, and footprint
conditions.

The following distinctions are present and correctly bounded:

- VIIRS phase 1 / CloudType 2 is a cloud-top retrieval category, not proof of a
  warm, single-layer, nonprecipitating full native column. The report preserves
  the model-clear versus retrieved-liquid difference as a question, not as a
  KDM cause, QA pass, or satellite truth claim.
- Corrected stored-byte QA remains separate from scientific QA approval. The
  prior range-mask false-fill count is not repeated as a real fill population;
  the fixed selected byte is 0 and QA encoding/approval remain open.
- The VIIRS time is a product-anchored scan bracket, not a per-pixel time.
  AMI numeric epoch and pixel UTC remain unresolved; the conditional legacy
  epoch interpretation is not promoted to UTC evidence.
- Nominal-center proximity and provided parallax coordinates are kept distinct
  from footprint overlap, cloud displacement, datum certainty, and column
  reassignment. The candidate and native cell stay fixed across scenarios.
- The original failed 358-minute native run remains invalid/diagnostic. The
  supplemental local 20-second KDM endpoint is explicitly not an observation
  pixel-time or valid forecast matchup; the original observation stays frozen
  for that local operator test.
- The clear-state result is a one-column, one-snapshot diagnosis. Both main
  report and decision update state that it does not attribute earlier
  advection, mixing, flux, initialization, or subgrid causes. `q/qs` remains
  separate from `e/es`; no all-column or event-cause claim is made.
- The observation receipt says its forecast payload was not present or
  rehashed **in that bounded packet review**. It does not claim the payload is
  unavailable globally. The main report can cite the team's separate
  before/after 2.54 GB forecast hash verification without conflict. ZIP
  integrity is not represented as full-model validation.

## Actionables

No blocking omission found. One precision edit would make the 20-second pairing
harder to misread: the main report does not name the source snapshot time. The
linked T/Q response report identifies the source as the failed-run forecast
`klfs_lc05_fcst.202507190000`, `ti=0`, at model time `2025-07-19_05:55:40`; the
local 20-second KDM endpoint is therefore `05:56:00`, compared against the
unchanged AMI `(row=320,col=48)` receipt. Suggested sentence in report section 5:

> The KDM step starts from the failed-run `ti=0` snapshot at 05:55:40 and ends
> at 05:56:00 while holding the AMI row 320/column 48 observation fixed; this
> is a fixed-time what-if and does not establish VIIRS/AMI pixel-time
> collocation.

This preserves the existing statement that the local endpoint is not a
certified pixel-time/native-forecast matchup. The exact time identity is in
`harness/evidence/pr391_tq_response_2026-10-09/REPORT.md`, lines 5–7, and the
observed pixel identity/time caveats are in the linked observation summary.

No web research, new data access, geometry calculation, or Huber calculation
was needed for this omission check.
