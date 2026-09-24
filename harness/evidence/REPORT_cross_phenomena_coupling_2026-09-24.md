# X7: component properties versus coupled order and equilibrium

Two synthetic reservoirs exchange one conserved quantity. Operator A moves
left→right at rate `a` and B moves right→left at rate `b`, each with its
**exact** one-way time map. Their simultaneous reference is the analytic
solution of `dL/dt=-aL+bR`, `dR/dt=aL-bR`. This is a noncommuting toy system,
not an implementation or physical-error estimate for KDM, land-surface,
radiation or dynamics coupling.

At `a=1 s⁻¹`, `b=2 s⁻¹`, `dt=0.5 s` from `(L,R)=(1,0)`:

| Same final time | Left | Right | Total |
| --- | ---: | ---: | ---: |
| A then B | 0.8552507189769876 | 0.1447492810230125 | 1 |
| B then A | 0.6065306597126334 | 0.3934693402873666 | 1 |
| Coupled exact | 0.7410433867161432 | 0.2589566132838568 | 1 |

All states are nonnegative and preserve the total. The A-then-B distribution
has L1 difference `0.22841466452168863` from the coupled reference;
the two orders differ by `0.49744011852870823`. A validator checking only
component conservation and positivity would miss that distinction. A
declared-order comparison rejects the BA result when AB was requested,
even though its total passes.

The coupled equilibrium `(2/3,1/3)` remains fixed under the simultaneous
equation. One A-then-B split over 0.5 s moves it to approximately
`(0.780874,0.219126)`, so combined equilibrium is another independent gate.
The example's rates are held constant over one interval and have no threshold
or event-time branch. No operational source was modified to force this result.

Eleven synthetic tests passed locally with warnings treated as errors. They
cover same-final-time order, conserved/nonnegative totals, joint equilibrium,
zero or one active operator, invalid signed reservoirs/rates, unknown order
and a boolean comparison tolerance. Large finite values that would overflow
the naive intermediate product `total*b` are evaluated as
`total*(b/(a+b))`, with final-state/metric finiteness checks. This result demonstrates why X7 needs a
coupling gate; it does not validate a particular KDM process split, host
feedback, physical numerical convergence or forecast skill.
