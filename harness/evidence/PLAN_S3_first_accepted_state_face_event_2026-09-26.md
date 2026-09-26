# S3 first-negative QN face-event plan

**S3 remains OPEN.** This is a source-pinned capture plan and public replay
contract. It does not change host source, build/link an executable, or claim a
physical particle-number budget.

## What the existing G2/G4 evidence says

The whole-owned-grid G2 summaries first record new QN negatives at step 2,
RK1, `RK_AFTER` in both original and normalized mp237 trajectories. In each
variant, the lexicographically first per-tile transition is QNCLOUD at Fortran
`(i,k,j)=(46,1,2)`: `−243.41905212402344` (original) and
`−243.55775451660156` (normalized), from zero. The summaries cover all
2,573,532 owned mass cells per QN field across two tiles. Their `first` field
means lexicographic first transition at the sampled checkpoint, not first
instruction inside a call.

These RK1 values are solver-intermediate states. `rk_scalar_tend` dispatches
to ordinary `advect_scalar` unless `rk_step == rk_order`; the positive-definite
`advect_scalar_pd` path is only called at the final RK step. Therefore the
RK1 first transition has no PD limiter decision to blame. `flow_dep_bdy`
executes after `rk_update_scalar`; it can copy an existing state to an edge
cell, but it is not the producer. A later RK3 boundary/history negative is a
separate accepted-step question. The selected QNCLOUD donor `(233,12,124)` in
the older negative trace is a later RK3 case, not the first whole-grid RK1
candidate.

Evidence references: [G2 face/whole-grid report](REPORT_number_face_flux_2026-09-24.md),
[negative-number call-boundary trace](REPORT_negative_number_origin_2026-09-24.md),
and [bounded synthetic backoff report](REPORT_S3_face_budget_backoff_candidate_2026-09-25.md).
The synthetic backoff pairs four donor faces with equal-metric receivers; it
does not identify the RK1 face cause or supply physical-unit evidence.
The retained G4 restart checkpoint and surface-handoff reports measure
restart-field equality and a bounded surface-driver divergence; they do not
contain a whole-grid QN negativity trace and do not add S3 evidence.

## Native capture declaration

Use the retained 5 km case and both mp237 trajectories, `dt=20 s`, two steps,
one MPI rank, one OpenMP thread, and one tile covering Fortran-owned
`i=1:234`, `j=1:282`, `k=1:39`. The capture target is fixed before compiling:
original and normalized QNCLOUD `(46,1,2)`, step 2, RK1. Keep Fortran coordinate
order in the file header as `(i,k,j)` and record global and tile-local
coordinates separately. No external model data or changed timestep is used.
The source G2 discovery used two tiles: tile 1 owns `i=1:234,j=1:142,k=1:39`
(1,295,892 cells), tile 2 owns `i=1:234,j=143:282,k=1:39` (1,277,640).
`first_qn_candidate` pins these exact extents and counts at every prior
checkpoint, plus rank 0, selected/species identity, and each first-transition
coordinate's membership in its owning tile. It pins the accepted G2 JSON bytes
by SHA-256, so mutation tests exercise the structural validator directly.
Because the prior G2 run used two tiles, the planned one-tile capture needs its
own one-tile dump-off control; compare capture against that same-layout control,
not against the two-tile G2 history.

Declare this checkpoint order in the manifest before execution, separately
from captured records. For each step, start with `BEGIN`; for RK1 and RK2
record `RK_TEND_BEFORE`, `RK_TEND_AFTER`, `RK_BEFORE`, `RK_AFTER`,
`FLOW_BC_BEFORE`, `FLOW_BC_AFTER`, `RK_PHYS_BC_BEFORE`, and
`RK_PHYS_BC_AFTER`. For RK3 record `PD_OLD_PHYS_BC_BEFORE/AFTER`,
`RK_PD_BEFORE/AFTER`, the same tendency, store, and flow-boundary checkpoints,
then `FINAL_PHYS_BC_BEFORE/AFTER` at RK4. Finish the step with
`MICRO_BEFORE`, `MICRO_AFTER`, `STEP_ACCEPTED`, `HISTORY_SAVED`, and `END`.
For the first step-2 RK1 candidate, require every step-1 QN scan and step-2
`BEGIN`, RK1 tendency, and `RK_BEFORE` scan to be present and nonnegative.

At the target's step-2 RK1 producer, record the `rk_scalar_tend` input scalar,
`scalar_old`, `advect_tend`, `sc_tend`, RK coefficients, `mu_old`, `mu_new`,
`mub`, `msfty`, `dt_rk`, and the exact six oriented face flux operands used to
form the tendency. Record the `rk_update_scalar` output store before the
following boundary call. Since RK1 uses ordinary `advect_scalar`, explicitly
write `limiter="none_at_this_stage"`; do not retrofit the later PD scale onto
this update. Capture the final-RK PD `PRE`/`POST` limiter rows for this same
coordinate only as a separate stage comparison if the cell remains in the
trace. Record all adjacent face owners and their cell metrics; a shared face
must appear once as the same stored REAL4 word on both sides. The boundary
checkpoint records donor and receiver values and flow direction separately.

The source anchors are private host `dyn_em/module_em.F`:
`rk_scalar_tend` dispatch at lines 1260–1340 and RK store at 1720–1798;
`rk_update_scalar_pd` at 1803–1916; private host
`dyn_em/module_advect_em.F`: `advect_scalar_pd` limiter budget and scale at
7733–7775; private host `dyn_em/solve_em.F`: final-stage PD call at 1760–1860
and ordinary moisture RK update/boundary ordering at 2280–2380. The exact
pre-instrumentation SHA-256 values are embedded in
`harness/s3_accepted_state_events.py`; re-hash the three source files and
fail before compiling if any differs. Graph query was attempted in the fresh
main worktree but `graphify-out/graph.json` is absent there; the query against
the existing canonical graph returned no relevant host edge, so these anchors
were verified directly against the private source.
The code graph was incrementally rebuilt and the parser nodes/relationships
were inspected. Graphify's doc-semantic extraction was unavailable in this
environment (the update reports it needs a Gemini/Google API key), so the new
plan document has no semantic graph edges yet.

## Parser contract and interpretation

`harness/s3_accepted_state_events.py` fails closed on schema, source hashes,
1-rank/1-thread layout, QN identity, producer/checkpoint class, transition
signs, six raw face words, finite operands, and RK-stage types. The G2 scan
reader pins exact rank/tile extents and cell counts at each preceding
checkpoint and verifies candidate membership in its owning tile.

The v2 internal event schema carries raw REAL4 face words in Fortran order
`yS,yN,xL,xR,zB,zT`, all local map metrics, RK mass coefficients, scalar
tendency, observed advective tendency, observed before/after words, and
control/capture history hash fields. It rejects caller-supplied `available` or
`amount_delta` fields. At RK1 it replays the ordinary `advect_scalar` source
order Y→X→Z, rounding each pair difference, metric product, and tendency store
to REAL4. It also requires the recorded horizontal/vertical orders to match
the retained `5/3` advection configuration:

```text
mrdy = f32(msftx * rdy)
tend = f32(0 - f32(mrdy * f32(yN - yS)))
mrdx = f32(msftx * rdx)
tend = f32(tend - f32(mrdx * f32(xR - xL)))
tend = f32(tend - f32(rdzw * f32(zT - zB)))
```

It requires that result to match the native `advect_tend`, reconstructs the
fused RK store from `c1/c2`, `mu_old/mu_new/mu_base`, `dt`, `msfty`, scalar
reference and `scalar_tend`, and requires the output bits to match. To find a
directional crossing, it replays the RK numerator after each *grouped*
source-order pair update Y→X→Z; the source forms each opposing-face difference
before applying its metric, so separate per-face rounding is not a valid
crossing ledger:

```text
Y = f32(0 - f32(mrdy * f32(yN - yS)))
N_Y = fma32(M_old, q_before, f32(dt * f32(f32(Y * msfty) + scalar_tend)))
X = f32(Y - f32(mrdx * f32(xR - xL)))
N_X = fma32(M_old, q_before, f32(dt * f32(f32(X * msfty) + scalar_tend)))
Z = f32(X - f32(rdzw * f32(zT - zB)))
N_Z = fma32(M_old, q_before, f32(dt * f32(f32(Z * msfty) + scalar_tend)))
```

The first nonnegative-to-negative prefix is stored as a directional replay
diagnostic, not a physical cause. The build/history hashes are supplied in the
event but no external receipt manifest currently authenticates them, so every
internal replay returns `UNVERIFIED_RECEIPT` and never claims source execution
or exchange conservation. No adjacent-cell shared-face words are present.
The focused regression suite includes the Y=`2^24+2`, X=`−1`, Z=`−2^24`
half-ULP tie (Y→X retains a `2^24` prefix, while reversed X→Y first records
`−1`) and a mixed-sign Y/X/Z case whose first source-order negative prefix is
Z; these check the grouped tendency stores and RK result, not native physics.

The candidate replay scope is step 2, RK1, QNCLOUD `(46,1,2)`;
ordinary advection has no PD limiter there. RK3 PD limiter owner/scale
attribution remains unsupported until its source-derived donor neighborhood,
`ph_low`, `flux_out`, scale and post-limit face words are captured and replayed.
The event requires the retained `module_em` object SHA from the G2/RK FMA
evidence before using the fused RK store replay. The RK3 PD source's outgoing
face owner/scale rules are not treated as captured or source-validated by this
RK1 parser.
Accepted-step values are after RK3, microphysics, boundary processing, and
history preparation. The parser therefore returns
`UNVERIFIED_ARITHMETIC` for `STEP_ACCEPTED` classification and will not reuse
RK1 face operands as their cause. The native operand schema and synthetic
arithmetic tests exercise validation logic only; they do not establish a
native face cause, conservation, or S3 closure. **S3 remains OPEN.**

Validation for this plan: `python harness/replay_number_face_flux.py`, the
focused S3 parser tests, Ruff, and diff review. Native compilation/execution is
deferred while the S10 lane is queued.
