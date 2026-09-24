# Fixed-coefficient ice distribution and layerwise derivatives

## What this adds

The same second-call native 39-layer operands from PR232 are used without new
atmospheric data or vertical remapping. Existing conservative substeps are run
at a fixed final numerical interval of 20 with m=1,2,4,8,16,32,64,128. Raw work,
source density and thickness remain fixed. State and fall accumulators are
carried between substeps. No operating time step, default physics or tolerance
is changed. This is distinct from re-estimating fall speed or size each substep.

A critical source-contract caveat was confirmed while interpreting the result:
**the captured first ice handoff is raw fall speed, not a verified normalized
rate**. The curves below reproduce the executed numerical coefficient map.
They cannot yet be called physical temporal-error or physical Courant estimates.

## Raw handoff versus normalized rate

The private canonical source audited here has SHA-256
`fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5`.
Source locations below refer to that file. Public coordinator assignments and
the frozen conservative-interface document corroborate the raw handoff.

Canonical `module_mp_kdm6.F` first divides both main and ice work by delz before
selecting mstep/mstep_i (1170–1177). After each main substep it calls slope_kdm6
again (1263), overwriting work with terminal velocities, then divides only main
slots 1/2/3 and workn slot 1 by delz (1269–1274). The first ice substep consumes
the undivided ice slots 4/2 (1284–1285); later ice substeps reslope and normalize
ice again (1335–1336). Existing conservative-interface-v1 explicitly preserves
this handoff, as documented in `docs/FREEZE_LIFT_CONSERVATIVE_INTERFACE_V1.md`.

Thus increasing a divisor while freezing this raw coefficient is a different
experiment from running the host's full subcycling/reslope logic. In particular,
`dt*work` must not be labeled a dimensionless physical Courant number here.
For the selected active layers, the following are *numerical multipliers* and
separate hypothetical `dt*velocity/dz` values; no normalization fix was applied:

| Native layer | dt*raw mass work | dt*raw number work | dt*raw mass work/dz | dt*raw number work/dz |
|---|---:|---:|---:|---:|
| 24 | 4.36083 | 1.09021 | 0.00600207 | 0.00150052 |
| 23 | 4.18808 | 1.04702 | 0.00571423 | 0.00142856 |
| 22 | 4.01202 | 1.00300 | 0.00540493 | 0.00135123 |
| 21 | 3.64150 | 0.91038 | 0.00483861 | 0.00120965 |
| 20 | 6.37989 | 1.59497 | 0.00839030 | 0.00209757 |

The fact that recorded mstep_i=1 coexists with a large raw multiplier must be
read with that intervening overwrite. This audit identifies a separate existing
handoff/unit issue; it does not negate PR232's paired-transfer improvement.
The host's source coefficient meaning must be resolved before a time-accuracy
threshold can support operational adoption.

## Independent formal references

In inventory coordinates y_k=w_k*x_k, choose w=dz for number and w=rho*dz for
mass. For each separate frozen numeric coefficient vector a, construct

    y'_0 = -a_0 y_0
    y'_k = a_(k-1) y_(k-1) - a_k y_k
    S'   = a_bottom y_bottom

The extra component S is a surface counter, **not an additional atmospheric
layer**. The 40×40 matrix has zero column sums. Its matrix exponential is one
reference. A second, positive Poisson series uses lambda=max(a), transition
P=I+A/lambda, and exp(-lambda*t) sum_j (lambda*t)^j/j! P^j y0. The remaining
Poisson tail is bounded geometrically once successive term ratios are below
one. This bounded implementation accepts lambda*t<=64 (actual maxima: 47.6300
mass, 11.9075 number) and stops with tail bound <=1e-17. A known two-cell solution
and a zero-rate stationary case independently check indexing and surface sink.

The two references differ in normalized L1 by 5.18e-15 (mass) and 1.05e-15
(number). These compare two numerical solutions of the **defined formal frozen
map**, not an observed atmospheric truth or a unit-corrected KDM solution.

## Distribution versus total inventory

Define E as the sum of absolute layer-inventory differences plus absolute
surface-export difference, divided by initial inventory. Both quantities are
reported separately; no time-accuracy acceptance threshold is introduced.

| m | Numerical interval per substep | Number 100E | Mass 100E |
|---|---:|---:|---:|
| 1 | 20 | 81.195602% | 158.699152% |
| 2 | 10 | 32.813251% | 128.713047% |
| 4 | 5 | 13.009166% | 116.757240% |
| 8 | 2.5 | 5.918706% | 18.883233% |
| 16 | 1.25 | 2.833634% | 8.499297% |
| 32 | 0.625 | 1.387531% | 4.051729% |
| 64 | 0.3125 | 0.687353% | 1.980387% |
| 128 | 0.15625 | 0.342549% | 0.979281% |

The maximum normalized total closure residual is 4.98e-16.
The nonnegative layer/surface inventories remain conservative to rounding while
distribution differences remain substantial. An L1 difference above 100% is
possible for two nonnegative distributions with equal totals (maximum 200%);
it is **not mass loss**. None of these percentages is a forecast-error estimate,
project completion percentage, or evidence that m=128 is operationally adequate.
All reference and substep layer inventories and surface counters are published.

## Genuine forward-mode layerwise derivative

With fixed work/density/thickness, use zero-based top-down k and directions
0.01*qi*sin(k+0.3), 0.01*ni*cos(k+0.7). `torch.func.jvp` and `torch.func.vjp`
exercise forward and reverse modes on all four output arrays. Independent
centered differences use h=1e-4. The direction leaves zero inputs at zero and
preserves positive inputs; no threshold crossing is introduced by this scaling.

| Output | Array max-norm JVP–FD relative difference |
|---|---:|
| qi | 1.4893e-10 |
| ni | 1.0281e-10 |
| fall_qi | 8.0070e-11 |
| fall_ni | 5.4059e-11 |

Seeds vary by layer and are scaled per output array. The recorded dual residual
is zero for their combined contraction. This extends total-inventory derivative
checks to one nonuniform layer direction. It is not the full Jacobian, a native
AD run, or differentiation through reslope, density or geometry changes.

## Validation and remaining scope

Four focused Python 3.12/Torch 2.14 tests pass, including the independent
reference cases, measured distribution/closure and true forward-mode layer
checks. A Torch JIT deprecation warning is retained. Public replay performs the
existing substep calculation; it does not rerun the original private inputs.
Operational legacy transfer P1, raw ice handoff normalization, physical number
basis, full model temporal accuracy and independent radiation accuracy remain
open. Liquid observation approval remains 0/9; no RTTOV execution is implied.

## Reproduce

```bash
python3.12 harness/replay_ice_time_accuracy.py
python3.12 -m pytest oracle/tests/test_ice_time_accuracy.py -q
```

Inputs: `native_ice_transfer_2026-09-20.json` (unchanged PR232 evidence).
Outputs: `ice_time_accuracy_2026-09-20.json`, regenerated from the public input
and existing Python conservative function. The native host is not invoked by
these commands.
