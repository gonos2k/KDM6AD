"""Focused checks for the opt-in normalized dry-number window map."""
from __future__ import annotations

import pytest
import torch

import kdm6.da_window as da_window
from kdm6.da_linearization import WindowLinearization
from kdm6.da_window import WindowConfig, collect_window_trajectory, run_da_window
from kdm6.runtime import Handle, _kdm6_pure, kdm6_step, make_parameters
from kdm6.sed_conservative import CONSERVATIVE_SED_FNS
from kdm6.state import Forcing, State, zeros_like_state


F64 = {"dtype": torch.float64}
DT = 20.0


def _state(qv=None):
    def t(a, b):
        return torch.tensor([[a, b]], **F64)

    return State(
        th=t(296.8, 282.4), qv=t(1.40e-2, 2.0e-3) if qv is None else qv,
        qc=t(1.0e-3, 5.0e-4), qr=t(1.0e-4, 1.0e-5),
        qi=t(0.0, 1.0e-6), qs=t(0.0, 5.0e-5), qg=t(0.0, 1.0e-5),
        nccn=t(1.0e9, 1.0e9), nc=t(1.0e8, 1.0e8),
        ni=t(0.0, 1.0e8), nr=t(1.0e4, 1.0e3), bg=t(0.0, 0.0),
    )


def _forcing():
    return Forcing(
        rho=torch.tensor([[1.089, 0.9567]], **F64),
        pii=torch.tensor([[0.9704, 0.9031]], **F64),
        p=torch.tensor([[9.0e4, 7.0e4]], **F64),
        delz=torch.tensor([[500.0, 500.0]], **F64),
    )


def _explicit_normalized_step(state, forcing, params, xland):
    return _kdm6_pure(
        state, forcing, params, DT, xland=xland,
        ncmin_land=10.0, ncmin_sea=10.0,
        dry_number=True, normalize_ice_handoff=True,
        sed_substep_fns=CONSERVATIVE_SED_FNS,
    )


def _terminal_nc_seed(state):
    return State(*(torch.ones_like(x) if name == "nc" else torch.zeros_like(x)
                   for name, x in zip(State._fields, state)))


def _assert_state_equal(a, b):
    for name, left, right in zip(State._fields, a, b):
        assert torch.equal(left, right), name


def test_normalized_dry_window_maps_match_two_step_pure_reference_and_fd():
    x0 = _state()
    forcings = [_forcing(), _forcing()]
    params = make_parameters()
    xland = torch.tensor([2.0], **F64)

    direct = [x0]
    for forcing in forcings:
        direct.append(_explicit_normalized_step(direct[-1], forcing, params, xland))

    one_step, handle = kdm6_step(
        x0, forcings[0], params, DT, xland=xland,
        ncmin_land=10.0, ncmin_sea=10.0, normalized_dry=True)
    _assert_state_equal(one_step, direct[1])
    _assert_state_equal(handle.func(x0, forcings[0], params, DT), direct[1])
    handle.close()

    config = WindowConfig(dt=DT, params=params, xland=xland,
                          ncmin_land=10.0, ncmin_sea=10.0,
                          normalized_dry=True)
    collected = collect_window_trajectory(x0, forcings, config, {0, 1, 2})
    for t in (0, 1, 2):
        _assert_state_equal(collected[t], direct[t])

    seed = _terminal_nc_seed(direct[-1])
    recomputed = run_da_window(x0, forcings, lambda t, _: seed if t == 2 else None,
                               config)
    _assert_state_equal(recomputed.state_final, direct[-1])

    with WindowLinearization(x0, forcings, dt=DT, params=params, xland=xland,
                             ncmin_land=10.0, ncmin_sea=10.0,
                             normalized_dry=True) as retained:
        _assert_state_equal(retained.state_final, direct[-1])
        retained_adj = retained.apply_adjoint({2: seed})
    _assert_state_equal(retained_adj, recomputed.adj_x0)

    direction = x0.qv * 0.01
    adj_directional = float((recomputed.adj_x0.qv * direction).sum())

    def direct_objective(offset):
        state = x0._replace(qv=x0.qv + offset * direction)
        for forcing in forcings:
            state = _explicit_normalized_step(state, forcing, params, xland)
        return float((state.nc * seed.nc).sum())

    h = 1.0e-4
    fd = (direct_objective(h) - direct_objective(-h)) / (2.0 * h)
    assert adj_directional != 0.0
    assert fd == pytest.approx(adj_directional, rel=2.0e-5, abs=1.0e-12)


def test_normalized_dry_is_opt_in_and_rejects_non_bool(monkeypatch):
    seen = []

    def legacy(*args, **kwargs):
        seen.append((args, kwargs))
        return args[0]

    monkeypatch.setattr("kdm6.runtime.kdm6_fn", legacy)
    state, handle = kdm6_step(_state(), _forcing(), dt=DT, value_only=True)
    handle.close()
    assert seen[-1][1] == {}
    assert len(seen[-1][0]) == 8  # the existing positional call boundary

    with pytest.raises(TypeError, match="normalized_dry must be a bool"):
        kdm6_step(state, _forcing(), dt=DT, value_only=True, normalized_dry=1)
    with pytest.raises(TypeError, match="normalized_dry must be a bool"):
        collect_window_trajectory(state, [_forcing()],
                                  WindowConfig(dt=DT, normalized_dry=1), {1})
    with pytest.raises(TypeError, match="normalized_dry must be a bool"):
        WindowLinearization(state, [_forcing()], dt=DT, normalized_dry=1)


def test_window_snapshots_normalized_dry_flag_for_forward_and_recompute(monkeypatch):
    config = WindowConfig(dt=DT, normalized_dry=True)
    observed = []

    def identity_step(state, forcing, params=None, dt=60.0, **kwargs):
        observed.append(kwargs.get("normalized_dry", False))
        return state, Handle(state_in=state, state_out=state, forcing=forcing,
                             params=params, dt=dt, func=lambda s, f, p, d: s,
                             value_only=kwargs.get("value_only", False))

    monkeypatch.setattr(da_window, "kdm6_step", identity_step)

    def obs(t, state):
        if t == 0:
            config.normalized_dry = False
        return zeros_like_state(state) if t == 2 else None

    run_da_window(_state(), [_forcing(), _forcing()], obs, config)
    assert observed == [True, True, True, True]
