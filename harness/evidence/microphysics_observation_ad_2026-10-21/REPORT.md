# Native microphysics to actual observation cost: local composition

The selected native-column map now runs **prep → KDM → all-mass cleanup →
finish → diagnostic EOS → native all-sky profile → actual RTTOV-K → KMA BT
Huber cost**. The seven representative full-composition directions pass the
unchanged first-order transpose and independent central-difference gates.
A separate saved cloudy column also supplies nonzero liquid-NC observation
sensitivity, filling the prior profile-only number case's local-zero gap.

These are offline continuous-fp64 substep experiments. No native model
integration, optimizer or operational forecast executable was run or changed.
The old whole-domain KO assimilation remains paused.

## Primary composition and phase attribution

`native39_composed_cost.json` records native step 2 at `(i=156,j=21)`, using
the same saved trace and 39-level/40-interface geometry as the earlier prep
case. The trace comes from the prior saved-T/Q two-step experiment, whose
posterior was diagnostic and scientifically unaccepted. This experiment does
not promote it to an accepted analysis.

The selected endpoint checkpoint is `2025-07-19_00:00:40`. It supplies the
source-reconstructed PH/MU/hybrid geometry and fixed profile weights. The
dynamic starting theta/QV are the corresponding **pre-KDM physics-entry**
operands reconstructed from the trace; the ten other kernel fields are the
captured MP inputs. This is not a new `0→40 s` host run and does not use the
saved checkpoint's final T/Q as a replacement for KDM/finish output.

Loading the case reuses and checks the earlier f32 evidence: all five prep
outputs match the captured 39 layers, finish T/Q match the checkpoint at all
39 layers, and reconstructed terminal EOS pressure matches `P+PB` at all
39 layers. The captured pre-MP pressure differs from terminal pressure at
9 layers; the JSON preserves this phase distinction. These value checks are
separate from the continuous-fp64 derivative experiment.

The executed kernel contract is `physics_variant=0`, `dry_number=0`,
`dt=20 s`, `XLAND=2`, `ncmin_land=ncmin_sea=10`. The isolated research
library SHA-256 is `3e968dcd43f6d361a2e1be6b963f76dcb9de1381313875e5c805af187a1693e4`.
It is reused with its build manifest and unchanged C++ source hashes;
the historical Fortran shim/test hashes differ from the later INOUT fix and
are not presented as freshly rebuilt. This verifier calls the C ABI directly.

Host cleanup with `MP_ZERO_OUT=2`, `MP_ZERO_OUT_ALL=0` affects the six water
mass fields, while the number fields pass through. Finish uses cleaned QV/QC
and its direct old-state terms. Observations receive cleaned QC/QI/QS, raw
NC/NI, finished moist theta and cleaned QV. EOS pressure/density are then
diagnosed at **the same original MU/PH**. P8W/P_HALF is reconstructed using
the actual profile source formulas, not copied from pre-MP forcing or
substituted from the auxiliary hybrid pressures.

For `USE_THETA_M=1`, QV has no direct EOS P/rho sensitivity at fixed moist
theta/MU/PH. Its paths through KDM/finish, dry-theta conversion and observed
humidity remain live. Density depends on the held-column MU/PH geometry.
The observation interface keeps native pressure levels and interfaces; only
the prescribed fixed-reference upper prefix and its live partial-layer
junction are added.

## Actual BT and cost verification

The final run uses **71 actual RTTOV calls**: one recording point and five
central-difference epsilons for each of seven directions. Every difference
reruns the entire local map, including the opaque KDM and actual RTTOV.
The seven KO channels 10–16 are retained. The baseline Huber cost is
`101.90147755152957`, with sigma `1 K`, delta `1`, zero added bias and the
existing KMA BT conversion. This cost is a diagnostic, not a reported
improvement over a different state, mode or experiment.

Predeclared criteria remain `dot_rtol=1e-10` and fieldwise
`FD_atol=1e-8`, `FD_rtol=3e-5`. One common eligible epsilon must satisfy
**every retained channel and the final cost**. Eligibility preserves the
exposed finish/cleanup signatures, cloud fraction and quality mask.

| Direction | Cost direction (VJP) | Dot relative error | Best epsilon | Maximum BT/cost tolerance ratio | Passing epsilons |
| --- | ---: | ---: | ---: | ---: | ---: |
| moist theta | 0.3806388600 | 2.92e-16 | 0.003 | 0.0001873 | 5/5 |
| QV | -0.04710189094 | 4.42e-16 | 0.003 | 0.0153989 | 4/5 |
| cloud mass | -0.000476551951 | 7.92e-14 | 0.01 | 0.00320076 | 5/5 |
| cloud number | 2.328588052e-7 | 6.82e-16 | 0.001 | 0.00796916 | 4/5 |
| MU | 0.05895111014 | 0 | 0.01 | 0.000417874 | 5/5 |
| PH interfaces | 0.01670438372 | 4.15e-16 | 0.01 | 0.00212948 | 5/5 |
| mixed | 0.4087161438 | 2.72e-16 | 0.003 | 0.00142828 | 5/5 |

The number direction changes positive captured NC/NI proportionally and leaves
zero reservoirs zero. In this primary column NC is zero; the actual input
number perturbation is NI. Its path includes KDM, so a small nonzero cost
direction does not imply an unclipped direct optical NI sensitivity. The
separate cloudy-column case below has the complementary direct liquid NC
signal. Neither proves parameter identifiability.

The JSON includes control vectors, full kernel and cleaned outputs, all five
applied finish fields, observation-state covectors, pre-KDM X/rest cost
covectors, profile K, channelwise FD values, failures at other epsilons and
the selected best epsilon. The baseline state has four positive QI layers,
one QS layer, no QC and seven positive NI layers after KDM. It retains the
same optical number-unit qualification as the prior work.

## Independent cloudy-column number case

`native40_number_obs.json` and [NUMBER_CASE.md](NUMBER_CASE.md) use the
unchanged native-observation verifier on the same checkpoint at
`(i=110,j=110)`. All nine directions pass in **91 actual RTTOV calls**.
This run starts from a saved checkpoint, so its scope is **profile → RTTOV
cost**, separately from the primary microphysics composition.

The combined NC/NI direction gives a cost derivative `0.00158313453354`;
the independent FD at epsilon `0.003` is `0.00158313450749`, with maximum
tolerance ratio `0.00045314`. Liquid NC carries the nonzero signal (23 levels);
NI's cost contribution is approximately `5.05e-30`, despite one locally
unclipped Deff response. It is not reported as meaningful NI sensitivity.
No invalid `QC>0,NC=0` or `QI>0,NI=0` state was repaired to create this case.

## Evidence, verification and limits

The final primary run checks **117** input/source hashes before and after;
the cloudy-column run checks **81**. The pinned actual RTTOV executable is
`0909d289778d3ea91f6300fd8c5f88e5e1dcc0528d260aec94f3aab0bc7692fd`.
The previously existing RTTOV build is reused; no clean vendor rebuild or
new source-to-binary certificate is claimed. Fixed template trace gases,
surface and viewing geometry are assumptions, not demonstrated collocation
with either native column. Ozone-state assimilation is not implemented.

KO nominal time is `00:00:00`; the reconstruction endpoint/checkpoint is
`00:00:40`, a **+40 s diagnostic offset**. Pixel acquisition time is unknown.
P8W is source-reconstructed, not independently captured. The PH/MU staging
is source/replay supported rather than a newly recorded full prep snapshot.

The runtime's internal integer substep/branch schedules are not fully exposed;
the independent FD checks provide additional evidence beyond an inner-product
test. Rounding of the operational f32 map is not differentiated. Independent
coverage of every kernel-state block, arbitrary limiter branches, full-host RK,
retained heating memory across timesteps, HVPs, long-window optimization and
forecast skill are outside this result.

The raw C kernel numbers are passed unchanged into the selected
Registry-based optical interpretation. This composition tests that declared
mathematical map; it does not settle legacy raw number units, moment
admissibility for every state or mass/number/energy conservation. Cleanup
removals are not a closed applied water budget. Named-process attribution
remains distinct from state and BT/cost sensitivity.

The prior **2–3% whole-reference/native pressure** discrepancy remains
unresolved. This experiment holds upper-reference arrays fixed and does not
reclassify that failure as solved. The raw NCCN stress limitation also remains
in the earlier state+forcing evidence.

Synthetic tests independently check the adapter's JVP/VJP against differences,
full number pass-through, mass cleanup/ties and observation layout. NumPy-only
tests check refusal and channelwise/common-epsilon acceptance. The Torch tests
are in the mandatory Oracle suite. Full local/CI results and source/build/run
counts are recorded in `manifest.json`; skips are not counted as passes.
