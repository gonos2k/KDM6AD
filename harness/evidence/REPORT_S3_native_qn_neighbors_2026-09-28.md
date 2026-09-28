# S3 selected native QNCLOUD face neighbors

**S3 remains OPEN.** This bounded run measures the final-RK QNCLOUD donor at
`(i,j,k)=(233,124,12)` and its four interior outgoing-face receivers on the
retained 5 km input. It records the existing mp237 operator; no positivity
repair, number-unit change or operational default change was run.

The fixed `qn=True` capture selects the runtime scalar with `is==P_QNC`, then
uses a separate owner-3 record identifier. It does not assume the Registry's
parameter ID is the scalar array slot or reuse the S15 QIB owner. Its expected
schedule is one donor plus west, south, north and upper receivers, all on tile 1
at step 2/RK3. The east face leads into the boundary strip and is
not an accepted RK receiver.

The [bounded S3QN face stream](S3_QN_face_neighbors_run1/S3QN_face.stream)
has SHA-256
`848eae8889159d880640134581f29b3e830638cfb5f68cd6c3219ae3969747dd`.
The [native receipt](S3_QN_face_neighbors_run1/native_receipt.json), SHA-256
`2e84c9a1b8351394a25f261461a9133d9a535bc27797104637320fb680a77071`,
pins the source, fresh objects, executable, inputs, execution and comparisons. Full RSL
and original host inputs remain in the isolated private run.

The three macro-off Fortran outputs matched the configured uninstrumented
preprocessing byte-for-byte. Three macro-on objects were compiled and linked
with the verified mp237 object ahead of the unchanged host archive. The same
executable, SHA-256
`e12e973cf903e431f2a893e610c19cb3f5fcd188d47a6a569a8f9e07c56408b5`,
completed capture OFF and ON for 40 s with one MPI rank and one thread. Both
forecasts and the separately run current uninstrumented baseline have SHA-256
`59b8a0abd7a027a546414f51b5c30f10fa10e22f4a470cb95d9380824afdd3e9`.
All 254 common variables match raw-bit at each saved 0/20/40 s frame in the
OFF/ON and baseline/OFF comparisons. The fixed stream contains exactly 15
axis, 5 PD-limiter and 5 RK records; all five producer-to-consumer joins replay
the recorded source-order arithmetic.

This is a **new baseline**, not a bitwise reproduction of the earlier G2 run.
The input and effective namelist identities match G2, but its original history
SHA-256 was `7d2afb3236ea6ea53a1df5c75f17b2b1da27f963ace697a8a912eda871c0f750`.
The old G2 executable and matching instrumented objects were not reused.

| Measured step-2/RK3 cell `(i,j,k)` | Role | RK before word | RK after word | After value |
| --- | --- | --- | --- | ---: |
| `(233,124,12)` | QNCLOUD donor | `00000000` | `BAEC299F` | −0.0018017775 |
| `(232,124,12)` | west receiver | `4696AC1A` | `495954F4` | 890,191.25 |
| `(233,123,12)` | south receiver | `00000000` | `4543A4F3` | 3,130.3093 |
| `(233,125,12)` | north receiver | `00000000` | `47EEE329` | 122,310.3203 |
| `(233,124,13)` | upper receiver | `4C135297` | `4C13B223` | 38,717,580 |

All four measured interior interfaces carry identical stored high and low
binary32 face words on both sides:

| Donor face → receiver opposite face | High word | Low word |
| --- | --- | --- |
| xL → west xR | `D4321DAE` | `5010A3FD` |
| yS → south yN | `D00C3FBB` | `00000000` |
| yN → north yS | `50E26B86` | `00000000` |
| zT → upper zB | `CBA28A2D` | `4C359948` |

The donor also has an outgoing xR high-order correction word `502AB870`
with low-order word `00000000`. Its adjacent `(234,124,12)` cell lies in the
east boundary strip, outside the accepted RK receiver set. The
captured donor RK-after word `BAEC299F` equals the 40-s east-boundary QNCLOUD
history word exactly; the donor's own saved value is `00000000`. This is a
measured RK/history word comparison. This run has no direct `flow_dep_bdy`
tap, so the exact boundary-copy operation in this binary was not replayed.

Matching face words do not by themselves prove a metric-weighted particle
budget, an admissible physical number basis, or a repair. The next algorithm
experiment must decide one face transfer, account for the east boundary as an
external exchange, and check the affected receiver RK stores and whole-host
accepted state. This capture supplies the missing local operands for that
experiment; S3 nonnegativity approval remains open.
