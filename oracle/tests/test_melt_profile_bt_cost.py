"""Synthetic melt -> profile -> fixed-K BT -> cost first-order closure.

This is a portable fixed-K regression.  It exercises the supported
``RttovObsOp`` bridge for reverse AD and independent FD, while the forward AD
path traverses the same analytic fixed-K contraction in torch because the
custom bridge intentionally exposes backward K^T only.  It does not claim
live RTTOV execution or dK/dx.
"""
from __future__ import annotations

import numpy as np
import torch

from kdm6.obs.model_profile_builder import RttovProfileConfig, model_to_rttov_tensors
from kdm6.obs.obs_loss import compute_obs_loss
from kdm6.obs.rttov_input_builder import RttovInputConfig
from kdm6.obs.rttov_obs_operator import RttovObsOp
from kdm6.process_attribution import melt_fixture
from kdm6.process_controls import ProcessControls
from kdm6.runtime import kdm6_step, make_parameters
from kdm6.sensitivity_diagnostics import SensitivityTrace
from kdm6.state import Forcing, State


F64 = torch.float64
DT = 20.0
FD_EPSILONS = (1.0e-4, 1.0e-3)
CHANNELS = (1, 2, 3)
K_T = np.array([0.10, 0.20, 0.30], dtype=np.float64)
K_Q = np.array([1.0e-4, 2.0e-4, 3.0e-4], dtype=np.float64)


def _column(state: State) -> State:
    return State(*(getattr(state, name).squeeze(0) for name in State._fields))


def _column_forcing(forcing: Forcing) -> Forcing:
    return Forcing(*(getattr(forcing, name).squeeze(0)
                     for name in Forcing._fields))


def _fixed_run_k(rttov_input):
    t = rttov_input.profile["T"]
    q = rttov_input.profile["Q"]
    nprofiles, nlayers = t.shape
    bt = (K_T[None, :] * t.sum(axis=1)[:, None]
          + K_Q[None, :] * q.sum(axis=1)[:, None])
    kt = np.broadcast_to(K_T[None, :, None],
                         (nprofiles, len(CHANNELS), nlayers)).copy()
    kq = np.broadcast_to(K_Q[None, :, None],
                         (nprofiles, len(CHANNELS), nlayers)).copy()
    quality = np.zeros((nprofiles, len(CHANNELS)), dtype=np.int64)
    return bt, {"T": kt, "Q": kq}, quality


def _profile(state: State, forcing: Forcing, cfg: RttovProfileConfig):
    return model_to_rttov_tensors(_column(state), _column_forcing(forcing), cfg)


def _fixed_bt(profile):
    ts = profile.t_lay.sum()
    qs = profile.q_lay.sum()
    return torch.stack([K_T[c] * ts + K_Q[c] * qs
                        for c in range(len(CHANNELS))]).reshape(1, -1)


def _bridge_bt(profile, input_cfg):
    return RttovObsOp.apply(
        _fixed_run_k, input_cfg, profile.t_lay, profile.q_lay,
        profile.p_lay, profile.p_half,
    )[0]


def _cost(bt, bt_obs):
    return compute_obs_loss(
        bt, {"bt": bt_obs, "obs_quality": torch.zeros_like(bt)},
        torch.ones_like(bt), sigma=2.0,
    )


def _run_control(state, forcing, alpha, *, graph):
    trace = SensitivityTrace()
    output, handle = kdm6_step(
        state, forcing, make_parameters(), DT,
        value_only=not graph,
        controls=ProcessControls(alpha_melt=alpha),
        diagnostic_trace=trace,
    )
    return output, trace, handle


def _assert_trace_equal(reference: SensitivityTrace, candidate: SensitivityTrace):
    assert reference.subcycles == candidate.subcycles
    assert len(reference.records) == len(candidate.records)
    for expected, actual in zip(reference.records, candidate.records):
        assert (expected.step, expected.name, expected.dtcld) == (
            actual.step, actual.name, actual.dtcld)
        if expected.branch is None or actual.branch is None:
            assert expected.branch is None and actual.branch is None
        else:
            assert torch.equal(
                expected.branch.detach().to(torch.bool),
                actual.branch.detach().to(torch.bool),
            )


def test_melt_profile_fixed_k_cost_forward_reverse_fd():
    """D5 melt reaches fixed-K cost with matching first-order products."""
    state, forcing = melt_fixture()
    profile_cfg = RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry", cloud=False,
    )
    # This bounded fixture deliberately validates the clear-sky T/Q profile only;
    # it makes no claim about live RTTOV cloud-hydrometeor K fields.
    input_cfg = RttovInputConfig(coef_id="synthetic-fixed-k", channels=CHANNELS)

    # Reverse AD uses the supported K^T bridge.
    alpha = torch.tensor(0.0, dtype=F64, requires_grad=True)
    reverse_state, reverse_trace, reverse_handle = _run_control(
        state, forcing, alpha, graph=True)
    reverse_profile = _profile(reverse_state, forcing, profile_cfg)
    reverse_bt = _bridge_bt(reverse_profile, input_cfg)
    bt_obs = (reverse_bt.detach() + 1.0)
    reverse_cost = _cost(reverse_bt, bt_obs)
    vjp = torch.autograd.grad(reverse_cost, alpha)[0]
    reverse_handle.close()

    # Forward AD traverses KDM and the pure-torch profile/fixed-K contraction.
    from torch.autograd import forward_ad
    with forward_ad.dual_level():
        alpha_dual = forward_ad.make_dual(
            torch.tensor(0.0, dtype=F64), torch.tensor(1.0, dtype=F64))
        forward_state_dual, forward_trace, forward_handle = _run_control(
            state, forcing, alpha_dual, graph=False)
        forward_profile_dual = _profile(forward_state_dual, forcing, profile_cfg)
        forward_cost_dual = _cost(_fixed_bt(forward_profile_dual), bt_obs)
        forward_cost, jvp = forward_ad.unpack_dual(forward_cost_dual)
        forward_state = State(*(
            forward_ad.unpack_dual(getattr(forward_state_dual, name))[0]
            for name in State._fields
        ))
        forward_profile = _profile(forward_state, forcing, profile_cfg)
        forward_handle.close()

    # The two first-order routes must start from the same executed primal.
    for name in State._fields:
        assert torch.equal(getattr(reverse_state, name), getattr(forward_state, name))
    for name in ("t_lay", "q_lay"):
        assert torch.equal(getattr(reverse_profile, name),
                           getattr(forward_profile, name))
    assert torch.equal(reverse_bt, _fixed_bt(forward_profile))
    assert torch.equal(reverse_cost, forward_cost)
    assert reverse_trace.records and reverse_trace.subcycles
    d5_records = reverse_trace.by_name("d5_limited")
    assert d5_records
    # This is the executed d5_limited record at alpha=0 (controlled scope),
    # not an isolated raw-rate attribution outside the coordinator stage.
    d5_melt_signal = [
        getattr(record.rates, name)
        for record in d5_records for name in ("pseml", "pgeml")
    ]
    assert all(bool(torch.isfinite(value).all()) for value in d5_melt_signal)
    assert any(bool(value.abs().sum() > 0.0) for value in d5_melt_signal)
    _assert_trace_equal(reverse_trace, forward_trace)

    # Independent central FD uses fresh value-only KDM runs and the bridge BT.
    fd_results = []
    for epsilon in FD_EPSILONS:
        fd_costs = []
        fd_traces = []
        for signed_epsilon in (epsilon, -epsilon):
            fd_state, fd_trace, fd_handle = _run_control(
                state, forcing, torch.tensor(signed_epsilon, dtype=F64), graph=False)
            fd_profile = _profile(fd_state, forcing, profile_cfg)
            fd_costs.append(float(_cost(
                _bridge_bt(fd_profile, input_cfg), bt_obs).detach().item()))
            fd_traces.append(fd_trace)
            fd_handle.close()
        _assert_trace_equal(reverse_trace, fd_traces[0])
        _assert_trace_equal(reverse_trace, fd_traces[1])
        fd = (fd_costs[0] - fd_costs[1]) / (2.0 * epsilon)
        inf = torch.tensor(float("inf"), dtype=F64)
        spacing = max(
            abs(float((torch.nextafter(torch.tensor(cost, dtype=F64), inf)
                       - torch.tensor(cost, dtype=F64)).item()))
            for cost in fd_costs
        )
        fd_results.append((fd, spacing / (2.0 * epsilon)))

    for value in (reverse_cost, forward_cost, vjp, jvp):
        assert bool(torch.isfinite(value).all())
    for name in ("t_lay", "q_lay"):
        assert bool(torch.isfinite(getattr(reverse_profile, name)).all())
    assert bool(torch.isfinite(reverse_bt).all())
    assert all(np.isfinite(fd) for fd, _ in fd_results)
    reverse_cost_value = float(reverse_cost.detach())
    vjp_value = float(vjp.detach())
    jvp_value = float(jvp.detach())
    assert abs(reverse_cost_value) > 0.0
    max_fd_ulp_bound = max(bound for _, bound in fd_results)
    assert abs(vjp_value) > max_fd_ulp_bound
    assert abs(jvp_value) > max_fd_ulp_bound
    assert abs(jvp_value - vjp_value) <= 1.0e-10 * max(abs(vjp_value), 1.0e-30)
    for fd, fd_ulp_bound in fd_results:
        assert abs(fd) > fd_ulp_bound
        assert abs(fd - vjp_value) <= 1.0e-5 * abs(vjp_value)
