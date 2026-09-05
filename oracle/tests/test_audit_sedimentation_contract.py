"""Focused sedimentation measure regression for the production dend contract."""
from __future__ import annotations

import torch

from kdm6.sedimentation import (
    SubstepAdvectionState,
    default_substep_advection_params,
    substep_advection_torch,
    surface_accumulation_torch,
)


def test_dend_rho_and_surface_delz_conversion_are_applied_once():
    """A one-layer direct fixture uses dend=rho; surface adds the one delz factor."""
    dtype = torch.float64
    rho = 1.1
    delz = 500.0
    q = 1.0e-3
    work1 = 1.0e-3  # vt / delz [s^-1]
    dtcld = 60.0
    state = SubstepAdvectionState(
        qr=torch.tensor([[q]], dtype=dtype),
        nr=torch.zeros((1, 1), dtype=dtype),
        qs=torch.zeros((1, 1), dtype=dtype),
        qg=torch.zeros((1, 1), dtype=dtype),
        brs=torch.zeros((1, 1), dtype=dtype),
    )
    zeros = torch.zeros((1, 1), dtype=dtype)
    out = substep_advection_torch(
        state,
        zeros, zeros.clone(), zeros.clone(), zeros.clone(), zeros.clone(),
        torch.full((1, 1), work1, dtype=dtype),
        zeros.clone(), zeros.clone(), zeros.clone(),
        torch.full((1, 1), delz, dtype=dtype),
        torch.full((1, 1), rho, dtype=dtype),
        dtcld=dtcld,
        params=default_substep_advection_params(),
    )

    # falk = rho * q * (vt/delz), a volumetric mass rate. Surface conversion
    # then multiplies by delz/denr*1000 exactly once.
    expected_falk = rho * q * work1
    assert torch.allclose(out.fall_qr[0, 0], torch.tensor(expected_falk, dtype=dtype))
    surface = surface_accumulation_torch(
        out.fall_qr[:, -1], zeros[:, -1], zeros[:, -1], zeros[:, -1],
        torch.full((1,), delz, dtype=dtype), dtcld=dtcld,
    )
    expected_mm = expected_falk * delz / 1000.0 * dtcld * 1000.0
    assert torch.allclose(surface.rain_increment, torch.full((1,), expected_mm, dtype=dtype))
    assert torch.allclose(surface.rain_increment, torch.tensor([0.033], dtype=dtype))


def test_direct_substeps_refuse_broadcast_and_empty_grids():
    import pytest
    from kdm6.sedimentation import IceSubstepState, ice_substep_advection_torch
    for shape, forcing_shape, mstep_shape in (
            ((2, 1), (1, 1), (2,)), ((2, 1), (2, 1), (2, 1)),
            ((1, 0), (1, 0), (1,))):
        s = torch.ones(shape, dtype=torch.float64)
        f = torch.ones(forcing_shape, dtype=torch.float64)
        kwargs = dict(dtcld=1.0, mstep_col=torch.ones(mstep_shape),
                      params=default_substep_advection_params())
        with pytest.raises(ValueError, match='shape'):
            substep_advection_torch(SubstepAdvectionState(s, s, s, s, s),
                                    s, s, s, s, s, s, s, s, s, f, f, **kwargs)
        with pytest.raises(ValueError, match='shape'):
            ice_substep_advection_torch(IceSubstepState(s, s),
                                        s, s, s, s, f, f, **kwargs)
