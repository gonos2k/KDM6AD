# S15 face discovery replay (provisional)

One capture-on, 40-second, one-rank run completed on the pinned run-3 case.
The runner reported success on a 1x1 grid, and the forecast file contains times
00:00:00, 00:00:20, and 00:00:40. The strict extractor accepted exactly 18
`S15AX`, 2 `S15PD`, and 6 `S15RK` events. The independent six-key schedule,
producer/consumer joins, face-prefix replay, conditional limiter checks, RK
store replay, and six nonnegative-to-negative QIB transitions all passed.

The replay models the pinned GCC 15.2 `-O2` executable's binary32 contraction
at the face-prefix update and in the RK old-mass sum, numerator accumulation,
and new-mass denominator. The `dt*tendency` product is rounded before the
numerator FMA. These changes leave this run's six stored words unchanged
because all six incoming values are zero. For the RK3 limiter tap, the local
post-limit value is kept distinct from the later divergence face: an adjacent
cell can scale a shared incoming face after the selected cell's local limiter
record.

| RK / tile / cell `(i,j,k)` | `advect_tend` | Prefix-step changes in Y / X / Z | Largest absolute step and source-oriented face difference | QIB before → after; `sc_tend` |
| --- | ---: | --- | --- | --- |
| 1 / 1 / (143,2,16) | −4.73175e−12 | 0 / 0 / −4.73175e−12 | Z: −4.73175e−12; ΔF −2.33656e−13 | 0 → −3.27578e−16; 0 |
| 1 / 2 / (144,143,14) | −2.86570e−9 | 0 / 0 / −2.86570e−9 | Z: −2.86570e−9; ΔF −1.35410e−10 | 0 → −2.16701e−13; 0 |
| 2 / 1 / (111,2,16) | −3.34702e−14 | −8.42107e−15 / 0 / −2.50491e−14 | Z: −2.50491e−14; ΔF −1.23694e−15 | 0 → −3.48645e−18; 0 |
| 2 / 2 / (146,143,13) | −1.80524e−14 | 0 / 0 / −1.80524e−14 | Z: −1.80524e−14; ΔF −8.26259e−16 | 0 → −1.93596e−18; 0 |
| 3 / 1 / (141,2,17) | −3.78269e−20 | −4.90112e−15 / +5.13407e−15 / −2.32985e−16 | X: +5.13407e−15; ΔF −2.58416e−11 | 0 → −7.86300e−24; 0 |
| 3 / 2 / (141,143,16) | −2.18404e−18 | +1.30955e−11 / −1.30580e−11 / −3.74354e−14 | Y: +1.30955e−11; ΔF −6.72311e−8 | 0 → −4.83431e−22; 0 |

The prefix-step columns are observed binary32 differences between consecutive
captured tendency prefixes. Ordinary stages follow Y/X/Z order; RK3 follows
the source's Z/X/Y order. For ordinary stages, ΔF is the oriented high-order
`plus − minus` face difference. For RK3, it is the source-ordered high- and
low-order face-difference expression. The RK3 updates nearly cancel across
axes; their small negative residual reaches the RK store.

At these six selected cells, the captured arithmetic explains the negative
store: `sc_tend` is zero, `advect_tend` and the assembled tendency are negative,
the RK denominator is positive, and the incoming QIB is zero. This is a
selected-cell result from one diagnostic run; it does not establish a global
physical cause or a graupel-policy conclusion.

| Artifact | SHA-256 |
| --- | --- |
| Executable | `28fb18b32772fd0235d3df5cf421050a365863377665764bb6fcd98565f57ca2` |
| Link map | `f64bbc7639173f697ebf054a5261c49d939cf5d5b0ee17b53ea88427784df90e` |
| Active LC05 input identity | `12e132ecefa9e0f7e0a0bd67d57353ec3a7ec113ab1b43121474340293125fdf` |
| Selected face stream (private; not included) | `52159d3aee80a958699e245e5406ae9b3ddf5f70025f6a37789a32c846c90fe7` |

The link map places the three fresh dyn_em objects and the pinned reused
`module_mp_kdm6.o` before the unchanged S8 archive; no stale copies of those
four modules are selected.

No same-executable logging-off control or confirmation run was made, so
instrumentation noninterference is unmeasured. S15 remains OPEN; the trace-
graupel policy remains OPEN.
