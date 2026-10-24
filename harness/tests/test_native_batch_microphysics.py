"""Focused batch adapter checks with an independent affine KDM backend."""

from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip(
    "torch", reason="native batch first-order boundary needs Torch"
)

from harness.native_batch_microphysics import (
    BatchPrepGeometry,
    NativeBatchDirection,
    NativeBatchMicrophysics,
)
from oracle.kdm6.native_finish import FinishConfig, ZeroOutConfig
from oracle.kdm6.native_prep import NativePrepConfig


class AffineBatchKernel:
    def __init__(self, batch=2, levels=3, *, fail_vjp=False):
        self.B, self.L = batch, levels
        self.A = np.eye(12, dtype=np.float64)
        self.A[0, 1] = 0.015
        self.A[1, 0] = 2e-5
        self.A[2:7, 0] = 1e-7
        self.A[7:12, 0] = 1e-5
        self.Bf = np.zeros((12, 4), dtype=np.float64)
        self.Bf[:, 0] = 2e-7
        self.Bf[:, 1] = 1e-7
        self.Bf[:, 2] = 1e-9
        self.Bf[:, 3] = 2e-8
        self.bias = np.zeros((12, batch, levels), dtype=np.float64)
        self.bias[0] = 0.01
        self.bias[1] = 1e-4
        self.bias[2:7] = 2e-6
        self.bias[7:12] = 0.01
        self.bias[:, 1] *= 1.7
        self.fail_vjp = fail_vjp
        self.calls = 0
        self.jvp_calls = 0
        self.vjp_calls = 0
        self.forward_grad_modes = []
        self.jvp_grad_modes = []
        self.vjp_grad_modes = []
        self.jvp_handles = []
        self.vjp_handles = []
        self.closed = []
        self.row_mix = None

    def forward(self, state, forcing, *, record=False):
        self.forward_grad_modes.append(torch.is_grad_enabled())
        assert state.shape == (12, self.B, self.L)
        assert forcing.shape == (4, self.B, self.L)
        self.calls += 1
        s = torch.tensor(state, dtype=torch.float64, requires_grad=record)
        f = torch.tensor(forcing, dtype=torch.float64, requires_grad=record)
        after = self._map(s, f)
        handle = (s, f, after) if record else None
        return np.ascontiguousarray(after.detach().numpy()), handle

    def _map(self, state, forcing):
        a = torch.as_tensor(self.A, dtype=state.dtype, device=state.device)
        bf = torch.as_tensor(self.Bf, dtype=state.dtype, device=state.device)
        bias = torch.as_tensor(self.bias, dtype=state.dtype, device=state.device)
        value = (
            torch.einsum("ij,jbl->ibl", a, state)
            + torch.einsum("if,fbl->ibl", bf, forcing)
            + bias
        )
        if self.row_mix is not None:
            return torch.einsum("uv,fvl->ful", self.row_mix, value)
        return value

    def vjp(self, handle, cotangent):
        self.vjp_calls += 1
        self.vjp_grad_modes.append(torch.is_grad_enabled())
        self.vjp_handles.append(handle)
        assert torch.is_grad_enabled()
        state, forcing, after = handle
        if self.fail_vjp:
            raise RuntimeError("synthetic VJP failure")
        u = torch.as_tensor(cotangent, dtype=torch.float64)
        gs, gf = torch.autograd.grad(after, (state, forcing), grad_outputs=u)
        return gs.detach().numpy(), gf.detach().numpy()

    def jvp(self, handle, dstate, dforcing):
        self.jvp_calls += 1
        self.jvp_grad_modes.append(torch.is_grad_enabled())
        self.jvp_handles.append(handle)
        assert torch.is_grad_enabled()
        state, forcing, _ = handle
        ds = torch.as_tensor(dstate, dtype=torch.float64)
        df = torch.as_tensor(dforcing, dtype=torch.float64)
        _, tangent = torch.autograd.functional.jvp(
            self._map, (state, forcing), (ds, df), create_graph=False, strict=True
        )
        return tangent.detach().numpy()

    def close(self, handle):
        self.closed.append(handle)


def make_adapter(*, fail_vjp=False):
    batch, levels = 2, 3
    geom = BatchPrepGeometry(
        phb=torch.zeros((batch, levels + 1), dtype=torch.float64),
        c3h=torch.tensor([[0.85, 0.55, 0.25], [0.82, 0.52, 0.22]], dtype=torch.float64),
        c4h=torch.zeros((batch, levels), dtype=torch.float64),
        c3f=torch.tensor(
            [[1.0, 0.7, 0.4, 0.1], [1.0, 0.68, 0.39, 0.1]], dtype=torch.float64
        ),
        c4f=torch.zeros((batch, levels + 1), dtype=torch.float64),
    )
    kernel = AffineBatchKernel(batch, levels, fail_vjp=fail_vjp)
    adapter = NativeBatchMicrophysics(
        kernel,
        geom,
        NativePrepConfig(
            ptop=5000.0,
            rd=287.0,
            p0=100000.0,
            t0=300.0,
            alpha=1.6083624362945557,
            gamma=1.3999999761581421,
            kappa=0.2857142984867096,
            g=9.8100004196167,
        ),
        FinishConfig(dt=20.0, alpha=1.6083624362945557, t0=300.0, mp_tend_lim=3.0),
        ZeroOutConfig(mode=2, threshold=1e-7),
    )
    inputs = (
        torch.tensor(
            [[-20.0, -15.0, -10.0], [-19.0, -14.0, -9.0]],
            dtype=torch.float64,
            requires_grad=True,
        ),
        torch.tensor(
            [[0.001, 0.004, 0.01], [0.002, 0.005, 0.011]],
            dtype=torch.float64,
            requires_grad=True,
        ),
        torch.tensor([50000.0, 50500.0], dtype=torch.float64),
        torch.tensor(
            [[0.0, 50000.0, 110000.0, 180000.0], [0.0, 51000.0, 111000.0, 181000.0]],
            dtype=torch.float64,
            requires_grad=True,
        ),
        torch.tensor(
            [
                [[2e-3, 3e-3, 4e-3], [2.1e-3, 3.1e-3, 4.1e-3]],
                [[5e-4, 1.5e-3, 7e-4], [6e-4, 1.6e-3, 8e-4]],
                [[2e-3, 6e-4, 4e-3], [2.1e-3, 7e-4, 4.1e-3]],
                [[1e-4, 2e-3, 1e-4], [2e-4, 2.1e-3, 2e-4]],
                [[2e-3, 3e-3, 2e-3], [2.1e-3, 3.1e-3, 2.1e-3]],
                [[1e5, 2e5, 3e5], [1.1e5, 2.1e5, 3.1e5]],
                [[2e5, 3e5, 4e5], [2.1e5, 3.1e5, 4.1e5]],
                [[3e5, 4e5, 5e5], [3.1e5, 4.1e5, 5.1e5]],
                [[4e5, 5e5, 6e5], [4.1e5, 5.1e5, 6.1e5]],
                [[5e5, 6e5, 7e5], [5.1e5, 6.1e5, 7.1e5]],
            ],
            dtype=torch.float64,
            requires_grad=True,
        ),
    )
    return adapter, kernel, inputs


def _objective(output, weights):
    values = [*output.native_profile, *output.cloud_state, output.rho_d, *output.finish]
    return sum(torch.sum(value * weight) for value, weight in zip(values, weights))


def test_batch_graph_matches_total_directional_difference_and_preserves_columns():
    adapter, kernel, inputs = make_adapter()
    output = adapter(*inputs)
    assert kernel.calls == 1  # one full-B schedule/kernel call
    assert output.native_profile.thm_pert.shape == (2, 3)
    assert output.native_profile.p_center_Pa.shape == (2, 3)
    assert output.native_profile.phi_interfaces.shape == (2, 4)
    assert output.rho_d.shape == (2, 3)
    assert not torch.equal(
        output.native_profile.p_center_Pa[0], output.native_profile.p_center_Pa[1]
    )
    assert torch.all(output.cloud_state.qg > 0.0)

    values = [*output.native_profile, *output.cloud_state, output.rho_d, *output.finish]
    generator = torch.Generator().manual_seed(1701)
    weights = [torch.randn(v.shape, generator=generator, dtype=v.dtype) for v in values]
    objective = _objective(output, weights)
    grads = torch.autograd.grad(objective, (inputs[0], inputs[1], inputs[3], inputs[4]))
    directions = [
        torch.randn(v.shape, generator=generator, dtype=v.dtype)
        for v in (inputs[0], inputs[1], inputs[3], inputs[4])
    ]
    directions[0] *= 0.1
    directions[1] *= 1e-4
    directions[2] *= 0.1
    directions[3] *= torch.maximum(inputs[4].abs(), torch.tensor(1e-4)) * 1e-5
    ad_direction = sum(torch.sum(g * d) for g, d in zip(grads, directions))

    eps = 2e-5
    plus = list(inputs)
    minus = list(inputs)
    for index, direction in zip((0, 1, 3, 4), directions):
        plus[index] = inputs[index].detach() + eps * direction
        minus[index] = inputs[index].detach() - eps * direction
    yp, ym = adapter(*plus), adapter(*minus)
    fd_direction = (_objective(yp, weights) - _objective(ym, weights)) / (2 * eps)
    assert torch.isclose(ad_direction, fd_direction, rtol=3e-5, atol=1e-7)
    assert kernel.calls == 3
    # This batch wrapper owns one opaque C ABI checkpoint; one backward closes it.
    assert len(kernel.closed) == 1


def test_batch_backward_closes_abi_handle_when_vjp_raises():
    adapter, kernel, inputs = make_adapter(fail_vjp=True)
    output = adapter(*inputs)
    with pytest.raises(RuntimeError, match="synthetic VJP failure"):
        output.native_profile.thm_pert.sum().backward()
    assert len(kernel.closed) == 1


def test_explicit_jvp_reuses_one_kernel_checkpoint_and_matches_fd_and_vjp_dot():
    adapter, kernel, inputs = make_adapter()
    generator = torch.Generator().manual_seed(2801)
    direction = NativeBatchDirection(
        torch.randn(inputs[0].shape, generator=generator, dtype=torch.float64) * 0.1,
        torch.randn(inputs[1].shape, generator=generator, dtype=torch.float64) * 1e-4,
        torch.randn(inputs[3].shape, generator=generator, dtype=torch.float64) * 0.1,
        torch.randn(inputs[4].shape, generator=generator, dtype=torch.float64)
        * torch.maximum(inputs[4].detach().abs(), torch.tensor(1e-4))
        * 1e-5,
    )
    primal, tangent = adapter.forward_with_jvp(*inputs, direction)
    assert kernel.calls == 1
    assert kernel.jvp_calls == 1
    assert not any(
        value.requires_grad
        for value in (
            *tangent.native_profile,
            *tangent.cloud_state,
            tangent.rho_d,
            *tangent.finish,
        )
    )

    values = [*primal.native_profile, *primal.cloud_state, primal.rho_d, *primal.finish]
    weights = [torch.randn(v.shape, generator=generator, dtype=v.dtype) for v in values]
    objective = _objective(primal, weights)
    grads = torch.autograd.grad(objective, (inputs[0], inputs[1], inputs[3], inputs[4]))
    jvp_dot = _objective(tangent, weights)
    vjp_dot = sum(
        torch.sum(g * d)
        for g, d in zip(
            grads, (direction.theta_m_pert, direction.qv, direction.ph, direction.rest)
        )
    )
    assert torch.isclose(jvp_dot, vjp_dot, rtol=2e-10, atol=1e-7)

    for eps in (1e-4, 3e-5):
        plus, minus = list(inputs), list(inputs)
        for index, delta in zip((0, 1, 3, 4), direction):
            plus[index] = inputs[index].detach() + eps * delta
            minus[index] = inputs[index].detach() - eps * delta
        yp, ym = adapter(*plus), adapter(*minus)
        fd = (_objective(yp, weights) - _objective(ym, weights)) / (2 * eps)
        assert torch.isclose(fd, jvp_dot, rtol=3e-5, atol=1e-6)
    assert kernel.calls == 5
    assert kernel.jvp_calls == 1
    assert kernel.vjp_calls == 1
    assert kernel.forward_grad_modes[0] is True
    assert kernel.jvp_grad_modes == [True]
    assert kernel.vjp_grad_modes == [True]
    assert kernel.jvp_handles[0] is kernel.vjp_handles[0]
    assert len(kernel.closed) == 1


@pytest.mark.parametrize("row", range(2, 7))
def test_positive_cleanup_ties_reject_ad_but_preserve_forward(row):
    adapter, _, _ = make_adapter()
    raw = torch.ones((12, 2, 3), dtype=torch.float64)
    raw[row, 0, 0] = adapter.threshold
    result = adapter._clean(raw)
    assert result[row, 0, 0] == adapter.threshold
    with pytest.raises(ValueError, match="cleanup discontinuity"):
        adapter._clean(raw.requires_grad_())


def test_zero_cleanup_ties_select_clipped_side_for_every_mass_field():
    adapter, _, _ = make_adapter()
    adapter.threshold = 0.0
    adapter.zero_config = ZeroOutConfig(mode=2, threshold=0.0)
    raw = torch.ones((12, 2, 3), dtype=torch.float64)
    raw[1:7] = 0.0
    raw.requires_grad_()
    adapter._clean(raw)[1:7].sum().backward()
    assert torch.equal(raw.grad[1:7], torch.zeros_like(raw.grad[1:7]))


def test_retained_graph_refuses_a_second_reverse_pass_before_calling_closed_abi():
    adapter, kernel, inputs = make_adapter()
    value = adapter(*inputs).native_profile.thm_pert.sum()
    torch.autograd.grad(value, inputs[0], retain_graph=True)
    with pytest.raises(RuntimeError, match="single reverse pass"):
        torch.autograd.grad(value, inputs[0], retain_graph=True)
    assert len(kernel.closed) == 1


def test_full_batch_preserves_cross_column_tangent_and_adjoint_paths():
    adapter, kernel, inputs = make_adapter()
    kernel.row_mix = torch.tensor([[1.0, 0.05], [0.03, 1.0]], dtype=torch.float64)
    dtheta = torch.zeros_like(inputs[0])
    dtheta[1] = torch.tensor([0.1, 0.2, 0.3], dtype=torch.float64)
    direction = NativeBatchDirection(
        dtheta,
        torch.zeros_like(inputs[1]),
        torch.zeros_like(inputs[3]),
        torch.zeros_like(inputs[4]),
    )
    primal, tangent = adapter.forward_with_jvp(*inputs, direction)
    assert kernel.calls == 1
    assert bool(tangent.native_profile.thm_pert[0].abs().sum() > 0)
    gradient = torch.autograd.grad(primal.native_profile.thm_pert[0].sum(), inputs[0])[
        0
    ]
    assert bool(gradient[1].abs().sum() > 0)
    ad = (gradient * dtheta).sum()
    jvp = tangent.native_profile.thm_pert[0].sum()
    assert torch.isclose(ad, jvp, rtol=1e-12, atol=1e-12)
    eps = 1e-4
    plus = [value.detach() for value in inputs]
    minus = [value.detach() for value in inputs]
    plus[0] = plus[0] + eps * dtheta
    minus[0] = minus[0] - eps * dtheta
    fd = (
        adapter(*plus).native_profile.thm_pert[0].sum()
        - adapter(*minus).native_profile.thm_pert[0].sum()
    ) / (2 * eps)
    assert torch.isclose(fd, ad, rtol=3e-6, atol=1e-8)
