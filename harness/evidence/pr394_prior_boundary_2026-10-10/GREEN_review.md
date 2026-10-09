# Green review: bounded prior cost to the warm saturation boundary

This is a standard-library arithmetic replay of exactly three public JSON
receipts: the PR391 clear-state thermodynamic result, the saved `T−0.8 K`
weak-state receipt, and the PR391 KMA cost scenarios. Input SHA-256 values and
the reader hash are recorded in `RESULT.json`. The analysis did not open the
referenced NPZ, forecast, private host, or RTTOV assets, and did not run a model,
operator, or optimizer.

## Recomputed scalar boundary

The clear-state result supplies the code-rounded water saturation constants
and baseline `Tb=296.7488237473604 K`, `qb=0.018194574862718582 kg/kg dry`.
The weak-state receipt supplies `p=97710.18029785156 Pa`, `ΔT=-0.8 K`, and
`Δθ=-0.8053122875524954 K`; their ratio gives `Pi=0.9934034440618801` and the
temperature prior scale `sT=0.8 Pi=0.7947227552495041 K`. The other control
scale is the specified qv log prior `sq=0.08`.

The reader evaluates the uncapped warm-water expression

```text
es(T) = psat exp(log(ttp/T) xa) exp(xb (1-ttp/T))
qs(T) = ep2 es/(p-es)
f(T)  = 0.5 ((T-Tb)/sT)^2 + 0.5 (log(qs(T)/qb)/sq)^2
```

and bisects the analytic stationary equation
`(T-Tb)/sT² + log(qs/qb)(dlogqs/dT)/sq² = 0` in `[Tb−1,Tb]`. It finds
`T*=296.5460608375879 K`, `ΔT=-0.2027629097725 K`, `qv/qb=1.0336621156719`,
`u=-0.2551366604683`, `v=0.4138493584030`, and `J=0.1181830034827`.

An independent 20,001-point grid over `[Tb−2,Tb+2]` has spacing
`0.0002 K`; its lowest point has `J=0.1181830049844`, only
`1.5017e-9` above the stationary solution. The exact objective derivative at
the root is about `−8.8e-14`. Cooling-only reaches the stored saturation root
`296.0134076624113 K` at prior cost `0.42815888094`; moist-only reaches
`qs(Tb)` at cost `0.16304710739`. The local linearized minimum-norm estimate is
`J=0.11822165610`, close to the bounded nonlinear result.

The independent Red review also bounds the scalar second derivative positive
throughout this interval, supporting a unique minimum for this one-dimensional
boundary objective. That convexity result does not establish global optimality
over the full 51-control state space.

The saturation expression remains on its warm, unclamped water branch across
the complete bracket and grid: `T>ttp`, `T>1 K`, `es<0.99p`, `qs>qmin`, and
`p-es>qmin`. The receipt records minimum guard margins. These checks justify
the derivative formula for this scalar interval; they do not validate every
branch of the KDM operator.

## Saved cost scenarios and interpretation

The saved baseline observation cost is `26.5885759031` with seven valid
channels. The saved `T−0.8 K` scenario has `Jo=22.6160331265`, also with seven
valid channels. Its separate two-control thermal prior penalty is
`Jb=0.5066624066`, giving arithmetic `Jb+Jo=23.1226955332`, which is
`3.4658803699` below the saved baseline `Jo`. This combines saved scenario
cost with a declared prior penalty; it is not an analysis or optimizer result.

The thermal prior uses physical-temperature scale `sT=0.8 Pi`, where
`Pi=ΔT/Δθ=0.9934034440618801` comes from the saved weak-state coordinate
conversion. This keeps the additive prior in potential temperature while
expressing its equivalent physical-temperature scale at the selected layer.
For the saved `T−0.8 K` perturbation the receipt checks both forms:
`0.5(ΔT/sT)^2 = 0.5(Δθ/0.8)^2 = 0.5066624066`.

| Saved case | Physical `ΔT` | `Jo` (7 supported channels) | Thermal `Jb=0.5(ΔT/sT)^2` | `Jb+Jo` | Difference vs baseline `Jo` |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 0 K | 26.5885759031 | 0 | 26.5885759031 | 0 |
| `T−0.5 K` | −0.5 K | 26.4926801856 | 0.1979150026 | 26.6905951882 | +0.1020192851 |
| `T−0.8 K` | −0.8 K | 22.6160331265 | 0.5066624066 | 23.1226955332 | −3.4658803699 |

The two prior-adjusted temperature points are nonmonotonic relative to baseline:
the `T−0.5 K` total is `0.1020192851` higher, while `T−0.8 K` is lower. These are
selected saved what-if cases, not a continuous optimizer trajectory. The
`T−1 K` and qv `+6%` scenarios have only four and six valid channels,
respectively, so their smaller Huber sums are incomparable with the fixed
seven-channel objective. The qv `+2%` case retains seven channels and has
`Jo=26.5732112932`.

This arithmetic is deliberately only a two-control boundary model: one
temperature degree of freedom and one qv log degree of freedom. The original
native-state CVT projected 51 active controls (`th=39`, `qv=12`), so `J*=0.11818`
is not a global minimum in that 51-control space and does not identify an
optimizer seed. No path barrier or global minimum over the full 51-control
space has been tested. It also does not prove that an observation is physically
admissible or validate any full KDM6/RTTOV derivative. No prior scales,
full-domain defaults, physics, or optimizer were changed.

The initial graph query returned generic calculation/cost nodes rather than
these receipt-specific dependencies. The accompanying semantic fragment is a
scoped map of this packet, not a complete project graph or an execution-path
certificate.

Reproduce from the repository root with:

```sh
/opt/local/bin/python3 harness/evidence/pr394_prior_boundary_2026-10-10/analyze_boundary.py \
  --output /tmp/pr394_prior_boundary_recheck.json
```

The CLI also accepts `--clear-result`, `--weak-result`, `--cost-result`, and
`--output`. It refuses to overwrite an existing output. It writes a JSON
receipt and checks its stationary/grid arithmetic, saved roots, guard
applicability, and channel-support comparability.
