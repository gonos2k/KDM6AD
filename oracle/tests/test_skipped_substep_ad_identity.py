"""Inactive per-column sedimentation steps are identity maps for AD."""

import torch

from oracle.kdm6.coordinator import (
    CoordinatorForcing,
    CoordinatorState,
    sedimentation_chain_torch,
)
from oracle.kdm6.sedimentation import default_substep_advection_params


def _case(*, species: str, columns: int, dtype: torch.dtype):
    levels = 2

    def full(value):
        return torch.full((columns, levels), value, dtype=dtype)

    values = [[0.0, 0.0]] + ([[0.005, 0.005]] if columns == 2 else [])
    moment = torch.tensor(values, dtype=dtype, requires_grad=True)
    state = CoordinatorState(
        qv=full(0.01),
        qc=full(0.001),
        qr=moment if species == "rain" else full(0.001),
        qs=full(0.001),
        qg=full(0.001),
        qi=moment if species == "ice" else full(0.0),
        nc=full(1.0e8),
        nr=full(0.0 if species == "rain" else 1.0e3),
        ni=full(0.0),
        brs=full(1.0e-6),
        t=full(280.0),
    )
    forcing = CoordinatorForcing(
        p=full(8.0e4), den=full(1.1), delz=full(250.0), dend=full(1.1)
    )
    work = full(0.001)
    main = torch.tensor(
        [1.0]
        + (
            [5.0]
            if columns == 2 and species == "rain"
            else [1.0]
            if columns == 2
            else []
        ),
        dtype=dtype,
    )
    ice = torch.tensor(
        [1.0]
        + (
            [5.0]
            if columns == 2 and species == "ice"
            else [1.0]
            if columns == 2
            else []
        ),
        dtype=dtype,
    )
    out = sedimentation_chain_torch(
        state,
        forcing,
        work,
        work,
        work,
        work,
        work,
        work,
        mstep_main=int(main.max().item()),
        mstep_ice=int(ice.max().item()),
        dtcld=20.0,
        params=default_substep_advection_params(),
        mstep_col_main=main,
        mstep_col_ice=ice,
    )
    selected = (
        out.state.qr[0, 1] + out.rain_increment[0]
        if species == "rain"
        else out.state.qi[0, 1]
    )
    grad = torch.autograd.grad(selected, moment)[0][0]
    return selected.detach(), grad.detach()


def test_skipped_main_and_ice_steps_have_identity_tangent():
    for dtype in (torch.float32, torch.float64):
        for species in ("rain", "ice"):
            one_value, one_grad = _case(species=species, columns=1, dtype=dtype)
            two_value, two_grad = _case(species=species, columns=2, dtype=dtype)
            if not torch.equal(one_value, two_value):
                raise AssertionError("skipped-column forward differs from one-column value")
            if not torch.equal(one_grad, two_grad):
                raise AssertionError("skipped-column tangent differs from identity carry")
