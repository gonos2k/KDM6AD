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
- [x] C4: Resolve the unit-documentation and optical-representation gaps found
  by C3 in a bounded opt-in change; verify paired DSD inputs and directional
  derivatives without relaxing f32 parity or substituting model data.
  Unit comments are corrected without changing equations. The [explicit
  dry-number optical adapter](REPORT_S2_dry_number_optics_2026-10-03.md) pairs
  volume number/mass with the fixed observation measure and passes native-input
  size JVP/VJP/FD and profile tests. This resolves the discovered representation
  gap, not empirical calibration, all process budgets or a coupled qv Jacobian.
- [ ] C5: Once the S2 physical contract is resolved, validate number-to-size/optical
  inputs and then S11 using retained native model/observation data. An empty
  liquid observation support is a failure, not accepted zero cost.
  A liquid input is now frozen by the [input-only rule](native_liquid_input_selection_2026-10-03.json)
  and its NC/size derivative is checked. The [actual RTTOV baseline](REPORT_C5_liquid_baseline_2026-10-03.md)
  now executes and returns BT/K, but coefficient/solver flags leave **0/9**
  accepted channels. No independent derivative/reference or accepted cost is
  claimed. A [global input-only coefficient census](REPORT_C5_coefficient_support_2026-10-03.md)
  now freezes a supported sea candidate (73,157), before new radiative output.
  Its [actual BT/NC derivative and observed-support diagnostic](REPORT_C5_supported_liquid_BT_2026-10-03.md)
  now pass the bounded numerical gates after correcting output serialization:
  7/9 Delta-Eddington channels survive the combined mask, and DOM 8/16/32 each
  have 9/9 radiance support. DOM 64 is unsupported by the installed table.
  The following C5 subitems are resolved; full scientific approval remains OPEN.
  - [x] Input-only native liquid selection and coherent dry-number DSD/optics.
  - [x] Actual BT/K and unchanged-mask NC JVP/VJP/independent FD.
  - [x] Actual nonempty observation support and frozen-support score derivative.
  - [x] Bounded solver comparison and explicit unsupported 64-stream failure.
  - [ ] Original threshold calibration, physical solver/optical accuracy and
    accepted observation error/cost policy. Empirical
  threshold calibration and the coupled density/DA contract remain unresolved.

Use mathematical dimensions and budgets, meteorological validity and native
inputs, and source-ordered numerical/derivative checks as separate evidence.
If empirical provenance or a physical policy cannot be established, record the
specific unresolved decision rather than certify it from small residuals.
Release/deployment, unrelated generalization and new completion percentages
remain outside this sequence. S2/S8/S11 and broader host approval are not closed
by C1/C2 or by the earlier NCCN numerical result.
