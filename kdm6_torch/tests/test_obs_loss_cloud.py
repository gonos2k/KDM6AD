"""Phase 3 (all-sky) -- symmetric cloud observation error + IR-10ch channel gate.

The symmetric cloud-amount obs error (Okamoto 2014): sigma ramps sigma_clr->sigma_cld
over CA=(|B-Bclr|+|O-Bclr|)/2. It is a DETACHED weighting (no ghost gradient into
lambda_BT). The IR gate masks the solar channels (IR-10ch first).
"""
import pytest
import torch

from kdm6.obs.obs_loss import (
    SymmetricObsError, symmetric_obs_error, ir_channel_gate, compute_obs_loss)

F64 = torch.float64
_MODEL = SymmetricObsError(sigma_clr=2.0, sigma_cld=20.0, ca_clr=1.0, ca_cld=30.0)


def _ca_to_bt_hat(ca, bt_clear):
    """bt_hat such that CA = 0.5*|B-Bclr| (with O==Bclr so |O-Bclr|=0) equals `ca`."""
    return bt_clear + 2.0 * torch.as_tensor(ca, dtype=F64)


def test_symmetric_error_ramp_monotone():
    bt_clear = torch.full((1, 5), 250.0, dtype=F64)
    bt_obs = bt_clear.clone()                              # |O-Bclr| = 0 -> CA = 0.5|B-Bclr|
    cas = torch.tensor([[0.0, 1.0, 15.5, 30.0, 100.0]], dtype=F64)   # below/at/mid/at/above
    bt_hat = bt_clear + 2.0 * cas
    sig = symmetric_obs_error(bt_hat, bt_obs, bt_clear, _MODEL)
    s = sig[0]
    assert float(s[0]) == pytest.approx(2.0)              # CA=0 <= ca_clr -> sigma_clr
    assert float(s[1]) == pytest.approx(2.0)              # CA=ca_clr -> sigma_clr
    assert float(s[3]) == pytest.approx(20.0)             # CA=ca_cld -> sigma_cld
    assert float(s[4]) == pytest.approx(20.0)             # CA>ca_cld -> sigma_cld
    assert 2.0 < float(s[2]) < 20.0                       # mid -> interior
    assert float(s[2]) == pytest.approx(2.0 + 18.0 * (15.5 - 1.0) / (30.0 - 1.0))
    assert bool((s[1:] >= s[:-1]).all())                  # monotone non-decreasing


def test_sigma_is_detached_no_ghost_gradient():
    """sigma(CA) depends on B=bt_hat, but is DETACHED: the loss gradient w.r.t. bt_hat
    must equal the static-sigma formula m·psi'(r)/sigma -- NO dsigma/dB ghost term."""
    bt_clear = torch.full((1, 3), 250.0, dtype=F64)
    bt_obs = torch.tensor([[248.0, 270.0, 200.0]], dtype=F64)
    bt_hat = torch.tensor([[251.0, 285.0, 240.0]], dtype=F64, requires_grad=True)
    sig = symmetric_obs_error(bt_hat, bt_obs, bt_clear, _MODEL)
    assert sig.requires_grad is False                     # detached weighting

    mask = torch.ones(1, 3, dtype=F64)
    loss = compute_obs_loss(bt_hat, {"bt": bt_obs}, mask, sig, delta=1.0)
    (g,) = torch.autograd.grad(loss, bt_hat)
    # analytic gradient with sigma treated as CONSTANT (Huber psi', delta=1)
    r = (bt_hat.detach() - bt_obs) / torch.clamp(sig, min=1.0e-12)
    psi = torch.where(r.abs() <= 1.0, r, torch.sign(r))
    g_expect = mask * psi / torch.clamp(sig, min=1.0e-12)
    assert torch.allclose(g, g_expect, rtol=1e-10, atol=1e-12)


def test_ca_sigma_downweights_cloudy_channel():
    """A high-CA (cloudy) channel gets a larger sigma -> smaller gradient magnitude
    than the same residual under the clear-sky sigma."""
    bt_clear = torch.tensor([[250.0, 250.0]], dtype=F64)
    bt_obs = torch.tensor([[250.0, 250.0]], dtype=F64)
    bt_hat = torch.tensor([[251.0, 300.0]], dtype=F64, requires_grad=True)   # ch1 clear, ch2 cloudy
    sig = symmetric_obs_error(bt_hat, bt_obs, bt_clear, _MODEL)
    assert float(sig[0, 1]) > float(sig[0, 0])            # cloudy channel: larger sigma
    loss = compute_obs_loss(bt_hat, {"bt": bt_obs}, torch.ones(1, 2, dtype=F64), sig, delta=1.0)
    (g,) = torch.autograd.grad(loss, bt_hat)
    # both residuals are large (linear Huber): |grad| = 1/sigma -> cloudy channel smaller.
    assert float(g[0, 1].abs()) < float(g[0, 0].abs())


def test_ir_channel_gate_masks_solar():
    gate = ir_channel_gate(channels=tuple(range(1, 17)), solar_channels=(1, 2, 3, 4, 5, 6))
    assert gate.shape == (1, 16)
    assert bool((gate[0, :6] == 0.0).all())              # solar masked
    assert bool((gate[0, 6:] == 1.0).all())              # IR kept


def test_symmetric_error_param_validation():
    bt = torch.zeros(1, 2, dtype=F64)
    with pytest.raises(ValueError, match="ca_cld"):
        symmetric_obs_error(bt, bt, bt, SymmetricObsError(2.0, 20.0, 5.0, 5.0))   # ca_cld == ca_clr
    with pytest.raises(ValueError, match="sigma_cld"):
        symmetric_obs_error(bt, bt, bt, SymmetricObsError(20.0, 2.0, 1.0, 30.0))  # sigma_cld < sigma_clr


def test_symmetric_error_rejects_nonfinite_bt_clear():
    bt = torch.zeros(1, 2, dtype=F64)
    bad = torch.tensor([[250.0, float("nan")]], dtype=F64)
    with pytest.raises(ValueError, match="bt_clear"):
        symmetric_obs_error(bt, bt, bad, _MODEL)


def test_symmetric_error_rejects_nonfinite_bt_hat_or_obs():
    """CA is built from B (bt_hat) and O (bt_obs) too -- a NaN there must be rejected,
    not turned into a NaN sigma that poisons even the IR channels via the loss sum."""
    ok = torch.zeros(1, 2, dtype=F64)
    nan = torch.tensor([[0.0, float("inf")]], dtype=F64)
    with pytest.raises(ValueError, match="bt_hat"):
        symmetric_obs_error(nan, ok, ok, _MODEL)
    with pytest.raises(ValueError, match="bt_obs"):
        symmetric_obs_error(ok, nan, ok, _MODEL)


def test_symmetric_error_rejects_nonpositive_or_nonfinite_sigma_params():
    bt = torch.zeros(1, 2, dtype=F64)
    with pytest.raises(ValueError, match="sigma_clr"):
        symmetric_obs_error(bt, bt, bt, SymmetricObsError(0.0, 20.0, 1.0, 30.0))   # sigma_clr=0
    with pytest.raises(ValueError, match="finite"):
        symmetric_obs_error(bt, bt, bt, SymmetricObsError(2.0, float("inf"), 1.0, 30.0))


def test_compute_obs_loss_rejects_bad_sigma():
    bt_hat = torch.zeros(1, 2, dtype=F64, requires_grad=True)
    obs = {"bt": torch.zeros(1, 2, dtype=F64)}
    mask = torch.ones(1, 2, dtype=F64)
    for bad in (0.0, -3.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="finite and > 0"):
            compute_obs_loss(bt_hat, obs, mask, bad)


def test_ir_channel_gate_rejects_unknown_solar():
    with pytest.raises(ValueError, match="not in channels"):
        ir_channel_gate(channels=(1, 2, 3, 4), solar_channels=(1, 99))   # 99 not a channel


def test_compute_obs_loss_rejects_nonfinite_kept_channel():
    """A NaN bt_hat in a KEPT channel poisons the loss -> reject (not silent NaN)."""
    bt_hat = torch.tensor([[250.0, float("nan")]], dtype=F64, requires_grad=True)
    obs = {"bt": torch.zeros(1, 2, dtype=F64)}
    mask = torch.ones(1, 2, dtype=F64)                 # both kept -> NaN in ch1 is a bug
    with pytest.raises(ValueError, match="kept channel"):
        compute_obs_loss(bt_hat, obs, mask, 5.0)


def test_compute_obs_loss_masked_nan_is_safe():
    """A non-finite value in a MASKED channel (m=0, e.g. a solar fill) must contribute
    EXACTLY 0 -- NaN-safe in both forward and backward (0*NaN=NaN otherwise)."""
    bt_hat = torch.tensor([[250.0, float("nan")]], dtype=F64, requires_grad=True)
    obs = {"bt": torch.tensor([[248.0, float("nan")]], dtype=F64)}
    mask = torch.tensor([[1.0, 0.0]], dtype=F64)        # ch1 masked out
    loss = compute_obs_loss(bt_hat, obs, mask, 5.0)
    assert torch.isfinite(loss)                         # forward NaN-safe
    (g,) = torch.autograd.grad(loss, bt_hat)
    assert torch.isfinite(g).all()                      # backward NaN-safe
    assert float(g[0, 1]) == 0.0                        # masked channel: zero gradient
