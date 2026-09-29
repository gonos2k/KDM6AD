# S1: normalized first-ice handoff in one native mp337 case

PR #343 added opt-in physics selector 2. This measurement connects that selector
to the current private mp337 wrapper with `KDM6_S1_NORMALIZED_ICE=1`, while
holding `KDM6_S2_DRY_NUMBER=1`. The experiment used the retained 5 km input,
39 native levels, 20 s timestep, 40 s total, one local MPI rank on `en0` and
one thread. Its isolated build used the current public source, the existing
[S2 dry-number patch](../g33_fortran/s2_mp337_dry_number_optin.patch), the
existing [S1 tile log](../s1_dry_ice_tile_log.patch), and the new
[selector patch](../g33_fortran/s1_normalized_ice_selector.patch). Fresh
private ISO/wrapper objects precede the unchanged host archive in the link
map. The canonical host sources and operational install were untouched.

Three runs used the **same executable**: selector 1 without logging, selector 2
without logging, and selector 2 with the bounded ice-face trace. All completed
and saved exactly 0, 20 and 40 s. The two selector-2 histories and auxiliary
output files have identical SHA-256 hashes. The strict comparison matched all
254 common variables raw-bit at every saved time (253 numeric and `Times`).
No saved numeric field contained NaN or Inf. Selector 1 and 2 matched at 0 s,
then differed in 22/254 variables at 20 s and 75/254 at 40 s. Those differences
are an intended **between-variant** result, not an instrumentation failure or
a measure of forecast skill. The selector-1 forecast SHA-256 also matches the
earlier [S1 raw-handoff run](REPORT_S1_dry_ice_face_trace_2026-09-28.md)
on this retained 40 s input; that is a bounded saved-output comparison, not
a claim that the two executable builds are identical.

The selected column is global `(i,j)=(144,153)`, owned by host tile calls 2
and 4. The [source-order replayer](../replay_s1_dry_ice_faces.py) parses all
four complete 39-row ice blocks and reproduces every capped departure,
next-layer arrival and f32 state store in the two selected calls. In the first
selected call, layer 15
has the same pre-ice `qi` as the earlier raw-handoff capture. Its **offered**
mass rate `falk_q` changes from `4.8664687711e-6` to `6.6989982450e-9`;
their ratio is `726.447238`, matching `delz=726.447266 m` to f32 rounding.
Layer 24 gives the same offer check: ratio `555.323725`,
`delz=555.323730 m`. The **applied** layer-15 departure is different from
that offer ratio: the raw case caps `dq_out` at the full
`q_before=5.8221589825e-6`, while the normalized case applies
`dq_out=3.4969298213e-7`.

| Selected call | Ice `mstep_i` | Positive number faces | Number caps | Internal `dn_out*dz` | Internal `dn_in*dz` | Bottom number export |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Step 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| Step 2 | 1 | 14 | 0 | 1,148,741.238078 | 1,148,741.295045 | 0 |

The step-2 signed internal-face difference is `+0.056967`, or
`+4.95908e-8` of departure, on the **conditional operator measure** `N*dz`.
The corresponding moist-density mass-face relative difference is
`-1.49586e-8`. The stored number-inventory change is `-4.660913` on that
measure, which includes f32 store rounding; the replayer does not label it
physical loss. All these quantities are one selected column and two calls.

**S1 remains OPEN.** This retained state still selects only one ice substep
and has zero bottom ice-number export. The host's physical QN basis is OPEN
under S2; neither `N*dz` nor the moist-density mass measure certifies that
basis. Variant 2 also lacks a long-window cross-tree derivative and an
independent forecast/observation accuracy comparison. The full run, source,
object, executable, input and output identities are in the
[measurement receipt](native_s1_normalized_ice_2026-09-30.json); the bounded
[trace](s1_normalized_ice_face_2026-09-30.log) and
[tile map](s1_normalized_ice_tile_calls_2026-09-30.txt) are public.
