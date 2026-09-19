"""Synthetic melt -> profile -> fixed-K BT -> cost first-order closure.

This is a portable fixed-K regression.  It exercises the supported
``RttovObsOp`` bridge for reverse AD and independent FD, while the forward AD
path traverses the same analytic fixed-K contraction in torch because the
custom bridge intentionally exposes backward K^T only.  It does not claim
live RTTOV execution or dK/dx.
"""
from __future__ import annotations

import numpy as np
import pytest
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
# The original selected scalar test retains both perturbations below.
# Asymmetric channel FD at 1e-4 is endpoint-roundoff limited, so its
# channelwise regression uses two fixed resolved perturbations instead.
ASYM_FD_EPSILONS = (1.0e-3, 3.0e-3)
FD_EPSILONS = (1.0e-4, 1.0e-3)
CHANNELS = (1, 2, 3)
K_T = np.array([0.10, 0.20, 0.30], dtype=np.float64)
K_Q = np.array([1.0e-4, 2.0e-4, 3.0e-4], dtype=np.float64)
ASYM_K_T = np.array([0.07, -0.13, 0.29], dtype=np.float64)
ASYM_K_Q = np.array([2.0e-4, -3.0e-4, 7.0e-4], dtype=np.float64)
ASYM_RESIDUAL_OFFSETS = torch.tensor([[0.8, -1.0, 0.6]], dtype=F64)
FD_REL_TOL = 1.0e-5


def _column(state: State) -> State:
    return State(*(getattr(state, name).squeeze(0) for name in State._fields))


def _column_forcing(forcing: Forcing) -> Forcing:
    return Forcing(*(getattr(forcing, name).squeeze(0)
                     for name in Forcing._fields))


def _fixed_run_k(rttov_input, k_t=K_T, k_q=K_Q):
    t = rttov_input.profile["T"]
    q = rttov_input.profile["Q"]
    nprofiles, nlayers = t.shape
    bt = (k_t[None, :] * t.sum(axis=1)[:, None]
          + k_q[None, :] * q.sum(axis=1)[:, None])
    kt = np.broadcast_to(k_t[None, :, None],
                         (nprofiles, len(CHANNELS), nlayers)).copy()
    kq = np.broadcast_to(k_q[None, :, None],
                         (nprofiles, len(CHANNELS), nlayers)).copy()
    quality = np.zeros((nprofiles, len(CHANNELS)), dtype=np.int64)
    return bt, {"T": kt, "Q": kq}, quality


def _asymmetric_run_k(rttov_input):
    return _fixed_run_k(rttov_input, ASYM_K_T, ASYM_K_Q)


def _permuted_asymmetric_run_k(rttov_input):
    bt, k, quality = _asymmetric_run_k(rttov_input)
    # Keep forward BT unchanged while swapping K rows, which should corrupt
    # channelwise reverse products and scalar cost adjoints.
    permutation = np.array([1, 0, 2])
    return bt, {name: value[:, permutation, :] for name, value in k.items()}, quality


def _profile(state: State, forcing: Forcing, cfg: RttovProfileConfig):
    return model_to_rttov_tensors(_column(state), _column_forcing(forcing), cfg)


def _fixed_bt(profile, k_t=K_T, k_q=K_Q):
    ts = profile.t_lay.sum()
    qs = profile.q_lay.sum()
    return torch.stack([k_t[c] * ts + k_q[c] * qs
                        for c in range(len(CHANNELS))]).reshape(1, -1)


def _bridge_bt(profile, input_cfg, run_k=_fixed_run_k):
    return RttovObsOp.apply(
        run_k, input_cfg, profile.t_lay, profile.q_lay,
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


def test_asymmetric_fixed_k_channels_and_cost_reject_k_row_permutation():
    """Unequal signed residuals expose channelwise K-row permutations."""
    state, forcing = melt_fixture()
    profile_cfg = RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry", cloud=False,
    )
    input_cfg = RttovInputConfig(coef_id="synthetic-asymmetric-fixed-k",
                                 channels=CHANNELS)
    assert np.linalg.matrix_rank(
        np.column_stack((ASYM_K_T, ASYM_K_Q))) == 2

    alpha = torch.tensor(0.0, dtype=F64, requires_grad=True)
    reverse_state, reverse_trace, reverse_handle = _run_control(
        state, forcing, alpha, graph=True)
    reverse_profile = _profile(reverse_state, forcing, profile_cfg)
    reverse_bt = _bridge_bt(reverse_profile, input_cfg, _asymmetric_run_k)
    bt_obs = reverse_bt.detach() + ASYM_RESIDUAL_OFFSETS
    residual = reverse_bt.detach() - bt_obs
    assert residual[0, 0] < 0.0 < residual[0, 1]
    assert residual[0, 2] < 0.0
    assert len({abs(float(x)) for x in residual.reshape(-1)}) == len(CHANNELS)
    reverse_cost = _cost(reverse_bt, bt_obs)
    cost_vjp = torch.autograd.grad(reverse_cost, alpha, retain_graph=True)[0]
    channel_vjp = torch.stack([
        torch.autograd.grad(reverse_bt[0, c], alpha, retain_graph=True)[0]
        for c in range(len(CHANNELS))
    ])
    reverse_handle.close()

    from torch.autograd import forward_ad
    with forward_ad.dual_level():
        alpha_dual = forward_ad.make_dual(
            torch.tensor(0.0, dtype=F64), torch.tensor(1.0, dtype=F64))
        forward_state_dual, forward_trace, forward_handle = _run_control(
            state, forcing, alpha_dual, graph=False)
        forward_profile_dual = _profile(forward_state_dual, forcing, profile_cfg)
        forward_bt_dual = _fixed_bt(
            forward_profile_dual, ASYM_K_T, ASYM_K_Q)
        forward_cost_dual = _cost(forward_bt_dual, bt_obs)
        forward_bt, channel_jvp = forward_ad.unpack_dual(forward_bt_dual)
        forward_cost, cost_jvp = forward_ad.unpack_dual(forward_cost_dual)
        forward_handle.close()

    assert torch.equal(reverse_bt, forward_bt)
    assert torch.equal(reverse_cost, forward_cost)
    _assert_trace_equal(reverse_trace, forward_trace)

    fd_channels_by_epsilon = {}
    fd_costs_by_epsilon = {}
    fd_endpoint_values = {}
    for epsilon in ASYM_FD_EPSILONS:
        fd_channels = []
        fd_costs = []
        for signed_epsilon in (epsilon, -epsilon):
            fd_state, fd_trace, fd_handle = _run_control(
                state, forcing, torch.tensor(signed_epsilon, dtype=F64),
                graph=False)
            fd_profile = _profile(fd_state, forcing, profile_cfg)
            fd_bt = _bridge_bt(fd_profile, input_cfg, _asymmetric_run_k)
            fd_channels.append(fd_bt.detach())
            fd_costs.append(float(_cost(fd_bt, bt_obs).detach()))
            _assert_trace_equal(reverse_trace, fd_trace)
            fd_handle.close()
        fd_channels_by_epsilon[epsilon] = (
            fd_channels[0] - fd_channels[1]) / (2.0 * epsilon)
        fd_costs_by_epsilon[epsilon] = (
            fd_costs[0] - fd_costs[1]) / (2.0 * epsilon)
        fd_endpoint_values[epsilon] = (fd_channels[0], fd_channels[1],
                                       fd_costs[0], fd_costs[1])

    # Fixed, independent acceptance bounds for channel products and scalar
    # cost.  The AD-vs-AD check keeps the original 1e-10 relative standard;
    # FD checks retain the original 1e-5 relative tolerance with zero atol.
    torch.testing.assert_close(channel_vjp, channel_jvp.reshape(-1),
                               rtol=1.0e-10, atol=0.0)
    torch.testing.assert_close(cost_vjp, cost_jvp,
                               rtol=1.0e-10, atol=0.0)
    inf = torch.tensor(float("inf"), dtype=F64)
    for epsilon, channel_fd in fd_channels_by_epsilon.items():
        torch.testing.assert_close(channel_vjp, channel_fd.reshape(-1),
                                   rtol=FD_REL_TOL, atol=0.0)
        plus_bt, minus_bt, plus_cost, minus_cost = fd_endpoint_values[epsilon]
        bt_spacing = torch.maximum(
            torch.nextafter(plus_bt, inf) - plus_bt,
            torch.nextafter(minus_bt, inf) - minus_bt,
        ) / (2.0 * epsilon)
        assert bool(torch.all(channel_vjp.abs() > bt_spacing))
        assert bool(torch.all(channel_fd.abs() > bt_spacing))
        cost_spacing = max(
            float(torch.nextafter(torch.tensor(value, dtype=F64), inf)
                  - torch.tensor(value, dtype=F64))
            for value in (plus_cost, minus_cost)
        ) / (2.0 * epsilon)
        cost_fd = fd_costs_by_epsilon[epsilon]
        assert abs(cost_fd - float(cost_vjp)) <= (
            FD_REL_TOL * abs(float(cost_vjp)))
        assert abs(float(cost_vjp)) > cost_spacing
        assert abs(cost_fd) > cost_spacing
    assert bool(torch.isfinite(channel_vjp).all())
    assert bool((channel_vjp.abs() > 0.0).all())
    channel_fd = fd_channels_by_epsilon[ASYM_FD_EPSILONS[0]]

    # The permuted K rows leave forward BT values unchanged, so a BT-only
    # comparison would miss this ABI/consumer ordering error. Channelwise and
    # scalar reverse products must reject it against the independent FD.
    bad_alpha = torch.tensor(0.0, dtype=F64, requires_grad=True)
    bad_state, _, bad_handle = _run_control(
        state, forcing, bad_alpha, graph=True)
    bad_profile = _profile(bad_state, forcing, profile_cfg)
    bad_bt = _bridge_bt(bad_profile, input_cfg, _permuted_asymmetric_run_k)
    assert torch.equal(bad_bt, reverse_bt.detach())
    bad_channel_vjp = torch.stack([
        torch.autograd.grad(bad_bt[0, c], bad_alpha, retain_graph=True)[0]
        for c in range(len(CHANNELS))
    ])
    bad_cost_vjp = torch.autograd.grad(
        _cost(bad_bt, bt_obs), bad_alpha)[0]
    bad_handle.close()
    with pytest.raises(AssertionError):
        torch.testing.assert_close(bad_channel_vjp, channel_fd.reshape(-1),
                                   rtol=FD_REL_TOL, atol=0.0)
    with pytest.raises(AssertionError):
        assert abs(float(bad_cost_vjp) - fd_costs_by_epsilon[ASYM_FD_EPSILONS[0]]) <= (
            FD_REL_TOL * abs(fd_costs_by_epsilon[ASYM_FD_EPSILONS[0]]))
