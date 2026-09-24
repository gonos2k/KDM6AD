# G2: PD face budgets and stage-wide negative-number discovery

## Result and scope

Two new read-only, 40-second native captures connect the positive-definite (PD)
advection limiter to the retained host RK stores. They use the original mp237
trajectory and the separately normalized mp237 trajectory from PR233, with the
same 5 km inputs, 39 mass levels, dt=20 s, one MPI rank, one thread, and two host
tiles. Both history files are **byte-identical to their respective retained
controls**, including the normalized trajectory's nine final negative cells.
The installed host, its archive, KDM source, operational defaults, number-unit
interpretation, QC and tolerances are unchanged.

The selected donors' nonnegative low-order budgets do not guarantee a
nonnegative executed final RK store. Stored limiter budgets, rounded face
scaling, and fused directional divergence/RK operations are distinguishable
parts of the measured path. This is a cause-localization result, **not a
positivity repair or operational approval**. The legacy transport P1, physical
number basis and liquid observation/cost acceptance remain open (the prior
observational status is still 0/9; no new RTTOV run was made).

## What was executed and preserved

| Item | New evidence |
| --- | --- |
| Native captures | Original mp237 and normalized mp237, one completed run each |
| New build | Private copies of `module_advect_em.F` and `solve_em.F`; read-only CPP blocks strip exactly to canonical sources |
| Retained physics | Original conservative or normalization-only KDM object, respectively; retained host `module_em` object |
| Build failure | One solver instrumentation syntax compile failed before execution; corrected private copy then compiled successfully |
| Per trajectory | 160 face snapshots, 12 configuration records, 384 whole-owned-grid summaries |
| Local stores per trajectory | 96 ordinary RK and 32 PD preparation stores |
| Event examples | 251 original / 249 normalized transition examples, plus 256 local operand records each |
| Runtime | Single rank / thread, physical mass grid 234 × 282 × 39 = 2,573,532 cells per number field |

The source changes add observation points only; no assignment to a host physics
or dynamics array is changed. `solve_em` uses a frozen source snapshot whose hash
is recorded. The newly compiled advector retains general-host contraction;
KDM's separate `-ffp-contract=off` contract is unchanged. The original advector
object's exact historical compiler command is not recovered here. Consequently
the decisive noninterference test is each complete history file, rather than an
assumption that compiler options alone establish equivalence.

History SHA-256:

- Original: `7d2afb3236ea6ea53a1df5c75f17b2b1da27f963ace697a8a912eda871c0f750`
- Normalized: `a065598b870815220ba36f7b2fbcdc6f65f8d69910c2e261961203b78d6683d8`

Each capture is compared with its own control, **not with the other variant**.
Active input canonical identities and effective namelists match. The evidence
contains build/source/log hashes and runner identities. The public replay
checks their recorded consistency; it does not reopen private sources or raw
NetCDF and independently authenticate those files.

## Face-to-store contract

The capture targets the union of 16 distinct inner donors associated with the
original and normalized final-negative cells. Selection is intentionally tied
to those regression cells; it is separate from whole-grid discovery below.
At each final RK PD call it records:

1. `PRE`: low-order face fluxes, high-minus-low correction fluxes, stored
   `ph_low`, stored `flux_out`, and seven neighboring limiter budgets.
2. `POST`: the same faces after donor limiting.
3. `Z`, `X`, `Y`: stored tendency after each successive divergence update.
4. The caller's RK operands before/after the update; PD preparation's
   `scalar_old` stores are recorded separately.

For a high-order correction face, use its **donor's** limiter decision, not
necessarily the cell being inspected. In this mass coordinate, `rdzw < 0`:
vertical flux orientation is reversed relative to x/y. The scale is

    scale = max(0, ph_low / (flux_out + eps))   if flux_out > ph_low

with the observed binary32 rounding. No uninitialized inactive `scale` variable
is read. Its recorded diagnostic is a recomputed expression with an explicit
valid flag. The independently measured POST faces verify that reconstruction.
Neighbor budgets outside the actual limiter bounds are marked invalid and are
not read; those donors do not apply this limiter.

For the captured cells, all **384 correction-face values** across both runs
reproduce exactly from PRE values and their donor budgets. The low-order faces
are unchanged. The source-grouped differences and host fused subtractions then
reproduce all **192 Z/X/Y stores**, which match the caller's actual advective
tendencies. The retained `module_em` FMA witness reproduces all **192 ordinary
RK and 64 PD preparation stores**. The final RK3 scalar tendency is zero after
PD preparation at these targets; it is not silently dropped from the replay.

This does not rederive the original fifth-order horizontal/third-order vertical
fluxes from their full stencils. It starts from their measured low/correction
faces. It also does not differentiate the host advection operator.

## Two distinct rounding locations in one donor

Consider QNCLOUD at Fortran `(i,k,j)=(233,12,124)`, step 2, RK3. The RK reference
`scalar_old` is zero; using its nonzero current intermediate scalar as the
reference would explain a different update.

| Diagnostic | Original | Normalized |
| --- | ---: | ---: |
| Stored low-order available numerator | 21,500,395,520 | 20,942,075,904 |
| Real arithmetic on stored low faces | 21,500,394,569.234 | 20,942,075,426.793743 |
| Real arithmetic on stored POST faces, final numerator | −2,094.688522845616 | +315.73554981755814 |
| RK3 donor after-store (also copied to history edge) | −0.028539743274450302 | −0.0018450510688126087 |

The “real arithmetic” columns use exact rational arithmetic on the captured
binary32 operands before converting the resulting diagnostic to binary64.
They are **not** an exact advection solution, a physical particle-count budget,
or an upper bound on all numerical errors.

For the original cell, a deficit already exists in the rounded POST face
operands; subsequent directional/RK arithmetic reconstructs the RK numerator
−2744.953369140625 as `f32(20 * f32(msfty * advect_tend))`, with
`msfty=0.9764036536216736`, and reproduces the recorded negative donor state. In the normalized cell,
those stored faces have a positive exact combined numerator, but the executed
binary32 grouping and fused updates produce a negative final state. Thus both
rounding already present in the limiter/face representation and subsequent
arithmetic matter. A universal explanation based only on the final division,
or a blanket change to the limiter scale alone, is not established.

The small final value is not a license to label every negative harmless. The
replay establishes the executed numerical path, not a physical error budget or
an approved positivity correction. No clipping, widened tolerance, advection
option switch or flux modification was introduced.

## Whole-grid discovery changes the apparent scope

The new scan observes **every owned physical mass cell** at named RK, PD,
flow-boundary, physical-boundary and microphysics call boundaries. Current
scalar and the separate PD reference buffer have independent prior samples.
It records negative counts, minima, recovered counts, first nonnegative-to-
negative transition in lexicographic `(k,j,i)` order, and up to eight largest
new-negative examples per scan. The examples are not an exhaustive event list.

All first-step scans are nonnegative. The first detected negative transitions
in both trajectories occur during the second step's first ordinary RK update.
PD scalar advection is applied only at the final RK stage in this configuration;
large intermediate-stage negatives therefore must not be confused with final
PD failures or saved forecast values.

Counts below aggregate disjoint tiles at the same stage, not overlapping
whole-domain and tile summaries. Species order is cloud / rain / ice number.

| Step 2 stage | Original negative counts | Normalized negative counts |
| --- | --- | --- |
| RK1 after update | 86,853 / 25,100 / 164,469 | 86,745 / 25,081 / 171,342 |
| RK2 after update | 165,557 / 49,170 / 225,309 | 165,496 / 49,151 / 233,496 |
| RK3 after update | 4,808 / 856 / 6,204 | 4,872 / 833 / 6,389 |
| Before microphysics, after boundary processing | 4,812 / 860 / 6,207 | 4,876 / 834 / 6,393 |
| After microphysics / solver exit / 40-s history | 4 / 4 / 3 | 4 / 1 / 4 |

For example, original intermediate QNCLOUD reaches −68,298,792 at RK2; this is
not its final saved value. Original/normalized pre-microphysics QNCLOUD minima
are −11.897686004638672 / −8.734195709228516. Final normalized minima are
−0.0018450510688126087 (cloud), −4.4934076015579194e−8 (rain), and
−4.6429790927504655e−6 (ice).

The final RK flow-boundary transitions have exactly the same coordinates and
stored values as the 11/9 negative history cells. Each matches its measured
adjacent donor's RK3 result. This includes the normalized south-boundary ice
cell, absent from the old east/north-only regression. The trace observes the
boundary call and paired values; it does not newly capture each instantaneous
boundary normal velocity or all boundary-condition branches.

Microphysics removes the interior negative states in this run while its
excluded physical-edge strip retains the final negatives. These counts do not
show how much physical number was added/removed by clipping or other processes.
The logged `pressure_weighted_deficit` uses current `mu2` for both buffers and
omits area/map factors and a resolved physical number basis. It is a diagnostic
only, **not an integrated particle-count or conservation measurement**.

The scan's “first” means first at these sampled call boundaries. An event made
and removed wholly inside one call is not observed. There is no MPI ownership
aggregation, rank-decomposition, restart, new atmospheric case or general
all-boundary positivity certification in this experiment.

## Public replay, schema and remaining work

Run `python harness/replay_number_face_flux.py`. Standard-library arithmetic
replays both complete captures. Existing exact-rational binary32 FMA support is
reused. Generic face-scaling, divergence and exact stored-face budget functions
are separated from the **fixed** case schedule. The latter requires all 16
specified donors, both calls, all five flux phases, both tiles, all three
species, and all 384 summaries per run. Removing records and shrinking a
manifest cannot redefine that expected coverage.

The JSON's compact `flux` rows have nine leading fields:
`tag, step, rk, species, tile, target, i, k, j`, followed by 103 widened REAL4
values. The complete value layout is in `SCHEMA_number_face_flux.md`. Other
records have named fields. Full captured summaries and local operands are
public; private vendor Fortran and NetCDF remain local.

Next design work must preserve a common face transfer while making the
**executed final update** respect its available budget, with conservation,
rounding and boundary treatment tested together. This evidence does not select
such a production change. It also does not justify requiring each intermediate
high-order RK stage to satisfy an invariant that the present scheme only
attempts to enforce at its final stage.

G2's selected upstream-budget localization and normalized stage-wide discovery
are now measured. Global positivity repair, full high-order stencil attribution,
physical number units, multi-rank/restart coverage, normalized full AD/ABI and
independent radiative accuracy remain separate open work.

Validation: Python 3.12.13 focused suite passed **33 tests** (18 new face-budget
checks, 7 retained negative-trace checks, 8 retained normalization checks).
The new tests include missing phases/donors/summaries/operand and transition
records, wrong face signs/stores, nonfinite values, variant-proof substitution,
false approval, scan/event provenance labels and Python `-O`; a separate synthetic case checks reversed z
orientation and distinct neighboring limiter budgets. Ruff passed.
