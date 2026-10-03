"""Dry-specific moments in the fixed-density optical adapter, not RTTOV runs."""
import pytest
import torch

from harness.replay_supported_native_nccn import parse_trace
from kdm6 import coordinator as coord
from kdm6.runtime import _state_to_coord, _build_coord_forcing
from kdm6.rttov_bridge import dsd_diagnostics, rttov_cloud_profile
from kdm6.obs.model_profile_builder import (
    RttovProfileConfig, model_to_rttov_tensors, with_dry_air_density,
)
from kdm6.state import State, Forcing


def native_input():
    arrays = parse_trace()["arrays"]
    state = State(*(torch.tensor(x, dtype=torch.float64)[None, :]
                    for x in arrays["STATE_IN"]))
    forcing = Forcing(*(torch.tensor(x, dtype=torch.float64)[None, :]
                        for x in arrays["FORCING"]))
    return state, forcing, forcing.rho / (1 + state.qv)


def test_native_dry_slopes_use_the_same_physical_moments():
    state, forcing, rho = native_input()
    volume = state._replace(nc=rho*state.nc, ni=rho*state.ni, nr=rho*state.nr)
    cf = _build_coord_forcing(forcing)._replace(dend=rho)
    pre = coord.preamble_torch(
        _state_to_coord(volume, forcing), cf, torch.ones_like(state.qc, dtype=torch.bool),
        params=coord.default_coordinator_params(), ncmin_tensor=torch.full_like(rho, 10),
    )
    kw = dict(xland=torch.tensor([2.]), ncmin_land=10, ncmin_sea=10, rho_d=rho)
    dry = dsd_diagnostics(state, forcing, **kw, dry_number=True)
    legacy = dsd_diagnostics(state, forcing, **kw)
    for actual, expected in ((dry.rslope_c, pre.rslopec),
                             (dry.rslope_i, pre.slope.rslope_i),
                             (dry.rslope_r, pre.slope.rslope_r)):
        assert torch.equal(actual, expected)
    active_ice = state.qi > 1e-15
    assert int(active_ice.sum()) == 9
    assert int(((dry.rslope_i != legacy.rslope_i) & active_ice).sum()) == 8
    assert torch.equal(dry.wc_i, rho * state.qi)
    # Scaling both volume moments changes their totals, not mean particle mass.
    scaled = dsd_diagnostics(state, forcing, **dict(kw, rho_d=.75*rho), dry_number=True)
    torch.testing.assert_close(dry.rslope_i, scaled.rslope_i, rtol=1e-14, atol=0)


def test_dry_ice_size_keeps_number_tangent_with_frozen_air_measure():
    state, forcing, rho = native_input()
    direction = torch.linspace(.7, 1.3, 39, dtype=torch.float64)[None, :] * state.ni
    def size(ni):
        return dsd_diagnostics(state._replace(ni=ni), forcing,
                               rho_d=rho, dry_number=True).rslope_i
    value, jv = torch.func.jvp(size, (state.ni,), (direction,))
    h = 1e-4
    fd = (size(state.ni+h*direction)-size(state.ni-h*direction))/(2*h)
    assert torch.isfinite(value).all() and torch.isfinite(jv).all()
    assert torch.count_nonzero(jv) > 0
    torch.testing.assert_close(jv, fd, rtol=1e-7, atol=1e-15)
    seed = torch.linspace(-.5, .8, 39, dtype=torch.float64)[None, :]
    _, pullback = torch.func.vjp(size, state.ni)
    (adj,) = pullback(seed)
    torch.testing.assert_close((seed*jv).sum(), (adj*direction).sum(), rtol=1e-12, atol=1e-20)


def test_profile_config_preserves_dry_basis_when_density_is_selected():
    state, forcing, rho = native_input()
    column = State(*(x.squeeze(0) for x in state))
    fcol = Forcing(*(x.squeeze(0) for x in forcing))
    cfg = RttovProfileConfig(2, "mixing_ratio_kgkg_dry", cloud=True, dry_number=True)
    cfg = with_dry_air_density(cfg, rho.squeeze(0))
    assert cfg.dry_number is True
    # Native data here are bottom-up. The observation builder requires top-down.
    column = State(*(x.flip(0) for x in column))
    fcol = Forcing(*(x.flip(0) for x in fcol))
    cfg = with_dry_air_density(cfg, cfg.rho_d.flip(0))
    profile = model_to_rttov_tensors(column, fcol, cfg)
    cp = rttov_cloud_profile(State(*(x[None, :] for x in column)),
                             Forcing(*(x[None, :] for x in fcol)),
                             rho_d=cfg.rho_d[None, :], dry_number=True)
    assert torch.equal(profile.clw, cp.clw.squeeze(0))
    # Keep native snow in the existing qi+qs optical blend.
    assert torch.count_nonzero(column.qs) > 0
    assert torch.isfinite(profile.deff_ice).all()
    legacy = model_to_rttov_tensors(column, fcol, cfg._replace(dry_number=False))
    assert torch.equal(profile.ciw, legacy.ciw)
    assert torch.any(profile.deff_ice != legacy.deff_ice)


def test_dry_basis_rejects_implicit_or_live_observation_density():
    state, forcing, rho = native_input()
    with pytest.raises(ValueError, match="rho_d is required"):
        dsd_diagnostics(state, forcing, dry_number=True)
    with pytest.raises(ValueError, match="frozen"):
        dsd_diagnostics(state, forcing, rho_d=rho.requires_grad_(), dry_number=True)
