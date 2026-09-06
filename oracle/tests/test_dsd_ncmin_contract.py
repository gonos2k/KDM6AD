"""Final ice DSD gates: per-cell identity and the active analytic snap."""
import pytest
import torch

from kdm6 import constants as c, fconst
from kdm6.coordinator import CoordinatorState, apply_dsd_number_limiters_torch


def _ice_state(qi, ni):
    z = torch.zeros_like(qi)
    return CoordinatorState(
        qv=z, qc=z, qr=z, qs=z, qg=z, qi=qi,
        nc=z, nr=z, ni=ni, brs=z, t=torch.full_like(qi, 260.0),
    )


def test_final_ice_ncmin_per_cell_values_and_other_fields():
    qi = torch.tensor([[0.001, 0.001, 0.001, 0.001, 0.0]], dtype=torch.float64)
    ni = torch.tensor([[50.0, 50.0, 100.0, 0.001, 200.0]], dtype=torch.float64)
    floor = torch.tensor([[10.0, 100.0, 100.0, 100.0, 100.0]], dtype=torch.float64)
    state = _ice_state(qi, ni)
    out = apply_dsd_number_limiters_torch(state, torch.ones_like(qi), ncmin_tensor=floor)
    # Cells 0/2 are active with lambda below LAMDAIMIN; cell 2 tests equality.
    snap = 0.001 * c.LAMDAIMIN ** c.DMI / fconst.PIDNI
    expected = torch.tensor([[snap, 50.0, snap, 0.001, 200.0]], dtype=torch.float64)
    torch.testing.assert_close(out.ni, expected, rtol=0, atol=0)
    for field in state._fields:
        if field != "ni":
            assert torch.equal(getattr(out, field), getattr(state, field))


def test_final_ice_ncmin_tangent_and_adjoint():
    qi = torch.full((1, 3), 0.001, dtype=torch.float64, requires_grad=True)
    ni = torch.tensor([[50.0, 50.0, 100.0]], dtype=torch.float64, requires_grad=True)
    floor = torch.tensor([[10.0, 100.0, 100.0]], dtype=torch.float64)
    coefficient = c.LAMDAIMIN ** c.DMI / fconst.PIDNI
    dq = torch.tensor([[coefficient, 0.0, coefficient]], dtype=torch.float64)
    dn = torch.tensor([[0.0, 1.0, 0.0]], dtype=torch.float64)

    def run(q, n):
        return apply_dsd_number_limiters_torch(
            _ice_state(q, n), torch.ones_like(q), ncmin_tensor=floor,
        ).ni

    seed = torch.tensor([[2.0, 3.0, 5.0]], dtype=torch.float64)
    vq = torch.tensor([[0.1, 0.2, 0.3]], dtype=torch.float64)
    vn = torch.tensor([[0.4, 0.5, 0.6]], dtype=torch.float64)
    gq, gn = torch.autograd.grad((run(qi, ni) * seed).sum(), (qi, ni))
    torch.testing.assert_close(gq, seed * dq, rtol=1e-15, atol=0)
    torch.testing.assert_close(gn, seed * dn, rtol=0, atol=0)
    _, tangent = torch.func.jvp(run, (qi, ni), (vq, vn))
    torch.testing.assert_close(tangent, dq * vq + dn * vn, rtol=1e-15, atol=0)
    torch.testing.assert_close((seed * tangent).sum(), (gq * vq + gn * vn).sum())


@pytest.mark.parametrize("explicit_floor", [False, True])
def test_final_ice_ncmin_scalar_default(explicit_floor):
    qi = torch.full((1, 3), 0.001, dtype=torch.float64)
    ni = torch.tensor([[0.001, c.NCMIN, 50.0]], dtype=torch.float64)
    floor = torch.full_like(qi, c.NCMIN) if explicit_floor else None
    out = apply_dsd_number_limiters_torch(_ice_state(qi, ni), torch.ones_like(qi), ncmin_tensor=floor)
    snap = 0.001 * c.LAMDAIMIN ** c.DMI / fconst.PIDNI
    expected = torch.tensor([[0.001, snap, snap]], dtype=torch.float64)
    torch.testing.assert_close(out.ni, expected, rtol=0, atol=0)


def test_final_ice_ncmin_retains_mass_threshold():
    qmin = torch.tensor(1e-15, dtype=torch.float64)
    qi = torch.stack((torch.nextafter(qmin, torch.zeros_like(qmin)), qmin)).reshape(1, 2)
    ni = torch.full_like(qi, 100.0)
    out = apply_dsd_number_limiters_torch(_ice_state(qi, ni), torch.ones_like(qi), ncmin_tensor=ni)
    # Just below qmin is identity; equality is active with lambda above LAMDAIMAX.
    expected = torch.stack((ni[0, 0], qmin * c.LAMDAIMAX ** c.DMI / fconst.PIDNI)).reshape(1, 2)
    torch.testing.assert_close(out.ni, expected, rtol=0, atol=0)
