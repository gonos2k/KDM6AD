# Fixed-column radiance derivative boundary

PR227's required-file evidence check and PR226's cap-location measurements remain
closed. This task uses the same column 35711, five stored native-layer endpoint
inputs and unchanged solver/QC. No external atmospheric data are introduced.

- [x] Identify one nonoverlapping optical boundary and all bypass inputs.
- [x] Confirm BT versus radiance adjoint seed and cloud-weight derivative contract.
- [x] Capture boundary operands and baseline adjoints in isolated copies;
  compare all five required original output files for noninterference.
- [x] Compare baseline adjoint × endpoint boundary central differences with
  retained full channel derivatives at both existing epsilon values. Label the
  boundary differences as finite differences, not genuine forward AD.
- [x] Publish channel contributions, closure residuals and limitations; independent
  Green/Red review. Do not count upstream and downstream contributions twice.
- [x] Trace the separate number-to-effective-size unit contract using existing
  host/kernel evidence; leave physical ambiguity explicit.

For a complete cut xi of the executed graph, sum_j lambda_j * dot(xi_j) equals
the total derivative. Substituting finite endpoint differences for dot(xi_j)
adds truncation and serialization errors and is a separate numerical comparison.
Radiance columns are weighted before conversion to BT. Fixed cloud weights have
zero control tangent in this declared experiment; their radiance weights are not
BT sensitivity fractions.

The accepted liquid-process observation/cost gate remains open (0/9 channels).
Independent radiative accuracy, number-unit reconciliation, transport and time
step convergence are not closed by this diagnostic.

Measured finite-width contraction maximum differences from retained channel JVP:
0.0154858% (epsilon=0.03), 0.171884% (epsilon=0.1). Five completed isolated
executions preserve all required outputs; two failed setup attempts are excluded.
See REPORT_radiance_boundary_2026-09-20.md and the public operand JSON.
