# §7's mechanism is real and ~3%; the large differences are not it, and the headline number is not reproducible

Owner review §7. The conservative interface moves **mass** with a ρΔz measure and
**number** with the legacy Δz-only one (`sedimentation_conservative.cpp:91-92`
against `:109`), so a transferred population's mean particle mass should shift by
the density ratio:

    Δq_l / Δn_l = (ρ_u / ρ_l) (Δq_u / Δn_u)

## Measured against the right baseline

Not against the same run's own start. Over 300 s of full microphysics, `q` and `n`
change independently through condensation, nucleation and aggregation, so a changed
`q/n` **within** one run is ordinary physics — an earlier version of this diagnostic
compared endpoints and would have reported that as a conservation defect.

The baseline is the **legacy run at the same cell**: the interface is the only
difference between the two runs. The **top level has no inflow from above**, so its
ratio of exactly `1.0000` is the control, and it holds in every run below.

## §7's prediction: the mechanism is real, but "confirmed quantitatively" overstates it

Column 3 densities give ρ_u/ρ_l = **1.0330, 1.0319, 1.0309** for the three
transfers. Measured within a fine-step run (dtcld = 3.125 s), conservative/legacy
mean ice-particle mass at t = 25 s:

| | k0 | k1 | k2 | k3 |
|---|---|---|---|---|
| predicted | 1.0330 | 1.0319 | 1.0309 | — |
| **measured** | **1.0331** | **1.0296** | **1.0126** | 1.0000 |

k0 matches to four figures — but only k0. Read as deviations from 1, which is the
actual signal: k0 is 0.3% off the prediction, **k1 is 7% low and k2 is 59% low**.
One of three points matching is not quantitative confirmation of all three.

Two further limits on this number, both material:

* **It is not reproducible from committed evidence.** The t = 25 s figures come from
  an ad-hoc `--emit-each` boundary run, not from any committed stream — every
  committed member is a single end-state. The measurement should be re-taken from a
  reproducible artifact before it is relied on.
* A null model of "ratio = 1 + noise" **is** refuted by the data (about 6× worse
  fit), and the measured effect has the right sign and roughly the right size. So
  **there is a real 1–3% effect and the mechanism is verifiable from source** — what
  fails is the word "quantitatively", not the existence of the effect.

## But the 300 s outcome is not that number, and does not converge

Final mean ice-particle mass ratio at 300 s, against the internal step:

| dtcld (s) | k0 | k1 | k2 | k3 |
|---|---|---|---|---|
| 100 | 3.009 | 2.962 | 1.907 | 1.0000 |
| 50 | 6.767 | 4.190 | 2.130 | 1.0000 |
| 25 | 5.612 | 3.248 | 1.650 | 1.0000 |
| 12.5 | 8.651 | 5.157 | 2.684 | 1.0000 |
| 6.25 | 1.547 | 1.450 | 1.315 | 1.0000 |
| **3.125** | **0.9998** | **0.9998** | **0.9999** | 1.0000 |

Erratic — 3.0, 6.8, 5.6, 8.7, 1.5 — then collapsing to 1 at the finest step. Not a
convergent sequence, and the reason is already established: **column 3's branch
topology moves with resolution** (graupel presence flips on, off for four members,
and on again), so these are not comparable integrations. Within one run the ratio
follows the same shape in time: a large transient at 3 s, §7's 1.033 at 25 s, then
settling to 0.9998 by 100 s and staying there.

## What this establishes

1. **§7's ρΔz-vs-Δz mechanism is real** — the effect has the right sign and roughly
   the right size, and a "ratio = 1 + noise" null is refuted by the data. But only
   k0 matches the prediction closely (k1 7% low, k2 59% low), and the t = 25 s
   figures are **not reproducible from a committed stream**, so "quantitatively
   confirmed" is withdrawn.
2. **It is a ~3% effect per transfer**, not the 200–800% seen at coarse steps.
3. **The large coarse-step differences are UNATTRIBUTED.** An earlier version said
   they were "dominated by branch-topology divergence"; that is withdrawn — the
   flipping species carries 3.99e-06 of the column (ρΔz-weighted) and cannot
   dominate anything. The measured cause of the erratic convergence is the
   **sedimentation sub-step count** (`mstep` 10 → 5 → 3 → 2 in column 3), but that
   explains the *convergence sequence*, not the size of the mean-mass differences,
   which remain unexplained.
4. **The finest-step endpoint shows little difference (0.9998). That does NOT make
   the mismatch non-structural.** What became small is this fixture's *final-state
   manifestation* at a fine step. The transfer arithmetic still uses ρΔz for mass
   and Δz-only for number — that asymmetry is in the source and does not depend on
   the timestep. An earlier version drew the opposite conclusion and it is
   withdrawn.

Column number is reported as a **change**, not a residual: the surface number flux
is not emitted — only mass precipitation is — so no closure can be formed here.
`ni` column number is 1.69× legacy at dtcld = 25 s, which inherits the same
topology caveat.

## What this does NOT establish

- **No number closure.** `ΔN_col + F_N,surface = R_N` cannot be evaluated without
  the surface number flux, which neither driver emits.

  **Correction.** An earlier version of this line said "adding it is a driver
  change, not a kernel change". That is wrong. The surface number flux is
  `falln(i,kts,1)` (rain number, paired with `nrs`) and `falln(i,kts,2)` (ice
  number, paired with `nci`), and `falln` is declared at `module_mp_kdm6.F:719`
  **in the local block, with no `intent`** — it is never returned, so no driver
  can see it. It is reachable, but by the SHA-pinned macro-gated **overlay** —
  the same mechanism that recovered `mstep` from a local — which requires a new
  anchored injection site and its A/B/C non-invasiveness proof, not a driver
  edit. The conclusion "reachable, simply not done" stands; the cost does not.

  Visible at that same site, in the pinned reference itself, is the measure
  asymmetry this finding is about: `falk = dend*qrs*work1/mstep` against
  `falkn = nrs*workn/mstep`, and `qrs -= falk*dtcld/dend` against
  `nrs -= falkn*dtcld`.
- **No operational size.** The one step where the mechanism is cleanly measurable
  (3.125 s) is far finer than operational. The operationally normal steps
  (25–100 s) sit where the sedimentation sub-step count changes most (`mstep`
  10 → 5 → 3 → 2), so the chain there is not refining the quantity sedimentation
  actually integrates. This fixture cannot say what the 3% costs a forecast.
- **The endpoint mean-mass ratio is not the interface transfer ratio.** The
  recipient cell already holds `(q, n)` and continues to condense, nucleate and
  aggregate afterwards, so `(q/n)_cons / (q/n)_legacy` at 300 s is not
  `Δq/Δn` across the interface. Measuring the mechanism directly needs the
  per-interface increments, which are not emitted.
- **Nothing about `nr`.** The interface never touches `nr` or `qr` on this fixture,
  so the rain-number channel the release blocker names is not exercised at all. The
  measurement above is the ICE channel.
- DSD slope, terminal velocity, reflectivity and the adjoint consequences §7 lists
  downstream of a mean-mass shift are not measured.

The fixture requirement is the same one the refinement work arrived at: a cold
column that stays on one branch across the chain. Until then the mechanism is
confirmed but its magnitude is only bounded at one impractically fine step.
