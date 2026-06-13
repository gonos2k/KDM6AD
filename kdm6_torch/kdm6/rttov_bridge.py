"""[DA §9.3] KDM6AD DSD/optical bridge — KDM6AD-consistent diagnostics for the
RTTOV cloudy-radiance adjoint chain.

    KDM6AD hydrometeor state (q*, n*, bg)
      -> KDM6AD-consistent DSD diagnostics (rslope/lamda/Reff/contents)
      -> RTTOV cloud/scattering profile variables
      [-> RTTOV-K ... handled on the AD-RTTOV side]

CONSISTENCY CONSTRAINT (design §9.3, option 1 — the recommended route): this
bridge NEVER re-derives (q,n) -> lamda/Reff with its own constants or
evaluation forms. The slopes come from the SAME functions the scheme itself
runs — ``preamble_torch`` (which internally uses the f32-stepwise pidnc/pidni,
the exp(log(·)·f32(1/dm)) lamda evaluation form, and the lamda bounds of the
bitwise-validated port). The effective radii are the scheme's OWN
radiation coupling — a 1:1 port of ``effectRad_kdm6`` (module_mp_kdm6.F:4042,
"entirely consistent with microphysics assumptions"), NOT a naive standard-
gamma M3/(2·M2) ratio: the KDM6 cloud DSD is a Cohard-Pinty GENERALIZED gamma
(adversarial review F2 — the naive (μ+3)/2 prefactor overestimated cloud Reff
by 4.5×). Rain has no effectRad entry; the §9.3 "rain Dm" proxy is the
scheme's own ``avedia_r``. The graupel density proxy is the rime-mass
fraction brs/qg.

Differentiability: the operator is pure tensor ops on the scheme's
AD-validated preamble — VJP/JVP compose through ``torch.autograd`` (the bridge
adds no custom autograd Functions). The independent §9.3 gates live in
tests/test_rttov_bridge.py (consistency, FD, adjoint inner-product).

The fp64 oracle path is the DA target (§0.1.A); feed fp64 states.
"""
from __future__ import annotations

from typing import NamedTuple

import math as _math

import torch

from . import constants as c
from . import coordinator as _coord
from .runtime import _state_to_coord, _build_coord_forcing
from .state import State, Forcing


class DsdDiagnostics(NamedTuple):
    """Per-category DSD diagnostics, scheme-consistent (SI units)."""
    # slopes (rslope = 1/lamda, scheme-clamped) [m]
    rslope_c: torch.Tensor
    rslope_r: torch.Tensor
    rslope_s: torch.Tensor
    rslope_g: torch.Tensor
    rslope_i: torch.Tensor
    # radiation effective radii — the SCHEME'S OWN effectRad_kdm6 formulas
    # (module_mp_kdm6.F:4042-4144), incl. its radiation clamps [m]:
    #   re_c = rslopec·Γ(3/(μc+1)+1)/(2Γ(2/(μc+1)+1))  (Cohard-Pinty
    #          GENERALIZED gamma — NOT the standard (μ+3)/2 moment ratio;
    #          the naive 2.5× was a 4.5× overestimate, adversarial-review F2)
    #   re_i = rslope_i·Γ(3+μi)/(2Γ(4+μi))
    #   re_s = 0.5·rslope_s
    reff_c: torch.Tensor
    reff_s: torch.Tensor
    reff_i: torch.Tensor
    # scheme's own mean-volume diameters (preamble diagnostics) [m]
    # avedia_r doubles as the §9.3 "rain Dm" proxy (λ_nr carrier).
    avedia_c: torch.Tensor
    avedia_r: torch.Tensor
    # graupel density proxy: rime-mass fraction brs/qg (λ_bg carrier, §9.3);
    # 0 (with zero adjoint) where qg ≤ 1e-15 — inactive-graupel gate
    graupel_rime_frac: torch.Tensor
    # water contents rho·q [kg/m^3]
    wc_c: torch.Tensor
    wc_r: torch.Tensor
    wc_s: torch.Tensor
    wc_g: torch.Tensor
    wc_i: torch.Tensor


class RttovCloudProfile(NamedTuple):
    """RTTOV all-sky cloud profile variables (GK2A AMI = unified VIS/IR scatt --
    NOT MW RTTOV-SCATT; design core-claim #6 / §9.1).

    Contents in [g/m^3] (RTTOV hydrotable convention), effective radii in
    [micron]. Category mapping (design §9.3 example):
        qc+nc -> clw + reff_liq;  qi+ni -> ciw + reff_ice;
        qr+nr -> rain;  qs -> snow;  qg(+bg) -> graupel.
    """
    clw: torch.Tensor        # cloud liquid water content [g/m^3]
    ciw: torch.Tensor        # cloud ice water content [g/m^3]
    rain: torch.Tensor       # rain water content [g/m^3]
    snow: torch.Tensor       # snow water content [g/m^3]
    graupel: torch.Tensor    # graupel water content [g/m^3]
    reff_liq: torch.Tensor   # liquid effective radius [micron] (effectRad_kdm6)
    reff_ice: torch.Tensor   # ice effective radius [micron] (effectRad_kdm6)
    reff_snow: torch.Tensor  # snow effective radius [micron] (effectRad_kdm6)
    rain_dm: torch.Tensor    # rain mean-volume diameter avedia_r [micron] — §9.3
                             # "rain Dm" proxy; carries the λ_nr adjoint
    graupel_rime_frac: torch.Tensor  # brs/qg [—] — §9.3 graupel density proxy;
                             # carries the λ_bg adjoint


def _sea_mask_from_xland(xland, ref: torch.Tensor) -> torch.Tensor:
    if xland is None:
        return torch.ones_like(ref, dtype=torch.bool)
    return (xland.view(-1, 1) >= 1.5).expand_as(ref)


def dsd_diagnostics(state: State, forcing: Forcing,
                    xland: "torch.Tensor | None" = None,
                    ncmin_land: float = 0.0,
                    ncmin_sea: float = 0.0) -> DsdDiagnostics:
    """Compute the scheme-consistent DSD diagnostics by RUNNING the scheme's
    own preamble (slopes, avedia) on the given state — no re-derivation.

    xland/ncmin_land/ncmin_sea must MATCH what the forward step was given:
    the per-cell ncmin feeds the cloud-slope inactive gate inside the
    preamble (1:1 fix #18), so omitting it would make the bridge's rslopec
    diverge from the scheme's own on land cells (Codex stop-review)."""
    cs = _state_to_coord(state, forcing)
    cf = _build_coord_forcing(forcing)
    sea_mask = _sea_mask_from_xland(xland, cs.qc)
    if xland is not None:
        # EXACT mirror of runtime._kdm6_pure's per-cell ncmin construction
        ncmin_tensor = torch.clamp(
            torch.where(sea_mask, torch.full_like(cs.qc, ncmin_sea),
                        torch.full_like(cs.qc, ncmin_land)),
            min=c.NCMIN)
    else:
        ncmin_tensor = None   # scalar c.NCMIN fallback — same as the runtime
    pre = _coord.preamble_torch(cs, cf, sea_mask,
                                params=_coord.default_coordinator_params(),
                                ncmin_tensor=ncmin_tensor)

    rslope_c = pre.rslopec
    rslope_r = pre.slope.rslope_r
    rslope_s = pre.slope.rslope_s
    rslope_g = pre.slope.rslope_g
    rslope_i = pre.slope.rslope_i

    # effectRad_kdm6 (F:4117-4143): re = prefactor · rslope, then the scheme's
    # radiation clamps. Γ ratios are exact fp64 here (the Fortran init computes
    # them once via its f32 rgmma; the DA path is fp64 — documented deviation,
    # constants only, ~1e-7 rel). If a fully f32-stepwise BITWISE bridge ever
    # becomes a goal, swap these for the port's rgmma mirror (fconst/_RgmmaF32
    # family) evaluated at f32 — the four prefactors are compile-time constants,
    # so the change is local to this block.
    #   cloud: lamco = lamc·2·Γ(2/(μc+1)+1)/Γ(3/(μc+1)+1); re = 1/lamco
    #   ice:   lamio = lami·2·Γ(4+μi)/Γ(3+μi);            re = 1/lamio
    #   snow:  re = 0.5/lamdas
    cdm2 = _math.gamma(2.0 / (c.MUC + 1.0) + 1.0)
    cdm3 = _math.gamma(3.0 / (c.MUC + 1.0) + 1.0)
    idm3 = _math.gamma(3.0 + c.MUI)
    idm4 = _math.gamma(4.0 + c.MUI)
    reff_c = torch.clamp(rslope_c * (cdm3 / (2.0 * cdm2)),
                         min=2.51e-6, max=50.0e-6)
    reff_i = torch.clamp(rslope_i * (idm3 / (2.0 * idm4)),
                         min=10.01e-6, max=125.0e-6)
    reff_s = torch.clamp(0.5 * rslope_s, min=25.0e-6, max=999.0e-6)

    # Rime fraction is meaningful only where graupel is ACTIVE. (qg→0, bg>0)
    # is reachable at the DA boundary (bg is prognostic; analysis increments
    # need not keep the qg/bg pair coupled) and the bare ratio would return
    # ~bg/1e-15 garbage with an explosive ∂/∂bg = 1e15 adjoint. Gate to 0 with
    # a zero adjoint — no graupel, no optical signal (Codex review finding 2).
    # The clamp inside keeps the inactive branch finite, so torch.where's
    # both-branch backward stays NaN-free (§30 Inf×0 class).
    qg_active = state.qg > 1.0e-15
    graupel_rime_frac = torch.where(
        qg_active, state.bg / torch.clamp(state.qg, min=1.0e-15),
        torch.zeros_like(state.qg))

    return DsdDiagnostics(
        rslope_c=rslope_c, rslope_r=rslope_r, rslope_s=rslope_s,
        rslope_g=rslope_g, rslope_i=rslope_i,
        reff_c=reff_c, reff_s=reff_s, reff_i=reff_i,
        avedia_c=pre.avedia_c, avedia_r=pre.avedia_r,
        graupel_rime_frac=graupel_rime_frac,
        wc_c=forcing.rho * state.qc, wc_r=forcing.rho * state.qr,
        wc_s=forcing.rho * state.qs, wc_g=forcing.rho * state.qg,
        wc_i=forcing.rho * state.qi,
    )


def rttov_cloud_profile(state: State, forcing: Forcing,
                        xland: "torch.Tensor | None" = None,
                        ncmin_land: float = 0.0,
                        ncmin_sea: float = 0.0) -> RttovCloudProfile:
    """Map the DSD diagnostics onto RTTOV VIS/IR all-sky cloud profile variables.

    Pure tensor ops — the RTTOV-K adjoint composes with this operator's VJP
    via torch.autograd (chain: lambda_BT -> RTTOV-K -> lambda_profile ->
    THIS operator's VJP -> lambda_{q*,n*} -> Handle.vjp; design §9.3)."""
    d = dsd_diagnostics(state, forcing, xland, ncmin_land, ncmin_sea)
    KG2G = 1.0e3      # kg/m^3 -> g/m^3
    M2UM = 1.0e6      # m -> micron
    return RttovCloudProfile(
        clw=d.wc_c * KG2G, ciw=d.wc_i * KG2G, rain=d.wc_r * KG2G,
        snow=d.wc_s * KG2G, graupel=d.wc_g * KG2G,
        reff_liq=d.reff_c * M2UM, reff_ice=d.reff_i * M2UM,
        reff_snow=d.reff_s * M2UM,
        rain_dm=d.avedia_r * M2UM,
        graupel_rime_frac=d.graupel_rime_frac,
    )
