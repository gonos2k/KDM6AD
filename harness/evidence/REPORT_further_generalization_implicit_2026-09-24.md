# F3: executed Newton iteration versus converged implicit solution

The verification-only `implicit_solution_contract.py` uses the dimensionless
positive-root equation `R(y,p)=y²-p=0`. It executes a fixed number of Newton
iterations and propagates the **algorithmic** derivative through those
iterations. The result records the initial iterate and count; the audit
replays the same fixed iteration to check its reported value, tangent and
convergence flag before testing the state equation and tangent
equation `2y(dy/dp)-1=0`, a local linearized error estimate `|R/(2y)|`, and
the declared solver/active-set statuses.

The gates are fixed before the synthetic test: `|R|/max(1,p) <= 1e-12`,
`|R/(2y)|/max(1,|y|) <= 1e-12`, `|2y dy/dp-1| <= 1e-10`, and
`|2y| >= 1e-8`. The local linearized estimate is **not** a global root-error
bound. A non-converged solver flag or changed active-set flag is rejected even
when some numerical residual is small. This scalar positive branch is not a
policy for every implicit physical model.

At `p=4`, `y0=1`, one executed Newton step gives `y1=2.5` and propagated
`dy1/dp=0.5`. Independent central differences of that one-step algorithm
also give 0.5. Nevertheless `R(y1,4)=2.25`, while the intended positive
solution is `y*=2` with implicit derivative `1/(2y*)=0.25`. The audit rejects
the one-step result. Seven iterations pass the stated state and tangent gates
and agree with a separate finite difference of the seven-step map. Conversely,
starting at the exact value `y0=2` and performing zero iterations leaves the
algorithmic tangent at 0; value convergence alone does not pass the tangent
equation.

Six new tests additionally reject a forged convergence flag, an incorrect
tangent, a mathematically self-consistent value/tangent that could not have
come from the declared iteration, an active-set change, a near-singular
Jacobian and malformed inputs. Combined with F2/F1/X1, 24 focused tests pass
with warnings treated as errors;
Ruff passes. Replay proves internal consistency of a **supplied** initial
iterate and iteration count; it does not independently attest an external
solver's execution history. The synthetic code does not instrument KDM
saturation adjustment, land-surface solve, native iteration count/status or
an AD implementation. It demonstrates the acceptance distinction needed
before any such solver's sensitivities are promoted.
