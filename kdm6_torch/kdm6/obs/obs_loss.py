"""P6 -- observation-space loss (design 8; math kdm6ad+da.md §4/§9.1).

`compute_obs_loss` returns a **torch scalar J_obs**, differentiable in ``bt_hat``.
λ_BT = ∂J_obs/∂bt_hat is NOT an output — it is the autograd cotangent the callback
produces and feeds to `RttovObsOp.backward` (design 8; runK takes no seed).

Masking (design 8): only (profile, channel) with BOTH obs-quality and RTTOV
rad_quality == 0 enter the metric/gradient. The caller passes the combined
DETACHED 0/1 ``masks`` (obs_quality & rad_quality==0 & channel-gate); a clipped
cloudy radiance (rad_quality≠0) thus contributes exactly 0 to J_obs and λ_BT.
Bias correction is a detached static (or VarBC-frozen) per-channel offset applied
at residual definition, so ∂J/∂state is unaffected.

solar (VIS/NIR 6 channels) BT is reflectance, BT-residual undefined — IR 10
channels first, solar later (principle 6); the caller masks solar out.
"""
from __future__ import annotations

import math
from typing import NamedTuple

import torch


def _huber(x: torch.Tensor, delta: float) -> torch.Tensor:
    """Huber ψ_δ: quadratic within ±δ, linear outside (robust to outliers)."""
    ax = x.abs()
    return torch.where(ax <= delta, 0.5 * x * x, delta * (ax - 0.5 * delta))


def compute_obs_loss(bt_hat, obs, masks, sigma, *, delta: float = 1.0):
    """Masked Huber BT-residual loss -> torch scalar J_obs (differentiable in bt_hat).

    ``bt_hat`` [nprofiles, nchannels] (torch); ``obs`` dict with ``bt`` (same
    shape) and optional detached ``bias``; ``masks`` detached 0/1 [nprofiles,
    nchannels]; ``sigma`` obs error (scalar or per-channel). Returns
    ``Σ_{p,c} m·ψ_δ((bt_hat − (bt_obs+bias))/σ)``. ``bias``/``masks``/``sigma`` are
    detached/constant so λ_BT = ∂J/∂bt_hat = m·ψ_δ'(r)/σ is unaffected by them.
    """
    bt_obs = torch.as_tensor(obs["bt"], dtype=bt_hat.dtype, device=bt_hat.device).detach()
    bias = obs.get("bias")
    if bias is not None:
        bt_obs = bt_obs + torch.as_tensor(bias, dtype=bt_hat.dtype, device=bt_hat.device).detach()
    m = torch.as_tensor(masks, dtype=bt_hat.dtype, device=bt_hat.device).detach()
    sig = torch.as_tensor(sigma, dtype=bt_hat.dtype, device=bt_hat.device).detach()
    # obs error must be finite and strictly positive (a NaN survives clamp and poisons
    # the loss; a non-positive sigma is meaningless) -- reject-don't-drop.
    if not bool(torch.isfinite(sig).all()) or bool((sig <= 0.0).any()):
        raise ValueError("sigma (obs error) must be finite and > 0.")
    r = (bt_hat - bt_obs) / torch.clamp(sig, min=1.0e-12)
    # Masked positions (m==0) must contribute EXACTLY 0 -- and must not poison the
    # forward or backward with a non-finite residual there (0*NaN=NaN, and the 0*NaN
    # gradient too, §30 Inf×0 class). Zero the residual at masked positions (the local
    # d r/d bt_hat = 1/sigma stays finite, so backward is NaN-safe). Then any remaining
    # non-finite is in a KEPT channel -> a real bug (NaN simulated/observed BT) -> reject.
    r = torch.where(m > 0.0, r, torch.zeros_like(r))
    contrib = m * _huber(r, delta)
    if not bool(torch.isfinite(contrib).all()):
        raise ValueError(
            "non-finite obs-loss contribution in a kept channel -- bt_hat / obs['bt'] "
            "must be finite where the mask keeps them (reject-don't-drop).")
    return contrib.sum()


# --- Phase 3: symmetric cloud-amount observation error (all-sky IR) -----------

class SymmetricObsError(NamedTuple):
    """Okamoto-2014 symmetric cloud obs-error params (design: all-sky-ir-observation-
    error-symmetric). ``sigma`` ramps piecewise-linearly from ``sigma_clr`` to
    ``sigma_cld`` over the cloud-amount predictor CA in [``ca_clr``, ``ca_cld``]."""
    sigma_clr: float    # clear-sky obs-error SD
    sigma_cld: float    # cloudy obs-error SD (>= sigma_clr)
    ca_clr: float       # CA at/below which sigma = sigma_clr
    ca_cld: float       # CA at/above which sigma = sigma_cld


def symmetric_obs_error(bt_hat, bt_obs, bt_clear, model: SymmetricObsError):
    """Per-(profile, channel) obs-error SD from the SYMMETRIC cloud-amount predictor
    ``CA = (|B-Bclr| + |O-Bclr|)/2`` (Okamoto et al. 2014), a piecewise-linear ramp
    ``sigma_clr -> sigma_cld`` over ``[ca_clr, ca_cld]``.

    Returned DETACHED: the obs error is a WEIGHTING, not part of the forward operator.
    CA depends on B (=bt_hat); if sigma carried that dependence it would leak a ghost
    gradient into lambda_BT. ``Bclr`` is the clear-sky first-guess BT (detached).
    """
    if not all(math.isfinite(p) for p in
               (model.sigma_clr, model.sigma_cld, model.ca_clr, model.ca_cld)):
        raise ValueError(f"SymmetricObsError params must be finite: {model}.")
    if model.sigma_clr <= 0.0:
        raise ValueError(f"sigma_clr ({model.sigma_clr}) must be > 0.")
    if not (model.ca_cld > model.ca_clr):
        raise ValueError(f"ca_cld ({model.ca_cld}) must be > ca_clr ({model.ca_clr}).")
    if model.sigma_cld < model.sigma_clr:
        raise ValueError(
            f"sigma_cld ({model.sigma_cld}) must be >= sigma_clr ({model.sigma_clr}).")
    B = bt_hat.detach()
    O = torch.as_tensor(bt_obs, dtype=B.dtype, device=B.device).detach()
    Bclr = torch.as_tensor(bt_clear, dtype=B.dtype, device=B.device).detach()
    # CA is built from B and O too -- finite-guard all three (a NaN here yields a NaN
    # sigma that survives clamp and poisons even the IR channels via the loss sum).
    for _nm, _v in (("bt_hat", B), ("bt_obs", O), ("bt_clear", Bclr)):
        if not bool(torch.isfinite(_v).all()):
            raise ValueError(f"{_nm} has non-finite values -- invalid obs-error input.")
    ca = 0.5 * ((B - Bclr).abs() + (O - Bclr).abs())
    frac = ((ca - model.ca_clr) / (model.ca_cld - model.ca_clr)).clamp(0.0, 1.0)
    sigma = model.sigma_clr + (model.sigma_cld - model.sigma_clr) * frac
    return sigma.detach()


def ir_channel_gate(channels, solar_channels, *, dtype=torch.float64):
    """Keep-mask [1, nchannels] (1=keep) that masks the SOLAR (VIS/NIR) channels --
    IR-10ch first (solar reflectance residual is a later phase). ``channels`` is the
    1-based RTTOV channel list; ``solar_channels`` the subset to mask (AMI 1-6). Set
    as ``obs['channel_gate']`` -> multiplied into the design-8 keep-mask."""
    chan_set = set(int(c) for c in channels)
    solar = set(int(c) for c in solar_channels)
    unknown = solar - chan_set
    if unknown:
        # an unknown solar id silently leaves that channel UNMASKED (active) -- reject.
        raise ValueError(
            f"solar_channels {sorted(unknown)} are not in channels {sorted(chan_set)}; "
            "an unknown solar id would leave that channel unmasked (reject-don't-drop).")
    return torch.tensor([[0.0 if int(c) in solar else 1.0 for c in channels]], dtype=dtype)
