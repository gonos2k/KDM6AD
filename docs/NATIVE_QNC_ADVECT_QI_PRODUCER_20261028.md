# Native QNC producer and QI boundary writer, 2026-10-28

Base: `main 69a87a507a3e1ea421131c176ad7498155fc4535`, after PR #468.
The [raw packet](../harness/evidence/native_qnc_advect_qi_2026-10-28/README.md)
and versioned replay contain the measured values and provenance. This is a
trace-only extension of the existing target donor-scale variant, not a new
limiter rule or an accepted analysis.

## What is now measured

Four READY40→60 s full-host steps use the same native input and full forward
physics with recording off/on for control and α=0.25. The changed private
archive members are only `module_advect_em.o` and `solve_em.o`; the Fortran
advection module interface remains byte-identical. Within each case the
off/on checkpoint and applied-control ACK are byte-identical and the endpoint
also matches PR #468. The run uses `mp_physics=137`, `no_mp_heating=0`, active
radiation, one MPI rank and one thread. No new RTTOV or optimizer call occurs.

At `(113,70,12)`, `scalar_adv_opt=1` reaches the ordinary scalar advection
routine for RK2 and the positive-definite routine for RK3 in this executed
three-stage step. The new trace connects their final `ADVECT_TEND` words to
the already recorded QNC RK inputs.

| Measured RK2 boundary | Control `ADVECT_TEND` | Candidate `ADVECT_TEND` |
| --- | ---: | ---: |
| Entry | 0 | 0 |
| After Y | −8,411,937,792 | −8,411,937,792 |
| After X | −15,488,231,424 | −15,488,232,448 |
| After Z / RK input | −16,758,736,896 | −16,758,738,944 |

The Y lower face already differs, but its accumulated tendency rounds to the
same word. The first **applied tendency** difference appears after X, where
the X upper face also differs. A single-rounded FMA-compatible source-order
calculation matches both case records through Z. This is a candidate
arithmetic replay from stored binary32 values, not compiler opcode evidence.

The RK3 outgoing limiter is active in both cases at this cell and its stored
scale word is the same (`3C54898F`). Its `PH_LOW`, `FLUX_OUT`, post-limiter
faces and Z→X→Y tendencies are recorded separately. Identical scale bits
therefore do not imply identical applied flux or QNC result. The selected
seven-cell record does not prove whole-domain conservation or a general
positivity remedy.

At ice `(1,168,33)`, both cases write QI word `00000007` in the RK3 moist
state update. The following conditional `flow_dep_bdy` call changes control
to zero and alpha to subnormal `00000002`; its runtime flags are
`specified=true` and `have_bcs_moist=false`. The positive alpha result is
consistent with the routine's interior-copy branch. The exact donor value
and boundary velocity were not captured. This is separate from the liquid
NC sign split.

At `(155,120,15)`, both cases write QC from exact zero to `354ECF22` in the
RK1 moist update, while NC is still zero. Its common QC appearance precedes
the later QNC control/candidate divergence.

## Checklist after this measurement

| Item | State | Next evidence |
| --- | --- | --- |
| Same-layer endpoint and representative RK validity split | Complete in PR #467–#468 | Control/alpha checkpoint and RK records retained. |
| First QNC `ADVECT_TEND` producer difference at `(113,70,12)` | Complete here for the stored ordinary RK2 axis order | Y face differs without a tendency bit change; X produces the first applied difference; Z reaches the recorded RK input. |
| RK3 limiter and applied local tendency at that cell | Recorded here | Analyse neighboring donor scales, shared faces and mass/number budget before proposing a rule. |
| Ice QI subnormal writer at `(1,168,33)` | Narrowed to `flow_dep_bdy` call | Capture its actual donor QI and boundary velocity if the branch reason matters to a correction. |
| QC appearance from zero at `(155,120,15)` | Located at RK1 moist update | Derive the paired NC budget if this mechanism is targeted for correction. |
| Admissible full-domain candidate and RTTOV cost | Open | Preserve every fixed M0 profile, then evaluate direct checkpoint→RTTOV cost and T/Q/cloud changes. |
| Cumulative representable optimization and next assimilation | Open | Use a fixed background/prior; carry only an accepted full-host state forward. |

The candidate still loses **54 M0 profiles / 378 channel cells**. Its
full-support cost remains undefined and no second assimilation has run.
Raw number units, physical conservation and the full-host derivative remain
uncertified. A numerical NC floor or mask reduction is not supported by this
local trace.
