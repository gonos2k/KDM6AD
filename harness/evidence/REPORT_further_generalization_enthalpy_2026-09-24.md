# F2: a separate phase-enthalpy state-function pilot

The verification-only `phase_enthalpy_contract.py` declares one reference
temperature, one dry-air heat capacity and a constant heat capacity plus
reference enthalpy for each of vapour, liquid and ice. On a declared common
`kg species / kg dry air` basis it evaluates

```
H(T,q) = cp_dry (T-Tref) + sum_phase q_phase [h_phase,ref + cp_phase (T-Tref)].
```

At the common reference state it requires every supplied latent coefficient
to equal `h_source,ref-h_destination,ref`. A declared closed cycle must also
sum to zero within the fixed `1e-8 J/kg species` pilot threshold. With
`h_v=2.5e6`, `h_l=0`, `h_i=-334000 J/kg`, the coefficients for vapour→liquid,
liquid→ice and ice→vapour are `2.5e6`, `334000` and `-2.834e6 J/kg`.
Replacing the last with `-2.8e6` leaves `34000 J/kg` per unit transferred,
or `34 J/kg dry air` for a `0.001 kg/kg dry air` synthetic cycle, and fails.

A separate before/after audit requires
`H_after-H_before = external heat + declared work + mass-exchange energy`.
The three external terms are named even when zero; the fixed f64 residual
criterion is `1e-8 J/kg dry air`, not a mass or observation tolerance. A
finite residual above it fails. This is an energy check only; F1/X1 continue
to check applied water-mass transfers.

With `q_l=0.01`, `T=283.15 K`, `cp_l=4200`, `cp_i=2100` and
`cp_dry=1000 J/kg/K`, the liquid→ice heat coefficient at the initial
temperature is `355000 J/kg`. X1's initial-`cpm` local update gives
`dT=3.4069097888675626 K` and passes its applied-mass and local heat
equations. The independent state function then has a **-71.5451055662
J/kg dry air** enthalpy change without an external term, so F2 rejects it.
Solving the declared final-composition H equation instead closes that
synthetic budget. This counterexample does **not** measure an energy error in
the actual KDM run or suggest changing its operational update.

Other tests keep external heat, work and mass energy separate, reject an
omitted term, verify the equal-phase-heat-capacity special case and reject
invalid phase states or nonfinite inputs. Five new F2 tests, eight F1 tests
and five retained X1 tests pass together (18/18, warnings as errors); Ruff
passes. The pilot assumes fixed pressure and constant phase heat capacities.
It does not include actual KDM pressure work, temperature-dependent heat
capacities or latent coefficients, transported enthalpy, a native model event,
or an independently certified thermodynamics library.
