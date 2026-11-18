# Six-face source of the QI lower-owner outflow split

This packet traces the RK3 QI `FLUX_OUT` at `(i,j,k)=(2,168,32)`, the lower
limiter owner of the vertical face identified in the [parent face packet](../native_qi_face_producer_2026-10-30/README.md).
The source arrays and TSV use `(i,k,j)` order. It captures the six correction
and low-order faces after the aggregate `FLUX_OUT` loop and before any limiter
mutation, the aggregate operands and stored result, the six faces again at
that owner's limiter visit, and the third-order vertical flux stencil inputs
at k=32 and 33. The separate, opt-in writer makes no numerical-array writes.

## What changed between control and α=0.25

The recorded `PH_LOW=01821C4D` is the same in both cases. Replaying its
source-grouped f32 expression from the stored old state and low-order faces
matches that word. The six-face source-grouped f32 `FLUX_OUT` expression also
matches the two recorded words:

| Lower owner | Control | α=0.25 |
| --- | --- | --- |
| Bottom correction PRE | `01B121C9` (+6.50680106e-38) | `8036BE12` (−5.02730117e-39) |
| Bottom exact saved-face outflow term | +1.0203802487e-34 | 0 |
| Exact six-term sum | +1.0204501173e-34 | +6.9868600793e-39 |
| Stored f32 `FLUX_OUT` | `0707A41E` (+1.0204500898e-34) | `004C147C` (+6.9868461172e-39) |
| Limiter hit | true | false |

All displayed decimals are approximations to the saved-word exact rational
calculation. The signed vertical source term is
`dt*MSFTY*RDZW*(min(0,FZ_TOP)-max(0,FZ_BOTTOM))`. The recorded `RDZW(32)`
is negative; the positive control bottom face contributes almost all of the
control outflow, while the negative α bottom face contributes zero. The west X,
east X and south Y PRE words also differ, but only the west X difference
changes an exact outflow term, by about −1.06e-47 from control to α. The north
Y and top Z terms are the same. PRE and limiter-visit face words are equal for
this owner in these two runs.

The bottom face comes from the third-order vertical `flux3` stencil at
k=30–33, its `ROM` velocity, and a low-order subtraction. The k=32 low-order
face is negative zero in both runs. The saved k=30 and k=31 `FIELD` words and
`ROM` differ; k=32/33 `FIELD` words do not. A bounded separate/FMA replay of
the saved stencil reproduces each PRE word in four compatible modes at k=32
and eight at k=33. These are compatible arithmetic candidates, not a recovered
instruction trace or a physical ice-budget proof. The integer `time_step`
operand was not recorded, so both possible signs were enumerated; only its
positive-sign candidates match these saved words.

## Host execution and offline replay

Control and α each completed one 20 s full-domain step with this trace off
and on, one MPI rank and one thread. Each pair's checkpoint SHA-256 and
applied ACK match, and both match the corresponding prior face-trace run.
All inherited QI donor, applied-face and QNC trace bytes match the parent.
Only `module_advect_em.o` changed in the isolated build; the solve object,
QNC guard objects and KDM DSO were retained. Four runs form the accepted
set. An earlier α preflight step used a trace without a VISIT flush and owner
tile gate; it is excluded from that set and from this packet's data.
After the accepted runs, trailing whitespace outside the overlay's generated
Fortran string was removed. The current overlay renders the built Fortran
source byte for byte; the execution summary records both overlay hashes and
the private publication check establishes this equivalence.

```bash
python3 -m harness.evidence.native_qi_outflow_terms_2026-10-30.replay
```

The offline replay verifies file and source pins, the parent replay,
recorded host-lineage and endpoint hash consistency, exact record inventory,
shared-face and input joins,
source-grouped f32 `PH_LOW`/`FLUX_OUT`, exact six-face contributions, and
bounded vertical producer candidates. It makes zero host, KDM, RTTOV and
optimizer calls. It does not open the private build or run receipts,
executable, full checkpoint arrays, or compile logs. Their hashes were checked
against the available private files during packet production; the public
replay checks the published summary against its parent packet and data.

No correction was applied to QI by this trace. The α checkpoint still loses
one ice QI/NI profile and seven channels from the original fixed M0. This
packet does not establish whole-M0 RTTOV cost, analysis acceptance, a second
assimilation, or a physical QI/NI conservation condition. See the [review
note](../../../docs/NATIVE_QI_OUTFLOW_TERMS_20261030.md) for the bounded next
question.
