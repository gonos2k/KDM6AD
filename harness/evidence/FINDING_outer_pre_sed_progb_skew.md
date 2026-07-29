# Finding: `outer_pre_sed` is recorded on opposite sides of ProgB in the two backends

Status: **CONFIRMED by a four-leg anchored run.** An instrumentation-boundary defect in
the harness, not a physics difference — and it corrects a claim I made earlier.

## What was measured

`boundary_mapping_v1`, kernel boundary, protocol v6, all four legs `verdict_ready` under
the six external anchors plus a clean-checker Gate A report:

```
verdict            INCONCLUSIVE
first divergence   loop 1 outer_pre_sed  col 2  k 1  brs  f32
                   Fortran 0x327c8b48   C++ 0x327c8b49   +1 ULP   C>F
                   IDENTICAL in legacy and conservative
kernel_call_input  matched across all four legs
```

`kernel_call_input` matching is what makes the rest readable: the two backends were
handed the same arguments, and `brs` at that cell is the fixture's own value
`0x327c8b49`. The C++ leg still holds it at `outer_pre_sed`. The Fortran leg is one ULP
lower.

## Why

`brs` is `INTENT(INOUT)` in `ProgB_param` — the declaration calls it
`!prognosticparameter` — and the two backends record the snapshot on opposite sides of
it:

| backend | ProgB | `outer_pre_sed` |
|---|---|---|
| Fortran (`module_mp_kdm6.F`) | `call ProgB_param(brs, ...)` at **:1154** | **:1189** (after) |
| C++ (`runtime.cpp`) | `progb::make_zero_progb_state` at **:579** | **:547** (before) |

So the comparator has been comparing Fortran's post-ProgB `brs` against C++'s pre-ProgB
`brs`. They agree only where ProgB happens to leave `brs` unchanged, which is why no
earlier fixture surfaced it.

This is the same cell the Fortran-only `kernel_call_input` → `outer_pre_sed` diagnostic
flagged on this fixture. Two independent measurements, from opposite directions, land on
the same cell.

## Correction

When I first reported that 1-ULP change I wrote that the only write to `brs` between the
call boundary and the sedimentation snapshot was `brs(i,k) = max(brs(i,k),0.0)` at
`:864`, a no-op on a positive value. **That was wrong.** I had searched lines 840–1130
while the snapshot is at :1189, so the search window ended 35 lines short of
`ProgB_param` at :1154. The conclusion I drew from it — "unexplained" — was an artifact
of the window, not of the code.

## What it means for the existing evidence

The `dt=300` kernel artifact's first divergence is at loop 2 `outer_post_micro.qr`, not
at `brs`, so this skew is not what produced it. But `brs` is in the compared field set
at `outer_pre_sed` in that run too, which means one of the twelve carried fields was
being compared at two different instants. The claim "loop 1 was bit-identical" holds for
the other eleven and is only accidentally true for `brs`.

## The fix, and why it is not applied here

Either the C++ snapshot moves after ProgB, or the Fortran injection moves before
`ProgB_param`. The C++ side is the overlay, so both are harness-only — no production
change.

Which one is right is not arbitrary: `outer_pre_sed` is defined as "the state ENTERING
sedimentation", and sedimentation consumes ProgB's output. That argues for recording
after ProgB in both, i.e. moving the C++ snapshot. But it is a change to what every
existing bundle means, so it belongs with the `kernel_after_prologue` work rather than
as a quiet edit: with three snapshots — call input, after prologue, entering
sedimentation — the question stops being "which instant did we pick" and becomes a
measured interval.

## Separately: the `ncmin` finding is NOT confirmed by this run

`FINDING_ncmin_scalar_vs_percell.md` predicted a difference in the `ncmin`-gated fields
on this fixture. The first divergence is `brs`, upstream of any rate, so the run stops
before it could show. That finding remains source-level only. Re-running after the
snapshot skew is fixed is what would test it.
