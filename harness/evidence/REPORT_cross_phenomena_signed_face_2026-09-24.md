# X3: signed two-cell water exchange pilot

This item tests whether the checklist's common **applied face amount** idea
works outside one-way sedimentation. It is synthetic and deliberately scoped:
the public KDM6AD repository has no production soil-water/diffusion solver
being certified here. No KDM or private host physics, ABI, QC or tolerance
was changed.

The declared inventory is water depth per horizontal area,
`W_left=theta_left*dz_left` and `W_right=theta_right*dz_right`, in metres.
One signed integrated face amount `Q` is positive left→right. A separate
external amount for each cell is retained in the ledger:

    W_left_after  = W_left_before  - Q_applied + external_left
    W_right_after = W_right_before + Q_applied + external_right

The checker does **not** select a flux formula or limiter. The toy adapter
declares one example law only: `Q_requested=K*(head_left-head_right)*dt/distance`
with `K` in m/s and head/distance dimensionless. It bounds the transfer by
the donor's available water and the receiver's capacity
`porosity*thickness-W`. This is neither the sedimentation `v/dz` law nor a
proposal for an operational land-surface scheme.

The thirteen focused synthetic tests passed with warnings treated as errors.
They cover forward and reverse head gradients, unequal layer thicknesses,
receiver saturation, donor exhaustion, signed external supply, equal-head
equilibrium, invalid face direction/amount, NaN and inadmissible water states.
The forward example transfers 0.005 m: theta changes by −0.05 in the 0.1 m
left layer and +0.025 in the 0.2 m right layer while the **water depth sum**
remains fixed. A separate capacity case requests 0.1 m but applies only
0.002 m, filling the receiver to porosity. A zero-transfer state is returned
unchanged rather than performing an unnecessary theta→depth→theta roundtrip
that can move its last bit.

This is a bounded algebra/adapter check. The relation between real soil
hydraulic head and moisture, actual diffusivity, heat coupling, moving
geometry, time-varying intervals, boundary forcing and host execution are
not supplied by this synthetic pilot. X5–X8 track those distinct contracts.
It cannot be counted as another native KDM run or a meteorological case.
