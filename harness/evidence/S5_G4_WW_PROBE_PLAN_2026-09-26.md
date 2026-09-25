# S5 next capture plan: `calc_ww_cp` internal first-divergence probe

Status: **prepared, not executed**. S5 remains **OPEN**; this plan does not
attribute the selected 2x1 `ww` difference to arithmetic, compiler code
generation, halo data, or call extents.

The merged S5 trace reports equal selected caller/stencil words at RK entry
for i=117 and i=234, followed by selected stage-2 `ww` differences in the
2x1 layout. The actual `calc_ww_cp` tile extents differ between layouts, so
equal caller words do not isolate the cause. The next bounded capture should
record the first internal values produced by the exact pinned routine, in
source order, at the same selected i coordinates.

## Source and scope pin

The overlay generator accepts only
`host/KIM-meso_v1.0/dyn_em/module_big_step_utilities_em.F` with SHA-256
`27ce690b27b24c80247a5551b48d37fc32fc47470d806cbef1bb859d58edc31c`. It
requires one `calc_ww_cp` routine and unique anchors for its declarations,
derived loop bounds, completed local `muu`/`muv` construction, completed
vertical `divv`/`dmdt` sum, and completed `ww` recurrence. It writes only a
shadow source file. It does not edit the private host tree, build, link, or
run the host.

Every inserted block is guarded by `KDM6AD_S5_WW_CAPTURE`. The generator
removes the marked blocks and requires byte-for-byte equality with the pinned
source. The macro-off stripping test runs on a small source fixture; a local
read-only generation check against the pinned private source also reproduced
the source SHA after stripping. That generation check is not a compiler or
native-run result.

## Bounded records

When a later isolated capture build defines the guard and sets
`KDM6AD_S5_WW_CAPTURE_PREFIX`, the routine records only the first three
invocations for each distinct `its:ite,jts:jte` tile bound. Each file records
the call ordinal, rank (when exposed by OpenMPI/PMI), global and memory bounds,
actual `its/ite/jts/jte/kts/kte`, derived `itf/jtf/ktf`, and default REAL and
INTEGER storage widths. Selected REAL values are written as raw default
INTEGER transfer words. The saved per-tile invocation counter assumes the
G4 capture's single-threaded execution; threaded captures are outside this
schedule.

For owned output i=117 and i=234, the capture records:

- the local `muu(i:i+1,j)` and `muv(i,j:j+1)` values after their construction;
- each `divv(i,k,j)` and the vertically accumulated `dmdt(i,j)` before the
  `ww` recurrence;
- each `ww(i,k,j)` after the recurrence.

The selected output schedule is j=1..282, `divv` k=1..39, and `ww` k=1..40.
Inputs include the minimal local staggered neighbors used by the selected
output cells. Capture calls are labeled by per-tile invocation ordinal; they
are not labeled as RK stages by assumption. The later run receipt must map
these ordinals to the existing stage trace before interpreting a difference.

The independent schedule validator pins the expected tile bounds and first
three invocation ordinals for both 1x1 and 2x1 layouts. It derives selected
sample keys from that declared schedule, not from files received. It rejects
missing, duplicate, additional, or relocated selected samples and unexpected
tile/call headers. Each sample stores both the target output i and the actual
array coordinates, so the `muu(i+1,j)` stencil word cannot be mistaken for a
second `muu(i,j)` value. The test schedule has six tile/call headers for 1x1
and twelve for 2x1; both layouts have 140,448 selected words across the three
invocations because the 2x1 tiles split the two target i columns between owners.

The parser also pins the global bounds to `(ids:ide,jds:jde,kds:kde) =
(1:235,1:283,1:40)`, consistent with the retained LC05 namelist
`e_we/e_sn/e_vert = 235/283/40` and its 234x282x39 mass plus staggered input
dimensions. Rank memory bounds are independently fixed from the accepted
G4 exact2 tile metadata: 1x1 rank 0 uses i=-4:240, 2x1 rank 0 uses i=-4:124,
and 2x1 rank 1 uses i=111:240; all use j=-4:288 and k=1:40. Changed global
origins/extents and impossible rank memory ranges are regression cases.
Capture mode stops with an explicit error if a fifth distinct tile appears,
rather than silently omitting it. Further invocations on an expected tile are
left unlogged after the first three; they do not abort a later RK stage or
timestep. Control-off behavior is unchanged because the overflow check remains
inside the opt-in guard.
The parser returns these checked global, rank-memory, per-call tile and
derived-loop bounds in its receipt alongside the selected raw-word map.

## Next discriminating experiment

After the native lane is released, first build the guarded shadow object using
the exact WRF preprocessing pipeline already pinned by S5. Preserve the
operational object and defaults. For each layout, compare capture-on against
same-binary capture-off output and the accepted G4 baseline before using any
internal trace. If either layout changes history, discard causal
interpretation and retain the failure receipt.

Only after the noninterference gate passes, compare the earliest differing
record in source order: local `muu/muv`, then `divv`, then `dmdt`, then `ww`.
Keep the actual call bounds alongside each record. Equal intermediate inputs
and different output under different call bounds would still leave a
call-extent versus code-generation question; a subsequent one-factor
counterfactual is required to attribute cause. No operational fix or S5
closure follows from this probe alone.

## Current validation

The focused Python tests pass (13 total) for macro-off exact stripping,
source-anchor uniqueness and source-hash refusal, declared selected-cell
schedule completeness, raw-word parser behavior, and
missing/duplicate/relocated-record rejection, global/memory-bound mutation, and
fifth-tile fail-closed coverage. A local
generation against the pinned private source returned matching original and
macro-off-stripped hashes. A standalone CPP-only guard-on pass confirmed that
the `muu/muv` snapshot follows both local-array loops and precedes the outer
`j` loop, the `divv/dmdt` snapshot follows its vertical sum and precedes the
`ww` recurrence, and the `ww` snapshot runs inside that `j` loop after its
recurrence. The 19 apostrophe-in-comment warnings also occur when CPP processes
the unmodified source; no warning points to the probe block. This was not the
WRF `standard.exe` preprocessing pipeline. Macro-off source stripping is
byte-exact; standalone CPP output has only the additional blank lines left by
the guarded blocks. No Fortran compilation, linking, native run, or
code-generation counterfactual was performed here.
