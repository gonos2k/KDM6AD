# PR224 follow-up: fixed-column extinction-cap diagnosis

Scope: column 35711 and the five retained native 39-layer endpoints. Preserve
original outputs, solver, QC, controls, observations and all atmospheric inputs.
No external atmospheric data or replacement candidate.

- [x] Recompute the public nine-channel JVP/VJP maximum difference and correct
  the report exponent: 5.421010862427522e-20 in binary64.
- [x] Audit retained hydro slots/units, fractions, effective sizes and fixed
  auxiliary files against producer/reader source. Exact instrumented consumed
  arrays remain unmeasured.
- [x] Define the installed solver's capped quantity and units from source:
  pre-delta-scaling extinction coefficient, maximum 20 km^-1; distinct from
  the later dimensionless optical-depth cap of 30.
- [ ] Identify measured channel/layer/hydrometeor-column pre-cap and post-cap
  values and gas/hydrometeor contributions.
- [ ] Compare exact cap-active sets across all five endpoints; identical
  channel flags alone are insufficient.
- [ ] Relate cap-active layers to the accretion profile tangent, preserving
  the distinction between native and internal coordinates.
- [ ] Independently review diagnostic noninterference and publish reproducible
  scoped evidence; retain unsupported conclusions as open.

The fixed project QC excludes all nine clean IR observations. A cap flag alone
is not proof of erroneous radiance or an input-unit defect. This diagnosis does
not automatically approve the excluded BT/cost sensitivity. Physical number
units, nonzero transport, timestep convergence and broader regimes remain open.

Build outcome: original-source object probe succeeded, isolated executable
link failed on SDK/system symbols; no diagnostic run, installed modification
or license acceptance. See REPORT_extinction_contract_2026-09-20.md and
extinction_contract_2026-09-20.json. Actual masks and attribution remain open.
