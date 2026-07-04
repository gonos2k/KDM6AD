"""ProgB_param oracle 검증.

slope.py 테스트와 같은 패턴: 파라미터 finite, 비활성 게이트의 zero-branch,
활성 셀의 grad finite, density clamp 동작."""
from __future__ import annotations

import math

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
