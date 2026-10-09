# RED review — bounded saturation-boundary prior cost

Review scope: the user-provided 00:41 main-review snapshot and the local PR394 head `01048862`. This is a branch-scoped arithmetic review of the scalar receipt, not a claim that PR394 changes are merged into the `b679` main snapshot or any remote branch. I did not inspect GitHub status, open a forecast, run KDM/RTTOV/host/optimizer code, or hash large data.

## Independent arithmetic and bounded minimum

I recomputed the objective from the three small public JSON receipts using the stated warm-water saturation formula and its analytic derivative. The saved values agree: `Tb=296.7488237473604 K`, `qb=0.018194574862718582 kg/kg dry`, `p=97710.18029785156 Pa`, and `Pi=ΔT/Δθ=0.9934034440618801`. Since the existing `th` control is additive potential temperature, the physical-temperature scale is `sT=0.8 Pi=0.7947227552495041 K`; the second scalar control is `v=log(qs/qb)/0.08`.

For

`J(T) = 0.5 ((T−Tb)/sT)^2 + 0.5 (log(qs(T,p)/qb)/0.08)^2`,

the independent derivative root and 20,001-point grid reproduce `T*=296.5460608375879 K`, `J*=0.11818300348272258`, and a grid minimum only `1.5017e−9` higher. The derivative changes sign once on the grid, and the stationary derivative is approximately `−8.8e−14` at the root.

I also checked that the root is the unique bounded scalar minimum, rather than only a stationary candidate. With `a=d(log es)/dT`, `g=d(log qs)/dT=(p/(p−es))a`, and `L=log(qs/qb)`,

`J'' = 1/sT² + (g² + L g')/0.08²`.

Across `[Tb−2,Tb+2]`, the warm-water expression gives `a≥0.0592266`, `|L|≤0.168942`, and a conservative `|g'|<6.84e−4`. Thus `g²−|L||g'|>0.00339`, so `J''>1/sT²≈1.5833` throughout the unclamped scalar interval. Together with the derivative signs at the interval endpoints, this establishes a unique bounded minimum for this two-control saturation-boundary model. It says nothing about global optimality in the 51-control state space.

All clipping and branch assumptions hold throughout the bracket: `T>1 K`, `T>ttp`, `es<0.99p`, `qs>qmin`, and `p−es>qmin`. The saved clear-state saturation root independently matches `296.0134076624113 K`. The candidate at the scalar minimum has `qv/qb=1.0336621`, but `qv=qs` is exactly water-saturation onset: KDM's strict `sw_percent>0` activation predicate is false at equality. This is a prior distance to the onset boundary, not activation, condensate creation, or a cloud result.

The cooling-only and moisture-only comparisons are also consistent: cooling to the fixed-qv root costs `0.42815888`; moistening at fixed `Tb` costs `0.16304711`; the joint scalar boundary costs `0.11818300`. These are penalties in the two selected prior-scaled controls only.

## Saved `Jo+Jb` samples and limits

Using the same Exner-mapped `th` prior, the saved baseline has `Jo=26.58857590`, `Jb=0`. The `T−0.5 K` what-if retains seven channels; adding its one-component prior penalty `0.19791500` gives `Jo+Jb=26.69059519`, slightly above baseline. The `T−0.8 K` what-if also retains seven channels; `Jo=22.61603313` plus `Jb=0.50666241` gives `23.12269553`, below baseline. These three saved points demonstrate a nonmonotonic sampled `Jo+Jb` sequence; they do not define the continuous operator cost curve or demonstrate an LBFGS failure.

The `T−1 K` and `qv+6%` saved scenarios retain only 4 and 6 channels, respectively, and are not comparable with the frozen seven-channel objective. Their smaller reported Huber sums must not be treated as improvements.

The scalar result does not evaluate the full prior, the other 50 controls, the full KDM/RTTOV operator, parameter identifiability, observation admissibility, or a real analysis. It is not an optimizer seed recommendation. The PR394 P2 concerns and their fixes remain conditional on the new path; this calculation neither establishes that the earlier clear-path analysis was wrong nor proves the new routing/pinning choice is physically required. No numeric posterior probability is supported.

## Evidence identity

The machine receipt records the three input JSON hashes and the arithmetic reader hash. The computation uses only those JSON inputs and Python scalar formulas; it did not open NPZ/forecast data or invoke source physics. The local PR394 head is `01048862`; the user's `b679` main-review snapshot is distinct. Keep that source/branch distinction explicit in any report.
