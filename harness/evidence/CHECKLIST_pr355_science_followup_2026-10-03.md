# PR #353–#355 follow-up: exact-main provenance and S2

Baseline: `603ea4a681faf3822915cbf4f9f6f2c61cd758cf`.
Keep the bounded NCCN return closure and its existing regression criteria fixed.
Do not extend that arithmetic to NC/NI/NR or add a new framework.

- [x] C1: Verify the merge commit's required checks actually execute and succeed.
  Ubuntu, macOS, oracle, harness and path detection completed successfully.
- [x] C2: Fresh-build the exact baseline library, link the existing isolated
  private wrapper, and run the same 40 s normal forecast with the AD/FD probe
  disabled. Compare OFF/ON and the archived candidate trajectory raw-bit,
  including actual 0/20/40 s records; retain source/library/executable lineage.
  [Exact-main host confirmation](REPORT_main603ea4a_host_confirmation_2026-10-03.md)
  records two completed runs, unchanged saved forecasts and explicit source/build
  provenance. This is normal f32 forecast confirmation; no new fp64 FD probe ran.
- [x] C3: Derive and source-anchor the S2 contract for stored dry-specific
  number, internal volume number, paired mass/volume moments, every number
  threshold/cap and representative empirical source/sink coefficients. Separate
  dimensional requirements, original calibration evidence and chosen policy.
  [Source/unit inventory](REPORT_S2_number_dimensions_2026-10-03.md) distinguishes
  the legacy boundary from the opt-in volume-coordinate kernel and corrects
  rate/cap unit descriptions without changing any value. Dimensional inventory
  is complete; physical calibration/approval is not. The original basis of the
  host 10/100 gates and large-number safety limits is still undocumented.
- [x] C4: Resolve repository-actionable inconsistencies found by C3 in a
  separate bounded opt-in change; verify applied budgets and directional
  derivatives without relaxing f32 parity or substituting model data.
  Unit comments are corrected without changing equations. The [explicit
  dry-number optical adapter](REPORT_S2_dry_number_optics_2026-10-03.md) pairs
  volume number/mass with the fixed observation measure and passes native-input
  size JVP/VJP/FD and profile tests. This resolves the discovered representation
  gap, not empirical calibration, all process budgets or a coupled qv Jacobian.
- [ ] C5: With that physical contract, validate actual number-to-size/optical
  inputs and then S11 using retained native model/observation data. An empty
  liquid observation support is a failure, not accepted zero cost.

Use mathematical dimensions and budgets, meteorological validity and native
inputs, and source-ordered numerical/derivative checks as separate evidence.
If empirical provenance or a physical policy cannot be established, record the
specific unresolved decision rather than certify it from small residuals.
Release/deployment, unrelated generalization and new completion percentages
remain outside this sequence. S2/S8/S11 and broader host approval are not closed
by C1/C2 or by the earlier NCCN numerical result.
