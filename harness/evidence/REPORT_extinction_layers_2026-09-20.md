# Measured fixed-column extinction caps — 2026-09-20

The five retained column 35711 endpoints now have measured pre/post extinction,
cap predicates, particle optical contributions, cloud-column mappings and
weights. **All five direct/K radiance, transmission and profile-K output files
per endpoint remain byte-identical to PR224.** The installed binary, original
inputs, solver, QC and tolerances are unchanged. The nine observation-clean IR
channels remain excluded; this is cap diagnosis, not accepted BT/cost validation.

## Execution and noninterference

The existing executable has symbols but no DWARF. LLVM 22 LLDB could not launch
because `debugserver` was unavailable; no guessed Fortran descriptors were read.
The successful route invokes the already-installed CLT linker by absolute path,
`/Library/Developer/CommandLineTools/usr/bin/ld`, via an isolated `-B` shim.
No license agreement, SDK editing, installation or system setting was changed.
This resolves the earlier link-path obstacle; the PR225 failure remains an
accurate record of the paths tried then.

First, the isolated uninstrumented executable was relinked from the installed
objects/archives and its baseline matched the retained original. Then three
copied routines received append-only writes: `rttov_scatt_optp` records particle
optical extinction, `rttov_eddington_setup` records cap arrays/predicates and
`icldarr`, and `rttov_eddington` records column radiances/weights. Instrumented
objects used gfortran 15 assembly and LLVM 22's assembler, with the same CLT link
route. The instrumented baseline matched the isolated baseline and original;
the other four instrumented endpoints matched their originals too.

There were **7 completed executions**: one installed-binary rerun, one isolated
uninstrumented baseline, and five instrumented endpoints. Compiler attempts and
the incomplete debugger launch are not RTTOV executions. Local live runtime is
separate from the Python 3.12 standard-library evidence replay. No KDM trajectory
or atmospheric input was regenerated for these diagnostic runs.

## Captured arrays and indexing

Each endpoint produces two identical appended passes. After verifying exact
agreement before deduplication, there are 780 pre/post rows (10 thermal channels
× 2 combinations × 39 user layers), 390 particle rows, 7,410 column/layer mapping
rows and 190 column radiance rows. Combination 0 is clear; combination 1 is the
scaled cloudy mixture. The eight particle slots are a different axis.

Channel and user-layer indices below are **1-based**. User layers run from top
to surface. Pressure identifies the correspondence to native bottom-up index
`39-user_layer`; original 39 center and 40 interface pressures are preserved.
The original strict `pre > 20` expression is recorded as a boolean before the
cap, along with 18-significant-digit scientific output. Post values are read from
the array after the original `MIN` operation. The boolean is not inferred from
rounded display values. Coefficients and margins have units km^-1.

## Measured masks and components

All five endpoint masks are identical: **62 active rows**, 59 cloudy and 3 clear.
The closest coefficient to the threshold at any captured endpoint has absolute
margin `0.14493800976697457 km^-1`. This verifies these five evaluated masks;
it is not a proof for every alpha between endpoints or every internal branch.

| channel | clear cap user layers | cloudy cap user layers |
|---:|---|---|
| 7 (outside selected nine IR) | none | 25,26,27,28,29,35,36,37 |
| 8 WV063 | 35,36,37 | 25,26,27,28,29,35,36,37,38,39 |
| 9 WV069 | none | 25,26,27,28,29,35,36,37,39 |
| 10 WV073 | none | 25,26,27,28,29,35 |
| 11 IR087 | none | 25,26,27,28,29 |
| 12 IR096 | none | 25,26,27,28 |
| 13 IR105 | none | 26,27 |
| 14 IR112 | none | 26,27,28 |
| 15 IR123 | none | 25,26,27,28,29,35 |
| 16 IR133 | none | 25,26,27,28,29,35 |

Baseline maximum pre-cap coefficient is `137.09228173102707` at channel 7,
combination 1, user layer 27; post-cap is 20. For the selected nine IR channels,
the maximum is `100.4991191851208`. The three clear caps are WV063 layers 35–37,
with coefficients `20.390651685236957`, `26.774661687232452`, and
`22.490517701843444`.

For the 59 cloudy cap rows, mutually exclusive baseline categories are:
51 where liquid alone exceeds 20; 3 where both liquid and clear contributions
individually exceed 20; and 5 where neither individually exceeds 20 but their
sum does. Ice optical contribution is at most `0.0005458074805827798` on these
rows. These are measured additive coefficient contributions, not causal shares
of BT or proof that the model's unresolved particle-number units are correct.
The particle dump records interpolated optical coefficients, not raw
`hydro_scaled` concentrations.

## Connection to accretion and radiance weights

The selected accretion tangent lives at native bottom-up layers 11/12/14,
corresponding to user layers 28/27/25 and pressures approximately
723.445/685.311/604.449 hPa. Across the nine target IR channels, **24 of these
27 cloudy channel/layer pairs are capped**. The exceptions are IR105 layers 25
and 28 and IR112 layer 25. Only 30 cloudy coefficient rows change across the
10 thermal channels at perturbed endpoints; 27 stay fixed at 20 after clipping.
For the selected nine channels, 24 of 27 changing rows stay fixed at 20.

The installed TL/AD source zeros this intermediate extinction derivative where
the strict cap predicate is true. Together with the measured overlap, this
locates where the selected liquid-control extinction path is suppressed. Other
SSA/asymmetry/source-function paths remain; the complete BT derivative is not
zeroed. No unclipped counterfactual or quantitative decomposition of the entire
BT derivative was performed.

There are 19 radiance columns, q=0..18, distinct from the two optical combinations.
The same mapping and weights apply to all five endpoints. Column 10 has weight
`0.9999980000009977`; columns 8 and 18 each have `9.99998984507755e-7`;
clear column 0 has `9.999778782798785e-13`; other columns each have
`2.220446049250313e-15`. Column 10 selects cloudy combination 1 at all three
accretion-active layers. Thus the cloudy caps there are not confined to
negligibly weighted columns. A weight is still not a BT sensitivity fraction.

Weighted column radiances reconstruct the total for all nine target IR channels
within floating-point accumulation roundoff. Channel 7 also has a solar
contribution: its total accumulator differs from the captured thermal sum by
about 0.1334759, so it is explicitly excluded from that reconstruction assertion.
A quality diagnostic should test `quality & (1 << 15)`; equal whole quality
values are not required by the bit's definition. The current measured values
remain 32768 and the project's QC is unchanged.

## Replay and remaining scope

`python3 harness/replay_extinction_layers.py` checks coverage, finiteness,
pressure ordering, explicit booleans, margins, pre/post arithmetic, component
sums, five masks, column weights/radiance sums and the recorded equality hashes.
It is an **arithmetic replay**, not a new RTTOV run or independent verification
of the original files from hashes alone. Public JSON includes every baseline
row and exact replacement rows for each endpoint; unchanged keys reuse baseline.
Raw dump hashes, source/executable hashes and two-stage comparisons are included.

Python 3.12 replay and deliberate boolean/post/weight corruption tests pass.
Independent Green/Red review compared raw dumps and original output hashes.
Physical number-unit reconciliation, overall BT derivative attribution,
unclipped physics, broader regimes, transport and timestep convergence remain
open. This closes the selected cap-location/mask measurement, not the
QC-excluded liquid-process observation-validation gate.
