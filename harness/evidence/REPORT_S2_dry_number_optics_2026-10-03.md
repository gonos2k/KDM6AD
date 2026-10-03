# Dry-specific number in the fixed-density optical DSD bridge

The previous bridge supplied stored QN directly to the scheme preamble and used
moist forcing density for DSD mass, although water contents used the separate
frozen dry density. That mapping remains the default legacy behavior. It must
not be silently used to interpret the opt-in dry-number state.

An explicit `dry_number=True` now converts NC/NI/NR with the supplied, frozen
observation `rho_d` and uses it for the DSD mass measure (`dend`). Moist `den`
remains available for air properties. The existing cloud profile configuration
carries the flag through density selection and the single-column profile
builder. No ABI, microphysics runtime, threshold/coefficient or f32 forecast
changes. NCCN is not an input to the optical DSD calculation.

For `q_d,n_d`, the paired moments are `C=rho_d*q_d` and `N=rho_d*n_d`.
Away from DSD limits, `lambda^d=pid*N/C=pid*n_d/q_d`. Content remains
`rho_d*q_d`. Thus changing the air measure with both volume moments consistently
does not change mean particle mass or unconstrained size. Volume-number gates
and scheme/radiation bounds still apply; no limiter or radius floor is removed.

The frozen observation density is not inferred from trial qv. Its derivative is
zero in this optical operator. This differs from the microphysics runtime's
live `rho_m/(1+qv_entry)` conversion under fixed moist forcing. These two maps
must not be combined into a claimed full coupled-step qv Jacobian. This change
defines the fixed-air optical map; it does not settle that coupled DA contract.

## Direct validation

Four new focused checks reuse the public supported native input selected before
outputs (call 2, global one-based 142,50). Its native layers and snow are retained.
Nine ice layers have `qi>1e-15`; the old raw mapping and paired dry mapping
produce different reciprocal slopes in eight. The new diagnostics match the
scheme's preamble on the declared volume moments bit-for-bit. Scaling the air
measure together with both ice moments preserves size within rounding.

A nonuniform NI direction verifies nonzero size JVP, independent central
difference and VJP duality with fixed density. The profile configuration keeps
its flag through density selection; the profile's ice diameter changes while
its content remains on the same dry measure. Missing or gradient-bearing
observation density is rejected. The new and directly affected existing bridge,
profile and density checks pass together: **31 tests**.

These are local profile/AD calculations on retained native inputs, not new
RTTOV calls or accepted liquid observations. Default legacy consistency and
gradient checks remain in the same test set. Sharded all-sky and the existing
DA-window physics are not automatically switched to dry-number mode. S2
physical calibration, S8 coupled routing and S11 observation approval stay OPEN.
No release or deployment follows.
