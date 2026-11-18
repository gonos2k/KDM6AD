# Applied QI face that creates the remaining subnormal tendency

This packet adds a passive, opt-in RK3 QI face trace to the same native host
variant as the [QI donor trace](../native_qi_donor_transient_2026-10-30/README.md).
It records PRE, LOW and final POST correction faces at donor
`(i,j,k)=(2,168,33)`, the limiter decisions at that cell and its six
neighbors, and the actual Z→X→Y cumulative `ADVECT_TEND`. The source code
uses `(i,k,j)` array order. The west neighbor `(1,168,33)` has no executed
limiter in this specified-boundary case; its record says `SEEN=false` and
does not read undefined `PH_LOW` or faces there.

## Four completed host steps

Control and α=0.25 each ran one 20 s full-domain step with this trace off and
on, one MPI rank and one thread. Every new checkpoint SHA-256 and applied ACK
matches the corresponding preceding QI-donor-trace run. Its existing QI
donor, QNC face and RK trace files are also byte-identical to the parent.
Only private `module_advect_em.o` and `solve_em.o` changed; the QNC guard
objects and KDM DSO were retained. The trace writer reports 85 typed raw-word
records per case. These are new host runs; the offline replay below makes no
model call.

## First applied-face difference

The donor's six **PRE** correction faces, six **LOW** faces, field/old state,
mass and map factors, time step and limiter-loop metadata are raw-bit equal
between control and α. The first changed donor face is the final applied
bottom vertical correction face:

| `(2,168,33)` bottom face | Control | α=0.25 |
| --- | --- | --- |
| PRE correction | `80000060` | `80000060` |
| LOW | `80000000` | `80000000` |
| POST correction | **`80000000`** | **`80000060`** |

The relevant outgoing owner is the cell below, `(2,168,32)`. Its saved
`PH_LOW` is the same `01821C4D` in both runs. Control records
`FLUX_OUT=0707A41E`, `hit=true`, `scale=22B0552B`; α records
`FLUX_OUT=004C147C`, `hit=false`, `scale=1`. Replaying the source-compatible
f32 branch and scale formula reproduces the control scale. Multiplying the
shared PRE face by that scale rounds to negative zero. With no limiter hit,
α retains the original negative subnormal face. A different limiter branch
is also recorded at eastern neighbor i=3, but its donor-shared X face is zero
in both cases.

The actually accumulated donor tendency is:

| Stage | Control | α=0.25 |
| --- | --- | --- |
| Start | `00000000` | `00000000` |
| After Z | `00000000` | **`000021A3`** |
| After X / Y | `00000000` | **`000021A3`** |

The stored-face Z expression in exact arithmetic is **8611.28173828125
binary32 subnormal ULP** for α, versus zero for control. A separate-f32
calculation rounds it to `000021A3`, exactly the recorded value passed to
the [QI RK3 donor update](../native_qi_donor_transient_2026-10-30/README.md).
The f32 result is a source-compatible replay, not identification of emitted
instructions.

This trace identifies the applied face and limiter-owner branch that produce
the saved tendency. It does **not** decompose the lower owner's differing
`FLUX_OUT` into all six of that cell's faces or expose the upstream vertical
high-order flux stencil and velocity. It is a numerical coordinate analysis,
not a certified physical ice mass/number conservation statement. It supplies
no basis for a blanket subnormal flush or for reusing the QNC limiter scale
on QI.

## Offline replay and remaining gate

```bash
python3 -m harness.evidence.native_qi_face_producer_2026-10-30.replay
```

The replay verifies source and packet pins, the parent packet, exact
stage/field inventory, limiter decisions, applied-face f32 calculations,
directional tendency and the join to the recorded QI RK input. It makes zero
host, KDM, RTTOV and optimizer calls. Full-checkpoint identity is linked by
private run receipts and SHA-256; private NetCDF arrays are not in this packet.

The α checkpoint still loses **one ice QI/NI profile and seven channels**
from the original fixed M0. Whole-M0 RTTOV cost, analysis acceptance and a
second assimilation remain unreported. The next upstream question is why
the lower owner's `FLUX_OUT` differs with the donor's recorded PRE/LOW faces
held fixed; any correction must also account for both sides of affected
faces, QI/NI, boundary copying, physical units and derivative behavior.
