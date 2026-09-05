"""Focused regressions for the PR208 DA-core fixes."""
from types import SimpleNamespace

import pytest
import torch

from kdm6.da_cvt import make_default_cvt
from kdm6.da_dual import (default_param_prior, make_dual_frozen_obs_eval,
                          run_dual_minimizer)
from kdm6.da_linearization import WindowLinearization
from kdm6.da_minimizer import run_minimizer
from kdm6.da_partition import PartitionSpec
from kdm6.da_window import WindowConfig, run_da_window
from kdm6.runtime import make_parameters
from kdm6.state import Forcing, State

F64 = {"dtype": torch.float64}


def _t2(a, b):
    return torch.tensor([[a, b]], **F64)


def _state():
    return State(
        th=_t2(296.8, 282.4), qv=_t2(.014, .002),
        qc=_t2(.001, .0005), qr=_t2(.0001, .00001),
        qi=_t2(.0002, 1.0e-6), qs=_t2(0.0, 5.0e-5),
        qg=_t2(0.0, 1.0e-5), nccn=_t2(1.0e9, 1.0e9),
        nc=_t2(1.0e8, 1.0e8), ni=_t2(0.0, 1.0e8),
        nr=_t2(1.0e4, 1.0e3), bg=_t2(0.0, 0.0))


def _forcing():
    return Forcing(rho=_t2(1.089, .9567), pii=_t2(.9704, .9031),
                   p=_t2(9.0e4, 7.0e4), delz=_t2(500.0, 500.0))


def _zeros(x):
    return State(*(torch.zeros_like(v) for v in x))


def test_review208_t0_active_projection_preserves_full_observation_pullback():
    x = _state()
    u = _zeros(x)._replace(th=torch.ones_like(x.th))
    result = run_da_window(
        x, [], lambda t, _: u if t == 0 else None,
        WindowConfig(dt=20.0, active_fields=("qv",)))
    assert torch.equal(result.adj_x0.th, torch.zeros_like(x.th))
    assert torch.equal(result.adj_x0.qv, torch.zeros_like(x.qv))

    # The output covector is not in the same subspace as the input control:
    # one real microphysics step has a nonzero qv pullback from a th output
    # covector.  Pre-projecting that output covector would erase this signal.
    propagated = run_da_window(
        x, [_forcing()], lambda t, _: u if t == 1 else None,
        WindowConfig(dt=20.0, active_fields=("qv",)))
    assert float(propagated.adj_x0.qv.abs().sum()) > 0.0
    assert torch.equal(propagated.adj_x0.th, torch.zeros_like(x.th))

    with WindowLinearization(x, [_forcing()], dt=20.0) as lin:
        retained = lin.apply_adjoint({0: u}, active_fields=("qv",))
    assert torch.equal(retained.th, torch.zeros_like(x.th))
    assert torch.equal(retained.qv, torch.zeros_like(x.qv))
    with WindowLinearization(x, [_forcing()], dt=20.0) as lin:
        retained_propagated = lin.apply_adjoint({1: u}, active_fields=("qv",))
    assert float(retained_propagated.qv.abs().sum()) > 0.0
    assert torch.equal(retained_propagated.th, torch.zeros_like(x.th))


def test_review208_partition_cvt_record_uses_diagonal_intermediate():
    x = _state()
    spec, sigma = make_default_cvt(
        x, sigma_overrides={"qc": 0.0, "qi": 0.0, "qs": 0.0,
                            "nc": 0.0, "ni": 0.0})
    target = x.qi + .0002

    def obs(t, xt):
        if t != 0:
            return None
        d = xt.qi - target
        return .5 * ((d / 1.0e-6) ** 2).sum(), _zeros(xt)._replace(
            qi=d / (1.0e-6 ** 2))

    result = run_minimizer(
        x, [], obs, WindowConfig(dt=20.0), sigma, max_iter=5, cvt=spec,
        partition=PartitionSpec(), partition_forcing=_forcing())
    assert result.partition["n_active"]["vap2ice"] > 0
    assert result.cvt["n_created"]["qi"] == 0
    assert result.cvt["ratio_minmax"]["qi"] == pytest.approx([1.0, 1.0])
    assert not torch.equal(result.x_analysis.qi, x.qi)


def test_review208_dual_partition_cvt_record_uses_diagonal_intermediate():
    x = _state()
    spec, sigma = make_default_cvt(
        x, sigma_overrides={"qc": 0.0, "qi": 0.0, "qs": 0.0,
                            "nc": 0.0, "ni": 0.0})
    result = run_dual_minimizer(
        x, [], lambda _t, _xt: None, WindowConfig(dt=20.0), sigma,
        default_param_prior(.2), max_iter=1, require_obs_slots=False,
        cvt=spec, partition=PartitionSpec(), partition_forcing=_forcing())
    assert result.partition is not None
    assert result.cvt["n_created"]["qi"] == 0
    assert result.cvt["ratio_minmax"]["qi"] == pytest.approx([1.0, 1.0])


def test_review208_mixed_solar_adapter_rejects_scalar_sigma():
    def run_k(_):
        raise AssertionError("mixed sigma validation must precede H evaluation")
    run_k.solar_channels = (1,)
    cfg = SimpleNamespace(
        run_k=run_k,
        profile_cfg=SimpleNamespace(),
        input_cfg=SimpleNamespace(channels=(7, 1, 8)),
        obs_sigma=1.0)
    x = _state()._replace(
        th=_t2(280.0, 280.0), qv=_t2(.005, .005),
        qc=_t2(0.0, 0.0), qr=_t2(0.0, 0.0), qi=_t2(0.0, 0.0),
        qs=_t2(0.0, 0.0), qg=_t2(0.0, 0.0), nccn=_t2(0.0, 0.0),
        nc=_t2(0.0, 0.0), ni=_t2(0.0, 0.0), nr=_t2(0.0, 0.0),
        bg=_t2(0.0, 0.0))
    with pytest.raises(ValueError, match="mixed solar.*per-channel"):
        make_dual_frozen_obs_eval(
            x, [], {}, cfg, WindowConfig(dt=0.0), default_param_prior(.2))


def test_review208_retained_linearization_rejects_nonintegral_and_bool_times():
    x = _state()
    u = _zeros(x)._replace(th=torch.ones_like(x.th))
    with WindowLinearization(x, [_forcing(), _forcing()], dt=20.0) as lin:
        # Integral string and scalar-tensor aliases remain accepted.
        ref = lin.apply_adjoint({1: u})
        via_str = lin.apply_adjoint({"1": u})
        via_tensor = lin.apply_adjoint({torch.tensor(1): u})
        for name in State._fields:
            assert torch.equal(getattr(via_str, name), getattr(ref, name))
            assert torch.equal(getattr(via_tensor, name), getattr(ref, name))
        with pytest.raises(ValueError, match="finite and exactly integral"):
            lin.apply_adjoint({1.9: u})
        with pytest.raises(TypeError, match="non-bool"):
            lin.apply_adjoint({True: u})
        with pytest.raises(ValueError, match="finite and exactly integral"):
            lin.apply_tangent(x, obs_times=[1.9])
        with pytest.raises(TypeError, match="non-bool"):
            lin.apply_tangent(x, obs_times=[True])
