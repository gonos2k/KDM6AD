# Host dry-mass reference: one retained snapshot

The active private host equations and saved native fields identify a dry-pressure
coordinate measure for the selected C5 column. This source/snapshot audit reads
the retained NetCDF; it does not run the host, KDM, RTTOV or optimization and
does not change any density or budget policy.

For HYBRID_OPT=2, the Registry declares dry column pressure mass MU+MUB and
`p_dry = C3*(MU+MUB)+C4+P_TOP`. The active coefficient construction uses
`C1H = delta(C3F)/DNW` and `C2H=(1-C1H)*(p0-P_TOP)`. At the scalar prep path,
`rk_step_prep` calls `calculate_full(mut,mub,mu)`; the implementation sums base
and perturbation fields. `phy_prep` uses `(C1H*MUT+C2H)*DNW` in its hydrostatic
pressure calculation. With native DNW negative, the layer measure is

`w_eta = -(C1H*(MU+MUB)+C2H)*DNW/g`, in kg per physical m².

The source gravity is nominally 9.81 m/s². Map scale factors enter horizontal
flux divergence, not this pressure mass per physical area. Converting to total
kg per grid cell requires a separate physical-area definition; no such
conversion is performed here. The active physics area helper has a disabled
map-corrected branch, so its `area2d` must not silently supply that conversion.

Source trace in the active `host/KIM-meso_v1.0` tree:

- `Registry/registry.hyb_coord`: dry pressure and C1/C2 definitions.
- `dyn_em/nest_init_utils.F:1153`: half-level coefficient construction.
- `dyn_em/module_em.F:143`: total-column mass construction.
- `dyn_em/module_big_step_utilities_em.F:3632`: base plus perturbation sum.
- `dyn_em/module_big_step_utilities_em.F:4957`: hybrid hydrostatic pressure.
- `dyn_em/module_big_step_utilities_em.F:1045`: logarithmic hypsometry.
- `share/module_model_constants.F:17`: gravity.

## Measures evaluated from decoded native fields

The saved frame is 2025-07-19 00:00:20, native `(i,j)=(73,157)`, 39 layers.
MU=216.010437 Pa, MUB=95000 Pa, P_TOP=5000 Pa. HYPSOMETRIC_OPT=2.

| Fixed layer measure | Column sum, kg/m² | Initial analysis water increment, kg/m² |
| --- | ---: | ---: |
| Hybrid coordinate, decoded fields in f64 | 9706.015299 | +0.101509463 |
| Existing background diagnostic rho_d*dz | 9711.775806 | +0.101512531 |
| Log-pressure depth implied by hypsometric option 2 | 9711.774791 | Computed separately in result |

The maximum diagnostic/hybrid layer difference is 0.09430% relative to the
hybrid weight, at bottom-up index 19. The initial water-increment difference is
about 3.07e-6 kg/m². No earlier inventory is overwritten or retroactively changed.

## Why the density-times-height measure differs

The active nonhydrostatic `hypsometric_opt=2` branch calculates inverse dry
density with `p_dry_mid*log(p_dry_lower/p_dry_upper)`, rather than the linear
pressure thickness. Combining that equation with geometric layer height gives
the third measure above. Its maximum relative difference from the retained
EOS-derived rho_d*dz is 8.44e-6. This explains the dominant offset; it does not
prove that all remaining differences are roundoff or isolate their full origin.

The code separately records explicit NumPy f32 arithmetic using decoded inputs,
including f32 MUT addition and the gravity literal. This is a reconstruction,
not a captured live Fortran intermediate or its reduction. The main table uses
f64 evaluation of the decoded source equation and nominal gravity.

The nine private source-file hashes identify the active equations reviewed
now. They do not certify that the retained historical executable was built from
all those current bytes. The saved run's coordinate flags and coefficient
vectors are the direct snapshot evidence.

## Bounded decision

The host-coordinate dry-mass reference is source-identified for this snapshot.
It is not algebraically identical to the density-derived measure used in the
current frozen-optics diagnostic. Keep those roles separate: no model or optical
policy is automatically switched by choosing a smaller inventory difference.

A future host physical ledger can bind to its captured hybrid dry-mass fields,
but it still needs compatible phase state functions, net boundary mass/enthalpy
flux and explicit work/heat. This audit is not a staged physics-call replay,
restart/MPI test, whole-domain mass budget, number-threshold calibration or S17
closure. S2/S11/S17 and operational approval remain OPEN.

- [Executed source](NATIVE_host_mass_reference_source_2026-10-06.py)
- [Native coefficient vectors, measures and hashes](NATIVE_host_mass_reference_result_2026-10-06.json)
- [Earlier declared inventory measure](REPORT_native_analysis_inventory_2026-10-05.md)
