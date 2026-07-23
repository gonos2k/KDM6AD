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
while the Fortran passes them as call parameters. The Fortran now records their
**actual runtime bits** as `G33F LOCALPARAM` records (not a re-hash of the
authority JSON), cross-checked against the fixture authority.

Cross-tree equivalence of these two is **gated by `outer_pre_sed` equality**, not
asserted separately: `ccn0`/`scale_h` influence droplet activation, which runs in
the microphysics *before* sedimentation. If the C++ baked values differed from the
Fortran authority values, the pre-sedimentation state (`outer_pre_sed`: qr, nr,
qv, t, rho, delz) would differ. The comparator checks `outer_pre_sed` for raw-bit
equality first; a mismatch there — from any upstream cause, `ccn0`/`scale_h`
included — yields **INCONCLUSIVE**, never a PASS or FAIL. This is the
conservative (option-3) closure: a parameter divergence cannot masquerade as a
sedimentation-mechanism verdict.

A stronger closure (a C++ diagnostic probe emitting the baked `ccn0`/`scale_h`
bits for direct raw-bit comparison) is optional and belongs to the comparator PR;
the `outer_pre_sed` gate already prevents a wrong verdict without it.

## Verdict bounds

- **PASS** — both pairs (legacy-F↔legacy-C++, conservative-F↔conservative-C++)
  first diverge at the **same shared** expression family, with `outer_pre_sed` and
  `substep_pre` (work1/workn/mstep/gate) equal.
- **FAIL** — the conservative pair's first divergence is at a **conservative-only**
  ρΔz operation (`dq_in`, no-clamp update) absent from the legacy pair.
- **INCONCLUSIVE** — `outer_pre_sed` or `substep_pre` already differ (upstream /
  fall-speed / gating divergence, incl. any `ccn0`/`scale_h` mismatch); the first
  divergence is in a non-instrumented species/stage; or the surface causal set
  cannot be closed.

A G3.3-M PASS certifies only that the observed Fortran↔C++ difference did **not
originate in conservative-only arithmetic**. It never licenses "conservative-
interface-v1 conserves two-moment sedimentation": the interface is
water-mass-conservative, and number transport is reference-faithful (Δz-only), not
column-number (ρΔz·nr) conserving.
