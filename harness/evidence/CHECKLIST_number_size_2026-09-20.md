# PR228 follow-up: fixed-column number and size contract

Scope: retained 5 km model column 35711, original 39 mass levels. This is a
conditional diagnostic of stored number semantics, not a changed KDM trajectory
or a new RTTOV experiment. Earlier cap and optical-path diagnoses remain closed.

- [x] Recover the same evolved baseline used by the retained liquid experiment;
  compare native pressures, liquid content and diameter with retained input.
- [x] Publish all layer operands and distinguish raw-number execution,
  number-only conversion, and coherent dry-mass moments.
- [x] Replay generalized-gamma moments, inactive gates and radius limits;
  report unclamped sizes separately from the actual optical input.
- [x] Review independent mathematical expectations and evidence scope, then run
  focused Python 3.12 checks and refresh Graphify.
- [ ] Resolve the host-to-kernel physical number contract end to end, including
  initialization, dynamics, microphysics and applied transport. Conditional size
  comparisons alone do not complete this item.
- [ ] Independently validate radiation accuracy with agreed physical inputs.
  Existing liquid observation/cost acceptance stays at 0/9; no QC relaxation.

One offline KDM baseline, zero new RTTOV calls, zero counterfactual integrations.
All nine retained profile vectors and four ASCII hydrometeor vectors matched
exactly. Public operands: `number_size_2026-09-20.json`; interpretation and
measurement limits: `REPORT_number_size_2026-09-20.md`.

Python 3.12 focused suite: 31 passed (11 number/size checks plus the previous
13 extinction and 7 optical-boundary checks). This is separate from the local
Python 3.10/Torch baseline extraction and does not reproduce RTTOV in CI.
Green/Red review found no remaining required change. Graphify structural update
and focused documentation-semantic merge completed. The local focus-summary
index was corrected to 24/26/27 for user layers 25/27/28; the public all-layer
operands and measurements were unchanged, with no new model run.
