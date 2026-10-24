"""Batch native all-sky profile wrapper tests; no RTTOV case or model calls."""

import pytest
import torch

from kdm6.obs.model_profile_builder import RttovProfileTensors
from kdm6.obs.native_batch_profile import native_to_rttov_cloud_profile_batch
from kdm6.obs.native_cloud_profile import (
    NativeCloudState,
    native_to_rttov_cloud_profile,
)
from kdm6.obs.native_profile_builder import (
    FrozenNativeProfileGeometry,
    NativeObservationConfig,
    NativeObservationState,
)


DTYPE = torch.float64
CONFIG = NativeObservationConfig(
    alpha=1.6083624362945557,
    t0=300.0,
    kappa=0.2857142984867096,
    p0=100000.0,
    g=9.8100004196167,
)


def _inputs(*, requires_grad=False):
    thm = torch.tensor([[-8.0, 1.0, 13.0], [-5.0, 4.0, 16.0]], dtype=DTYPE)
    qv = torch.tensor([[0.004, 0.008, 0.013], [0.003, 0.007, 0.012]], dtype=DTYPE)
    pressure = torch.tensor(
        [[100000.0, 50000.0, 10000.0], [98000.0, 48000.0, 9500.0]],
        dtype=DTYPE,
    )
    phi = torch.tensor(
        [[0.0, 15000.0, 40000.0, 80000.0], [0.0, 16500.0, 42000.0, 82500.0]],
        dtype=DTYPE,
    )
    qc = torch.tensor(
        [[1.0e-4, 1.2e-4, 0.8e-4], [0.9e-4, 1.1e-4, 0.7e-4]],
        dtype=DTYPE,
    )
    qi = torch.tensor(
        [[0.5e-4, 0.7e-4, 0.4e-4], [0.6e-4, 0.8e-4, 0.3e-4]],
        dtype=DTYPE,
    )
    qs = torch.tensor(
        [[0.4e-4, 0.3e-4, 0.5e-4], [0.3e-4, 0.5e-4, 0.2e-4]],
        dtype=DTYPE,
    )
    nc = torch.tensor([[1.0e7, 1.2e7, 0.9e7], [1.1e7, 1.3e7, 0.8e7]], dtype=DTYPE)
    ni = torch.tensor([[5.0e6, 6.0e6, 4.0e6], [5.5e6, 6.5e6, 3.5e6]], dtype=DTYPE)
    rho_d = torch.tensor([[1.0, 0.85, 0.55], [0.98, 0.82, 0.52]], dtype=DTYPE)
    geometry = FrozenNativeProfileGeometry(
        fnm=torch.full((3,), 0.5, dtype=DTYPE),
        fnp=torch.full((3,), 0.5, dtype=DTYPE),
    )
    xland = torch.tensor([1.0, 2.0], dtype=DTYPE)
    if requires_grad:
        thm, qv, pressure, phi, qc, qi, qs, nc, ni, rho_d = tuple(
            value.requires_grad_()
            for value in (thm, qv, pressure, phi, qc, qi, qs, nc, ni, rho_d)
        )
    native = NativeObservationState(thm, qv, pressure, phi)
    clouds = NativeCloudState(qc, qi, qs, nc, ni)
    return native, clouds, rho_d, xland, geometry


def _single_row(native, clouds, rho_d, xland, geometry, row):
    return native_to_rttov_cloud_profile(
        NativeObservationState(
            native.thm_pert[row],
            native.qv[row],
            native.p_center_Pa[row],
            native.phi_interfaces[row],
        ),
        NativeCloudState(
            clouds.qc[row],
            clouds.qi[row],
            clouds.qs[row],
            clouds.nc[row],
            clouds.ni[row],
        ),
        geometry,
        CONFIG,
        rho_d=rho_d[row],
        xland=xland[row],
        ncmin_land=10.0,
        ncmin_sea=10.0,
    )


def _batch(native, clouds, rho_d, xland, geometry):
    return native_to_rttov_cloud_profile_batch(
        native,
        clouds,
        geometry,
        CONFIG,
        rho_d=rho_d,
        xland=xland,
        ncmin_land=10.0,
        ncmin_sea=10.0,
    )


def _differentiable_vector(profile: RttovProfileTensors):
    # CFRAC is intentionally detached/non-differentiable in the single-column API.
    return torch.cat(
        [
            getattr(profile, name).reshape(-1)
            for name in (
                "t_lay",
                "q_lay",
                "p_lay",
                "p_half",
                "clw",
                "ciw",
                "deff_liq",
                "deff_ice",
            )
        ]
    )


def test_batch_wrapper_matches_each_native_column_without_pressure_remapping():
    native, clouds, rho_d, xland, geometry = _inputs()
    batched = _batch(native, clouds, rho_d, xland, geometry)
    for row in range(2):
        expected = _single_row(native, clouds, rho_d, xland, geometry, row)
        for name in RttovProfileTensors._fields:
            actual_value = getattr(batched, name)[row]
            expected_value = getattr(expected, name)
            torch.testing.assert_close(actual_value, expected_value, rtol=0.0, atol=0.0)

    assert batched.t_lay.shape == batched.q_lay.shape == (2, 3)
    assert batched.p_lay.shape == (2, 3)
    assert batched.p_half.shape == (2, 4)
    assert not torch.equal(batched.p_lay[0], batched.p_lay[1])
    assert not torch.equal(batched.p_half[0], batched.p_half[1])
    # Native mass centers and P8W interfaces retain each column's own values,
    # in RTTOV's top-to-surface order, with only Pa→hPa conversion.
    torch.testing.assert_close(
        batched.p_lay,
        torch.flip(native.p_center_Pa / 100.0, dims=(-1,)),
        rtol=0.0,
        atol=0.0,
    )
    assert not batched.cfrac.requires_grad


def test_batch_wrapper_preserves_jvp_vjp_and_row_dependent_pressure_paths():
    native, clouds, rho_d, xland, geometry = _inputs(requires_grad=True)
    inputs = (
        native.thm_pert,
        native.qv,
        native.p_center_Pa,
        native.phi_interfaces,
        clouds.qc,
        clouds.qi,
        clouds.qs,
        clouds.nc,
        clouds.ni,
        rho_d,
    )
    directions = tuple(
        torch.linspace(-scale, scale, value.numel(), dtype=DTYPE).reshape(value.shape)
        for value, scale in zip(
            inputs,
            (0.02, 1.0e-6, 2.0, 3.0, 1.0e-6, 1.0e-6, 1.0e-6, 1.0e4, 1.0e3, 1.0e-4),
        )
    )

    def output(*values):
        current_native = NativeObservationState(*values[:4])
        current_clouds = NativeCloudState(*values[4:9])
        return _differentiable_vector(
            _batch(current_native, current_clouds, values[9], xland, geometry)
        )

    value, tangent = torch.autograd.functional.jvp(output, inputs, directions)
    seed = torch.linspace(-0.7, 0.9, value.numel(), dtype=DTYPE)
    gradients = torch.autograd.grad(torch.dot(output(*inputs), seed), inputs)
    lhs = torch.dot(tangent, seed)
    rhs = sum(
        torch.sum(grad * direction) for grad, direction in zip(gradients, directions)
    )
    torch.testing.assert_close(lhs, rhs, rtol=2.0e-12, atol=2.0e-11)

    epsilon = 2.0e-4
    plus = output(
        *(
            base.detach() + epsilon * direction
            for base, direction in zip(inputs, directions)
        )
    )
    minus = output(
        *(
            base.detach() - epsilon * direction
            for base, direction in zip(inputs, directions)
        )
    )
    finite_difference = (plus - minus) / (2.0 * epsilon)
    torch.testing.assert_close(finite_difference, tangent, rtol=2.0e-5, atol=2.0e-8)
    assert torch.count_nonzero(gradients[2]) > 0  # Center-pressure derivatives.
    assert torch.count_nonzero(gradients[3]) > 0  # Interface-pressure derivatives.
    assert torch.count_nonzero(gradients[9]) > 0  # Per-row dry-density cloud path.
    assert torch.count_nonzero(gradients[6]) > 0  # Snow content contributes to HYDRO7.


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("qv", torch.zeros((2, 2), dtype=DTYPE), "native_state.qv"),
        ("rho_d", torch.ones((2, 2), dtype=DTYPE), "rho_d"),
        ("xland", torch.tensor([1.0], dtype=DTYPE), "xland"),
    ],
)
def test_batch_metadata_shapes_fail_before_column_stacking(field, value, match):
    native, clouds, rho_d, xland, geometry = _inputs()
    if field == "qv":
        native = NativeObservationState(
            native.thm_pert, value, native.p_center_Pa, native.phi_interfaces
        )
    elif field == "rho_d":
        rho_d = value
    else:
        xland = value
    with pytest.raises(ValueError, match=match):
        _batch(native, clouds, rho_d, xland, geometry)
