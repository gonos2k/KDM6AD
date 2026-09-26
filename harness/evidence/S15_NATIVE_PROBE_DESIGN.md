# S15 native probe: bounded capture and replay contract

Status: **OPEN**. This file records the measurement design and parser protocol;
it does not certify a native capture, change a graupel policy, or authorize a
host run.

## Existing evidence boundary

`FINDING_invalid_qib_producer_v1.md` localizes the negative-QIB increase to the
scalar-update interval and the count transition to `P_QIB`. That interval also
contains other tendencies and mass coupling, so the cause is not assigned to
pure advection. The paired QG counts are not co-located with QIB records. The
first RK entry already has positive QG paired with nonpositive QIB.

The private driver copies `qg` and `bg` into the KDM6 work arrays. At entry,
`kdm62D` clamps both to nonnegative values before `ProgB_param`. `ProgB_param`
defines `rhox` only if `qg > qcrmin OR brs > brs_min`; the melt consumer checks
only `qg > 0`. A diagnostic must carry the actual `rhox`-defined predicate
forward and must not serialize or inspect `rhox` when false.

The retained reports contain aggregate state counts and rounded event rows.
The local `wrfout_mp37_ieee.nc` has six frames on a 41 x 41 grid; it is not the
234 x 282 x 39 event trajectory. None of these files contains the paired raw
f32 operands needed to replay first-transition attribution or an event-level
latent ledger.

## Capture points and bounded output

The merged B20 probe keeps **model timestep 1 as its default** for replay and
overlay generation. A new step-2 overlay must pass `--capture-step 2`; replay
selects the window from its hash-pinned plan and accepts only exact timestep-1
or timestep-2 windows. The next investigation targets **S15-tagged records at
model timestep 2**. The merged 20-second owner-scoped B capture completed six
owner-5 summaries with zero QIB transitions and 51 trace-melt records. It
cannot observe transitions in the second 20-second dynamics step, so its event
keys and counts are not reused as step-2 expectations.

At `module_em.F::rk_update_scalar`, capture only finite `P_QIB` transitions
owned by solve-em call 5, `scalar_tile_loop_2`, whose prognostics are the
`scalar_old/scalar` arrays. `P_QIB` is only an array index; other generic
`rk_update_scalar` call sites update TKE, chemistry, and tracer arrays and can
reuse the same integer index. The overlay passes a call-owner ordinal through
all five call sites and enables QIB logging only for owner 5. Each summary is
keyed by step, RK stage, owner, and tile bounds; it carries the exact count and
each positive-count summary has one first-event row. Non-finite outputs are
excluded from the sign-transition count. Record step/stage/owner/tile and cell
indices, both state values, the reference scalar, `advect_tend`, `msfty`,
`sc_tend`, `dt`, `c1`, `c2`, `muold`, and `munew`, all as raw f32 words.

The pinned arm64/GNU Fortran 15.2 object uses fused multiply-add instructions
for the two RK mass terms and the final numerator. Its tendency path stores the
result of `advect_tend * msfty` in one loop and adds `sc_tend` in a later loop;
the disassembly shows separate binary32 multiply and add instructions there.
The bit-exact replay follows that compiled arithmetic:

```text
tendency = f32(f32(advect_tend * msfty) + sc_tend)
old_mass = fma32(c1, muold, c2)
new_mass = fma32(c1, munew, c2)
numerator = fma32(old_mass, reference, f32(dt * tendency))
result = f32(numerator / new_mass)
```

The r10 operation-audit receipt pins the disassembly to the r6 `module_em.o`
hash and records both instruction excerpts. A discriminating fixture checks
that separate tendency rounding produces `C1F2AFC0`, while fusing those
operands would produce `C1F2AFBF`. The `9693AF7D` example is an A owner-1
generic scalar arithmetic row; it does not establish an owner-5 QIB capture.

This identifies the first observed transition and its complete operands. It
requires the pre-state word to equal the `scalar_1` reference word used by the
formula. In the RK1 arm that follows the source's `scalar_1 = scalar_2` copy;
in the ELSE arm it avoids stale `scalar_2` output. It does not assign a physical
cause to terms inside `sc_tend` or to the wider scalar-update interval.

At the graupel melt consumer, capture the first trace-graupel matching cell per
timestep, Fortran `lat` row (`j`), and microphysics substep (`loop`) in source
`k`-outer descending, `i`-inner ascending order, satisfying `qg > 0`,
`qg <= qcrmin`, `brs <= brs_min`, and applied `pgmlt < 0`. This is one witness
per row/substep, not a census of all matching columns. Record the actual
selected `i/k` cell and last ProgB owner site alongside raw f32 words for
melt-time and ProgB-gate QG/QIB values, plus post QG/QR/QIB,
temperature, `cpm`, `xlf`, `pgmlt`, `den`, and `delz`. Replay verifies the
validity flag against the captured gate operands using
`qg_gate > qcrmin OR brs_gate > brs_min`. Also record the exact thresholds,
indices, and branch flags. When validity is false, the `rhox` field is empty
and the replayer refuses any supplied word. The S15 runtime switch also enables
S10's ProgB validity mask, so capture cannot silently omit the mask through a
separate environment switch. Column mass, latent cooling, and thermal work are
integrated with the same `den * delz` measure and labeled conditional on the
host density basis. Replay checks the source-order f32 temperature update and
reports thermal/latent mismatch explicitly. Both work terms include
`den * delz`: `den * delz * cpm * ΔT` and `den * delz * xlf * pgmlt`.
Malformed non-finite inputs, a gate-flag mismatch, impossible post-melt mass,
negative layer measures, and melt overdraw are refused. A non-finite
post-volume is retained only when the gate says `rhox` was undefined, and is
labeled as an invalid post-state rather than used in a ledger ratio. Any
post-volume or heat/latent closure with undefined `rhox` is marked untrusted;
a finite ratio such as 400 cannot turn it into an accepted active pair.

The first-event records and QIB transition counts are the bounded diagnostic.
A same-build uninstrumented control and capture run must produce bit-identical
model output and state records before event rows are accepted. The expected
plan separates the source-declared schedule from data-dependent event keys.
The QIB owner and owner-by-tile/RK summary keys are fixed before a B run. A
separate, hashed owner-scoped discovery capture provides only the first-cell
and first-melt key census for a later same-binary confirmation capture; those
discovered cells are a repeatability reference, not an independent physical
expectation. The shared runtime switch can also emit inherited `S10*`
diagnostics for step 1. Preserve and hash full rank stdout, then deterministically
extract only exact `S15Q`, `S15QC`, and `S15M` lines in their original order into
the selected S15 event stream. Hash both files separately. S10 lines remain
visible in the full stdout hash and do not contribute to step-2 S15 counts.
Unknown `S15*` tags are refused. The selected event plan SHA is pinned
out-of-band before confirmation and includes the expected S15 event-stream
digest, so confirmation must reproduce the entire selected stream byte-for-byte.
The parser checks each positive
summary's first QIB cell and first-melt keys per timestep/latitude-row/substep. It
cannot prove when the external pin was created; a trusted pre-capture record is
required. It rejects missing owner/tile/RK summaries, wrong owner keys,
inexact stream digests, repeated first-melt keys, or reference-hash mismatches.

## Pair classes and policy boundary

The parser keeps three measured properties separate: mass `qg` in kg kg-1,
volume `brs` in m3 kg-1, and the apparent ratio `qg/brs` in kg m-3 when `brs`
is positive. It also classifies f32 representability using the smallest
positive subnormal `eta`: `qg < 100*eta` cannot pair with a positive volume at
the stated lower density bound; `100*eta <= qg < 900*eta` admits only a sparse
set; and larger values may admit multiple volume words. These labels describe
the representable pair space, not a selected physical cleanup rule.

The melt ledger reports mass moved from QG to QR and latent work from the
applied `pgmlt` separately. It does not treat `g1`, `g3`, `g4`, or `g5` as the
approved policy. Whether positive trace QG melts, is skipped, or is repaired
at its producer remains an owner decision. The first owner-5 native window had
zero QIB transitions, so negative-QIB producer-term attribution remains open.

## Tooling and provenance

`g33_s15_probe.py` generates macro-guarded overlays in a disposable shadow
tree, checks the private-source pins and exact source anchors, and emits a
machine-readable patch plan. Its graupel consumer hook reuses S10's actual
ProgB assignment-validity mask, records its last producer site, and serializes
`rhox` only when that mask is true. The QIB hook records raw f32 operands and
a per-owner/tile/stage transition count while preserving the source update
expression. The pinned source inputs
are private `module_em.F`, `solve_em.F`, and `module_mp_kdm6.F`; the hashes are
embedded in the script. It never writes to its source root. The replay parser
checks the first-event records, per-tile summary census, cell/tile membership,
first-melt key uniqueness, f32 mass/temperature updates, and an externally
pinned independent reference artifact. `test_g33_s15_probe.py` uses constructed
protocol rows; those fixtures are not model evidence.

The r10 owner-scoped shadow overlays pass byte-exact strip audit against the
three pinned private sources. Green and Red approved the r10 pre-link plan.
The isolated B executable was linked from the exact r6 objects and untouched
S8 archive after setting the available macOS SDK root; its external-pin launch
gate passed. On the first 20-second window, all six owner-5 summary counts were
zero and 51 trace-melt rows passed applicable gate, mass and temperature
replay. All 51 had `rhox_valid=0`, so `brs1` remains untrusted; zero actual
valid-rhox volume updates were validated. The same executable's logging-off
control and logging-on capture matched bit-for-bit at both saved frame indices
for all 253 populated forecast variables and exact `Times`; the energy output
also matched at both frames. prcp and ocean had no populated frames and do not
establish parity. The confirmation event stream reproduced the frozen
discovery stream byte-for-byte.

The initial A capture is excluded from owner-5 evidence: its six `P_QIB` rows
had no call-owner field and came from generic scalar call sites. The public-safe
result and hashes are recorded in `S15_NATIVE_B_20S_RESULT.md`. S15 remains
OPEN; no graupel policy was selected, and the missing step-1 owner-5 QIB
transition does not resolve attribution. The separate step-2 plan requires a
new guard, source/preprocess/object/link/executable pins, a 40-second run, and
a same-executable control/capture pair. It is not evidence from the 20-second
run.

The executed 40-second step-2 discovery and same-executable pair are reported
in [`REPORT_S15_step2_40s_native_2026-09-26.md`](REPORT_S15_step2_40s_native_2026-09-26.md).
The discovery found 87,937 owner-5 transition occurrences across its six
source-pinned RK/tile summaries. They are stage/tile occurrences, not distinct
cells or accepted-state particle loss. Six bounded first-event rows replay
exactly in f32. The 258 melt rows all have invalid `rhox`; no melt thermodynamic
attribution or graupel policy is claimed. Populated forecast frames passed the
control/capture bitwise comparison, while empty auxiliary outputs are marked
insufficient. S15 remains OPEN pending process attribution and physical policy.
