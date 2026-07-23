# G3.3-M four-case evidence — scope and admissibility

What the standalone-Fortran ↔ C++ four-case comparison does and does **not**
certify. This bounds the eventual tri-state verdict so it is never over-read.

## Fixture scope (P1)

`harness/g33_fixture_v1.json` is `science_role: arithmetic_synthetic`. It exists to
exercise, on one shared raw-bit column:

- per-operation provenance of the sedimentation ladder,
- raw-bit cross-tree (Fortran ↔ C++) comparison,
- vertical orientation (top-first ↔ bottom-up permutation),
- branch arithmetic (min caps, positivity clamp, ρΔz vs Δz-only transfer).

It is **not** a meteorological column and does not certify precipitation-system
accuracy. Two coverage limits are explicit, not accidental:

- **Land/sea branch is not exercised.** All columns are land (`xland=1`) and
  `ncmin_land == ncmin_sea`, so the fixture verifies the *input identity* of
  `xland`/`ncmin`, not land/sea branch parity.
- **Meteorological replay and the number-moment budget remain separate gates.**

## ccn0 / scale_h equivalence (P0-9)

The C++ path has no explicit `ccn0`/`scale_h` runtime arguments (they are baked),
while the Fortran passes them as call parameters. The Fortran records their
**actual runtime bits** as `G33F LOCALPARAM` records (not a re-hash of the
authority JSON), cross-checked against the fixture authority.

**Execution order (corrected).** Within one micro subcycle the reference order is
`sedimentation → re-slope/aux → microphysics → state update`: sedimentation runs
*before* the microphysics. In `module_mp_kdm6.F` the sed sub-cycle is at the
`do n = 1, mstepmax` loop; accretion and nucleation — the paths that consume the
CCN/activation constants — are downstream of it (accretion ~line 1885+,
nucleation ~line 2487). The shared fixture's `dt` is `0x41A00000` (20 s) < the
120 s cloud-subcycle threshold, so there is exactly **one** outer loop: the
recorded sed ladder is not preceded by an activation step in this fixture.

**What this does and does not close.** For the G3.3 first scope — the recorded
sedimentation ladder and its surface operands — `ccn0`/`scale_h` are consumed only
downstream (nucleation/activation) and in `kdm6init` constant setup; they do not
enter the fall-speed (`work1`/`workn`) or transport arithmetic. So the recorded
sed evidence is independent of them, and the earlier claim that "`outer_pre_sed`
equality proves `ccn0`/`scale_h` equality" was WRONG (that order was backwards)
and is retracted.

For any comparison that reaches the **full-step final `STATE`/`PREC`** (which do
run through the downstream microphysics), `ccn0`/`scale_h` equivalence is NOT
established by the current evidence. Closing it is **required, not optional**, and
needs one of:
  1. a **dependency proof** — pin, from the source + execution order, that
     `ccn0`/`scale_h` are not consumed before the recorded sed ladder, OR
  2. a **direct C++ diagnostic probe** emitting the baked `ccn0`/`scale_h` bits for
     raw-bit comparison against the Fortran `LOCALPARAM`.
Until one holds, a full-step `STATE`/`PREC` divergence that could trace to
`ccn0`/`scale_h` must be reported **INCONCLUSIVE**, and the admissible G3.3 verdict
rests on the sed-ladder + `outer_pre_sed`/`substep_pre` scope only.

## `outer_pre_sed` capture position (P0-3)

The two backends capture `outer_pre_sed` at **different program points**:

- **C++** emits it before `preamble()` (before the fall-speed / `mstep`
  generation).
- **Fortran** emits it at the sed sub-cycle entry (`do n = 1, mstepmax`), i.e.
  *after* the preamble has computed `work1`/`workn`/`mstep` from the state.

They coincide only if the preamble is state-preserving for the compared fields
(`qr, nr, qv, t, rho, delz`) — which it is: the preamble derives the fall speeds
from those fields without mutating them. This is not assumed silently:

- `verify_semantics` check (4) proves the Fortran `outer_pre_sed` **is** the
  first substep's entry state (`substep_pre(n=1) == outer_pre_sed`), so the
  Fortran snapshot is a genuine sed-entry observation, not a stale copy.
- The comparator then requires `outer_pre_sed` raw-bit equality **across trees**.
  If the preamble had perturbed any compared field on one side, that equality
  would fail and the verdict is **INCONCLUSIVE** — never a false sedimentation
  verdict. So the differing capture point cannot silently corrupt the comparison;
  at worst it is surfaced as an upstream divergence.

## Verdict bounds

- **PASS** — both pairs (legacy-F↔legacy-C++, conservative-F↔conservative-C++)
  first diverge at the **same shared** expression family, with `outer_pre_sed` and
  `substep_pre` (work1/workn/mstep/gate) equal.
- **FAIL** — the conservative pair's first divergence is at a **conservative-only**
  arithmetic rung (ρΔz mass inflow, Δz number inflow, rate accumulation, capped
  TOP depletion, no-clamp update). **One-sentence definition (owner-pinned):**
  G3.3-M FAILs iff the conservative pair's first cross-tree divergence lands in
  conservative-only arithmetic — *any* such mismatch fails, even when the legacy
  pair also diverges at its corresponding variant-specific rung in parallel; the
  legacy pair is a label, not a mitigating control.
- **INCONCLUSIVE** — `outer_pre_sed` or `substep_pre` already differ (upstream /
  fall-speed / gating divergence, incl. any `ccn0`/`scale_h` mismatch); the first
  divergence is a **causal carry** or **external input** (grid metric / baked
  constant such as `delz_bottom`/`surface_denr`, not yet sealed by preflight); it
  is in a non-instrumented / out-of-scope species or output (`bottom_fall_qs/qg/qi`,
  snow/graupel increment); or the surface causal set cannot be closed.

A G3.3-M PASS certifies only that the observed Fortran↔C++ difference did **not
originate in conservative-only arithmetic**. It never licenses "conservative-
interface-v1 conserves two-moment sedimentation": the interface is
water-mass-conservative, and number transport is reference-faithful (Δz-only), not
column-number (ρΔz·nr) conserving.
