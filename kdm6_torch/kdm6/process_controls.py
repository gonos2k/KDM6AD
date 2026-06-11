"""[DA Phase 5.3] α process-rate controls — flag-gated, fp64-oracle-only
(kdm6ad+da.md §5.2).

Multiplicative controls R' = R · exp(α) applied to selected process-rate
GROUPS at the phase-output boundary, BEFORE the group conservation limiters
(so budgets still bound the perturbed rates — non-negativity is preserved by
the same Fortran-mirrored machinery that bounds the unperturbed rates).

Design constraints honored:
- ``controls=None`` (the default everywhere) adds ZERO ops — the oracle's
  graph and values are byte-identical to the pre-control code. The operational
  C++/f32 path never sees these hooks at all (strongest bitwise protection).
- Branch/gate masks (ifsat, complete-evap/sublim, conservation trip masks) are
  evaluated at the UNPERTURBED rates' state — α perturbs magnitudes, not
  branch selection. This keeps the α→output map smooth (no new kinks on the
  control path; cf. the §31/§45 kink lessons).
- exp(0) == 1.0 exactly in IEEE, so α = 0 gives bitwise-identical rates —
  but the α=None and α=0 paths differ in GRAPH (α=0 still inserts ops); use
  None when the control must not exist.
- α_sedimentation is intentionally ABSENT (design §5.2: the mstep integer /
  no-grad discontinuity makes it a different mechanism — deferred).

Per-process rate groups (mass + number of the same process move together):
  autoconv    → warm praut, nraut
  accretion   → warm pracw, nracw                      (warm rain ← cloud)
  deposition  → cold pidep, psdep, pgdep               (vapor ↔ ice/snow/graupel)
  riming      → cold psacw,nsacw,pgacw,ngacw,paacw_adj,naacw,piacw,niacw
  freeze      → mf D2 pinuc,ninuc + D3 pfrzdtc,nfrzdtc (Bigg cloud + contact)
                [D4 pfrzdtr EXCLUDED in v1: delta_brs_freeze is derived from
                 it inside the phase; scaling one without the other breaks the
                 brs bookkeeping — needs an in-phase hook]
  melt        → mf D5 pseml,nseml,pgeml,ngeml          (enhanced melting)
                [D1 instantaneous melt EXCLUDED in v1: sfac/gfac/delta_brs are
                 derived from psmlt/pgmlt inside the phase — same coupling]

NOT α-controlled in v1 (documented partial coverage, adversarial review):
homogeneous freezing (supcol>40 inline), warm rain evaporation prevp,
cold collection family (praci/piacr/psaci/pgaci/pracs/psacr/pgacr),
Hallett-Mossop multiplication, ice nucleation pinud, snow autoconv psaut,
snow/graupel evaporation psevp/pgevp, and sedimentation (design §5.2
deferral). Extending coverage = same phase-output-boundary pattern.
"""
from __future__ import annotations

from typing import NamedTuple, Optional

import torch


class ProcessControls(NamedTuple):
    """α controls; each entry is None (control absent — zero added ops) or a
    tensor broadcastable to the rate shape (per-cell) / scalar tensor."""
    alpha_autoconv: Optional[torch.Tensor] = None
    alpha_accretion: Optional[torch.Tensor] = None
    alpha_deposition: Optional[torch.Tensor] = None
    alpha_riming: Optional[torch.Tensor] = None
    alpha_freeze: Optional[torch.Tensor] = None
    alpha_melt: Optional[torch.Tensor] = None

    def any_active(self) -> bool:
        return any(a is not None for a in self)


def _scale(struct, fields: tuple, alpha: Optional[torch.Tensor]):
    """Return struct with the named rate fields multiplied by exp(alpha).
    alpha=None returns the SAME object (no ops, no copy)."""
    if alpha is None:
        return struct
    s = torch.exp(alpha)
    return struct._replace(**{f: getattr(struct, f) * s for f in fields})


def apply_warm_controls(warm_out, controls: Optional[ProcessControls]):
    if controls is None:
        return warm_out
    warm_out = _scale(warm_out, ("praut", "nraut"), controls.alpha_autoconv)
    warm_out = _scale(warm_out, ("pracw", "nracw"), controls.alpha_accretion)
    return warm_out


def apply_cold_controls(cold_out, controls: Optional[ProcessControls]):
    if controls is None:
        return cold_out
    cold_out = _scale(cold_out, ("pidep", "psdep", "pgdep"),
                      controls.alpha_deposition)
    cold_out = _scale(cold_out,
                      ("psacw", "nsacw", "pgacw", "ngacw",
                       "paacw_adj", "naacw", "piacw", "niacw"),
                      controls.alpha_riming)
    return cold_out


def apply_freeze_controls(mf_d234, controls: Optional[ProcessControls],
                          qc: torch.Tensor, nc: torch.Tensor):
    """D2 contact + D3 Bigg-cloud freezing — applied BEFORE the inline commit.
    D4 (pfrzdtr/nfrzdtr) deliberately untouched (delta_brs coupling, v1).

    RESERVOIR CAP (Codex stop-review): the D2/D3 rates commit through
    apply_melt_freeze_inline_torch, which is clamp-free and OUTSIDE the group
    conservation limiters (those bound warm/cold/D5 only). The unscaled rates
    respect Fortran's own per-rate caps; exp(α)>1 can overdraw qc/nc, and the
    downstream final clamps would then CREATE mass (qc clipped at 0 while qi
    keeps the full transfer). So after scaling, renormalize the combined draw:
        pinuc + pfrzdtc ≤ qc,   ninuc + nfrzdtc ≤ nc
    (the rates here are per-substep AMOUNTS — the inline applier subtracts
    them directly). The renorm factor is differentiable (min via clamp)."""
    if controls is None or controls.alpha_freeze is None:
        return mf_d234
    scaled = _scale(mf_d234, ("pinuc", "ninuc", "pfrzdtc", "nfrzdtc"),
                    controls.alpha_freeze)
    # BUDGET = max(reservoir, UNSCALED combined draw): Fortran's D2/D3 caps are
    # INDEPENDENT (each ≤ qc), so the unscaled combined draw may legitimately
    # exceed qc — the bitwise-validated baseline path must not be "corrected"
    # by the control (adversarial review finding 1: a qc-only budget BINDS at
    # α=0, breaking the α=0 value-identity by ULPs). The cap therefore only
    # bounds the EXCESS the control itself introduces: at α=0 the ratio is
    # budget/draw ≥ 1 → fac ≡ 1.0 exactly (clamp max=1.0, ×1.0 exact).
    eps = 1.0e-30
    base_q = mf_d234.pinuc + mf_d234.pfrzdtc
    base_n = mf_d234.ninuc + mf_d234.nfrzdtc
    fac_q = torch.clamp(torch.maximum(qc, base_q)
                        / torch.clamp(scaled.pinuc + scaled.pfrzdtc, min=eps),
                        max=1.0)
    fac_n = torch.clamp(torch.maximum(nc, base_n)
                        / torch.clamp(scaled.ninuc + scaled.nfrzdtc, min=eps),
                        max=1.0)
    return scaled._replace(
        pinuc=scaled.pinuc * fac_q, pfrzdtc=scaled.pfrzdtc * fac_q,
        ninuc=scaled.ninuc * fac_n, nfrzdtc=scaled.nfrzdtc * fac_n,
    )


def apply_melt_controls(mf5, controls: Optional[ProcessControls]):
    """D5 enhanced melting — applied BEFORE scale_rates_for_conservation."""
    if controls is None:
        return mf5
    return _scale(mf5, ("pseml", "nseml", "pgeml", "ngeml"),
                  controls.alpha_melt)
