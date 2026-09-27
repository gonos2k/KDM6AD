"""Focused checks for the opt-in dry-mass number boundary."""

import pytest
import torch

from kdm6.runtime import _kdm6_pure, kdm6_step, make_parameters
from kdm6.state import Forcing, State, zeros_like_state


def _case():
    def mk(value):
        return torch.full((1, 3), value, dtype=torch.float64)
    state = State(
        th=mk(290.0), qv=mk(0.014), qc=mk(0.001), qr=mk(0.0001),
        qi=mk(0.0), qs=mk(0.0), qg=mk(0.0), nccn=mk(1e9),
        nc=mk(1e8), ni=mk(0.0), nr=mk(1e4), bg=mk(0.0),
    )
    forcing = Forcing(rho=mk(1.0), pii=mk(0.97), p=mk(9e4), delz=mk(500.0))
    return state, forcing


def test_dry_number_qv_jvp_matches_independent_difference():
    state, forcing = _case()
    live = State(*(field.requires_grad_() for field in state))
    params = make_parameters()
    xland = torch.tensor([2.0], dtype=torch.float64)
    output, handle = kdm6_step(
        live, forcing, params, dt=20.0, xland=xland,
        ncmin_land=100.0, ncmin_sea=10.0, dry_number=True,
    )
    direction = zeros_like_state(live)._replace(qv=torch.full_like(live.qv, 1e-3))
    tangent = handle.jvp(direction)
    h = 1e-4
    fixed = State(*(field.detach() for field in live))

    def step(qv):
        return _kdm6_pure(
            fixed._replace(qv=qv), forcing, params, dt=20.0, xland=xland,
            ncmin_land=100.0, ncmin_sea=10.0, dry_number=True,
        )

    plus = step(fixed.qv + h * direction.qv)
    minus = step(fixed.qv - h * direction.qv)
    for name in ("nccn", "nc", "ni", "nr"):
        derivative = getattr(tangent, name)
        difference = (getattr(plus, name) - getattr(minus, name)) / (2 * h)
        assert torch.isfinite(getattr(output, name)).all()
        assert torch.isfinite(derivative).all()
        torch.testing.assert_close(derivative, difference, rtol=1e-5, atol=1e-7)
    handle.close()


@pytest.mark.parametrize("rho,qv", [(0.0, 0.014), (1.0, -1.0)])
def test_dry_number_rejects_nonpositive_density(rho, qv):
    state, forcing = _case()
    state = state._replace(qv=torch.full_like(state.qv, qv))
    forcing = forcing._replace(rho=torch.full_like(forcing.rho, rho))
    with pytest.raises(ValueError, match="dry-number density"):
        _kdm6_pure(state, forcing, make_parameters(), dt=20.0, dry_number=True)


def test_dry_number_rejects_moist_density_budget():
    state, forcing = _case()
    with pytest.raises(ValueError, match="dry-density ledger"):
        _kdm6_pure(state, forcing, make_parameters(), dt=20.0,
                   dry_number=True, budget=object())
    with pytest.raises(ValueError, match="number-basis label"):
        _kdm6_pure(state, forcing, make_parameters(), dt=20.0,
                   dry_number=True, diagnostic_trace=object())
