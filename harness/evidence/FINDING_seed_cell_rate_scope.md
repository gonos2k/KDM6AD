# Scoping the seed: which rates can even reach the divergent cell

Reconnaissance on the v10 result, from the recorded state alone — no new
instrumentation. Narrows the candidate operations at the first divergent cell
from the whole first half of the microphysics step to one branch and a bounded
rate set.

## The cell

First divergence: `micro_post_state_update`, loop 2, column 3, k 0, `qr`, both
pairs at −3 ULP. Column 3 at loop 2, as the microphysics receives it
(`outer_post_sed`, bit-identical across all four legs):

| k | t | qv | qc | qr | qi | qs | qg | nc | nr | ni |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 243.59 | 4.20e-4 | 6.12e-4 | 3.77e-8 | **0** | 1.37e-6 | 6.02e-10 | 1.10e9 | 262.3 | **0** |
| 1 | 243.18 | 3.85e-4 | 6.41e-4 | 9.38e-8 | **0** | 5.10e-6 | 2.16e-9 | 1.10e9 | 325.8 | **0** |
| 2 | 242.77 | 3.52e-4 | 6.66e-4 | 1.30e-7 | **0** | 1.15e-5 | 6.61e-9 | 1.10e9 | 223.9 | **0** |
| 3 | 242.35 | 3.23e-4 | 6.92e-4 | 1.33e-7 | **0** | 1.96e-5 | 1.56e-8 | 1.10e9 | 112.9 | **0** |

## Two eliminations, both from the state

**Every level takes the COLD branch.** `t` is 242.3–243.6 K against
`t0c = 273.15`, so `supcol ≈ +30 K` throughout and the update takes the
`t <= t0c` arm (F:2796). The warm arm at F:2918 never runs here, which removes
`paacw`, `pseml` and `pgeml` from the qr update entirely.

**`qi` and `ni` are identically zero at all four levels.** Every rate whose
operand is cloud ice therefore vanishes: `piacr`, `praci`, `psaci`, `pgaci`,
`piacw`, `pidep`, and the corresponding number rates.

The cold-branch qr update is

```fortran
qrs(1) = max(qrs(1) + (praut + pracw + prevp - piacr - pgacr
                       - psacr - pmulrs - pmulrg)*dtcld, 0.)
```

with the incoming `qrs(1)` bit-identical (it comes from `outer_post_sed`) and
`dtcld` a sealed scalar. With `piacr = 0`, the seed for this cell is in one of
**seven** rates: `praut`, `pracw`, `prevp`, `pgacr`, `psacr`, `pmulrs`,
`pmulrg`.

## The divergence pattern across the column

Fields differing between Fortran and C++ at `micro_post_state_update`, loop 2,
column 3:

| k | differing |
|---|---|
| 0 | `t`, `qr`, `qs` |
| 1 | `t`, `qi`, `qs`, `qg`, `nr`, `brs` |
| 2 | `t`, `qs`, `qg`, `brs` |
| 3 | `t`, `qv`, `qs`, `qg`, `brs` |

`t` and `qs` differ at every level; `qr` differs only at k 0, where `qr` is
smallest (3.8e-8 against 1.3e-7 at k 3), so a perturbation of the same size in
the rate sum tips the f32 result there and not below.

## What this does NOT establish

The candidate set is bounded but not resolved. Attributing to a particular rate
needs the rate values, and the sign pattern does not settle it by inspection:
the fields that differ at k 0 (`t`, `qr`, `qs`) share `psacr` and `prevp`, but
the observed directions (`qr` −3, `qs` −6, `t` +2) are not jointly consistent
with a single perturbed rate under either `delta2` setting, so either more than
one rate differs or a gate differs. That is a measurement, not an inference.

## What would settle it

The scaled rates as `state_update` consumes them, recorded on both sides:
Fortran after the mass-conservation feedback and before the branch at F:2796,
C++ at the `scaled.warm` / `scaled.cold` arguments to `state_update`.

The C++ carries name-matched members for all of them (`WarmPhaseOutputs`:
`praut`, `pracw`, `prevp`; `ColdPhaseOutputs`: `pmulrs`, `pmulrg`, …) with one
class of exception that needs care rather than assumption: `pgacr` and `psacr`
appear as `pgacr_adj` and `psacr_adj`, and `paacw` as `paacw_adj`. Whether the
`_adj` value is the quantity the Fortran update line reads has to be
established from the source, not from the name — this is exactly the kind of
site the two placement defects in this protocol came from.
