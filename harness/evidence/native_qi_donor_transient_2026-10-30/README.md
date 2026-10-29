# QI donor transient at the remaining M0 failure

This packet adds a passive trace to the opt-in QNC live-guard V7 host variant.
It records the ice-mass boundary target `(i,j,k)=(1,168,33)` and its actual
X-start donor `(2,168,33)` through QI tendency, RK updates and boundary calls
at RK1/2/3, then before/after microphysics and at finish. The Fortran arrays
use `(i,k,j)` order. No QI or NI assignment was changed.

## Executed path and noninterference

Control and α=0.25 each completed one 20 s native host step with this trace
off and on: four completed steps total, one MPI rank and one thread. Each
off/on pair has the same full checkpoint SHA-256 and applied ACK. Each
checkpoint also matches the corresponding QNC live-guard V7 checkpoint.
The existing 382-cell QNC face and RK traces are byte-identical to V7 in both
trace-on runs. Only `solve_em.o` changed in the private archive; the KDM DSO
and QNC guard objects are inherited. One preliminary compilation was
interrupted before link and is excluded from successful executions.

## First observed divergence

| Donor `(2,168,33)` | Control | α=0.25 |
| --- | --- | --- |
| RK1 and RK2 donor QI after update | `80000000` | `80000000` |
| RK3 before QI update | `80000000` | `80000000` |
| RK3 `ADVECT_TEND` after QI tendency call | `00000000` | **`000021A3`** |
| RK3 donor QI after update | `00000000` | **`00000002`** |
| RK3 target QI after `flow_dep_bdy` | `00000000` | **`00000002`** |
| Post-microphysics donor / target QI | `00000000` / `00000000` | `00000000` / **`00000002`** |

At RK3 the recorded donor `MOIST_OLD` and `MOIST_TEND` are both zero. With
the saved `C1H=−0` and `C2H=95000`, both exact old/new mass coefficients are
95000. The α stored-word RK expression equals about **1.7621405564
binary32 subnormal ULP**, whose nearest-even f32 word is `00000002`; a
source-compatible separate-f32 calculation also gives that word. Control's
saved tendency and calculated output are zero. This reproduces the **RK3
update result from stored operands**; it does not identify emitted FMA
instructions or the face-flux operation that first created `000021A3`.

The boundary input trace is present in both runs and records
`specified=true`, `have_bcs_moist=false`, `periodic_x=false`, `spec_zone=1`,
`ids=1`, donor `(2,168,33)`, and the same negative raw `ru_m` word. The
target's post-boundary QI word equals the donor's pre-boundary word at every
recorded RK stage. The α donor is zero again after microphysics while the
boundary target retains `00000002` through finish.

NI is a contemporaneous snapshot during the moist QI loop; the NI scalar is
updated later in the host sequence. These intermediate QI/NI observations
are therefore not treated as synchronized post-RK moment pairs. Final α
checkpoint NI is zero and one original M0 profile/seven channels remain
invalid. No whole-M0 RTTOV cost, accepted analysis or second assimilation is
reported. This trace provides no justification for a blanket subnormal flush
or a relaxed observation mask.

## Offline replay

```bash
python3 -m harness.evidence.native_qi_donor_transient_2026-10-30.replay
```

The replay checks source/data pins, the V7 parent packet, exact stage/field
inventory, the saved-word RK3 calculation, boundary branch inputs, raw-word
copy and microphysics boundary. It calls no host, KDM, RTTOV or optimizer.
Full checkpoint equality is linked by private run receipts and SHA-256; the
private NetCDF arrays are not included. The next measurement should identify
the QI RK3 advection face and limiter terms producing the small positive
tendency before any physical correction rule is chosen.
