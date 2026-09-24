# X10: nonlinear observation support and analysis increments

This is a **synthetic monochromatic Planck** example, not RTTOV, an AMI
channel response, or the project's operational Huber cost. It tests the
adapter ordering and support rules that should be declared before an actual
observation validation.

At a representative wavelength of 10.8 μm, the Planck radiances of 260 K
and 300 K are mixed with weights `(0.5,0.5)` **before** inversion to
brightness temperature. The result is `282.00394318978795 K`; the mean of
the two temperatures is `280 K`. The values differ because Planck inversion
is nonlinear. The toy monochromatic spectral-radiance unit is
`W sr^-1 m^-3`; it is not an RTTOV channel-band radiance unit. For changing
radiances and weights, the local chain is

    dBT = Psi'(sum_q w_q L_q) * (sum_q w_q dL_q + sum_q dw_q L_q).

The synthetic directional test includes both terms and matches a separate
central difference. It requires the weight direction to sum to zero, since
the weights must continue to sum to one. At a zero-weight column, a nonzero
weight direction is rejected by this **two-sided** local derivative contract:
one sign of a centered perturbation would leave the nonnegative simplex.
A separately defined one-sided boundary derivative is not claimed. It does
not add another Planck
derivative to a BT-seeded RTTOV adjoint.

A separate **quadratic demonstration cost** uses a declared boolean channel
support. Predicted BT `(280,290) K`, observed `(280,300) K` and sigma `(1,1)
K` give cost 50 with both channels, but cost 0 when the second channel is
excluded **with the same prediction**. A comparison function therefore
rejects changed support rather than calling that drop state improvement.
An empty support returns `(J,dJ,usable,accepted)=(0,0,0,False)` and cannot
approve a cost comparison. Excluded NaNs or masked values are unread;
included invalid values reject. Consumed boolean masks cannot silently
become physical BT or observed values. Kept BT/observation values must be
positive Kelvin temperatures, so finite missing sentinels such as −9999 K
cannot enter the synthetic cost.
For this small verification cost, the selected binary64 values' quadratic
terms and directional terms are accumulated as exact rational numbers before
the final conversion to binary64. That prevents `sigma²` overflow from
silently turning a representable gradient 0.5 into zero; an unrepresentable
nonzero result is refused. This does not alter the real Huber cost.

Finally, a synthetic analysis changes a nonnegative two-cell inventory by
−0.002 in the declared measure. This is recorded as an **analysis increment**,
not as a failed internal face-transfer balance. An invalid negative accepted
state is still refused. The helper does not assert that any analysis
increment is physically justified by observations or error statistics.
The sum uses compensated `math.fsum` across checked cell terms: a synthetic
`(+1e16,+1,−1e16)` change retains its net +1 rather than rounding to zero
under an ordinary dot-product reduction.

Eleven focused tests passed locally with warnings treated as errors. No RTTOV
or GK2A product was executed here, the real Huber/QC implementation was not
replaced, and the inherited liquid observation/cost approval remains **0/9**.
Independent radiative accuracy, optical-input units and identifiability
remain open beyond this adapter-order example.
