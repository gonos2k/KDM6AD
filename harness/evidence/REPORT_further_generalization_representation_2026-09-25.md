# F7: nonlinear moments and realization-wise transfers

The verification-only `resolution_stochastic_contract.py` separates three
claims that an averaged result can otherwise blur. Its small scalar radius
pilot uses positive `float64` radii and nonnegative normalized subcell weights.
For radii `[1,3] µm` with weights `[0.5,0.5]`, the mean radius is `2 µm`,
its cube is `8 µm³`, while the weighted third moment is **14 µm³**. The lost
third moment is `6 µm³`; using the mean-radius cube as that moment fails.
The checker marks mean-only output as *not approved for cubic-moment
equivalence*. A provided retained third moment or named closure output must
match the fine synthetic distribution within a fixed `1e-12` relative,
zero absolute comparison. Naming a closure does not independently validate
its physical construction or accuracy on unseen model states. The approval
helper recalculates from the supplied fine radii, weights and claim; it does
not trust a caller-created audit result as evidence. Positive cubic terms
that underflow to zero, and overflowing cubic terms, are refused rather than
silently presented as coarse-moment agreement.

For an internal stochastic exchange, the same signed integrated amount must
appear at departure and arrival for **each declared realization ID**. An
independent expected ID tuple is compared to both sides before value checks.
The synthetic outgoing `[1,-1]` and incoming `[0,0]` amounts both average to
zero but fail per-member pairing; matching both `[1,-1]` passes. The amounts
are assumed to use the same physical measure and exclude external forcing.
The checker does not infer alignment from coincident numerical positions.

Finally, an intentional analysis or ML correction is labeled separately
from internal physics. This adapter reuses X10's
`analysis_inventory_increment`; its two-cell example changes an inventory
by `2 kg` and requires the external correction to declare that amount.
Zero claimed correction fails. The input basis, area/volume measure and unit
are caller declarations; an external analysis or learned model was not run.

Six new test functions plus retained X6/X10 parameterized tests yield 28
passing cases under `-W error`; Ruff passes. The result is a set of bounded
representation counterexamples and consumer checks, not a resolution-change
equivalence theorem, a certified subgrid closure, a stochastic KDM trajectory,
or observed forecast/assimilation skill.
