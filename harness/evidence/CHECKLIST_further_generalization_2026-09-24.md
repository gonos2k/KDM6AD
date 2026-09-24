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
| F3 | Open | Implicit solve and derivative acceptance | A small nonlinear pilot checks state residual, scaled/conditioned error, tangent residual and algorithmic-versus-converged sensitivity against separate norm, scaling and precision-aware thresholds fixed before examining results; finite but nonconverged residuals fail. Refused convergence/active-set states cannot be accepted as physical solutions. No claim for an uninstrumented native implicit solver. |
| F4 | Open | Face constitutive law and thermodynamic direction | A declared two-material interface law checks serial-resistance flux against arithmetic-mean counterexample; paired face conservation and equal-head equilibrium are separately retained. A passive heat-transfer example must reject the energy-conserving but entropy-decreasing direction. No claim for a host soil/heat solver. |
| F5 | Open | Dual quantity transfer across grids | An intensive map and its measure-aware dual extensive map must preserve the declared power/work pairing as well as test constant-state and integral behavior. Reject a total-force-preserving map that changes work. Keep real-grid mapping accuracy separate. |
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
