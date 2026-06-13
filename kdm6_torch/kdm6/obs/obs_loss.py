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
    r = (bt_hat - bt_obs) / torch.clamp(sig, min=1.0e-12)
    return (m * _huber(r, delta)).sum()
