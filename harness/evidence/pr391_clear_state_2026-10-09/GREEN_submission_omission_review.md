# Green submission omission review — PR391 resolution packet

Date: 2026-10-09. Scope: final read-only comparison of the current report,
checklist, decision update and wiki summary against the saved receipts and
completed Green/Red/Cost reviews. No forecast, RTTOV, MPI, extinction or model
calculation was repeated.

## Findings for the final edit

| Priority | Location | Evidence and counterexample | Classification / suggested fix |
| --- | --- | --- | --- |
| P2 — resolved | [REPORT_pr391_review_resolution_2026-10-09.md](../REPORT_pr391_review_resolution_2026-10-09.md#L183) | “Current columns are clear” pluralized the result. The saturation receipt contains 39 levels for one saved `case_00` profile and one selected native column (`j=86,i=48` zero-based); no multicolumn saturation census was made. | The report now says “The selected saved column is clear under the diagnosed saturation tests.” Scope is accurate; no calculation was needed. |
| P2 — resolved | [CHECKLIST_pr391_review_resolution_2026-10-09.md](../CHECKLIST_pr391_review_resolution_2026-10-09.md#L19) | Local C2 is titled cloud fraction/diameter/RTTOV derivative boundary. Evidence covers source inspection, the actual selected profile/mask, direct-zero versus local T/Q indirect creation, and a weak-cloud local branch; it does not test derivatives across every RTTOV/cloud boundary. | Checklist status now reads `CLOSED IN SCOPE`, matching the main report's selected-branch limits. No calculation was needed. |

The two wording/status items are resolved. The other reviewed claims are
consistent with the available receipts:

- Guarded saturation replay returned 0 into a fresh path and produced the same
  result SHA-256 (`a5bf4f…d8a3c524`) and exact thermodynamic/control projections
  as the preserved prior receipt. The existing-output and pair-mismatch pytest
  regressions passed; the latter rejects a copied +1 K archive/public mismatch
  before forecast access and leaves the source receipt untouched.
- The selected T/Q cases change only their declared selected-layer
  `th`/physical-T or `qv` coordinate. `normalized_dry=True` recomputes runtime
  dry density from entry qv while optical `rho_d` stays fixed. Number units,
  the `+1e8 m^-3` NCCN floor departure and local-only water/latent transfers are
  accurately distinguished; no universal N or complete S17 claim is made.
- The whole-runtime FD uses only selected-layer `[qv,qc,T,nc,nccn]` outputs;
  selected-stage checks are separately labeled. The raw NC discrepancy is
  identified as one ULP over `2ε`; the NCCN residual is not attributed solely
  to rounding. The 20/10/5 s result is partition sensitivity under constant
  forcing, with no convergence-order or full-host T1 claim.
- RTTOV's `32768` flags exclude T−1 K and qv×1.06 from common-seven comparison.
  The T−0.8 K H∘M witness uses a `+1 K` physical-T direction and a
  `+0.01 kg/kg` dry-qv direction with scalar `h=1e-5`, i.e. endpoint changes
  `±1e-7 kg/kg`; quality/cloud masks remain fixed. This is local first-order
  cost evidence, not science-R2 admission, optimization, calibration, or
  validation.
- R1 regime/density-role decisions and R2 QA/time/footprint/correspondence stay
  open. The old native `exit1` cause, new valid host run, complete physical
  budgets, full-host timestep, native multicolumn, unused validation, and
  D1–D4 selections remain separate open work. No historical failure is claimed
  as a prerequisite to a separately validated future case.

There is no new production defect finding. The final report correctly states
that the original run was invalid and that these uncommitted diagnostics do not
constitute host, science or operational approval.
