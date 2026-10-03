# C5 input-only coefficient support and frozen liquid selection

The [first liquid baseline](REPORT_C5_liquid_baseline_2026-10-03.md) remains
flagged with 0/9 accepted channels. The new search applies a frozen,
pressure-local coefficient support rule to retained model inputs before any
new BT/K or finite-difference result. It does not rank radiative residuals or
numerical test outcomes, and it does not modify native humidity or quality flags.

## Declared domain and executed arithmetic

The [final rule](C5_coefficient_support_rule_2026-10-03.json) retains the same
sea/IREMIS, native-39-layer experiment. Each eligible owned column requires
finite positive forcing, nonnegative state, strict mass/moment pairs, and at
least one **same layer** with QC>1e-15 and volumetric NC>10 m⁻³. Sea eligibility
is XLAND>=1.5, LANDMASK=0 and SEAICE=0. A separate above-model-top reference
extension supplies missing atmosphere; it does not replace the native layers.

For gas_units=2 the per-user-layer conversion is
`factor=1/(1-Q_moist*1e-6)`: Q, O3 and CO2 all receive this factor before
averaging. The small compiled Fortran helper calls the installed RTTOV
`rttov_layeravg` in mode 4 and reduces T/Q/O3/CO2 with Fortran SUM over its
returned start/end ranges. The v13 coefficient reader's **overlapping adjacent**
envelope means supply 53 layer bounds from 54 levels, scaled by ±10% for
T and ±20% for gases. Coefficient-layer center pressures are arithmetic means
of adjacent coefficient interfaces. Checks use the source's inclusive
lay_upper:lay_lower range and strict out-of-range comparisons; equality is allowed.

The archived [executed script](C5_coefficient_support_census_2026-10-03.py)
is a case-specific local evidence runner requiring the retained private inputs
and licensed installed RTTOV; it is not a new product API. Its [receipt](C5_coefficient_support_census_2026-10-03.json)
pins source, script, helper, installed archive, compiler/link commands and data.
Known-profile State/Forcing/P8W and six extended atmospheric fields match the
first baseline arrays exactly. Source-language SUM replay alone does not certify
the installed engine object's exact arithmetic; actual returned quality remains
the downstream admission check.

## Census and input-only selection

| Native time | Owned interior | Strict active sea candidates | Coefficient-supported | Q-rejected |
| --- | ---: | ---: | ---: | ---: |
| 20 s | 64,960 | 8,317 | 4,329 | 3,988 |
| 40 s | 64,960 | 7,873 | 4,226 | 3,647 |

No candidate failed T, O3 or CO2 bounds. Some Q-rejected profiles violate two
layers, so layer-event counts are not independent profile counts. The selected
frame is the earliest with support; sorting uses ascending sequential-f64
sum(QC), then row-major `(j,i)`. Median index 2164 of 4329 selects global
one-based **(i,j)=(73,157)** at 20 s, sum(QC)=2.139174466719851e-5.
The [frozen state/forcing/profile payload](C5_coefficient_support_selected_2026-10-03.npz)
and [stdout](C5_coefficient_support_stdout_2026-10-03.txt) precede new radiative
output. The Fortran-reduction rerun preserves the NumPy prototype's selection
and all selected payload bytes.

The [superseded receipt note](C5_census_superseded_receipt_note_2026-10-03.md)
distinguishes the older NumPy run and its amended/superseded records; do not
claim unavailable earlier receipt bytes were preserved. The published final
script and selected payload hashes agree with the final execution receipt.

## Remaining work

This input predicate does not screen Delta-Eddington's spectral extinction cap,
verify the empirical number thresholds, or approve radiative accuracy. No new
RTTOV, NC-to-BT FD, DOM convergence or observation cost ran as part of this census.
Prepare the selected column's own optical fields, surface and matched satellite
geometry, preserve its actual output flags, then execute the frozen NC direction.
S2 physical calibration, coupled DA and full S11 approval remain OPEN.
