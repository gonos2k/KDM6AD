"""sedimentation oracle 검증 — Step E1, E2."""
from __future__ import annotations

import math

import torch

from kdm6 import constants as c
from kdm6.sedimentation import (
    IceSubstepOutputs,
    IceSubstepState,
    SubstepAdvectionOutputs,
    SubstepAdvectionParams,
    SubstepAdvectionState,
    SurfaceAccumOutputs,
    default_substep_advection_params,
    ice_substep_advection_torch,
    normalize_work_by_delz_torch,
    substep_advection_torch,
    surface_accumulation_torch,
)


def test_normalize_work_basic():
    """work / delz."""
    work = torch.tensor([[2.0, 4.0]], dtype=torch.float64)
    delz = torch.tensor([[100.0, 200.0]], dtype=torch.float64)
    out = normalize_work_by_delz_torch(work, delz)
    expected = torch.tensor([[0.02, 0.02]], dtype=torch.float64)
    assert torch.allclose(out, expected)


def test_normalize_work_protects_zero_delz():
    """delz=0 → no NaN (clamped by qcrmin)."""
    work = torch.tensor([[1.0]], dtype=torch.float64)
    delz = torch.tensor([[0.0]], dtype=torch.float64)
    out = normalize_work_by_delz_torch(work, delz)
    assert torch.isfinite(out).all()


# ─── E2: substep advection ───────────────────────────────────────────────────


def _adv_inputs(*, requires_grad: bool = False, K: int = 4):
    """B=1, K=4 (top→bottom). 모든 species 동일 초기 분포."""
    dtype = torch.float64
    qr = torch.full((1, K), 1.0e-3, dtype=dtype, requires_grad=requires_grad)
    nr = torch.full((1, K), 1.0e6, dtype=dtype, requires_grad=requires_grad)
    qs = torch.full((1, K), 5.0e-4, dtype=dtype, requires_grad=requires_grad)
    qg = torch.full((1, K), 5.0e-4, dtype=dtype, requires_grad=requires_grad)
    brs = torch.full((1, K), 1.0e-6, dtype=dtype, requires_grad=requires_grad)
    state = SubstepAdvectionState(qr=qr, nr=nr, qs=qs, qg=qg, brs=brs)
    fall_zero = torch.zeros((1, K), dtype=dtype)
    work1_qr = torch.full((1, K), 1.0e-3, dtype=dtype)  # already /delz
    workn_qr = torch.full((1, K), 1.0e-3, dtype=dtype)
    work1_qs = torch.full((1, K), 5.0e-4, dtype=dtype)
    work1_qg = torch.full((1, K), 8.0e-4, dtype=dtype)
    delz = torch.full((1, K), 500.0, dtype=dtype)
    dend = torch.full((1, K), 1.1 * 500.0, dtype=dtype)  # den * delz
    return (
        state, fall_zero, fall_zero.clone(), fall_zero.clone(),
        fall_zero.clone(), fall_zero.clone(),
        work1_qr, workn_qr, work1_qs, work1_qg, delz, dend,
    )


def test_substep_advection_state_nonneg():
    """모든 state 텐서는 substep 후 non-negative."""
    p = default_substep_advection_params()
    inputs = _adv_inputs()
    out = substep_advection_torch(*inputs, mstep=1, dtcld=60.0, params=p)
    s = out.state
    for x, name in [(s.qr, "qr"), (s.nr, "nr"), (s.qs, "qs"), (s.qg, "qg"), (s.brs, "brs")]:
        assert torch.all(x >= 0), name


def test_substep_advection_top_cell_loses_mass():
    """Top cell (k=0)은 위에서 들어오는 flux 없으므로 mass 감소."""
    p = default_substep_advection_params()
    inputs = _adv_inputs()
    state_in = inputs[0]
    out = substep_advection_torch(*inputs, mstep=1, dtcld=60.0, params=p)
    # Top cell loses some qr (work1_qr > 0 → falk > 0 → qr decrease)
    assert torch.all(out.state.qr[:, 0] < state_in.qr[:, 0])


def test_substep_advection_fall_accumulates():
    """fall_qr는 falk 합이라 양수."""
    p = default_substep_advection_params()
    inputs = _adv_inputs()
    out = substep_advection_torch(*inputs, mstep=1, dtcld=60.0, params=p)
    assert torch.all(out.fall_qr >= 0)
    assert torch.all(out.fall_qs >= 0)
    assert torch.all(out.fall_qg >= 0)


def test_substep_advection_mstep_scaling():
    """mstep 클수록 한 substep의 변화 작음 (1/mstep 비례)."""
    p = default_substep_advection_params()
    inputs1 = _adv_inputs()
    inputs2 = _adv_inputs()
    out1 = substep_advection_torch(*inputs1, mstep=1, dtcld=60.0, params=p)
    out2 = substep_advection_torch(*inputs2, mstep=10, dtcld=60.0, params=p)
    # 한 substep에서 mstep=10이 mstep=1보다 더 적게 변화 (top cell)
    delta1 = (inputs1[0].qr[:, 0] - out1.state.qr[:, 0]).abs()
    delta2 = (inputs2[0].qr[:, 0] - out2.state.qr[:, 0]).abs()
    assert torch.all(delta2 < delta1)


def test_substep_advection_grad_finite():
    """state inputs에 대해 backward 통과."""
    p = default_substep_advection_params()
    inputs = _adv_inputs(requires_grad=True)
    state_in = inputs[0]
    out = substep_advection_torch(*inputs, mstep=2, dtcld=60.0, params=p)
    loss = out.state.qr.sum() + out.state.qs.sum() + out.fall_qr.sum()
    loss.backward()
    for x, name in [(state_in.qr, "qr"), (state_in.qs, "qs")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


# ─── E4: ice substep ──────────────────────────────────────────────────────────


def _ice_inputs(*, requires_grad: bool = False, K: int = 4):
    dtype = torch.float64
    qi = torch.full((1, K), 1.0e-5, dtype=dtype, requires_grad=requires_grad)
    ni = torch.full((1, K), 1.0e5, dtype=dtype, requires_grad=requires_grad)
    state = IceSubstepState(qi=qi, ni=ni)
    fall_zero = torch.zeros((1, K), dtype=dtype)
    work1_qi = torch.full((1, K), 5.0e-4, dtype=dtype)
    workn_qi = torch.full((1, K), 5.0e-4, dtype=dtype)
    delz = torch.full((1, K), 500.0, dtype=dtype)
    dend = torch.full((1, K), 1.1 * 500.0, dtype=dtype)
    return state, fall_zero, fall_zero.clone(), work1_qi, workn_qi, delz, dend


def test_ice_substep_state_nonneg():
    p = default_substep_advection_params()
    inputs = _ice_inputs()
    out = ice_substep_advection_torch(*inputs, mstep=1, dtcld=60.0, params=p)
    assert torch.all(out.state.qi >= 0)
    assert torch.all(out.state.ni >= 0)


def test_ice_substep_top_loses_mass():
    p = default_substep_advection_params()
    inputs = _ice_inputs()
    state_in = inputs[0]
    out = ice_substep_advection_torch(*inputs, mstep=1, dtcld=60.0, params=p)
    assert torch.all(out.state.qi[:, 0] < state_in.qi[:, 0])


def test_ice_substep_grad_finite():
    """qi, ni 모두 backward 통과 — ni는 fall_ni 경로로 graph 들어감."""
    p = default_substep_advection_params()
    inputs = _ice_inputs(requires_grad=True)
    state_in = inputs[0]
    out = ice_substep_advection_torch(*inputs, mstep=2, dtcld=60.0, params=p)
    loss = out.state.qi.sum() + out.state.ni.sum() + out.fall_qi.sum() + out.fall_ni.sum()
    loss.backward()
    for x, name in [(state_in.qi, "qi"), (state_in.ni, "ni")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


# ─── E5: surface accumulation ─────────────────────────────────────────────────


def test_surface_accum_basic():
    """fall sum × delz / denr × dtcld × 1000 (mm)."""
    fall_qr = torch.tensor([1.0e-3, 0.0], dtype=torch.float64)
    fall_qs = torch.tensor([2.0e-4, 0.0], dtype=torch.float64)
    fall_qg = torch.tensor([5.0e-4, 0.0], dtype=torch.float64)
    fall_qi = torch.tensor([1.0e-4, 0.0], dtype=torch.float64)
    delz = torch.tensor([500.0, 500.0], dtype=torch.float64)
    out = surface_accumulation_torch(
        fall_qr, fall_qs, fall_qg, fall_qi, delz, dtcld=60.0
    )
    fallsum = fall_qr + fall_qs + fall_qg + fall_qi
    expected_rain = fallsum * 500.0 / 1000.0 * 60.0 * 1000.0
    assert torch.allclose(out.rain_increment, expected_rain, rtol=1e-12)


def test_surface_accum_decomposition():
    """rain = qr+qs+qg+qi 합. snow = qs+qi. graupel = qg."""
    fall_qr = torch.tensor([1.0e-3], dtype=torch.float64)
    fall_qs = torch.tensor([2.0e-4], dtype=torch.float64)
    fall_qg = torch.tensor([5.0e-4], dtype=torch.float64)
    fall_qi = torch.tensor([1.0e-4], dtype=torch.float64)
    delz = torch.tensor([500.0], dtype=torch.float64)
    out = surface_accumulation_torch(
        fall_qr, fall_qs, fall_qg, fall_qi, delz, dtcld=60.0
    )
    factor = 500.0 / 1000.0 * 60.0 * 1000.0
    assert torch.allclose(out.rain_increment, (fall_qr + fall_qs + fall_qg + fall_qi) * factor)
    assert torch.allclose(out.snow_increment, (fall_qs + fall_qi) * factor)
    assert torch.allclose(out.graupel_increment, fall_qg * factor)


def test_surface_accum_grad_finite():
    fall_qr = torch.tensor([1.0e-3], dtype=torch.float64, requires_grad=True)
    fall_qs = torch.tensor([2.0e-4], dtype=torch.float64, requires_grad=True)
    fall_qg = torch.tensor([5.0e-4], dtype=torch.float64, requires_grad=True)
    fall_qi = torch.tensor([1.0e-4], dtype=torch.float64, requires_grad=True)
    delz = torch.tensor([500.0], dtype=torch.float64)
    out = surface_accumulation_torch(
        fall_qr, fall_qs, fall_qg, fall_qi, delz, dtcld=60.0
    )
    loss = out.rain_increment.sum() + out.snow_increment.sum() + out.graupel_increment.sum()
    loss.backward()
    for x in (fall_qr, fall_qs, fall_qg, fall_qi):
        assert x.grad is not None and torch.isfinite(x.grad).all()
