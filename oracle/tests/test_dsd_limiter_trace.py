"""Focused tests for the opt-in final DSD limiter decision trace."""
from __future__ import annotations

import torch

from kdm6 import constants as c, fconst
from kdm6.coordinator import CoordinatorState, apply_dsd_number_limiters_torch
from kdm6.sensitivity_diagnostics import SensitivityTrace


def _state(qc, qr, qi, nc, nr, ni):
    z = torch.zeros_like(qc)
    return CoordinatorState(
        qv=z, qc=qc, qr=qr, qs=z, qg=z, qi=qi, nc=nc, nr=nr, ni=ni,
        brs=z, t=torch.full_like(qc, 260.0),
    )


def _mask(record, label):
    i = record.metadata["branch_labels"].index(label)
    return record.branch[i]


def test_final_dsd_trace_covers_inner_decisions_and_pre_cap_operands():
    dtype = torch.float64
    den = torch.ones((1, 5), dtype=dtype)
    q_r = torch.tensor([[0.0, 1.0e-4, 1.0e-4, 1.0e-2, 1.0e-2]], dtype=dtype)
    q_c = torch.tensor([[0.0, 1.0e-3, 1.0e-3, 1.0e-3, 1.0e-2]], dtype=dtype)
    q_i = q_c.clone()
    mid_r = (c.LAMDARMIN + c.LAMDARMAX) / 2.0
    small_r = c.LAMDARMIN * 0.5
    large_r = c.LAMDARMAX * 2.0
    n_r = torch.tensor([[1.0e3, q_r[0, 1] * mid_r ** c.DMR / fconst.PIDNR,
                         q_r[0, 2] * small_r ** c.DMR / fconst.PIDNR,
                         q_r[0, 3] * large_r ** c.DMR / fconst.PIDNR, 1.0e12]], dtype=dtype)
    mid_c = (c.LAMDACMIN + c.LAMDACMAX) / 2.0
    small_c = c.LAMDACMIN * 0.5
    n_c = torch.tensor([[1.0e3, q_c[0, 1] * mid_c ** c.DMC / fconst.PIDNC,
                         q_c[0, 2] * small_c ** c.DMC / fconst.PIDNC,
                         1.0e-3, q_c[0, 4] * mid_c ** c.DMC / fconst.PIDNC]], dtype=dtype)
    mid_i = (c.LAMDAIMIN + c.LAMDAIMAX) / 2.0
    small_i = c.LAMDAIMIN * 0.5
    large_i = c.LAMDAIMAX * 2.0
    n_i = torch.tensor([[1.0e3, q_i[0, 1] * mid_i ** c.DMI / fconst.PIDNI,
                         q_i[0, 2] * small_i ** c.DMI / fconst.PIDNI,
                         q_i[0, 3] * small_i ** c.DMI / fconst.PIDNI,
                         q_i[0, 4] * large_i ** c.DMI / fconst.PIDNI]], dtype=dtype)
    state = _state(q_c, q_r, q_i, n_c, n_r, n_i)
    floor = torch.tensor([[0.01, 0.01, 0.01, 0.01, 0.01]], dtype=dtype)

    plain = apply_dsd_number_limiters_torch(state, den, ncmin_tensor=floor)
    trace = SensitivityTrace()
    traced = apply_dsd_number_limiters_torch(
        state, den, ncmin_tensor=floor, diagnostic_trace=trace,
        diagnostic_step=3, diagnostic_dtcld=6.0)
    for field in state._fields:
        assert torch.equal(getattr(plain, field), getattr(traced, field)), field
    record = trace.by_name("dsd_limiter")[0]
    assert record.metadata["kind"] == "applied_transfer"
    assert record.step == 3 and record.dtcld == 6.0
    assert _mask(record, "rain_active").tolist() == [[False, True, True, True, True]]
    assert _mask(record, "rain_too_small").tolist() == [[False, False, True, False, False]]
    assert _mask(record, "rain_too_large").tolist() == [[False, False, False, True, True]]
    assert _mask(record, "cloud_final_ncmin_gate").tolist() == [[True, True, True, False, True]]
    assert _mask(record, "cloud_absolute_cap")[0, 4]
    assert _mask(record, "ice_too_small")[0, 2]
    assert _mask(record, "ice_too_large")[0, 4]
    assert record.operands["cloud_absolute_cap_input"][0, 4] < traced.nc[0, 4]
    assert not torch.equal(record.operands["cloud_absolute_cap_input"], traced.nc)
    assert record.as_dict()["operands"]["cloud_absolute_cap_input"]["finite"]


def test_final_dsd_trace_distinguishes_inner_snap_from_final_ncmin_gate():
    qi = torch.full((1, 3), 1.0e-3, dtype=torch.float64)
    ni = torch.tensor([[50.0, 100.0, 1.0e-3]], dtype=torch.float64)
    floor = torch.tensor([[10.0, 100.0, 100.0]], dtype=torch.float64)
    z = torch.zeros_like(qi)
    state = _state(z, z, qi, z, z, ni)
    trace = SensitivityTrace()
    out = apply_dsd_number_limiters_torch(
        state, torch.ones_like(qi), ncmin_tensor=floor, diagnostic_trace=trace)
    record = trace.by_name("dsd_limiter")[0]
    assert _mask(record, "ice_active").tolist() == [[True, True, True]]
    assert _mask(record, "ice_final_ncmin_gate").tolist() == [[True, True, False]]
    assert torch.equal(out.ni[0, 2], ni[0, 2])
    assert out.ni[0, 0] != ni[0, 0] and out.ni[0, 1] != ni[0, 1]
