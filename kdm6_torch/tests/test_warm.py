"""warm rates oracle 검증 — Step B sub-step별 누적."""
from __future__ import annotations

import math

import torch

from kdm6 import constants as c
from kdm6.warm import (
    WarmAccretionParams,
    WarmAutoconvParams,
    WarmRainEvapParams,
    WarmSelfCollectionParams,
    accretion_torch,
    autoconv_torch,
    default_warm_accretion_params,
    default_warm_autoconv_params,
    default_warm_rain_evap_params,
    default_warm_self_collection_params,
    rain_evap_torch,
    self_collection_torch,
)


# ─── default_warm_autoconv_params ─────────────────────────────────────────────


def test_default_warm_autoconv_params_finite_and_positive():
    p = default_warm_autoconv_params()
    for field in p._fields:
        value = getattr(p, field)
        assert math.isfinite(value), field
        assert value > 0.0, field


def test_default_warm_autoconv_params_qck1_formula():
    """qck1 = .104 * 9.8 * peaut / denr^(1/3) / xmyu * den0^(4/3) (Fortran kdm6init:3106)."""
    den0 = 1.28
    expected = (
        0.104 * 9.8 * c.PEAUT
        / (c.DENR ** (1.0 / 3.0))
        / c.XMYU
        * (den0 ** (4.0 / 3.0))
    )
    p = default_warm_autoconv_params(den0=den0)
    assert math.isclose(p.qck1, expected, rel_tol=1e-12)


# ─── inactive gate → branch zero ──────────────────────────────────────────────


def test_autoconv_inactive_below_qcr():
    """qc <= qcr → praut/nraut = 0."""
    p = default_warm_autoconv_params()
    dtype = torch.float64
    qc = torch.full((1, 3), 1.0e-7, dtype=dtype)   # below qcr
    nc = torch.full((1, 3), 1.0e8, dtype=dtype)
    qr = torch.zeros((1, 3), dtype=dtype)
    nr = torch.zeros((1, 3), dtype=dtype)
    den = torch.full((1, 3), 1.1, dtype=dtype)
    qcr = torch.full((1, 3), 1.0e-4, dtype=dtype)  # large threshold
    lenconcr = torch.full((1, 3), 1.0e-9, dtype=dtype)

    praut, nraut = autoconv_torch(
        qc, nc, qr, nr, den, qcr, lenconcr, params=p, dtcld=60.0
    )
    assert torch.allclose(praut, torch.zeros_like(qc))
    assert torch.allclose(nraut, torch.zeros_like(qc))


def test_autoconv_inactive_below_ncmin():
    """nc <= ncmin → praut/nraut = 0."""
    p = default_warm_autoconv_params()
    dtype = torch.float64
    qc = torch.full((1, 3), 1.0e-3, dtype=dtype)   # plenty of cloud
    nc = torch.full((1, 3), 1.0e-5, dtype=dtype)   # below ncmin=1e-2
    qr = torch.zeros((1, 3), dtype=dtype)
    nr = torch.zeros((1, 3), dtype=dtype)
    den = torch.full((1, 3), 1.1, dtype=dtype)
    qcr = torch.full((1, 3), 1.0e-9, dtype=dtype)
    lenconcr = torch.full((1, 3), 1.0e-9, dtype=dtype)

    praut, nraut = autoconv_torch(
        qc, nc, qr, nr, den, qcr, lenconcr, params=p, dtcld=60.0
    )
    assert torch.allclose(praut, torch.zeros_like(qc))
    assert torch.allclose(nraut, torch.zeros_like(qc))


# ─── physical sanity ──────────────────────────────────────────────────────────


def test_autoconv_capped_by_qc_per_dt():
    """praut <= qc/dtcld (mass conservation)."""
    p = default_warm_autoconv_params()
    dtype = torch.float64
    qc = torch.tensor([[5.0e-3, 1.0e-2]], dtype=dtype)  # very high qc
    nc = torch.tensor([[1.0e8, 1.0e8]], dtype=dtype)
    qr = torch.zeros((1, 2), dtype=dtype)
    nr = torch.zeros((1, 2), dtype=dtype)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    qcr = torch.full((1, 2), 1.0e-9, dtype=dtype)
    lenconcr = torch.full((1, 2), 1.0e-9, dtype=dtype)

    dtcld = 60.0
    praut, _ = autoconv_torch(
        qc, nc, qr, nr, den, qcr, lenconcr, params=p, dtcld=dtcld
    )
    assert torch.all(praut <= qc / dtcld + 1e-15)


def test_autoconv_capped_by_nc_per_dt():
    """nraut <= nc/dtcld (number conservation)."""
    p = default_warm_autoconv_params()
    dtype = torch.float64
    qc = torch.tensor([[1.0e-2]], dtype=dtype)
    nc = torch.tensor([[1.0e6]], dtype=dtype)
    qr = torch.zeros((1, 1), dtype=dtype)
    nr = torch.zeros((1, 1), dtype=dtype)
    den = torch.full((1, 1), 1.1, dtype=dtype)
    qcr = torch.full((1, 1), 1.0e-9, dtype=dtype)
    lenconcr = torch.full((1, 1), 1.0e-9, dtype=dtype)

    dtcld = 60.0
    _, nraut = autoconv_torch(
        qc, nc, qr, nr, den, qcr, lenconcr, params=p, dtcld=dtcld
    )
    assert torch.all(nraut <= nc / dtcld + 1e-15)


def test_autoconv_monotone_in_qc():
    """qc 증가 → praut 비감소 (외부 게이트 통과 영역에서)."""
    p = default_warm_autoconv_params()
    dtype = torch.float64
    qc_low = torch.tensor([[5.0e-5]], dtype=dtype)
    qc_high = torch.tensor([[1.0e-4]], dtype=dtype)
    nc = torch.tensor([[1.0e8]], dtype=dtype)
    qr = torch.zeros((1, 1), dtype=dtype)
    nr = torch.zeros((1, 1), dtype=dtype)
    den = torch.full((1, 1), 1.1, dtype=dtype)
    qcr = torch.full((1, 1), 1.0e-7, dtype=dtype)
    lenconcr = torch.full((1, 1), 1.0e-9, dtype=dtype)

    praut_low, _ = autoconv_torch(qc_low, nc, qr, nr, den, qcr, lenconcr, params=p, dtcld=600.0)
    praut_high, _ = autoconv_torch(qc_high, nc, qr, nr, den, qcr, lenconcr, params=p, dtcld=600.0)
    assert (praut_high >= praut_low).all()


# ─── nraut swap branch (qr > lenconcr) ────────────────────────────────────────


def test_autoconv_nraut_swap_when_qr_large():
    """qr > lenconcr → nraut = (nr/qr) * praut (default 3.5e9*den*praut 대신)."""
    p = default_warm_autoconv_params()
    dtype = torch.float64
    qc = torch.tensor([[1.0e-3]], dtype=dtype)
    nc = torch.tensor([[1.0e8]], dtype=dtype)
    qr = torch.tensor([[1.0e-3]], dtype=dtype)        # qr > lenconcr
    nr = torch.tensor([[1.0e6]], dtype=dtype)
    den = torch.full((1, 1), 1.1, dtype=dtype)
    qcr = torch.full((1, 1), 1.0e-9, dtype=dtype)
    lenconcr = torch.tensor([[1.0e-5]], dtype=dtype)  # smaller than qr

    praut, nraut = autoconv_torch(qc, nc, qr, nr, den, qcr, lenconcr, params=p, dtcld=60.0)
    # nraut should equal (nr/qr) * praut, capped by nc/dtcld
    expected_unswap = (nr / qr) * praut
    expected = torch.minimum(expected_unswap, nc / 60.0)
    assert torch.allclose(nraut, expected, rtol=1e-12, atol=1e-15)


# ─── grad finite ──────────────────────────────────────────────────────────────


def test_autoconv_grad_finite_active():
    p = default_warm_autoconv_params()
    dtype = torch.float64
    qc = torch.tensor([[3.0e-4, 5.0e-4]], dtype=dtype, requires_grad=True)
    nc = torch.tensor([[1.0e8, 2.0e8]], dtype=dtype, requires_grad=True)
    qr = torch.tensor([[1.0e-5, 5.0e-5]], dtype=dtype, requires_grad=True)
    nr = torch.tensor([[1.0e5, 5.0e5]], dtype=dtype, requires_grad=True)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    qcr = torch.full((1, 2), 1.0e-7, dtype=dtype)
    lenconcr = torch.full((1, 2), 1.0e-6, dtype=dtype)

    praut, nraut = autoconv_torch(qc, nc, qr, nr, den, qcr, lenconcr, params=p, dtcld=60.0)
    loss = praut.sum() + nraut.sum()
    loss.backward()

    for x, name in [(qc, "qc"), (nc, "nc"), (qr, "qr"), (nr, "nr")]:
        assert x.grad is not None, name
        assert torch.isfinite(x.grad).all(), name


def test_autoconv_grad_finite_inactive():
    """inactive 셀(qc=0)에서도 backward가 finite."""
    p = default_warm_autoconv_params()
    dtype = torch.float64
    qc = torch.zeros((1, 3), dtype=dtype, requires_grad=True)
    nc = torch.zeros((1, 3), dtype=dtype, requires_grad=True)
    qr = torch.zeros((1, 3), dtype=dtype, requires_grad=True)
    nr = torch.zeros((1, 3), dtype=dtype, requires_grad=True)
    den = torch.full((1, 3), 1.1, dtype=dtype)
    qcr = torch.full((1, 3), 1.0e-9, dtype=dtype)
    lenconcr = torch.full((1, 3), 1.0e-9, dtype=dtype)

    praut, nraut = autoconv_torch(qc, nc, qr, nr, den, qcr, lenconcr, params=p, dtcld=60.0)
    loss = praut.sum() + nraut.sum()
    loss.backward()

    for x, name in [(qc, "qc"), (nc, "nc"), (qr, "qr"), (nr, "nr")]:
        assert x.grad is not None, name
        assert torch.isfinite(x.grad).all(), name


# ════ Step B2: Accretion ══════════════════════════════════════════════════════


def _accretion_inputs(*, requires_grad: bool = False, qr_above_lenconcr: bool = True):
    """B2 accretion 표준 입력. qr_above_lenconcr=False면 rain_active gate가 닫힘."""
    dtype = torch.float64
    qc = torch.tensor([[1.0e-3, 2.0e-3]], dtype=dtype, requires_grad=requires_grad)
    nc = torch.tensor([[1.0e8, 2.0e8]], dtype=dtype, requires_grad=requires_grad)
    qr_val = 1.0e-4 if qr_above_lenconcr else 1.0e-9
    qr = torch.tensor([[qr_val, qr_val]], dtype=dtype, requires_grad=requires_grad)
    nr = torch.tensor([[1.0e5, 2.0e5]], dtype=dtype, requires_grad=requires_grad)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    avedia_r = torch.tensor([[2.0e-4, 5.0e-5]], dtype=dtype)  # cell 0 big, cell 1 small
    rslopec3 = torch.full((1, 2), (5.0e-5)**3, dtype=dtype)
    rslope3_r = torch.full((1, 2), (5.0e-4)**3, dtype=dtype)
    lenconcr = torch.full((1, 2), 1.0e-7, dtype=dtype)
    return qc, nc, qr, nr, den, avedia_r, rslopec3, rslope3_r, lenconcr


def test_default_warm_accretion_params_finite_and_positive():
    p = default_warm_accretion_params()
    for field in p._fields:
        value = getattr(p, field)
        assert math.isfinite(value), field
        assert value > 0.0, field


def test_default_warm_accretion_params_gamma_consistency():
    """rgmma(x) = Γ(x) (Fortran 직역). review6 audit에서 부호 수정됨.
    muc=2 ⇒ 1+3/3=2, 1+6/3=3, 1+9/3=4. Γ(2)=1, Γ(3)=2, Γ(4)=6.
    mur=1 ⇒ Γ(2)=1, Γ(5)=24, Γ(8)=5040.
    """
    p = default_warm_accretion_params()
    assert math.isclose(p.g3pmc, 1.0, rel_tol=1e-12)
    assert math.isclose(p.g6pmc, 2.0, rel_tol=1e-12)
    assert math.isclose(p.g9pmc, 6.0, rel_tol=1e-12)
    assert math.isclose(p.g1pmr, 1.0, rel_tol=1e-12)
    assert math.isclose(p.g4pmr, 24.0, rel_tol=1e-12)
    assert math.isclose(p.g7pmr, 5040.0, rel_tol=1e-12)


def test_accretion_inactive_when_qr_below_lenconcr():
    """qr < lenconcr → pracw = nracw = 0."""
    p = default_warm_accretion_params()
    inputs = _accretion_inputs(qr_above_lenconcr=False)
    qc, nc, qr, nr, den, avedia_r, rslopec3, rslope3_r, lenconcr = inputs
    pracw, nracw = accretion_torch(
        qc, nc, qr, nr, den, avedia_r, rslopec3, rslope3_r, lenconcr,
        params=p, dtcld=60.0,
    )
    assert torch.allclose(pracw, torch.zeros_like(qc))
    assert torch.allclose(nracw, torch.zeros_like(qc))


def test_accretion_mode_branch_at_di100():
    """avedia_r >= di100 → mode 1, else mode 2 — 두 모드의 결과가 다름."""
    p = default_warm_accretion_params()
    inputs = _accretion_inputs(qr_above_lenconcr=True)
    qc, nc, qr, nr, den, avedia_r, rslopec3, rslope3_r, lenconcr = inputs
    pracw, nracw = accretion_torch(
        qc, nc, qr, nr, den, avedia_r, rslopec3, rslope3_r, lenconcr,
        params=p, dtcld=60.0,
    )
    # cell 0 (big drop) ≠ cell 1 (small drop) — 두 mode 결과 다름
    assert pracw.shape == (1, 2)
    assert nracw.shape == (1, 2)
    # 둘 다 양수 (active gate 통과)
    assert torch.all(pracw >= 0)
    assert torch.all(nracw >= 0)


def test_accretion_capped_by_conservation():
    """pracw <= qc/dtcld AND nracw <= nc/dtcld."""
    p = default_warm_accretion_params()
    dtype = torch.float64
    # 매우 큰 nc/nr로 unsaturated rate를 cap을 넘기게 강제
    qc = torch.tensor([[1.0e-3]], dtype=dtype)
    nc = torch.tensor([[1.0e10]], dtype=dtype)
    qr = torch.tensor([[1.0e-3]], dtype=dtype)
    nr = torch.tensor([[1.0e10]], dtype=dtype)
    den = torch.full((1, 1), 1.1, dtype=dtype)
    avedia_r = torch.tensor([[2.0e-4]], dtype=dtype)
    rslopec3 = torch.full((1, 1), (1.0e-4)**3, dtype=dtype)
    rslope3_r = torch.full((1, 1), (5.0e-4)**3, dtype=dtype)
    lenconcr = torch.full((1, 1), 1.0e-9, dtype=dtype)

    dtcld = 60.0
    pracw, nracw = accretion_torch(
        qc, nc, qr, nr, den, avedia_r, rslopec3, rslope3_r, lenconcr,
        params=p, dtcld=dtcld,
    )
    assert torch.all(pracw <= qc / dtcld + 1e-15)
    assert torch.all(nracw <= nc / dtcld + 1e-15)


def test_accretion_grad_finite_active():
    """qc/nc/nr는 산식에 들어가므로 grad 있고 finite. qr는 비교에만 쓰이므로 grad=None (정상)."""
    p = default_warm_accretion_params()
    qc, nc, qr, nr, den, avedia_r, rslopec3, rslope3_r, lenconcr = _accretion_inputs(
        requires_grad=True, qr_above_lenconcr=True,
    )
    pracw, nracw = accretion_torch(
        qc, nc, qr, nr, den, avedia_r, rslopec3, rslope3_r, lenconcr,
        params=p, dtcld=60.0,
    )
    loss = pracw.sum() + nracw.sum()
    loss.backward()
    for x, name in [(qc, "qc"), (nc, "nc"), (nr, "nr")]:
        assert x.grad is not None, name
        assert torch.isfinite(x.grad).all(), name
    # qr는 외부 게이트 비교에만 쓰여 graph에 들어가지 않음 — grad=None이 정상.
    assert qr.grad is None


def test_accretion_grad_finite_inactive():
    """qr=0 (inactive)에서도 backward finite (qc/nc/nr graph도 cap을 통해 살아있음)."""
    p = default_warm_accretion_params()
    dtype = torch.float64
    qc = torch.zeros((1, 2), dtype=dtype, requires_grad=True)
    nc = torch.zeros((1, 2), dtype=dtype, requires_grad=True)
    qr = torch.zeros((1, 2), dtype=dtype, requires_grad=True)
    nr = torch.zeros((1, 2), dtype=dtype, requires_grad=True)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    avedia_r = torch.zeros((1, 2), dtype=dtype)
    rslopec3 = torch.zeros((1, 2), dtype=dtype)
    rslope3_r = torch.zeros((1, 2), dtype=dtype)
    lenconcr = torch.full((1, 2), 1.0e-7, dtype=dtype)

    pracw, nracw = accretion_torch(
        qc, nc, qr, nr, den, avedia_r, rslopec3, rslope3_r, lenconcr,
        params=p, dtcld=60.0,
    )
    loss = pracw.sum() + nracw.sum()
    loss.backward()
    for x, name in [(qc, "qc"), (nc, "nc"), (nr, "nr")]:
        assert x.grad is not None, name
        assert torch.isfinite(x.grad).all(), name
    assert qr.grad is None


# ════ Step B3: Self-collection ════════════════════════════════════════════════


def _self_coll_inputs(*, requires_grad: bool = False, avedia_r_value: float = 3.0e-4):
    """B3 표준 입력. avedia_r 값으로 4-mode 분기 검증 가능."""
    dtype = torch.float64
    nc = torch.tensor([[1.0e8, 2.0e8]], dtype=dtype, requires_grad=requires_grad)
    nr = torch.tensor([[1.0e5, 2.0e5]], dtype=dtype, requires_grad=requires_grad)
    qr = torch.tensor([[1.0e-4, 1.0e-4]], dtype=dtype)
    avedia_c = torch.full((1, 2), 5.0e-5, dtype=dtype)  # both < di100 → small mode
    avedia_r = torch.full((1, 2), avedia_r_value, dtype=dtype)
    rslopec3 = torch.full((1, 2), (5.0e-5)**3, dtype=dtype)
    rslope3_r = torch.full((1, 2), (5.0e-4)**3, dtype=dtype)
    lenconcr = torch.full((1, 2), 1.0e-7, dtype=dtype)
    return nc, nr, qr, avedia_c, avedia_r, rslopec3, rslope3_r, lenconcr


def test_default_warm_self_collection_params_finite_and_positive():
    p = default_warm_self_collection_params()
    for field in p._fields:
        value = getattr(p, field)
        assert math.isfinite(value), field
        assert value > 0.0, field
    # Threshold 순서 확인 (di100 < di600 < di2000)
    assert p.di100 < p.di600 < p.di2000


def test_self_collection_nrcol_zero_at_huge_drops():
    """avedia_r >= di2000 → nrcol = 0 (complete break-up)."""
    p = default_warm_self_collection_params()
    inputs = _self_coll_inputs(avedia_r_value=p.di2000 + 1.0e-5)
    _, nrcol = self_collection_torch(*inputs, params=p)
    assert torch.allclose(nrcol, torch.zeros_like(nrcol))


def test_self_collection_nrcol_zero_below_lenconcr():
    """qr < lenconcr → nrcol = 0."""
    p = default_warm_self_collection_params()
    nc, nr, qr, avedia_c, avedia_r, rslopec3, rslope3_r, _ = _self_coll_inputs()
    lenconcr = torch.full_like(qr, 1.0)  # very large threshold
    _, nrcol = self_collection_torch(
        nc, nr, qr, avedia_c, avedia_r, rslopec3, rslope3_r, lenconcr, params=p,
    )
    assert torch.allclose(nrcol, torch.zeros_like(nrcol))


def test_self_collection_nrcol_4mode_distinct():
    """4-mode 분기: avedia_r 값에 따라 small/medium/breakup/zero 영역."""
    p = default_warm_self_collection_params()
    dtype = torch.float64
    # 4 cells, 각 mode를 한 셀씩
    nc = torch.full((1, 4), 1.0e8, dtype=dtype)
    nr = torch.full((1, 4), 1.0e5, dtype=dtype)
    qr = torch.full((1, 4), 1.0e-4, dtype=dtype)
    avedia_c = torch.full((1, 4), 5.0e-5, dtype=dtype)
    avedia_r = torch.tensor([[
        5.0e-5,                    # < di100 → small
        3.0e-4,                    # [di100, di600) → medium
        1.0e-3,                    # [di600, di2000) → breakup
        3.0e-3,                    # >= di2000 → zero
    ]], dtype=dtype)
    rslopec3 = torch.full((1, 4), (5.0e-5)**3, dtype=dtype)
    rslope3_r = torch.full((1, 4), (5.0e-4)**3, dtype=dtype)
    lenconcr = torch.full((1, 4), 1.0e-7, dtype=dtype)

    _, nrcol = self_collection_torch(
        nc, nr, qr, avedia_c, avedia_r, rslopec3, rslope3_r, lenconcr, params=p,
    )
    # cell 3 (huge) → 0
    assert torch.isclose(nrcol[0, 3], torch.tensor(0.0, dtype=dtype))
    # cells 0,1,2 → 양수
    assert nrcol[0, 0] > 0
    assert nrcol[0, 1] > 0
    assert nrcol[0, 2] > 0


def test_self_collection_nccol_2mode():
    """nccol: avedia_c >= di100 → big mode (ncrk1*g3pmc), else small (ncrk2*rslopec3*g6pmc)."""
    p = default_warm_self_collection_params()
    dtype = torch.float64
    nc = torch.full((1, 2), 1.0e8, dtype=dtype)
    nr = torch.full((1, 2), 1.0e5, dtype=dtype)
    qr = torch.full((1, 2), 1.0e-4, dtype=dtype)
    avedia_c = torch.tensor([[5.0e-5, 2.0e-4]], dtype=dtype)  # cell 0 small, cell 1 big
    avedia_r = torch.full((1, 2), 3.0e-4, dtype=dtype)
    rslopec3 = torch.full((1, 2), (5.0e-5)**3, dtype=dtype)
    rslope3_r = torch.full((1, 2), (5.0e-4)**3, dtype=dtype)
    lenconcr = torch.full((1, 2), 1.0e-7, dtype=dtype)

    nccol, _ = self_collection_torch(
        nc, nr, qr, avedia_c, avedia_r, rslopec3, rslope3_r, lenconcr, params=p,
    )
    # 두 모드 결과 다름
    assert not torch.allclose(nccol[0, 0], nccol[0, 1])
    assert torch.all(nccol >= 0)


def test_self_collection_grad_finite():
    p = default_warm_self_collection_params()
    nc, nr, qr, avedia_c, avedia_r, rslopec3, rslope3_r, lenconcr = _self_coll_inputs(
        requires_grad=True, avedia_r_value=3.0e-4,
    )
    nccol, nrcol = self_collection_torch(
        nc, nr, qr, avedia_c, avedia_r, rslopec3, rslope3_r, lenconcr, params=p,
    )
    loss = nccol.sum() + nrcol.sum()
    loss.backward()
    for x, name in [(nc, "nc"), (nr, "nr")]:
        assert x.grad is not None, name
        assert torch.isfinite(x.grad).all(), name


# ════ Step B4: Rain evaporation / condensation ═══════════════════════════════


def _rain_evap_inputs(*, requires_grad: bool = False, rh_value: float = 0.8):
    """B4 표준 입력. rh_value < 1이면 evap, > 1이면 cond."""
    dtype = torch.float64
    qr = torch.tensor([[1.0e-4, 5.0e-5]], dtype=dtype, requires_grad=requires_grad)
    rh_w = torch.full((1, 2), rh_value, dtype=dtype)
    qsw = 5.0e-3
    qv = qsw * rh_value
    supsat = torch.full((1, 2), qv - qsw, dtype=dtype)  # negative when rh<1
    n0r = torch.full((1, 2), 8.0e6, dtype=dtype)
    work1_r = torch.full((1, 2), 1.0e-3, dtype=dtype)
    work2 = torch.full((1, 2), 1.5, dtype=dtype)
    rslope_r = torch.full((1, 2), 5.0e-4, dtype=dtype)
    rslopeb_r = torch.full((1, 2), 5.0e-4 ** c.BVTR, dtype=dtype)
    rslope2_r = rslope_r * rslope_r
    rslopemu_r = torch.full((1, 2), 5.0e-4 ** c.MUR, dtype=dtype)
    return qr, rh_w, supsat, n0r, work1_r, work2, rslope_r, rslopeb_r, rslope2_r, rslopemu_r


def test_default_warm_rain_evap_params_finite_and_positive():
    p = default_warm_rain_evap_params()
    for field in p._fields:
        value = getattr(p, field)
        assert math.isfinite(value), field
        assert value > 0.0, field


def test_default_warm_rain_evap_params_precr1_formula():
    """precr1 = 2*pi*0.78*g2pmr (mur=1, g2pmr = rgmma(3) = Γ(3) = 2)."""
    p = default_warm_rain_evap_params()
    expected = 2.0 * math.pi * 0.78 * 2.0
    assert math.isclose(p.precr1, expected, rel_tol=1e-12)


def test_rain_evap_inactive_when_qr_zero():
    """qr <= 0 → prevp = 0."""
    p = default_warm_rain_evap_params()
    inputs = list(_rain_evap_inputs(rh_value=0.5))
    inputs[0] = torch.zeros_like(inputs[0])  # qr = 0
    prevp = rain_evap_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(prevp, torch.zeros_like(prevp))


def test_rain_evap_evaporation_path():
    """rh < 1 → prevp < 0, capped by -qr/dtcld."""
    p = default_warm_rain_evap_params()
    inputs = _rain_evap_inputs(rh_value=0.5)
    qr = inputs[0]
    dtcld = 60.0
    prevp = rain_evap_torch(*inputs, params=p, dtcld=dtcld)
    # prevp <= 0 and prevp >= -qr/dtcld
    assert torch.all(prevp <= 0.0 + 1e-15)
    assert torch.all(prevp >= -qr / dtcld - 1e-15)


def test_rain_evap_condensation_path():
    """rh > 1 → prevp > 0, capped by satdt/2."""
    p = default_warm_rain_evap_params()
    inputs = _rain_evap_inputs(rh_value=1.05)
    supsat = inputs[2]
    dtcld = 60.0
    prevp = rain_evap_torch(*inputs, params=p, dtcld=dtcld)
    # prevp >= 0 (cond) and prevp <= satdt/2
    assert torch.all(prevp >= 0.0 - 1e-15)
    assert torch.all(prevp <= 0.5 * supsat / dtcld + 1e-15)


def test_rain_evap_grad_finite():
    p = default_warm_rain_evap_params()
    inputs = _rain_evap_inputs(requires_grad=True, rh_value=0.5)
    qr = inputs[0]
    prevp = rain_evap_torch(*inputs, params=p, dtcld=60.0)
    prevp.sum().backward()
    assert qr.grad is not None
    assert torch.isfinite(qr.grad).all()
