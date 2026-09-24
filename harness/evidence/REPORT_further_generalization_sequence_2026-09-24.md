# F1: ordered applied-phase stage pilot

`phase_sequence_contract.py` composes the existing X1
`check_phase_budget` without changing its same-stage shared-reservoir rule.
The caller supplies an independently fixed `(stage_id, owner, transfer paths)`
schedule and published before/after reservoir and temperature snapshots. Every
stage must match the scheduled transfer names and source/destination paths,
pass the X1 applied-mass/local-latent check, and
hand its exact published state to the following stage. The final state is
also separately declared. Stage handoffs use numerical equality of the
published arrays; they are not a raw-bit native boundary certification.
All stages use X1's one declared mass-mixing-ratio basis and fixed f64
thresholds (`1e-14` mass fraction and `1e-8 J kg^-1` local heat residual).
The caller cannot enlarge those thresholds through this pilot's API. They
resolve the demonstrated `1e-3`-scale amounts, but a sub-`1e-14` mass-fraction
creation such as `5e-15` can remain below the absolute check. This is not a
general near-zero conservation certificate.

The principal synthetic case starts at `(q_v,q_l,q_i)=(0.001,0,0)`.
Condensation applies `0.001` vapour→liquid; the following stage applies
`0.001` liquid→ice. The first stage raises temperature from 270 to 272.5 K
using a declared `2.5e6 J kg^-1` coefficient and `1000 J kg^-1 K^-1`
heat capacity; the second reaches 272.834 K with `334000 J kg^-1`. Both
isolated X1 budgets pass. Flattening both transfers against the initial
state fails, because initial liquid is zero. This is the intended difference
between a sequential chain and same-stage simultaneous draws.

Eight new synthetic tests also cover two competing freezes drawing from the
same `0.001` liquid store; a transient negative intermediate state later
repaired at the endpoint; missing/reordered/relabeled stages and transfer
paths; exact mass and
temperature handoff; stagewise heat mismatch hidden by a final endpoint;
masked applied amounts and raw mixed bool/numeric lists; a forbidden
caller-relaxed tolerance and final-state mismatch. The retained five X1
tests and eight new F1 tests pass together (13/13). Once a producer has
already promoted `[True, 0.001]` into an ordinary float array, the original
boolean provenance is lost; that requires a check before producer coercion.

This checker audits supplied applied amounts. It does not choose request
allocation, regenerate KDM rates, define a full enthalpy function, or run a
native vapour→liquid→ice event. The caller must fix stage grouping, owner and
expected transfer paths from source order before seeing records; a generic
verifier cannot prove its caller chose an independent plan. PR #239's measured
D2/D3 native event remains separate evidence for one actual coordinator stage, including
its recorded limiter and later updates. F2 will address whether the declared
latent coefficients and changing composition form a consistent thermodynamic
state function.
