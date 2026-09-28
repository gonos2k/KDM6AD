# S3 isolated QNCLOUD east-face shadow

**S3 remains OPEN.** This is a fixed, opt-in experiment on one retained-input
mp237 donor, not an operational limiter or a general positivity repair. It
tests whether changing one measured outgoing east face can remove that donor's
negative final-RK store without changing the four captured interior receivers.
The current baseline is the distinct trajectory established by the
[native QNCLOUD neighbor capture](REPORT_S3_native_qn_neighbors_2026-09-28.md),
not the older G2 executable/history.

The shadow is enabled only by `KDM6_S3_QN_XR_SHADOW=1`; any other value leaves
it off. Its latch is independent of the `KDM6_S15_NATIVE_CAPTURE_LOG` diagnostic
latch. The producer path selects runtime `is==P_QNC`, step 2, RK3, tile 1 and
`(i,j,k)=(233,124,12)`. After the ordinary PD limiter and before the x-face
divergence and PD post tap, it requires the positive high xR word `502AB870`.
Any mismatch stops the shadow run before modification. It then multiplies that
one word by the binary32 factor `3F7FFE97`; no low-order or interior face and
no `rk_update_scalar` formula is changed. With the shadow disabled, source
generation and the operational/default map remain unchanged.

The [bounded physics-OFF and physics-ON streams](S3_QN_xR_shadow_run1/) and
[native receipt](S3_QN_xR_shadow_run1/native_receipt.json), SHA-256
`d1c6496b5fb159ffa00d891e19ae0cbef1892df25bd00a36e7d4c756f92bf507`,
pin the generated source, build, inputs, executable and four completed 40-s runs. Full RSL and
original host files remain in the isolated private run. Macro-off configured
preprocessing matched the three unmodified source outputs; the macro-on
sources compiled and linked as three fresh host objects plus the verified mp237
object ahead of the unchanged archive.
An earlier private preprocessing setup attempt used the wrong intermediate
file paths and stopped before any compilation or model run; it is excluded
from the four completed experiments.

| Physics switch | Capture log | 40-s forecast SHA-256 | QNCLOUD negative cells | Selected east history word |
| --- | --- | --- | ---: | --- |
| OFF | OFF | `59b8a0ab…` | 3 | `BAEC299F` |
| OFF | ON | `59b8a0ab…` | 3 | `BAEC299F` |
| ON | OFF | `ac7ee62b…` | 2 | `3C3263AA` |
| ON | ON | `ac7ee62b…` | 2 | `3C3263AA` |

The full physics-ON forecast SHA-256 is
`ac7ee62bdc0abe244ecb8fec094a44eca24f907f43d853633f7519559ecf2262`;
the full physics-OFF SHA-256 is
`59b8a0abd7a027a546414f51b5c30f10fa10e22f4a470cb95d9380824afdd3e9`.

All four runs used the same linked executable. Within each fixed physics mode,
capture OFF and ON match raw-bit across all 254 common variables at 0, 20 and
40 s. With capture held fixed, physics OFF and ON are identical at 0 and 20 s.
At 40 s only QNCLOUD differs, at one of 2,573,532 cells: the east boundary
`(234,124,12)`, `BAEC299F` (−0.001801777514629066) to `3C3263AA`
(+0.010888019576). The domain QNCLOUD negative-cell count falls from 3 to 2;
no nonfinite QNCLOUD values appear in either variant.

Both bounded streams contain the exact five selected producer/consumer rows
(15 axis, 5 PD and 5 RK records). The physics-OFF replay retains the negative
donor RK word `BAEC299F`; the shadow replay checks the extra PD xR factor and
positive donor RK word `3C3263AA`. The xR high word changes
`502AB870→502AB77F`, a raw correction-face reduction of 246,784 in its stored
numeric representation. The donor's four interior receivers have identical
RK-after, high-face and low-face words across both variants. The donor itself
is zero in both saved 40-s histories; its RK-after word equals the east
boundary history word in each variant. No direct `flow_dep_bdy` tap was added.

This experiment establishes a **one-cell numerical effect and independent
instrumentation noninterference**. It does not show conservation of physical
particle number: the changed face points into the boundary strip, and its
signed, metric-weighted external exchange has not been closed in an approved
number basis. The other two negative QNCLOUD cells remain, as do other species,
trajectories, later times, AD, and accepted observation/cost gates. No
operational default is changed or approved by this shadow result.
