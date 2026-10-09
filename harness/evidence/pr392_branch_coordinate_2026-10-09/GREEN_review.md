# Green review — PR392 weak-point branch and coordinate arithmetic

Date: 2026-10-09. This is a cached/public arithmetic audit of the existing
T−0.8 K weak-cloud point and PR391 receipts. The verifier imports no KDM code
and runs no model, RTTOV, forecast reader, optimizer or derivative engine. It
reads the small public JSON receipts and the existing selected-column NPZ only.

At the cached weak point, `T=295.9488237473604 K`, `p=97710.18029785156 Pa`,
`qv=0.018194574862718582 kg/kg dry`, and source-rounded `qs=0.018121553586305645`
give `q/qs=1.0040295262801375` and `S=0.402952628013753%`. The saturation-based
fraction `F=min(1,max(S/0.48,0)^0.6)` is **0.9003422967**. Solving the saved
water-saturation equation at fixed pressure and qv gives:

- `S=0` at `296.0134076624 K`: the weak point is `0.0645839151 K` colder than
  onset, so warming by that amount would reach it.
- `S=0.48%` (the `F=1` cap) at `295.9365071904 K`: this is `0.0123165570 K`
  colder than the weak point.

These are margins for the diagnosed water-saturation/CCN-fraction sub-branch
only. They are not an all-operator safe radius: they do not cover the other
microphysics limits, clamps, cloud/profile mapping branches or RTTOV flags.

From the cached forcing and state arrays, `rho_m=1.1349405976479523 kg/m³` and
entry `qv=0.018194574862718582` give `rho_dry=rho_m/(1+qv)=1.1146598358186837
kg/m³`. Stored entry NCCN is `180630560 #/kg dry air`, or
`201341630.3534369 m⁻³` in the volume kernel coordinate. Returned NCCN is
`89713468.43815634 #/kg dry air`; multiplying by the same call-entry dry
density gives the `1.0e8 m⁻³` lower floor. With that volume coordinate held at
the active floor, converting back to dry-specific units gives
`Ndry=Nmin*(1+qv)/rho_m`; thus `dNdry/dqv=Nmin/rho_m=88110338.29192446`. This
matches the saved weak-point output JVP `88110338.29192445`. It is a local
coordinate-conversion derivative while the volume number is clamped, not a
physical NCCN production sensitivity.

The cached weak-point output has `qc=2.005882014205248e-5 kg/kg dry` and
`qi=0`; with the entry dry density its content is `0.0223587611663 g/m³`, above
the `1e-6 g/m³` binary content gate. The receipt's derived `cfrac=0.999999`
matches that condition; it is not a fractional cloud probability.

The saved seven-channel sums are `26.5885759031` at baseline and `22.6160331265`
at T−0.8 K, an arithmetic decrease of `3.9725427765` or **14.94078807%**.
Both points retain the same seven-channel support. This is a conditional
saved-artifact comparison, not evidence of an accepted observation matchup,
optimization descent or forecast improvement.

The IR105 observation (`291.302592154 K`) aligns with channel 13 in the saved
10–16 vector. Its residual is model minus observation: `4.9302250963 K` at
baseline and `4.1417174183 K` at T−0.8 K. With sigma 1 K, zero bias and Huber
delta 1, both are on the positive linear branch, so the contribution is
`r−0.5`: `4.4302250963` and `3.6417174183`. This relation and cost difference
are only meaningful under the matched support and recorded observation
assumptions.

For constant forcing, the cached selected qc values are `8.2495225850e-5`,
`8.0524260008e-5` and `8.0564829031e-5 kg/kg` for 20 s, 10+10 s, and four 5 s
partitions. The absolute successive-difference ratio is `48.58302477`, giving
the arithmetic `p_obs=log2(ratio)=5.60238041`. Activation histories differ
(`true`; `true,false`; `true,false,true,false`), and the 10 s and 5 s values
reverse ordering. This is a conditional three-partition diagnostic only; it
does not establish high-order convergence, an asymptotic order, or full-host
timestep accuracy.

The machine receipt [result.json](result.json) records the input hashes and
assertions. The source [verify_branch_coordinate.py](verify_branch_coordinate.py)
reproduced it without loading native inputs or executing a model. Closed
39-layer saturation, MPI, extinction, and prior H∘M evidence remain unchanged.
