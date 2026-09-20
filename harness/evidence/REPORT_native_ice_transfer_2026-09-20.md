# Existing conservative ice substep on native operands

## Scope and execution

PR231 measured a large legacy ice number departure/arrival mismatch. This
follow-up connects the **existing** conservative implementation to raw operands
from the same fixed 5 km model column 35711 and native 39 layers. It adds no
sedimentation algorithm and changes no operational default, host source, ABI,
density convention, QC, tolerance or Python 3.12 CI policy.

One additional isolated mp37 capture ran for 40 s at dt=20 s, np1, one thread,
with the existing model inputs. The previous uninstrumented control is reused.
All 12,050 previous capture scalars are exactly unchanged; the complete history
file has the same SHA-256 as that control, which had 254 numeric variables at
0/20/40 s. The new executable records 780 additional scalars: two calls × 39
layers × 10 raw operands. No RTTOV call or conservative full-host integration
was performed. Build setup failures preceding this completed run are not runs.

The extra capture is immediately before each ice `falk` calculation, before
both mass and number updates. It records qi, ni, actual work1/workn, source
rho, dz, dt, mstep, and both input fall accumulators. This matters because the
previous top-number capture occurs **after** the top mass update. Each local
pre-state is untouched by higher-cell updates at this stage. Both actual calls
have one substep; input fall accumulators are zero. The public vectors explicitly
reverse native bottom-first indices into the APIs' top-to-bottom order.

## Precision contracts and legacy reproduction

Native prognostics, density, thickness, dt and stored falk/fall are REAL(4),
while work1/workn are REAL(8). A separate REAL(8) emitter preserves the latter;
no velocity or flux is reconstructed by dividing the rounded offered removal.
Removing the capture blocks recovers the original canonical source exactly.

The independent scalar number replay evaluates ni*workn/mstep in binary64,
rounds at the native falk store, then follows binary32 multiply/divide/update
order. It exactly reproduces all 78 native number post-states, offered removals
and the recorded interior departure/arrival pairs. This is legacy reproduction,
not conservative validation or a newly measured native AD result.

The existing Python legacy/conservative APIs are then called with prognostics
exactly widened from their stored binary32 values and work coefficients retained
as binary64. This is a **promoted local substep comparison**. It is not expected
to reproduce every native binary32 result bit-for-bit and is not a rerun of the
whole microphysics coordinator or a corrected model trajectory.

## Existing conservative result

For number, the existing conservative implementation uses dz; for mass it uses
rho*dz. Each entry-capped departure is carried to the next layer once. The
receiver does not recap it against the already-updated donor state.

At native layer 24→23, actual legacy departure is 436252.71875, donor thickness
726.5537109375 m, and legacy arrival is zero. The promoted conservative arrival
is **432462.8106390596**, accounting for the different receiver thickness.
The two concentration changes need not be equal; their common interface quantity
must be equal. This is obtained by executing the existing kernel, not merely
relabeling a prescribed legacy transfer.

Second-call promoted binary64 inventories, including actual bottom export:

| Quantity | Before | Legacy after | Conservative after | Conservative residual |
|---|---:|---:|---:|---:|
| dz-weighted number | 415967610.3840862 | 977.6956750149552 | 415967610.3840862 | 0 |
| rho*dz-weighted qi | 0.000872088464913803 | 2.7273837481754944e-15 | 0.0008720884649138032 | 2.1684e-19 |

Actual bottom export is zero in this local case for both quantities. States
remain nonnegative. The mass row describes the promoted kernel evaluation on
captured qi operands; **native mass post-states were not independently captured
by this follow-up**, so it is not new raw-bit native mass validation. Neither
row resolves the host number-unit convention or dry/moist density contract.

## Derivative and independent transfer checks

For the existing conservative Python kernel, fixed density/thickness/work and
a homogeneous 1% qi/ni direction give weighted JVPs of
8.720884649138032e-6 and 4159676.1038408615. They agree with the differentiated
input inventories to relative errors 1.94e-16 and zero. The VJP/JVP dual residual
is zero; independent central differences with h=1e-4 differ by 5.59e-11 and
1.31e-10 relatively. Zero entries have zero direction; no min threshold is
crossed along this scaling direction. These are conservative local derivatives,
not native legacy AD, velocity sensitivity or density/geometry derivatives.

Additional explicitly synthetic tests cover an empty donor, unequal thickness,
nonzero pre-existing fall accumulators that must not be reinjected, and three
carried substeps with nonzero actual bottom export. The latter moves an inventory
of 16 completely to the surface; it is not an observed native surface-export case
or a time-step convergence study.

## Remaining P1 and approval boundaries

The measured legacy departure/arrival defect remains **P1 OPEN in the operational
track**. Validation of an already-existing opt-in conservative kernel does not
change that default or close the production issue. Legacy evidence is retained;
corrected transfer results are not required to equal the nonconservative legacy
trajectory. Wider decisions still require physical number units, native mp137
ABI/host integration, other species, density coupling and timestep convergence.
Liquid observation approval stays 0/9, with independent radiative accuracy open.

The public replay runs the existing Python kernels and checks the recorded raw
operands against PR231. It does not execute or authenticate the private original
Fortran/NetCDF files. Source/build identities and successful run validity are
recorded separately from the public arithmetic results.

## Actual C++ cross-check and mixed-precision residual

The standalone `harness/native_ice_driver.cpp` compiles the current existing
legacy/conservative sources and ops, without changing CMake, installed libraries
or automatic CI matrices. It accepts raw top-down operands on stdin and emits
hexfloat state/fall vectors for both variants in mixed f32 and promoted f64.
The f32 mode retains binary64 work arrays and the existing native falk casts.

Both actual captured calls were executed in all four driver modes. The legacy
mixed-precision **ni outputs match all 78 native values exactly**. All four
promoted f64 output vectors (qi, ni, fall_qi, fall_ni), for both variants and both
calls, match Python exactly. This is direct C++ kernel execution, not an mp137
ABI/host run. Local Python is 3.12 with Torch 2.14; the separately linked C++
Torch/build identity is recorded in the result evidence. The public CI policy
remains Python 3.12 with its existing pinned dependencies.

For the second mixed-f32 conservative call, the dz-weighted interface mismatch
is −1.3916910937049352 against departure 415967125.4978605: relative
−3.3456756757862904e-9. State-update rounding contributes +0.1830206229351461;
the signed cell-difference inventory is −1.2086704712351093. Subtracting separately
summed endpoint inventories instead gives −1.2086704969406128; these are distinct
floating-point evaluation orders. The signed ledger residual is −4.65e-10.
Thus the paired transfer fix removes the large systematic loss while retaining
ordinary f32 conversion/update residuals. It does not imply exact real-arithmetic
conservation or a newly approved dry-mass number basis.

Validation: **9 focused Python 3.12 tests passed**, covering both actual captures,
corruption rejection, differentiated inventory, empty donor/unequal dz and carried
substeps. C++ checks are explicit local executions through `--cpp`, not new CI
jobs. Example after building the standalone driver:

```text
python harness/replay_native_ice_transfer.py --cpp /path/to/native_ice_driver
```

On this machine the executable additionally uses the existing local OpenMP
runtime through `DYLD_LIBRARY_PATH`; build/runtime paths and hashes accompany
the recorded results. No external atmospheric data were acquired.
