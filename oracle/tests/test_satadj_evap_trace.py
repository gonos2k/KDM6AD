"""Focused coverage for the satadj complete-evaporation branch tap.

The qc=0 rows exercise the bare-equality numerical contract, including signed
zero; they are boundary checks, not claims about a populated hydrometeor or a
reachable full-step atmospheric state.
"""
from __future__ import annotations

import pytest
import torch

from kdm6.coordinator import (
    CoordinatorForcing,
    CoordinatorState,
    apply_satadj_step_torch,
    default_coordinator_params,
    default_warm_phase_params,
)
from kdm6.sensitivity_diagnostics import SensitivityTrace
from kdm6.thermo import compute_qs_water


def _z(value: float, *, requires_grad: bool = False) -> torch.Tensor:
    return torch.full((1, 1), value, dtype=torch.float64, requires_grad=requires_grad)


def _fixture(*, qv_offset: float, qc: float, nc_requires_grad: bool = False):
    state = CoordinatorState(
        qv=_z(0.0), qc=_z(qc), qr=_z(0.0), qs=_z(0.0), qg=_z(0.0), qi=_z(0.0),
        nc=_z(1.0e6, requires_grad=nc_requires_grad), nr=_z(0.0), ni=_z(0.0),
        brs=_z(0.0), t=_z(290.0),
    )
    forcing = CoordinatorForcing(
        p=_z(9.0e4), den=_z(1.0), delz=_z(500.0), dend=_z(1.0),
    )
    thermo_params = default_coordinator_params().thermo
    qs1 = compute_qs_water(state.t, forcing.p, params=thermo_params)
    return state._replace(qv=qs1 + _z(qv_offset)), forcing, thermo_params


def _run(*, qv_offset: float, qc: float, nc_requires_grad: bool = False):
    state, forcing, thermo_params = _fixture(
        qv_offset=qv_offset, qc=qc, nc_requires_grad=nc_requires_grad,
    )
    trace = SensitivityTrace()
    out, nccn_out = apply_satadj_step_torch(
        state, forcing, _z(2.5e6), _z(1004.0),
        default_warm_phase_params().satadj, thermo_params,
        dtcld=6.0, nccn=_z(1.0e9), diagnostic_trace=trace,
    )
    return state, out, nccn_out, trace.by_name("satadj")[0]


@pytest.mark.parametrize(
    ("qv_offset", "qcs", "expected_pcond", "expected_nc_deriv", "expected_nccn_deriv"),
    [
        (-1.0e-5, (1.0e-6, 1.0e-3), True, (0.0, 1.0), (1.0, 0.0)),
        (0.0, (0.0, 1.0e-3), False, (0.0, 1.0), (1.0, 0.0)),
    ],
)
def test_satadj_complete_evap_branch_and_number_transfer(
    qv_offset, qcs, expected_pcond, expected_nc_deriv, expected_nccn_deriv,
):
    members = [
        _run(qv_offset=qv_offset, qc=qc, nc_requires_grad=True)
        for qc in qcs
    ]
    first, second = members
    r0, r1 = first[3], second[3]

    assert torch.equal(r0.branch[:2], r1.branch[:2])
    assert bool(r0.branch[0].item()) is expected_pcond
    assert bool(r1.branch[0].item()) is expected_pcond
    assert bool(r0.branch[1].item()) is False
    assert bool(r1.branch[1].item()) is False
    assert bool(r0.branch[2].item()) is True
    assert bool(r1.branch[2].item()) is False

    # The equality gate is the applied NC→NCCN transfer, not a diagnostic proxy.
    assert torch.equal(first[1].nc, _z(0.0))
    assert torch.equal(second[1].nc, _z(1.0e6))
    assert torch.equal(first[2], _z(1.001e9))
    assert torch.equal(second[2], _z(1.0e9))

    d_nc = []
    d_nccn = []
    for state, out, nccn_out, _ in members:
        d_nc.append(torch.autograd.grad(out.nc, state.nc, retain_graph=True)[0])
        d_nccn.append(torch.autograd.grad(nccn_out, state.nc)[0])
    assert torch.equal(d_nc[0], _z(expected_nc_deriv[0]))
    assert torch.equal(d_nc[1], _z(expected_nc_deriv[1]))
    assert torch.equal(d_nccn[0], _z(expected_nccn_deriv[0]))
    assert torch.equal(d_nccn[1], _z(expected_nccn_deriv[1]))


def test_satadj_complete_evap_qc_signed_zero_uses_exact_equality():
    state, out, nccn_out, record = _run(qv_offset=0.0, qc=0.0)
    target = -state.qc / 6.0

    assert torch.equal(record.operands["pcond"], target)
    assert bool(torch.signbit(target).item())
    assert not bool(torch.signbit(record.operands["pcond"]).item())
    assert bool(record.branch[2].item())
    assert torch.equal(out.nc, _z(0.0))
    assert torch.equal(nccn_out, _z(1.001e9))

    negative_zero = _z(-0.0)
    assert bool(torch.signbit(negative_zero).item())
    state_negzero = state._replace(qc=negative_zero)
    trace = SensitivityTrace()
    out_negzero, nccn_negzero = apply_satadj_step_torch(
        state_negzero,
        CoordinatorForcing(p=_z(9.0e4), den=_z(1.0), delz=_z(500.0), dend=_z(1.0)),
        _z(2.5e6), _z(1004.0), default_warm_phase_params().satadj,
        default_coordinator_params().thermo, dtcld=6.0, nccn=_z(1.0e9),
        diagnostic_trace=trace,
    )
    record_negzero = trace.by_name("satadj")[0]
    assert torch.equal(record_negzero.operands["pcond"], -state_negzero.qc / 6.0)
    assert bool(record_negzero.branch[2].item())
    assert torch.equal(out_negzero.nc, _z(0.0))
    assert torch.equal(nccn_negzero, _z(1.001e9))
