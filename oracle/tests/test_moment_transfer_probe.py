import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from moment_transfer_probe import inventory_reference, transport, validate  # noqa:E402


def fixture():
    dtype = torch.float64
    moments = torch.tensor([[[1e-5, 2e-5, 3e-6]], [[1e4, 2e4, 3e3]]], dtype=dtype)
    rho = torch.tensor([[0.25, 0.8, 1.3]], dtype=dtype)
    dz = torch.tensor([[10.0, 17.0, 11.0]], dtype=dtype)
    velocity = torch.tensor([[[2.0, 1.0, 3.0]], [[1.0, 3.0, 2.0]]], dtype=dtype)
    return moments, rho, dz, velocity


@pytest.mark.parametrize("steps,dt", [(1, 2.0), (1, 30.0), (3, 30.0)])
def test_actual_kernel_matches_inventory_law_in_both_representations(steps, dt):
    m, rho, dz, v = fixture()
    validate(m, rho, dz, v, dt=dt, steps=steps)
    expected = inventory_reference(m, rho, dz, v, dt=dt, steps=steps)
    dry = transport(m, rho, dz, v, dt=dt, steps=steps)
    volume = transport(
        m * rho.unsqueeze(0), rho, dz, v, dt=dt, steps=steps, basis="volume"
    )
    for out in (dry, volume):
        torch.testing.assert_close(
            out, expected, rtol=32 * torch.finfo(m.dtype).eps, atol=0
        )
        assert bool((out >= 0).all())
        assert bool((out[..., -1] > 0).all())
        torch.testing.assert_close(
            out.sum(-1),
            (m * rho.unsqueeze(0) * dz).sum(-1),
            rtol=32 * torch.finfo(m.dtype).eps,
            atol=0,
        )


def test_density_geometry_and_velocity_derivatives_include_weight_terms():
    inputs = fixture()
    directions = tuple(
        x
        * 0.01
        * torch.cos(torch.arange(x.numel(), dtype=x.dtype).reshape(x.shape) + 0.3)
        for x in inputs
    )

    def fn(*x):
        return transport(*x, dt=2.0, steps=2)

    out, jvp = torch.func.jvp(fn, inputs, directions)
    seed = torch.sin(
        torch.arange(out.numel(), dtype=out.dtype).reshape(out.shape) + 0.7
    )
    _, pullback = torch.func.vjp(fn, *inputs)
    lhs = (jvp * seed).sum()
    rhs = sum((x * d).sum() for x, d in zip(pullback(seed), directions))
    torch.testing.assert_close(lhs, rhs, rtol=64 * torch.finfo(out.dtype).eps, atol=0)
    h = 1e-3
    fd = (
        fn(*(x + h * d for x, d in zip(inputs, directions)))
        - fn(*(x - h * d for x, d in zip(inputs, directions)))
    ) / (2 * h)
    for species in range(2):
        assert (
            float((jvp[species] - fd[species]).abs().max() / jvp[species].abs().max())
            < 1e-7
        )
    # Total cell + bottom derivative includes both changing rho and changing dz.
    m, rho, dz, _ = inputs
    dm, drho, ddz, _ = directions
    volume_inputs = (m * rho.unsqueeze(0), rho, dz, inputs[3])
    volume_directions = (
        dm * rho.unsqueeze(0) + m * drho.unsqueeze(0),
        drho,
        ddz,
        directions[3],
    )
    _, volume_jvp = torch.func.jvp(
        lambda *x: transport(*x, dt=2.0, steps=2, basis="volume"),
        volume_inputs,
        volume_directions,
    )
    torch.testing.assert_close(
        jvp, volume_jvp, rtol=128 * torch.finfo(out.dtype).eps, atol=0
    )
    expected = (dm * rho * dz + m * drho * dz + m * rho * ddz).sum(-1)
    torch.testing.assert_close(
        jvp.sum(-1), expected, rtol=128 * torch.finfo(out.dtype).eps, atol=0
    )


def test_unconverted_mass_number_is_a_detectable_counterexample():
    m, rho, dz, v = fixture()
    correct = transport(m, rho, dz, v)
    wrong = transport(m, rho, dz, v, basis="volume")
    assert not torch.allclose(correct[1], wrong[1], rtol=1e-3, atol=0)


@pytest.mark.parametrize("which", ["density", "thickness", "nonfinite", "shape"])
def test_invalid_experimental_domain_is_rejected(which):
    m, rho, dz, v = fixture()
    if which == "density":
        rho[0, 0] = 0
    elif which == "thickness":
        dz[0, 0] = -1
    elif which == "nonfinite":
        v[0, 0, 0] = float("nan")
    else:
        m = m[..., :2]
    with pytest.raises(ValueError):
        validate(m, rho, dz, v, dt=2, steps=1)
