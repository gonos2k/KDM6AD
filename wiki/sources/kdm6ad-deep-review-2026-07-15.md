---
title: kdm6ad-deep-review-2026-07-15
type: source
date_modified: 2026-07-15
provenance:
  sources:
    - external deep review (mathematical / meteorological / engineering), pasted 2026-07-15
    - baseline reviewed: origin/main@e1c701e
---
# KDM6AD deep review (2026-07-15)

External cross-review of the math/meteorology/engineering of KDM6AD at
`origin/main@e1c701e`, on source + docs + public-CI structure only (no host tree,
no live RTTOV re-run). Filed as a source; the load-bearing factual claims were
**verified against the tree** on ingest (status column below).

## Headline reframing

The review's central correction (endorsed):

> KDM6AD is a bitwise-matched **f32 forward port** plus a **separate f64,
> branch-local differentiable map** following the same process structure. The
> current DA runs in a **prescribed-forcing microphysics window** (pressure,
> density, Exner, layer-thickness, and dynamics held fixed) — a
> microphysics-window variational assimilation, **not** a fully-coupled WRF/KIM
> 4D-Var, and **not** the literal adjoint of the operational f32 map.

## Load-bearing claims — verified on ingest

| Claim | Verified against | Status |
|---|---|---|
| No LICENSE; downstream-provenance blocker | `ls`, `CITATION.cff` | ✅ exact |
| AD input = 12 state + 4 forcing; **forcing not differentiated** | `libtorch/bridge/kdm6_c_api.h` | ✅ |
| AD output = 12 states; precip/ρ_g/reflectivity/r_eff diagnostic-only | packed AD layout in header | ✅ |
| RTTOV cloud fraction is binary, non-diff passthrough | `rttov_obs_operator.py:68` (`cfrac = non-diff passthrough`) | ✅ |
| `threshold cleanup` zeroes mass+paired number, leaves `qv`, no latent/T fix | `coordinator.cpp:2277` (`/*qv=*/state.qv`) | ✅ exact |
| f32 handle is mechanics/diagnostics, not for DA | header:285 | ✅ |
| Raw `xland` pointer "carries no shape info" | header:107/227 | ⚠ imprecise — shape+NULL⇒maritime **is** documented; what is missing is **runtime enforcement** (no element count to validate). Remedy (descriptor w/ stride+count) still valid. |

## What is new vs already-tracked

Most of the *diagnosis* already lives in the KG tension log — see
[[Operational-Raw vs DA-Clamped Dual Path]] (dual map), [[KDM6AD Differentiability Audit]]
(jump vs kink), [[KDM6AD Automatic Differentiation ABI]] (12-state surface, forcing fixed),
[[KDM6AD Forward Parity]] (parity ≠ meteorological skill). The review's value-add is the
**strategic reframing + P0/P1/P2 prioritization**, not new defects.

## Priorities (as filed)

- **P0-1** LICENSE / SPDX / provenance — the real external-adoption blocker.
- **P0-2** State the precise differentiation contract in README/docs (done 2026-07-15:
  README "Scope & differentiation contract" + `docs/STATUS.md` — the docs were already careful,
  so this made the implicit contract explicit, not a correction of overclaiming).
- **P0-3** Expose forcing VJP (`M_fᵀ`) + diagnostic output seeds (precip, ρ_g, reflectivity).
  **FROZEN** — changes the AD/C ABI surface; needs an owner freeze-lift like PR1-A/B.
- **P0-4** Real column water/energy budget: `ρΔz`-weighted total water + explicit cleanup-sink
  + scheme-consistent moist enthalpy (oracle-side; not frozen).
- **P0-5** Public license-clean synthetic fixtures (smooth FD/VJP/JVP, jump crossing, sed flux
  closure, f32/f64 branch divergence, mock all-sky gradient).
- **P1** full-model outer loop / host adjoint; continuous cloud fraction + 5-species optics;
  multivariate B; independent (withheld) verification; regime-aware outer loop.
- **P2** fp64 AD ABI v2 descriptor; C-ABI domain validation; `closep`-only lifecycle;
  ASan/UBSan + fuzzing; toolchain matrix; true forward-mode JVP; STATUS.md (done).

> [!note] Verdict (endorsed)
> Strong as a **verified forward port** and a **promising differentiable-microphysics research
> platform**; the current adjoint is a **branch-local f64 conditional map**; full-coupled NWP
> 4D-Var and external product distribution remain the open gaps (LICENSE first).

## Candidate heuristics (NOT auto-promoted — confirm before `/kg-elicit`)

- "Adjoint dot-product identity `⟨Jv,u⟩=⟨v,Jᵀu⟩` proves transpose-consistency, not physical
  correctness — always add smooth-regime directional FD + an independent physical-invariant check."
- "Compare sensitivities in control/nondimensional space (`σ_x ∂J/∂x` or `∇_v J`), never raw
  `∂J/∂q` across fields with 10-order unit gaps."

Provenance: pasted external review 2026-07-15; verification greps/reads this session against
`origin/main@e1c701e`. Related: `docs/STATUS.md`, [[kdm6ad-differentiable-mathematics-2026-07-04]],
[[Differentiable Bulk Microphysics Research Gap]].
