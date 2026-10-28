# QNC failed-layer applied-face preflight, 2026-10-28

Base: `main 882e6f42d7be2465c0f35d854a50327e8055125f`, after PR #473.
The [public packet](../harness/evidence/native_qnc_domain_preflight_2026-10-28/README.md)
records a new passive measurement at the **54 liquid failure layers** identified
by PR #466. These are 54 layers in 53 profiles. The separate ice/NI failure
is outside this QNC measurement. The model still integrated all native
234×282 columns and 39 mass levels; only selected operands were recorded.

## Executed path and noninterference

Four accepted READY40→60 s full-host steps used the PR #471 experimental
physical map: control and α=0.25, each with the new trace off/on. The forward
kept `mp_physics=137`, `no_mp_heating=0`, radiation, one rank and one thread.
Within each case the off/on ACK and final checkpoint hashes are equal, and
each endpoint equals the same-input PR #471 endpoint. The isolated build
replaced only `module_advect_em.o` and `solve_em.o`; the advection module
interface and KDM DSO remained unchanged. The first advection preflight
compile and first isolated build-script attempt failed before any model run;
their failure evidence is kept private and excluded from the four accepted
steps. The private run files and prior retained matching checkpoints were
rehash-checked before the temporary RAM volume was detached. The public
replay verifies the path-free receipt, not those private binaries or NetCDFs.

The advection trace reads **post-limiter rounded faces after all donor scale
updates**, before Z→X→Y tendency accumulation. The expanded RK writer reads
the same layers' final RK inputs and stored QC/NC. All 54 cells in each run
join the advection old state, coefficients, timestep and `MSFTY` to RK input
by raw bits. Each recorded face set has a source-compatible directional
tendency, and each RK output has a source-compatible arithmetic mode. This
does not identify the compiler's executed FMA instructions.

## Selected-layer result

The classifications below evaluate **the stored binary32 face and RK input
words as exact rational numbers**. They are numerical numerator signs, not
certified physical particle-number budgets.

| Same 54 liquid failure layers | Control | α=0.25 |
| --- | ---: | ---: |
| Positive low-order plus source available amount | 54 | 54 |
| Active outgoing limiter | 54 | 54 |
| Applied correction leaves negative exact numerator | **7** | **48** |
| Exact numerator positive but stored RK3 NC negative | 0 | **6** |
| Stored RK3 NC positive | **54** | 0 |
| Stored RK3 NC negative | 0 | **54** |
| Nonzero final RK3 scalar source | 0 | 0 |

The seven control cells with negative exact saved-face numerators are also
negative in α. Of the other 47 control-positive cells, α has **41** negative
exact numerators and **6** positive exact numerators with negative stored
binary32 NC. At all 54 layers, QC is positive and the QC/NC pair is
bitwise unchanged across scalar boundary handling. The original PR #470
target `(113,70,12)` reproduces its previously published exact numerator
in both cases.

This result narrows the numerical design problem. A guard that requires
positive exact applied-face numerator would affect **seven control cells**
in this selected set, not only the failing α cells. It would also need an
executed-f32 or justified rounding condition for the six α cells whose exact
numerator is already positive. Reducing correction outflow cannot repair a
negative low-order baseline; none of these selected 54 cells has one in this
run, but unrecorded domain cells may differ. Multiple donors and tile seams
have not been evaluated under a changed face rule.

## Remaining gate

No donor-scale correction was introduced in these runs. The α checkpoint
still loses **54 fixed-M0 profiles and 378 channel cells**, so whole-support
RTTOV cost and a second accepted assimilation remain unavailable. A
coordinate-independent numerical guard needs the complete RK source/mass
inputs, simultaneous donor/receiver face updates, the actual rounded state
and seam ownership. Physical number conservation also requires resolving
the host/KDM/RTTOV number-unit basis; the Registry's per-kg label alone does
not establish that contract. The separate QI boundary donor state remains
outside a liquid-QNC transport change.
