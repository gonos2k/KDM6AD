# Isolated ice handoff normalization on the retained mp237 case

## Scope

This follows unmerged PR233 (`9954af4`). It leaves installed mp37/mp137/mp237
sources, binaries and the historical scope manifest unchanged. A private
experimental copy of the existing conservative Fortran module adds exactly two
assignments after the main-loop re-slope:

```
work1(i,k,4) = work1(i,k,4)/delz(i,k)
workn(i,k,2) = workn(i,k,2)/delz(i,k)
```

The original initial normalization/mstep selection and later ice normalization
are unchanged. No other process, limiter, fall-speed formula, density factor,
ABI, solver, QC or tolerance is changed. The binary still uses mp237 dispatch;
the experimental identity is **mp237 plus normalized ice handoff**, distinguished
by executable/source hashes, not a newly registered operational scheme number.
It is outside the unchanged conservative-interface-v1 freeze scope.

The source producer returns terminal velocities in m/s. Initial normalization
makes rates in s^-1 for mstep selection; main re-slope overwrites those slots
with velocities again. The extra two divisions restore the rate contract at
that boundary. Every later re-slope produces fresh velocities before its
existing division, so no already-normalized value is divided twice.

This is a measured experimental correction, **not an operational P1 closure,
physical number-basis resolution, full AD-port modification, or forecast-skill
claim**. Liquid observation approval remains 0/9; there is no RTTOV run.

## Actual execution and noninterference

Control and instrumented variants both completed the same native 5-km, 39-layer,
40-s case with dt=20 s, one MPI rank and one thread. Selected column remains
35711 (Fortran i=144,j=153). Other host objects/libraries are retained dependencies;
this is not a clean rebuild of the entire host or an mp337 ABI experiment.
Both runs used the repository runner, explicit 20-s history output, and the
currently available en0 PMIx/PRTE interface. Initial/boundary inputs are retained.

An earlier capture attempt terminated on an integer/real output-format mismatch.
It contributes no accepted scientific capture. The record formatter was fixed
and the capture rebuilt/rerun; this was not a physics failure or tolerance change.

All 253 numeric variables plus Times are byte-identical between accepted control
and capture at 0,20,40 s. The complete history SHA-256 is
`a065598b870815220ba36f7b2fbcdc6f65f8d69910c2e261961203b78d6683d8`.
Input hash records and namelists also match. Removing instrumentation restores
the normalized source exactly; its physical delta from the retained conservative
source is precisely the two lines above. This proves noninterference only for
these captured runs, not arbitrary cases/toolchains.

## Producer-to-consumer measurements

702 public records cover two calls and all 39 native layers: initial raw and
normalized rates, candidate mstep, main raw and normalized rates, ice entry/exit,
and the raw/normalized preparation after the ice substep. Work is binary64;
state, dz and dt originate in binary32 and are widened only for output.

All **234 raw/normalized pairs** (3 boundaries × 39 layers × 2 calls) reproduce
`raw_velocity/dz` exactly when parsed as binary64. Both calls selected mstep=1.
The initial and main-recomputed velocities happen to match at this column in
both calls; consumed first-ice coefficients match the main-normalized records.
This relates the selection and consumption coefficients for these calls only.

| Call | Maximum dt*mass_rate/m | Maximum dt*number_rate/m |
|---|---:|---:|
| 1 | 0.1629175974 | 0.04072939935 |
| 2 | 0.06742497278 | 0.01685624319 |

These now use measured normalized rates, unlike PR233's formal dt*raw-work
multipliers. The maxima cover the selected column, not the whole model domain.
The later-stage normalization was measured after substep 1; no substep n>=2
consumer executed in this column. This does not certify adaptive/subcycling
behavior after further velocity changes or establish time convergence.

Number post-state checks use actual capped departures, captured upper departures
and dz conversion in binary32 source order. Mass post-states are recorded, but
rho was not included in this coefficient capture: **no new independent full mass
budget is claimed**. PR233's separate measured mass-budget evidence is retained.

## Coupled changes and still-open positivity

Compared with original mp237, 0, 22, and 75 numeric fields differ at
0, 20, and 40 s, respectively.
At 40 s the selected-column maximum absolute differences include QICE
1.22430084e-5, QNICE 318755.4921875, QCLOUD 1.24525279e-4, QNCLOUD 275299072,
and perturbation potential temperature T 0.03271484375 K. These are differences
between coupled runs, not forecast errors or improvements. The initial state is
identical. This comparison separates normalization from the already-applied
conservative interface transfer; it does not compare to an independently correct
microphysics model.

All saved numeric fields are finite; hydrometeor masses remain nonnegative.
At 40 s the normalized domain still contains negative QNCLOUD (4 cells, minimum
-0.00184505107), QNRAIN (1, -4.49340760e-8) and QNICE (4, -4.64297909e-6).
Thus normalizing ice coefficients does **not** resolve whole-host number
positivity. A separate trace follows the original mp237 negatives through host
updates; it is not mixed into this normalization counterfactual.

## Historical source pin

The original pinned legacy file was found, matching SHA-256 `9354141b...`.
The current `fc0a72d...` source differs by deletion of exactly one line:
`rhox(i,k) = max(rhox(i,k),0.0)` at historical line 863. Private provenance records
label this an undefined-read cleanup: the producing routine's INTENT(OUT)
contract does not define rhox in every branch before that read. That source
rationale does not establish executable equivalence for all compilers/inputs.

The bounded history search found the recorded change but no explicit approval
chain sufficient for a new freeze certification. The four conservative edit
clusters still match; the historical legacy SHA gate still fails. **No pin is
replaced and no historical pass is fabricated.** See
`source_pin_lineage_2026-09-24.json` for exact hashes, source locations and limits.

## Reproduction

Public `normalized_handoff_2026-09-24.json` and `replay_ice_normalization.py`
replay measured arithmetic and recorded noninterference evidence. They do not
rebuild the private host or rehash its original files. Physical number units,
operational adoption, full differentiated normalized physics, meaningful number
surface export, coupled time convergence and independent radiation accuracy
remain separate open items.

Validation: eight focused normalization tests pass in Python 3.12. Both new
replayers reject Python -O. Separate negative-trace tests: seven passed.
