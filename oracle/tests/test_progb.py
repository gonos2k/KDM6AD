"""ProgB_param oracle 검증.

slope.py 테스트와 같은 패턴: 파라미터 finite, 비활성 게이트의 zero-branch,
활성 셀의 grad finite, density clamp 동작."""
from __future__ import annotations

import math

import pytest
import torch

from kdm6.progb import (
    AVTG_TABLE,
    BRS_MIN,
    BVTG_TABLE,
    DENSITY_TABLE,
    ProgBOutputs,
    RHO_MAX,
    RHO_MID,
    RHO_MIN,
    default_progb_params,
    progb_param_torch,
)


def _active_inputs(*, requires_grad: bool = False) -> tuple[torch.Tensor, torch.Tensor]:
    """rhox in (200, 800) 범위에 들어오도록 두 셀 구성."""
    dtype = torch.float64
    qg = torch.tensor([[3.0e-4, 5.0e-4]], dtype=dtype, requires_grad=requires_grad)
    bg = torch.tensor([[1.0e-6, 1.0e-6]], dtype=dtype, requires_grad=requires_grad)
    return qg, bg


# ─── default_progb_params ─────────────────────────────────────────────────────


def test_default_progb_params_finite_and_nonnegative():
    """모든 파라미터 finite. 대부분 양수이지만 `mug=0`(snow/graupel 기본)은 valid."""
    params = default_progb_params()
    strictly_positive = {"qcrmin", "dmg", "n0g", "g1pdgmg", "g1pmg", "rslopegmax"}
    for field in params._fields:
        value = getattr(params, field)
        assert math.isfinite(value), field
        assert value >= 0.0, field
        if field in strictly_positive:
            assert value > 0.0, field


def test_default_progb_params_g1pmg_mug_zero():
    """Fortran의 mug==0 special case: g1pmg=1 정확히."""
    params = default_progb_params()
    if params.mug == 0.0:
        assert params.g1pmg == 1.0


# review7#5 hardcoded regression: _rgmma_tensor=Γ 부호 영구 보호.


def test_progb_rgmma_tensor_returns_gamma():
    """`_rgmma_tensor`는 Γ(x), 1/Γ(x) 아님. review6 audit 후 부호 fix 검증."""
    import math
    from kdm6.progb import _rgmma_tensor
    x = torch.tensor([1.0, 2.0, 3.0, 4.0, 5.0], dtype=torch.float64)
    out = _rgmma_tensor(x)
    # Γ(1)=1, Γ(2)=1, Γ(3)=2, Γ(4)=6, Γ(5)=24
    expected = torch.tensor([1.0, 1.0, 2.0, 6.0, 24.0], dtype=torch.float64)
    assert torch.allclose(out, expected, rtol=1e-12), (
        f"_rgmma_tensor must compute Γ(x) (not 1/Γ); got {out.tolist()}"
    )


# ─── inactive gate → branch zero ──────────────────────────────────────────────


def test_progb_inactive_branches_to_zero():
    """qg <= qcrmin AND bg <= brs_min → 모든 *derived* 출력 0."""
    params = default_progb_params()
    shape = (1, 4)
    dtype = torch.float64
    qg = torch.zeros(shape, dtype=dtype)
    bg = torch.zeros(shape, dtype=dtype)

    out = progb_param_torch(qg, bg, params=params)
    zero = torch.zeros(shape, dtype=dtype)

    # cmg 계열 derived 출력들은 0
    assert torch.allclose(out.cmg, zero)
    assert torch.allclose(out.pidn0g, zero)
    assert torch.allclose(out.avtg, zero)
    assert torch.allclose(out.bvtg, zero)
    assert torch.allclose(out.pvtg, zero)
    assert torch.allclose(out.precg2, zero)
    assert torch.allclose(out.rslopegbmax, zero)
    assert torch.allclose(out.g1pbg, zero)

    # rhox는 default RHO_MID로 채워져서 후행 모듈이 division-by-zero를 만나지 않음.
    # bg는 입력 보존 (Fortran: INTENT(INOUT) 미갱신).
    assert torch.allclose(out.rhox, torch.full_like(qg, RHO_MID))
    assert torch.allclose(out.bg, bg)


def test_progb_midpoint_trace_positive_bundle_and_branch_derivative():
    """Opt-in positive inactive trace uses the midpoint bundle and local AD branch."""
    params = default_progb_params()
    qg = torch.tensor([[0.5 * params.qcrmin]], dtype=torch.float64, requires_grad=True)
    bg = torch.zeros_like(qg)

    out = progb_param_torch(qg, bg, params=params, midpoint_trace=True)

    assert out.rhox.item() == RHO_MID
    assert out.bg.item() == qg.item() / RHO_MID
    assert out.cmg.item() == math.pi * RHO_MID / 6.0
    assert out.avtg.item() == AVTG_TABLE[3]
    assert out.bvtg.item() == BVTG_TABLE[3]
    assert out.pidn0g.item() > 0.0
    assert out.precg2.item() > 0.0

    dqg = torch.autograd.grad(out.bg.sum(), qg, retain_graph=True)[0]
    drhox = torch.autograd.grad(out.rhox.sum(), qg)[0]
    assert dqg.item() == 1.0 / RHO_MID
    assert drhox.item() == 0.0


def test_progb_midpoint_trace_empty_clears_bundle_without_hidden_zero_division():
    """Opt-in inactive nonpositive qg returns an all-zero bundle and finite backward."""
    params = default_progb_params()
    qg = torch.tensor([[0.0, -1.0e-16]], dtype=torch.float64, requires_grad=True)
    bg = torch.zeros_like(qg)

    out = progb_param_torch(qg, bg, params=params, midpoint_trace=True)

    for value in out:
        assert torch.isfinite(value).all()
    assert torch.equal(out.rhox, torch.zeros_like(qg))
    assert torch.equal(out.bg, torch.zeros_like(qg))
    for name, value in zip(out._fields[2:], out[2:]):
        assert torch.equal(value, torch.zeros_like(qg)), name
    sum(value.sum() for value in out).backward()
    assert qg.grad is not None and torch.isfinite(qg.grad).all()


def test_progb_midpoint_trace_nan_takes_native_empty_branch():
    """Fortran's `qg > 0` is false for NaN in the inactive branch."""
    params = default_progb_params()
    qg = torch.tensor([[float("nan")]], dtype=torch.float64)
    out = progb_param_torch(qg, torch.zeros_like(qg), params=params,
                            midpoint_trace=True)
    assert out.rhox.item() == 0.0
    assert out.bg.item() == 0.0
    assert all(torch.isfinite(value).all() for value in out)


@pytest.mark.parametrize("dtype", [torch.float32, torch.float64])
def test_progb_midpoint_trace_cleans_inactive_nan_volume_without_hidden_grad(dtype):
    params = default_progb_params()
    qg = torch.tensor([[0.5 * params.qcrmin, 0.0]], dtype=dtype, requires_grad=True)
    bg = torch.full_like(qg, float("nan"), requires_grad=True)
    out = progb_param_torch(qg, bg, params=params, midpoint_trace=True)
    assert all(torch.isfinite(value).all() for value in out)
    assert out.rhox[0, 0].item() == RHO_MID
    assert out.rhox[0, 1].item() == 0.0
    loss = sum(value.sum() for value in out)
    dqg, dbg = torch.autograd.grad(loss, (qg, bg))
    assert torch.isfinite(dqg).all()
    assert torch.isfinite(dbg).all()


def test_progb_midpoint_trace_keeps_active_path_identical():
    """The opt-in affects only the inactive gate; active outputs stay exact."""
    params = default_progb_params()
    qg, bg = _active_inputs()
    legacy = progb_param_torch(qg, bg, params=params)
    opted = progb_param_torch(qg, bg, params=params, midpoint_trace=True)

    for name, expected, actual in zip(legacy._fields, legacy, opted):
        assert torch.equal(actual, expected), name


def test_progb_midpoint_trace_tiny_positive_depends_on_input_dtype():
    """A positive f64 trace can underflow to the empty f32 branch at input storage."""
    params = default_progb_params()
    qg64 = torch.tensor([[1.0e-50]], dtype=torch.float64)
    bg64 = torch.zeros_like(qg64)
    out64 = progb_param_torch(qg64, bg64, params=params, midpoint_trace=True)
    assert out64.rhox.item() == RHO_MID
    assert out64.bg.item() > 0.0

    qg32 = torch.tensor([[1.0e-50]], dtype=torch.float32)
    bg32 = torch.zeros_like(qg32)
    out32 = progb_param_torch(qg32, bg32, params=params, midpoint_trace=True)
    assert qg32.item() == 0.0
    assert out32.rhox.item() == 0.0
    assert out32.bg.item() == 0.0


# ─── density clamp ────────────────────────────────────────────────────────────


def test_progb_density_clamp_low():
    """rhox < RHO_MIN → RHO_MIN으로 clamp."""
    params = default_progb_params()
    dtype = torch.float64
    # rhox_raw = qg/bg = 50 (< 100). Active이므로 clamp 결과 100.
    qg = torch.tensor([[5.0e-4]], dtype=dtype)
    bg = torch.tensor([[1.0e-5]], dtype=dtype)
    out = progb_param_torch(qg, bg, params=params)
    assert torch.allclose(out.rhox, torch.full_like(qg, RHO_MIN))


def test_progb_density_clamp_high():
    """rhox > RHO_MAX → RHO_MAX으로 clamp."""
    params = default_progb_params()
    dtype = torch.float64
    # rhox_raw = qg/bg = 1000 (> 900). clamp 결과 900.
    qg = torch.tensor([[1.0e-3]], dtype=dtype)
    bg = torch.tensor([[1.0e-6]], dtype=dtype)
    out = progb_param_torch(qg, bg, params=params)
    assert torch.allclose(out.rhox, torch.full_like(qg, RHO_MAX))

    # rhox==900 → table interp endpoint
    assert torch.allclose(out.avtg, torch.full_like(qg, AVTG_TABLE[-1]))
    assert torch.allclose(out.bvtg, torch.full_like(qg, BVTG_TABLE[-1]))


# ─── 9-point linear interpolation ─────────────────────────────────────────────


def test_progb_table_interp_at_node_points():
    """rhox가 정확히 Tbl[i]일 때 (avtg, bvtg)는 (aTbl[i], bTbl[i])."""
    params = default_progb_params()
    dtype = torch.float64
    # 각 노드 i에 대해 qg/bg = Tbl[i] (그리고 rhox in clamp range)가 되도록 구성.
    # 단순화: bg=1e-6, qg=Tbl[i]*1e-6 (rhox = Tbl[i]).
    for i, rho_node in enumerate(DENSITY_TABLE):
        qg = torch.tensor([[rho_node * 1.0e-6]], dtype=dtype)
        bg = torch.tensor([[1.0e-6]], dtype=dtype)
        out = progb_param_torch(qg, bg, params=params)
        assert torch.allclose(out.rhox, torch.full_like(qg, rho_node)), f"rhox at node {i}"
        assert torch.allclose(out.avtg, torch.full_like(qg, AVTG_TABLE[i])), f"avtg at node {i}"
        assert torch.allclose(out.bvtg, torch.full_like(qg, BVTG_TABLE[i])), f"bvtg at node {i}"


def test_progb_table_interp_midpoint():
    """rhox=250 (Tbl[1]=200과 Tbl[2]=300의 중점) → avtg, bvtg가 산술평균."""
    params = default_progb_params()
    dtype = torch.float64
    qg = torch.tensor([[2.5e-4]], dtype=dtype)
    bg = torch.tensor([[1.0e-6]], dtype=dtype)
    out = progb_param_torch(qg, bg, params=params)

    expected_a = 0.5 * (AVTG_TABLE[1] + AVTG_TABLE[2])
    expected_b = 0.5 * (BVTG_TABLE[1] + BVTG_TABLE[2])
    assert torch.allclose(out.rhox, torch.full_like(qg, 250.0))
    assert torch.allclose(out.avtg, torch.full_like(qg, expected_a))
    assert torch.allclose(out.bvtg, torch.full_like(qg, expected_b))


def test_progb_table_node_ad_matches_selected_one_sided_fd():
    """At rho=500, AD follows the right=True (upper-density) table segment."""
    params = default_progb_params()
    dtype = torch.float64
    qg = torch.tensor([[1.0e-4]], dtype=dtype)
    bg = torch.tensor([[2.0e-7]], dtype=dtype, requires_grad=True)  # qg/bg = 500
    out = progb_param_torch(qg, bg, params=params)
    direction = torch.tensor([[-1.0e-8]], dtype=dtype)  # decrease bg -> rho > 500
    ad = torch.autograd.grad(out.avtg, bg, retain_graph=True)[0] * direction
    epsilon = 1.0e-6
    plus = progb_param_torch(qg, bg.detach() + epsilon * direction,
                             params=params).avtg
    fd = (plus - out.avtg.detach()) / epsilon
    assert torch.allclose(ad, fd, rtol=1.0e-6, atol=1.0e-10)

    # The opposite side is a different linear segment; central FD must not be
    # used as the acceptance oracle at this exact table knot.
    minus = progb_param_torch(qg, bg.detach() - epsilon * direction,
                              params=params).avtg
    opposite = (out.avtg.detach() - minus) / epsilon
    assert not torch.allclose(fd, opposite, rtol=1.0e-2, atol=1.0e-3)


# ─── grad finite (active 셀) ──────────────────────────────────────────────────


def test_progb_grad_finite_active_cells():
    """active 셀에서 모든 출력의 합이 qg, bg에 대해 finite gradient."""
    params = default_progb_params()
    qg, bg = _active_inputs(requires_grad=True)

    out = progb_param_torch(qg, bg, params=params)

    # 모든 출력이 finite
    for tensor in out:
        assert torch.isfinite(tensor).all()

    loss = sum(t.sum() for t in out)
    loss.backward()

    assert qg.grad is not None
    assert bg.grad is not None
    assert torch.isfinite(qg.grad).all()
    assert torch.isfinite(bg.grad).all()


def test_progb_grad_finite_inactive_cells():
    """inactive 셀에서도 backward가 finite (NaN/Inf 차단 검증)."""
    params = default_progb_params()
    dtype = torch.float64
    qg = torch.zeros((1, 3), dtype=dtype, requires_grad=True)
    bg = torch.zeros((1, 3), dtype=dtype, requires_grad=True)

    out = progb_param_torch(qg, bg, params=params)
    loss = sum(t.sum() for t in out)
    loss.backward()

    assert qg.grad is not None and torch.isfinite(qg.grad).all()
    assert bg.grad is not None and torch.isfinite(bg.grad).all()


# ─── consistency: bg = qg / rhox after update (active) ─────────────────────────


def test_progb_bg_consistency_after_update():
    """active 셀의 bg_out = qg / rhox_clamped."""
    params = default_progb_params()
    qg, bg = _active_inputs(requires_grad=False)
    out = progb_param_torch(qg, bg, params=params)
    expected_bg = qg / out.rhox
    assert torch.allclose(out.bg, expected_bg)
