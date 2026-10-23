# Applied finish and tendency derivatives

The new local operator composes the completed state/forcing KDM interface with
the actual thermodynamic application path: `R(s,Z(K(s,F)))`. `Z` is the
post-microphysics cleanup, and `R` is the moist-theta finish. The direct old
state dependence and the cleanup tangent/adjoint are included. This is a
first-order column operator, not a full native timestep or assimilation run.

## Attribution

* Base: feature `ac286b6ddb2067ff6c68b638c51d6354606cbbc0`, containing merged
  PR #427. Main remained `93037859` at intake.
* The primary input is the saved PR #426 second MP call, `(i=156,j=21)`, all
  39 native levels. The original trace SHA is `9ec44c6f…00dd2b5`.
* This run reuses the isolated fp64 kernel library from PR #427, SHA
  `3e968dcd…a1693e4`, with unchanged C++ kernel/bridge sources. It does not
  rebuild or replace the operational library. The Python finish map and the
  Fortran shim are the new source in this experiment.
* Local Torch is 2.13.0 and NumPy 2.2.6; pinned CI Torch 2.8.0 is a separate
  check. [Manifest](manifest.json) records source, library and Fortran checks.
* Captured configuration: `dt=20 s`, alpha f32 bits `3FCDDED2`, `T0=300 K`,
  `MP_TEND_LIM=10 K/s`, `MP_ZERO_OUT=2`, threshold f32 bits `322BCC77`.
  Kernel input coordinates remain legacy/raw `dry_number=0`; no number-unit
  normalization or new physical conservation claim is introduced.

## Saved value boundary

The [read-only boundary audit](saved_boundary_audit.json) and source call order
identify `zero_outb`/`zero_outa` between MP output and finish. The selected
column is interior, so the boundary-only operation does not apply. Mode 2
clamps negative QV and removes subthreshold QC before finish computes rates.

In saved step 1, QC at level 2 changes from `5.684341886e-14` to zero; other
levels are already zero. In step 2 every raw output QC is zero. The change in
step 1 rounds away in the stored QC_RATE, so equality of QC_RATE alone would
not prove an unchanged QC handoff. The source and checkpoint comparison are
used together. `FINISH_PRE` does not directly record QC before/after.

On the primary step-2 capture, the unchanged binary32/FMA finish replay plus
QC-rate calculation matches **312/312 values bitwise**, with zero mismatches.
Four T/Q handoff comparisons per layer also match (**156 pairs**). This is
saved f32 value evidence, distinct from the new continuous fp64 lift.

Both saved steps have 39 strictly interior temperature-clip samples, no active
temperature limits or ties, and positive QV throughout. QC is below the
cleanup threshold at all 39 levels. The active clip and other cleanup branches
are exercised by separate synthetic tests, not by this native profile.

## fp64 differential results

The [full sweep](native39_finish_ad.json) checks the five finish outputs
`T_NEW_AFTER,H_RATE,QV_RATE,QC_RATE,TH_PHY_M_T0`. It uses nine central-difference
epsilons per direction, a single branch-preserving epsilon across all five
field gates, and fixed output scales `(1,1e-3,1e-6,1e-6,1)`.

Each field requires scaled absolute error at most `1e-9+3e-6*scaled_signal`;
the maximum tolerance ratio must be at most 1. Dot relative error is bounded
by `1e-10`. These criteria were set before the first run and were not relaxed.

| Composed direction | Dot relative error | Best epsilon | Maximum field tolerance ratio |
| --- | ---: | ---: | ---: |
| State theta/QV/QC | 3.77e-16 | 1e-2 | 0.0126 |
| DEN | 0 | 1e-2 | 0.0101 |
| PII | 3.35e-13 | 3e-4 | 0.0153 |
| P | 2.37e-16 | 1e-2 | 0.133 |
| DELZ | 1.40e-16 | 1e-2 | 0.180 |
| Mixed | 8.90e-14 | 3e-4 | 0.00784 |

Finish alone passes six tested directions (old theta/QV/QC, new theta/QV,
mixed), with maximum dot relative error `1.54e-16` and maximum best field
ratio `0.00676`. The new-QC native direction is zero and explicitly **untested**;
old QC is also extremely small. Synthetic cases supply independent nonzero QC
derivative anchors. This does not certify every condensate direction on the
native profile.

For the chosen five-output cotangent and state direction, the direct old-state
VJP term contributes about `24.8724`; the complete paired dot is about
`-1.17938`. Omitting the direct term makes that RHS about `-26.0518`.
This is an operator diagnostic, not an observation cost or a physical-process
attribution. Independent finite differences verify the complete forward map.

## Fortran output-preservation fix

All corresponding public real array output declarations use `INTENT(INOUT)`
in both bind(C) and friendly wrappers; handles still use `INTENT(OUT)` and
are nulled on error. The analogous existing state-only declarations were
updated in the same sweep. There is no change to C signatures or symbol count.

With GNU Fortran 15.2.0, `-O3 -ffp-contract=off`, the **same new canary test**
linked to the **same kernel library** gives:

| Shim | Outcome |
| --- | --- |
| Unmodified base `ac286b6d` | exit 1: `local state-shape rejection changed output backing storage` |
| Corrected source | exit 0; shape/selector/null-handle noncontiguous output canaries preserved, normal parity and scaled derivative checks passed |

This reproduces a memory-level failure for this compiler, in addition to the
language-contract issue. It is not a prediction about every compiler. Outputs
must be defined by the caller if their values are to be retained; internal
errors do not gain transactional rollback. Existing compiled callers need
recompilation against the new module. The private operational host was not
rebuilt or patched.

The prior unscaled NCCN stress still reports `1.905e-9` relative against its
original `1e-10` target. Neither this interface fix nor the new finish map
closes that known kernel numerical limitation.

## Verification and limits

The focused local suite passed **42 tests**: finish/cleanup analytic and
autograd/FD checks, independent affine/identity-backend composition checks,
input/output refusal cases, and existing replay/verifier regression checks.
Fake backends test composition mechanics and are not native physics evidence.
The local Fortran test is compiled from the corrected public source against
the attributed existing library; it is separate from the saved host run.
The legacy Fortran smoke, normalized-AD, and state/forcing programs all passed
after recompilation with the corrected shim (**3/3 programs**).

The [API and mathematical contract](../../../docs/APPLIED_FINISH_AD.md) gives
the direct-state term, cleanup masks, units, and threshold policy. Positive QC
threshold equality is discontinuous and is rejected by explicit derivatives;
temperature-clip ties use a documented clipped-side convention. The existing
KDM ABI does not expose its internal integer schedules or all limiter branches.

No new native integration, restart campaign, observation processing, RTTOV,
minimization or forecast experiment was run. The saved posterior remains
unaccepted. This work excludes host prep, state-generated forcing `G_X`, RK,
all other moist fields, full checkpoint/adjoint replay and RTTOV pressure/cost
derivatives. The live native stepper remains value-only. H_DIABATIC has a
mass/map-scaled temperature-tendency consumer, but the resulting RK temperature
increment is not isolated or differentiated here. With `USE_Q_DIABATIC=0`, the
explicit water-rate RK-add branch is off; prognostic moisture still advances.

Graphify's public graph is supplemented by source inspection for private host
producer/consumer paths. It does not constitute complete private-host AST
coverage. Raw graph reports remain outside the wiki.
