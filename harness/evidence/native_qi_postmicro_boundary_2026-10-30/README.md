# Opt-in QI/NI boundary-ordering host diagnostic

The [PR #481 outflow packet](../native_qi_outflow_terms_2026-10-30/README.md)
found that α=0.25 sends `QI=00000002` from donor `(i,j,k)=(2,168,33)`
to the west boundary target `(1,168,33)`. The donor is zero after
microphysics, but the target retains the earlier copied subnormal QI with
`NI=0`. This packet tests an **isolated boundary-ordering diagnostic**:
after all microphysics, zero-out, and finish tile loops complete, the host
optionally reapplies its existing `flow_dep_bdy` to QI and NI under each
field's existing specified-boundary eligibility gate. No new threshold or
subnormal flush is introduced. The rule runs on all eligible edges, corners,
and levels, not only the witness column.

The pilot is disabled by default. The enabled path fails closed outside the
observed one-rank, one-thread, `mp_physics=137`, specified, nonpolar,
nonperiodic-x, `spec_zone=1` case with active QI/NI and both boundary gates.
The same source provides an independent trace switch. The new trace samples
QI, NI, west-boundary velocity, and the strict `u<0` branch at target/donor
`i=1,2`, `j=168`, `k=30..33`, immediately before and after the late boundary
call. The public trace is a sample; full boundary effects are reported from
the private checkpoint comparison.

## Actual host outcomes

Six completed 20 s full-domain host steps comprise control/α pilot-off with
trace on, and control/α pilot-on with trace off/on. Pilot-off endpoints match
PR #481 exactly. Within each enabled case, trace off/on checkpoint SHA and
applied ACK match. Only private `solve_em.o` changed; advection and QNC guard
objects and the KDM DSO were retained. The first two α runs used a controller
with an 8 GiB disk preflight; the remaining four used a byte-identical
controller apart from lowering that preflight to 6 GiB. Each run records its
controller SHA. No host numerical option changed with that storage check.

At the observed west outflow, α target QI changes `00000002 → 00000000` and
NI remains `00000000`; donor QI/NI are zero before and after. The new target
word reaches the inherited `POST_FINISH` trace. The only intentional alpha RK
writer change is its `POST_FINISH` target QI line; the one-line delta file
reconstructs the full new writer SHA from the pinned old public writer. A
checkpoint-hash-bound private extraction publishes QI/NI words at the same
target/donor, k=30..33, for both prior and pilot checkpoints. Public replay
joins those words to the corresponding BEFORE/AFTER trace records; it does
not reopen the private NetCDF arrays.

| Same-case PR #481 → pilot checkpoint | Control | α=0.25 |
| --- | ---: | ---: |
| QICE changed f32 elements | 12,190 | 12,183 |
| QNICE changed f32 elements | 7,143 | 7,142 |
| Changed interior elements | 0 | 0 |
| Other changed checkpoint variables | 0 | 0 |
| Newly hard-invalid full-domain profiles | 0 | 0 |
| Original fixed M0 hard-moment invalid profiles/channels | **0 / 0** | **0 / 0** |

The full comparison covered 652 variables and 322,426,586 numeric elements
per case. The changes are widespread across the outer boundary, particularly
the east edge. These are raw state-coordinate changes, not a conservative
two-cell transfer or certified physical ice-mass/number budget. The fixed M0
contains 53,906 profiles and 377,342 channel cells. The packet includes all
full-domain hard-invalid profile indices so the M0 intersection can be
recomputed from the already published support mask; the private producer
verified those indices against the full checkpoint. The actual private
NetCDF arrays and executable are not published.
The hard-moment scan checks `QC>0, NC<=0`, `QI>0, NI<=0`, `NC<0`, and
`NI<0`. It does not certify every physical moment constraint or RTTOV profile
and radiance quality.

## Replay and scope

```bash
python3 -m harness.evidence.native_qi_postmicro_boundary_2026-10-30.replay
```

The replay verifies the new source and packet hashes, nested PR #481 replay,
sampled branch/copy arithmetic, checkpoint-bound target/donor words, the changed
`POST_FINISH` line, recorded
off/on endpoint identities, full-checkpoint comparison receipts, and the
candidate hard-invalid lists against the unchanged original M0. It makes
zero host, KDM, RTTOV, and optimizer calls. It does not reopen the private
build/run receipts or the full checkpoint; those were checked during packet
production. The trace-only sample and the checkpoint-wide comparison are
separate evidence. Full original-M0 RTTOV profile admission and direct quality
are evaluated separately.

This is **not an accepted QI correction**. The late replacement changes
thousands of boundary QI/NI words and creates external boundary increments.
It does not repair the upstream high-order flux cancellation or establish
physical QI/NI units, a full-host derivative, or consistency of diagnostics
computed before replacement. RTTOV direct cost, analysis acceptance, and a
second assimilation are not part of this packet. See the [review note](../../../docs/NATIVE_QI_POSTMICRO_BOUNDARY_PILOT_20261030.md).
