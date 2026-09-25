# F4: conservation, material law and entropy are separate face gates

The verification-only `material_interface_contract.py` treats two closed
thermal reservoirs per unit interface area, with absolute temperatures in K
and fixed areal heat capacities in `J m^-2 K^-1`. An integrated signed face
amount `Q` is in `J m^-2`, positive left→right. The paired-energy checker
requires left and right temperature changes to use `-Q` and `+Q` separately;
it intentionally does not select a conductivity law or passive direction.

For one declared linear two-material interface, the constitutive flux is

```
F = (T_left-T_right)/(ell_left/K_left + ell_right/K_right) [W m^-2].
```

With `K_left=1`, `K_right=100 W m^-1 K^-1`, half-distances `0.5 m`,
temperatures `310/300 K` and a one-second interval, the series-law transfer
is `19.801980198019802 J m^-2`. Using the arithmetic mean conductivity gives
`505 J m^-2`, or **25.5025×** the correct amount for this declared problem.
Applying that wrong amount to both cells still passes paired energy and
increases entropy; the series-law gate rejects it. Hence conservation and
uniform-temperature equilibrium do not certify a discontinuous-material
constitutive flux.

The series-law amount is the **before-state flux multiplied by the declared
interval**, a frozen-gradient/forward-Euler increment. It is not the exact
time integral of a gradient that evolves as the cells exchange heat. Its
fixed relative comparison uses no absolute face-flux tolerance, and exact
equal-temperature equilibrium or opposite signs are rejected even for tiny
amounts. The separate paired-energy gate retains a fixed `1e-8 J m^-2`
absolute residual tolerance, so subthreshold near-zero energy discrepancies
are not certified as resolved.

The passive-direction gate checks the closed constant-heat-capacity entropy
change `sum C_cell ln(T_after/T_before) >= 0` after the paired-energy gate.
A synthetic `-10 J m^-2` transfer from the cooler right cell to the hotter
left cell conserves energy but gives about `-0.0010753764 J m^-2 K^-1` of
entropy change and is rejected. The series transfer gives about
`+0.0021288233 J m^-2 K^-1`. Equal temperatures give exactly zero flux in
the synthetic formula and no spurious entropy.

Six new tests and 13 retained signed-water-face tests pass together (19/19,
warnings as errors); Ruff passes. Each gate uses a fixed, dimensioned f64
pilot tolerance. No external source, temperature-dependent heat capacity,
nonlinear/unsaturated interface, host soil or road equation, or native
meteorological result is certified. F5 addresses a different issue: dual
intensive/extensive mapping between nonmatching grids.
