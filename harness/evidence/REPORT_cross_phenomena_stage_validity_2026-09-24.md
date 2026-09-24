# X8: validity at the stage that owns it

The G2 native trace found negative particle-number values created in an
internal RK update and copied to a boundary excluded from later microphysics.
The retained source evidence is `REPORT_number_face_flux_2026-09-24.md` and
`REPORT_negative_number_origin_2026-09-24.md`.
This X8 pilot does **not** re-run or repair that native event. It defines a
small independent event plan with four distinct roles:

| Role | Pilot rule |
| --- | --- |
| `solver_internal` | Finite numerical value required; an accepted-state bound violation is recorded but not automatically rejected |
| `physical_consumer_input` | The declared physical domain must hold at the actual consuming boundary |
| `accepted_state` | The declared physical domain must hold for the accepted output |
| `diagnostic_only` | Value may be undefined and is not read; it cannot supply a later physical stage |

The synthetic number domain is `[0,1e9]` in a declared internal numerical
unit. A finite RK value of −0.028539743 and an identical boundary copy are
retained as two internal out-of-domain observations. Sending that negative
value into a physical consumer is rejected. A separate **declared** repair
stage with output 0 followed by consumer input 0 passes the stage gate; the
checker does not choose, implement or certify that repair. In particular,
this is not permission to clamp an operational field: any actual repair must
account for its quantity change and upstream face/limiter cause.

The event set, roles, predecessors and quantity IDs come from the plan, not
the received records. A missing/relabelled stage or an attempt to feed a
diagnostic-only output into a physical stage is rejected. Unreadable
diagnostic values are not converted to 0. A signed temperature anomaly with
no nonnegativity bound remains valid as a physical input, showing that this
is a quantity-specific gate rather than universal positivity.

Nine focused synthetic tests passed with warnings treated as errors. They
check internal versus consumer/accepted negatives, missing or reordered
stages, diagnostic isolation, signed quantities and invalid scalar values.
The `consumes_from` label checks declared predecessor identity and ordering;
it does **not** replay a physical transformation or prove equality across a
producer/consumer edge. Actual host RK/PD/boundary positivity, conservation,
MPI ownership, native `INTENT(OUT)` validity and observational approval
remain separate unresolved gates.
