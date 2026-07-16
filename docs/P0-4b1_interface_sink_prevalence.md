# P0-4b.1 — interface-sink prevalence and correction decision package

Investigation-only follow-up to P0-4b (which attributed the sedimentation gap
100% to the reference-faithful post-update-reservoir inflow cap). This package
measures **how often and how strongly the sink fires in the real LC05 state
space**, provides a **conservative counterfactual**, and quantifies its
**impact** — the inputs to the freeze-lift / physics-variant decision. No
frozen code was touched; the legacy path stays byte-identical
(`torch.equal`-asserted).

Artifacts: `docs/reports/p0_4b1_cfl_sink_phase_map.json` (+`.png`),
`p0_4b1_lc05_replay_audit.json`, `p0_4b1_impact_comparison.json`.

## 1. CFL–sink phase map (synthetic, legacy substep)

With per-substep fall ratio `c = vt·Δt_sub/Δz`:

- The inflow cap first fires at **c = 0.55**, and the measured defect matches
  the theory `D = ρΔz·q·max(2c−1, 0)` **exactly for c ≤ 1** (the theory's
  validity range); above c = 1 the measured D keeps growing.
- **Structural exposure**: the operational substep rule
  `mstep = floor(C_total + 1)` guarantees per-substep `c < 1` but **not**
  `c < ½` — it lands in the sink-active region `c_sub > ½` for **54/60** of the
  swept `C_total` grid (all `C_total ≥ 0.6`). Virtually the entire
  precipitating regime operates where the sink can fire; the synthetic
  heavy-rain case was not a coincidence.
- Worst sampled point (c = 1.5): 75% of the initial hydrometeor mass deleted at
  a single interface in one substep.

## 2. LC05 frame-replay susceptibility audit

One oracle step (dt = 300 s) replayed on each of the 37 restored LC05 frames
(65,988 columns × 39 levels; sharded 16-way — batch-global `mstepmax` otherwise
lets single heavy columns dominate the whole domain's substep count).

**Naming contract**: WRF history frames are not the exact pre-physics host
states; these are susceptibility measurements, **not** "water actually lost in
the host integration".

| measure | value |
|---|---|
| columns firing, every frame | **51.4–60.7%** of the domain (threshold: sink > 1e-9 kg/m² — a deliberately permissive "any defect" count; the magnitude distribution below is the materiality measure) |
| domain sink, frames ≥ 1 | 54–104 kg/m² per step = **2.1–4.6% of surface fallout** |
| **frame 0 (analysis-IC-like state)** | **2,917 kg/m² = 41% of total hydrometeor mass in ONE step; 40× the surface diagnostic** |
| 3 h per-column cumulative (replay) | p50 0.010 · p90 0.219 · **p99 1.33 · max 10.0** kg/m² |
| species share (3 h aggregate) | **qi 65%** · qr 24% · qg 10% · qs ≈ 0 |
| worst interface | k = 15–16 ≈ **530–580 hPa** (mid-troposphere ice/mixed-phase) |
| positivity projection A | **≡ 0 across all frames** — the real-space sink is entirely the interface defect D |

Two readings matter for the decision:

- **In equilibrated precipitation the sink is modest domain-wide** (2.1–4.6% of
  fallout on every frame except the IC) **with a heavy tail** (p99 1.3 kg/m² per
  3 h; max 10). Only frame 0 is an outlier — frames 1–5 already sit in the
  normal 75–104 kg/m² band.
- **Freshly-initialized states are maximally susceptible**: frame 0 — the
  analysis IC, with unequilibrated hydrometeor profiles — loses 41% of its
  hydrometeor mass to the sink in a single step. This is precisely the state
  class a DA system hands the model after every analysis increment, so the
  defect bites hardest exactly where DA fidelity matters.
- The qi dominance (65%) flows through the mp37-faithful raw ice-velocity
  handoff (the documented "mp37 loses 37%/step of qi" pathway) meeting the
  interface cap at mid-levels; this is a *second* reference-faithful behavior
  that a variant decision should scope explicitly.

## 3. Conservative counterfactual (analysis-only)

`kdm6/sed_conservative.py` — each lower cell receives the mass **actually
removed** from its source cell (entry-capped outflow, ρΔz-converted) instead of
re-capping the stored raw flux by the source's post-update reservoir; the
surface diagnostic reports the actual bottom outflow. Explicit opt-in
(`kdm6_step_conservative_experiment`); injection-only wiring (`substep_fn`
defaults to legacy). Acceptance — all green (6 RED-first tests):

- `W_post − W_pre + P_actual = O(ε64)` per column, incl. dt=300 multi-mstep ×
  multi-subcycle; no negatives; interface defect at the fp64 floor;
- legacy path `torch.equal`; FD directional derivative matches autograd
  (rtol 1e-6); ice-chain variant conservative.

## 4. Impact: legacy vs conservative (same inputs)

- **One step** (synthetic heavy rain): surface precip identical (the legacy
  bottom diagnostic was accurate); the previously-vanishing ~6 kg/m² **stays in
  the upper column** (the upper-level q profile stays uniform instead of
  draining into nothing), with knock-on into qc/qv/th via satadj/warm.
- **LC05 heaviest-256-column window** (prescribed per-frame forcing): aggregate
  cumulative surface precipitation ratio conservative/legacy (ratio of the
  256-column mean totals) = **1.306 (1 h)**, **1.286 (3 h)** — the retained mass
  largely converts to **≈ +29% aggregate surface precipitation** as columns rain
  out (final hydro both → ~0). The mean of the per-column ratios is higher
  (1.379 / 1.336) because lighter-precip columns gain proportionally more —
  both statistics are in the artifact; the aggregate ratio is the headline.
- **Gradients**: VJP norms ≈ **2×** under the conservative variant (the legacy
  cap severs sensitivity paths); no NaN/Inf in either variant.
- All-sky BT / obs-cost comparison **deferred** (needs the local RTTOV runtime);
  the state-space impacts above are the merge-decision inputs.

## 5. Recommendation (owner decides)

The prevalence is structural (phase map), broad (>51% of real columns every
step, at the permissive >1e-9 threshold), and material where it matters most (analysis-IC states: 41%/step;
convective tails: p99 1.3 kg/m²/3 h; trajectory effect: ≈ +29% aggregate
cumulative precip on heavy columns; 2× adjoint sensitivity). Per the pre-stated policy this
supports the **new conservative physics variant** path — NOT a silent baseline
change:

```text
legacy KDM6 / KDM6AD       — current parity baseline, frozen permanently
                             (mp37/mp137/abi-v2-hardened@a53503e unchanged)
conservative KDM6 variant  — new scheme identifier / physics version,
                             corrected Fortran + corrected C++ with their own
                             parity lineage, 12 h × MPI revalidation, a column
                             -water closure gate, new tag + release evidence
```

Scope note for the variant decision: fixing the interface transfer (this
package's counterfactual) removes the D mechanism for **all** species; whether
the mp37-faithful **raw ice-velocity handoff** (the pathway feeding 65% of the
real-space sink into that mechanism) is *also* revised is a separate,
explicitly-scoped choice — the counterfactual here conserves mass either way.

P0-4c (process-wise latent/thermal work ledger) should start only after this
decision, treating any remaining sedimentation sink as an explicit external
mass/enthalpy term (or evaluating the energy ledger on the conservative
variant, where the term vanishes).
