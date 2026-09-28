# S1 selected dry-number ice-face transfer

The opt-in mp337 dry-number path already uses the conservative ice substep, but
its **actual native-host capped departure and next-layer arrival** had not been
paired. Two diagnostic-only patches now record one fixed internal C++ batch slot
and the host tile-call order. The [C++ patch](../s1_dry_ice_face_trace.patch)
adds no production arithmetic outside `KDM6_S1_FACE_TRACE`; its macro-off
projection equals the pinned source text. The [private host patch](../s1_dry_ice_tile_log.patch)
only checks trace controls and logs tile extents before the unchanged v2 ABI
call. The patches apply to the PR #311 path; the private host source and
operational install remain untouched.

The retained 5 km input was run for 40 s at dt=20 s, one MPI rank and one
thread, with `mp_physics=337` and `KDM6_S2_DRY_NUMBER=1`. One experimental
executable (SHA-256
`b5b1c533d39127a02b82d4d97f7dc8664c7a83df8e874c8d117259c4d83ccea4`)
ran with the trace off and on. It loaded the isolated C++ library SHA-256
`cac9a1e814b1844f1ae7e040dd8df0a01318021268fe54991e8f8d9d715c1a62`;
fresh private wrapper/ISO objects preceded the unchanged host archive in the
link map. All 254 common saved variables, including `Times`, matched raw-bit
at 0, 20 and 40 s. Both forecasts have SHA-256
`660b5af0c5ebeb46c5af2863dd2d76c4db237a0a11d3746de9b51f1810ea2a8f`.
The private source/build/input/run receipt has SHA-256
`3c826c7b7140944f547eaa2fee0f17b1552dff87711930f086467e18df220ad8`.
An earlier launch failure and a completed but tile-unattributed run were
excluded from these results.

The host produced four tile calls. The C++ trace produced four complete ice
substep blocks, each with 39 finite rows and `n=1`. Calls 2 and 4 alone own
predeclared global `(144,153)`: their tile origin is `(ITS,JTS)=(2,143)`,
logical local `(143,11)`, and C++ batch index
`(143-1)*139+(11-1)=19748`. Calls 1 and 3 belong to the other tile and are
excluded. The full [trace](s1_dry_ice_face_trace_2026-09-28.log) and
[tile-call log](s1_dry_ice_tile_calls_2026-09-28.txt) are public; their
fixed-case [replayer](../replay_s1_dry_ice_faces.py) checks the hashes,
complete record sets, selected owner, caps, source-order f32 updates and
paired face arithmetic. It refuses Python `-O`.

| Selected call | Ice-number faces with positive departure | Active number caps | Internal number departure `sum(dn_out*dz_src)` | Arrival `sum(dn_in*dz_dst)` |
| --- | ---: | ---: | ---: | ---: |
| Step 1 | 0 | 0 | 0 | 0 |
| Step 2 | 14 | 9 | 415,869,365.984184 | 415,869,341.769323 |

At step 2 the signed interface difference is
`-24.214861` on this conditional `N*dz` measure, or
`-5.82270849e-8` of internal departure. All 38 interior faces replay from
the preceding layer's **actual capped** departure with the source's f32
multiply/divide order; the selected column inventory change plus bottom
export has residual `-24.214862` in the same measure. Both bottom number
exports are zero; step 1 has a tiny conditional mass-bottom amount
`1.887669234651269e-15`. All raw/safe `dz` and density pairs in the selected blocks
are equal, so the numerical denominator floors were inactive.

The formerly problematic top-first layer 15→16 (native 24→23) illustrates the
mechanism. `falk_ni=25944.287109375` offers `518885.75` over 20 s against a
source reservoir of `436204.8125`; the actual departure is capped to
`436204.8125`, and the next layer receives `432414.3125` after its different
thickness is applied. The two thickness-weighted amounts differ by
`-23.8348388671875`, or `-7.52027309e-8` of departure. This is a new dry-mode
trajectory, so its raw values are not a same-input bitwise comparison with the
legacy zero-arrival capture.

The same step-2 trace has conditional ice-mass departures/arrivals of
`0.007805450436`/`0.007805450034` with a relative difference
`-5.15942599e-8` on `dend*dz`. Step 1 transports ice mass while its ice-number
outflow is zero; that moment pair still needs physical interpretation. These
are **internal sedimentation-segment** ledgers. Interpreting `N*dz` as physical
particles per area and `dend*dz` as dry-air-mass weighting depends on the
unapproved S2 dry-number contract. The replayer is arithmetic replay of public
rows, while the private receipt records the actual native execution.

S1 remains **OPEN**: the target had only `mstep=1`, no nonzero bottom number export,
and one selected column. Multi-substep, other faces/species, whole-domain
positivity, physical number policy and any default-path change remain separate.
No deployment action was taken.
