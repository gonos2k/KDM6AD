# Further cross-phenomenon generalization: resolution checklist

This checklist responds to the PR #238 review. The baseline `main` commit is
`e52fd069`; it contains X1 but not the subsequent X2–X12/G4 feature-branch
work. The integration branch was rebased onto that main commit while omitting
the patch-equivalent X1 commit. A reviewable PR to `main` is required before
describing the later evidence as mainline code. A PR alone is not a merge or a
new scientific acceptance result.

The previous [X1–X12 checklist](CHECKLIST_cross_phenomena_2026-09-24.md)
retains its bounded evidence and limitations. In particular, X2 measured an
actual isolated native D2/D3 applied phase event; it did **not** certify a
general sequential vapour→liquid→ice chain or a full enthalpy law. X3 and X6
cover a signed toy face and overlap-aware remapping; X5 covers independent
variable intervals and checkpoint-prefix identity. The new items below add
contracts absent from those checks, without relaxing them.

| ID | Status | New contract | Minimum completion evidence |
| --- | --- | --- | --- |
| F0 | **Branch reconstruction complete; PR #250 open, main merge pending** | Code/evidence provenance | X2–X12/G4 are rebased onto the actual PR #238 main commit with no duplicate X1 patch and all failed gates retained. Exact-head oracle/harness/port checks must pass for PR #250. Mainline inclusion remains pending merge. |
| F1 | **Bounded sequence pilot complete** | Ordered applied transitions | An independent two-stage plan fixes stage/owner and expected transfer names/paths, then checks before/requested/applied/after on X1's single declared mass-mixing-ratio basis and fixed f64 tolerances; same-stage draws share current availability, later stages consume the exact preceding published state. Eight new synthetic tests reject intermediate overdraw above tolerance, missing/reordered stages or transfers, handoff gaps, cancelled heat errors, masked/raw-boolean amounts and caller-relaxed tolerance. Sub-`1e-14` mass deviations are outside this pilot's conservation resolution. The actual X2 trace remains a separate bounded native witness; no native vapour→liquid→ice chain was executed. |
| F2 | **Bounded constant-cp state-function pilot complete** | Thermodynamic path and state function | One fixed-pressure, common-reference synthetic model checks phase heat capacities, declared latent-edge cycle and `H_after-H_before=Q+W+H_mass` at fixed `1e-8 J kg_d^-1` residual tolerance. Five new tests show that X1's local fixed-`cpm` update can pass while this model's total enthalpy fails by about `-71.5451 J kg_d^-1`; the state-function solution and explicit external heat/work/mass inputs close. No KDM enthalpy-error measurement or full pressure-work certification. |
| F3 | **Bounded scalar implicit pilot complete** | Implicit solve and derivative acceptance | Dimensionless positive-root Newton pilot fixes state residual, linearized-error, tangent residual and Jacobian lower-bound gates before evaluation, and replays the recorded initial iterate/iteration count to bind value and algorithmic tangent to execution. Six new tests show one step's correct algorithmic `dy/dp=0.5` but wrong root (`R=2.25`) versus converged root `y=2`, derivative `0.25`; forged trajectories, false status, changed active set and near-singular Jacobian fail. No KDM native implicit solver or general nonlinear error bound is certified. |
| F4 | **Bounded two-material heat-face pilot complete** | Face constitutive law and thermodynamic direction | At a synthetic fixed-capacity interface, paired heat amount, before-state serial-resistance flux × interval and passive entropy are separate gates. Six new tests show arithmetic-mean conductivity conserves energy but gives 25.5025× the declared flux, while reverse transfer conserves energy but decreases entropy; equal-temperature and tiny opposite/under-transfer also tested. Near-zero energy residual below the fixed absolute budget tolerance remains unresolved. Existing signed-water-face tests remain separate. No host soil/heat solver was executed. |
| F5 | **Bounded two-by-two dual-map pilot complete** | Dual quantity transfer across grids | Reuses X6's full-coverage `P 1=1` and `P^T w_t=w_s` gates, then checks intensive velocity `v_t=P v_s`, measure-aware force density `g_s=W_s^-1 P^T W_t g_t`, total force and power. Six new test functions (17 collected cases with retained X6) reproduce correct 11 N/28 W and reject a same-total-force 24 W map; constant/signed fields and invalid measure/precision also checked. No real-grid coupler or partial-overlap dual is certified. |
| F6 | Open | Accepted interval, rollback and restart | Separate trial from accepted integrated amount; reject or roll back a trial without accumulation, make identical accepted event replay idempotent, reject same-ID content conflict, and bind checkpoint to an independent interval plan. This does not close G4's measured host restart divergence. |
| F7 | Open | Resolution and stochastic meaning | Exhibit lost nonlinear moments under averaging; require declared retained moments/closure before claiming coarse-grid equivalence. For an internal stochastic exchange, require paired per-realization amounts, not merely ensemble-mean conservation; keep analysis/ML corrections in a separate external ledger. |

Each row is a bounded verification deliverable, not a replacement solver or an
operational approval. Implement and review one row at a time, preserving fixed
regression cases and using synthetic counterexamples only where there is no
corresponding native path. A row can close at its declared evidence level while
the following system-level gates stay explicitly open: operational ice
transport P1, physical number-unit basis, native `mstep>1`, 2×1 MPI and restart
trajectory divergence, full normalized AD/ABI, physical time convergence,
independent radiative accuracy and QC-accepted liquid observation cost (0/9).

F1 evidence: `REPORT_further_generalization_sequence_2026-09-24.md`,
`phase_sequence_contract.py` and its focused tests. The stage plan is a
caller-supplied source-order and transfer-path declaration, not inferred from
received records.

F2 evidence: `REPORT_further_generalization_enthalpy_2026-09-24.md`,
`phase_enthalpy_contract.py` and its focused tests. Its phase reference values
are synthetic and do not replace KDM's temperature-dependent coefficients.

F3 evidence: `REPORT_further_generalization_implicit_2026-09-24.md`,
`implicit_solution_contract.py` and its focused tests. Its scalar equation and
condition thresholds are dimensionless, not KDM tolerance settings.

F4 evidence: `REPORT_further_generalization_material_interface_2026-09-24.md`,
`material_interface_contract.py` and its focused tests. The declared series
law is one synthetic linear constitutive relation, not a general land model.

F5 evidence: `REPORT_further_generalization_dual_map_2026-09-25.md`,
`dual_work_mapping_contract.py` and its focused tests. The illustrative units
are m/s, N/m2, m2 and W; X6 retains the partial-overlap remap contract.
