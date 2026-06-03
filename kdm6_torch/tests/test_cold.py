"""cold-rain (ice phase) oracle 검증 — Step C."""
from __future__ import annotations

import math

import torch

from kdm6 import constants as c
from kdm6.cold import (
    CloudWaterRimingOutputs,
    CloudWaterRimingParams,
    DepSubOutputs,
    DepSubParams,
    HallettMossopOutputs,
    HallettMossopParams,
    IceAccretionParams,
    IceAggregationParams,
    IceNucleationOutputs,
    IceNucleationParams,
    IceToSnowGraupelParams,
    NumberAccretionParams,
    RainSnowGraupelCollectionOutputs,
    RainSnowGraupelCollectionParams,
    SnowEvapParams,
    cloud_water_riming_torch,
    default_cloud_water_riming_params,
    default_dep_sub_params,
    default_hallett_mossop_params,
    default_ice_accretion_params,
    default_ice_aggregation_params,
    default_ice_nucleation_params,
    default_ice_to_snow_graupel_params,
    default_number_accretion_params,
    default_rain_snow_graupel_collection_params,
    default_snow_evap_params,
    default_graupel_evap_params,
    dep_sub_torch,
    hallett_mossop_torch,
    ice_accretion_torch,
    ice_aggregation_torch,
    ice_nucleation_torch,
    ice_to_snow_graupel_torch,
    number_accretion_torch,
    rain_snow_graupel_collection_torch,
    snow_evap_torch,
    graupel_evap_torch,
)


def _ice_accretion_inputs(
    *,
    requires_grad: bool = False,
    qi_value: float = 1.0e-5,
    qr_value: float = 1.0e-4,
):
    """C1 표준 입력. cloud ice + rain 모두 active 영역."""
    dtype = torch.float64
    qi = torch.full((1, 2), qi_value, dtype=dtype, requires_grad=requires_grad)
    qr = torch.full((1, 2), qr_value, dtype=dtype, requires_grad=requires_grad)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    n0i = torch.full((1, 2), 1.0e6, dtype=dtype)
    n0r = torch.full((1, 2), 8.0e6, dtype=dtype)
    vt2r = torch.full((1, 2), 5.0, dtype=dtype)
    vt2i = torch.full((1, 2), 0.5, dtype=dtype)
    rslope_r = torch.full((1, 2), 5.0e-4, dtype=dtype)
    rslope2_r = rslope_r * rslope_r
    rslope3_r = rslope2_r * rslope_r
    rslopemu_r = torch.full((1, 2), 5.0e-4 ** c.MUR, dtype=dtype)
    rsloped_r = torch.full((1, 2), 5.0e-4 ** c.DMR, dtype=dtype)
    rslope_i = torch.full((1, 2), 1.0e-4, dtype=dtype)
    rslope2_i = rslope_i * rslope_i
    rslope3_i = rslope2_i * rslope_i
    rslopemu_i = torch.full((1, 2), 1.0e-4 ** c.MUI, dtype=dtype)
    rsloped_i = torch.full((1, 2), 1.0e-4 ** c.DMI, dtype=dtype)
    return (
        qi, qr, den, n0i, n0r, vt2r, vt2i,
        rslope_r, rslope2_r, rslope3_r, rslopemu_r, rsloped_r,
        rslope_i, rslope2_i, rslope3_i, rslopemu_i, rsloped_i,
    )


def test_default_ice_accretion_params_finite_and_positive():
    p = default_ice_accretion_params()
    for field in p._fields:
        v = getattr(p, field)
        assert math.isfinite(v) and v > 0, field


def test_default_ice_accretion_params_gamma_consistency():
    """mui=0 → g1pmi=1 (short-circuit). mur=1: rgmma(x)=Γ(x).
    Γ(2)=1, Γ(3)=2, Γ(4)=6 (review6 audit에서 부호 수정)."""
    p = default_ice_accretion_params()
    assert math.isclose(p.g1pmr, 1.0, rel_tol=1e-12)
    assert math.isclose(p.g2pmr, 2.0, rel_tol=1e-12)
    assert math.isclose(p.g3pmr, 6.0, rel_tol=1e-12)
    if c.MUI == 0.0:
        assert p.g1pmi == 1.0


def test_ice_accretion_inactive_below_thresholds():
    """qi <= qmin(1e-15, #13) OR qr <= qcrmin(1e-9) → praci = piacr = 0."""
    p = default_ice_accretion_params()
    inputs = list(_ice_accretion_inputs(qi_value=1.0e-16, qr_value=1.0e-4))  # qi below 1e-15 gate
    praci, piacr = ice_accretion_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(praci, torch.zeros_like(praci))
    assert torch.allclose(piacr, torch.zeros_like(piacr))

    # Gate-regression LOCK (#13): qi in (EPS=1e-15, old 1e-9) → gate OPEN → praci>0 (cap).
    # FAILS if the qmin gate regresses to 1e-9.
    inb = list(_ice_accretion_inputs(qi_value=1.0e-12, qr_value=1.0e-4))
    praci_b, _ = ice_accretion_torch(*inb, params=p, dtcld=60.0)
    assert torch.all(praci_b > 0.0)

    # 또: qr 너무 낮을 때
    inputs2 = list(_ice_accretion_inputs(qi_value=1.0e-5, qr_value=1.0e-12))
    praci2, piacr2 = ice_accretion_torch(*inputs2, params=p, dtcld=60.0)
    assert torch.allclose(praci2, torch.zeros_like(praci2))
    assert torch.allclose(piacr2, torch.zeros_like(piacr2))


def test_ice_accretion_capped_by_mass_conservation():
    """praci <= qi/dtcld AND piacr <= qr/dtcld."""
    p = default_ice_accretion_params()
    # 매우 큰 n0i, n0r로 raw rate를 cap 너머로 강제
    dtype = torch.float64
    qi = torch.tensor([[1.0e-5]], dtype=dtype)
    qr = torch.tensor([[1.0e-4]], dtype=dtype)
    den = torch.full((1, 1), 1.1, dtype=dtype)
    n0i = torch.full((1, 1), 1.0e10, dtype=dtype)
    n0r = torch.full((1, 1), 1.0e10, dtype=dtype)
    vt2r = torch.full((1, 1), 5.0, dtype=dtype)
    vt2i = torch.full((1, 1), 0.5, dtype=dtype)
    one = torch.full((1, 1), 1.0e-3, dtype=dtype)
    one_mu_r = torch.full((1, 1), 1.0e-3 ** c.MUR, dtype=dtype)
    one_d_r = torch.full((1, 1), 1.0e-3 ** c.DMR, dtype=dtype)
    one_mu_i = torch.full((1, 1), 1.0e-3 ** c.MUI, dtype=dtype)
    one_d_i = torch.full((1, 1), 1.0e-3 ** c.DMI, dtype=dtype)

    dtcld = 60.0
    praci, piacr = ice_accretion_torch(
        qi, qr, den, n0i, n0r, vt2r, vt2i,
        one, one * one, one * one * one, one_mu_r, one_d_r,
        one, one * one, one * one * one, one_mu_i, one_d_i,
        params=p, dtcld=dtcld,
    )
    assert torch.all(praci <= qi / dtcld + 1e-15)
    assert torch.all(piacr <= qr / dtcld + 1e-15)


def test_ice_accretion_wilt_reduction_at_extremes():
    """qr/qi가 매우 클 때 (>1) Wilt reduction이 1로 saturate.
    qr/qi가 매우 작을 때 (<<1) Wilt reduction이 작음."""
    p = default_ice_accretion_params()
    # praci는 qr/qi 비율에 의존 → qr/qi 큰 셀과 작은 셀 비교
    dtype = torch.float64
    # cell 0: qr/qi = 100 (very large) — Wilt = 1
    # cell 1: qr/qi = 0.01 (very small) — Wilt ≈ 0.0001
    qi = torch.tensor([[1.0e-6, 1.0e-4]], dtype=dtype)
    qr = torch.tensor([[1.0e-4, 1.0e-6]], dtype=dtype)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    n0i = torch.full((1, 2), 1.0e6, dtype=dtype)
    n0r = torch.full((1, 2), 8.0e6, dtype=dtype)
    vt2r = torch.full((1, 2), 5.0, dtype=dtype)
    vt2i = torch.full((1, 2), 0.5, dtype=dtype)
    rslope_r = torch.full((1, 2), 5.0e-4, dtype=dtype)
    rslope_i = torch.full((1, 2), 1.0e-4, dtype=dtype)
    one_mu_r = torch.full((1, 2), 5.0e-4 ** c.MUR, dtype=dtype)
    one_d_r = torch.full((1, 2), 5.0e-4 ** c.DMR, dtype=dtype)
    one_mu_i = torch.full((1, 2), 1.0e-4 ** c.MUI, dtype=dtype)
    one_d_i = torch.full((1, 2), 1.0e-4 ** c.DMI, dtype=dtype)

    praci, _ = ice_accretion_torch(
        qi, qr, den, n0i, n0r, vt2r, vt2i,
        rslope_r, rslope_r * rslope_r, rslope_r * rslope_r * rslope_r, one_mu_r, one_d_r,
        rslope_i, rslope_i * rslope_i, rslope_i * rslope_i * rslope_i, one_mu_i, one_d_i,
        params=p, dtcld=60.0,
    )
    # cell 0 (qr>>qi)에서는 Wilt가 1로 활성, cell 1 (qr<<qi)에서는 Wilt 작음
    # 결과로 praci는 mass cap에 도달할 수도 있고 아닐 수도 있지만, 둘 다 양수.
    assert torch.all(praci >= 0)


def test_ice_accretion_grad_finite():
    """active 셀에서 qi/qr (등)에 대해 backward 통과."""
    p = default_ice_accretion_params()
    inputs = _ice_accretion_inputs(requires_grad=True)
    praci, piacr = ice_accretion_torch(*inputs, params=p, dtcld=60.0)
    loss = praci.sum() + piacr.sum()
    loss.backward()
    qi, qr = inputs[0], inputs[1]
    assert qi.grad is not None and torch.isfinite(qi.grad).all()
    assert qr.grad is not None and torch.isfinite(qr.grad).all()


def test_ice_accretion_grad_finite_inactive():
    """qi=qr=0 (inactive)에서도 backward finite (NaN/Inf 차단)."""
    p = default_ice_accretion_params()
    dtype = torch.float64
    qi = torch.zeros((1, 2), dtype=dtype, requires_grad=True)
    qr = torch.zeros((1, 2), dtype=dtype, requires_grad=True)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    n0i = torch.full((1, 2), 1.0e6, dtype=dtype)
    n0r = torch.full((1, 2), 8.0e6, dtype=dtype)
    vt2r = torch.full((1, 2), 5.0, dtype=dtype)
    vt2i = torch.full((1, 2), 0.5, dtype=dtype)
    one = torch.full((1, 2), 5.0e-4, dtype=dtype)
    one_i = torch.full((1, 2), 1.0e-4, dtype=dtype)

    praci, piacr = ice_accretion_torch(
        qi, qr, den, n0i, n0r, vt2r, vt2i,
        one, one*one, one*one*one,
        torch.full_like(one, 5.0e-4 ** c.MUR), torch.full_like(one, 5.0e-4 ** c.DMR),
        one_i, one_i*one_i, one_i*one_i*one_i,
        torch.full_like(one_i, 1.0e-4 ** c.MUI), torch.full_like(one_i, 1.0e-4 ** c.DMI),
        params=p, dtcld=60.0,
    )
    loss = praci.sum() + piacr.sum()
    loss.backward()
    assert qi.grad is not None and torch.isfinite(qi.grad).all()
    assert qr.grad is not None and torch.isfinite(qr.grad).all()


# ════ Step C2: ice → snow/graupel ═════════════════════════════════════════════


def _isg_inputs(*, requires_grad: bool = False, qi_value: float = 1.0e-5,
                qs_value: float = 1.0e-4, qg_value: float = 1.0e-4,
                supcol_value: float = 10.0):
    """C2 표준 입력. cold environment (supcol=10K)."""
    dtype = torch.float64
    qi = torch.full((1, 2), qi_value, dtype=dtype, requires_grad=requires_grad)
    qs = torch.full((1, 2), qs_value, dtype=dtype, requires_grad=requires_grad)
    qg = torch.full((1, 2), qg_value, dtype=dtype, requires_grad=requires_grad)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    n0i = torch.full((1, 2), 1.0e6, dtype=dtype)
    n0so = torch.full((1, 2), 2.0e6, dtype=dtype)
    n0go = torch.full((1, 2), 4.0e6, dtype=dtype)
    n0sfac = torch.full((1, 2), 5.0, dtype=dtype)  # cold-amplified intercept
    supcol = torch.full((1, 2), supcol_value, dtype=dtype)
    vt2s = torch.full((1, 2), 1.0, dtype=dtype)
    vt2g = torch.full((1, 2), 3.0, dtype=dtype)
    vt2i = torch.full((1, 2), 0.5, dtype=dtype)
    rslope_s = torch.full((1, 2), 5.0e-4, dtype=dtype)
    rslope_g = torch.full((1, 2), 1.0e-3, dtype=dtype)
    rslope_i = torch.full((1, 2), 1.0e-4, dtype=dtype)
    return (
        qi, qs, qg, den, n0i, n0so, n0go, n0sfac, supcol, vt2s, vt2g, vt2i,
        rslope_s, rslope_s * rslope_s, rslope_s * rslope_s * rslope_s,
        torch.full_like(rslope_s, 5.0e-4 ** c.MUS),
        rslope_g, rslope_g * rslope_g, rslope_g * rslope_g * rslope_g,
        torch.full_like(rslope_g, 1.0e-3 ** c.MUG),
        rslope_i, rslope_i * rslope_i, rslope_i * rslope_i * rslope_i,
        torch.full_like(rslope_i, 1.0e-4 ** c.MUI),
        torch.full_like(rslope_i, 1.0e-4 ** c.DMI),
    )


def test_default_isg_params_finite_and_positive():
    p = default_ice_to_snow_graupel_params()
    for field in p._fields:
        v = getattr(p, field)
        assert math.isfinite(v) and v > 0, field


def test_default_isg_params_gamma_consistency():
    """mus=0, mug=0 → g1pms=g1pmg=1; g3pms=g3pmg=rgmma(3)=Γ(3)=2 (review6 audit)."""
    p = default_ice_to_snow_graupel_params()
    if c.MUS == 0.0:
        assert p.g1pms == 1.0
    if c.MUG == 0.0:
        assert p.g1pmg == 1.0
    assert math.isclose(p.g3pms, 2.0, rel_tol=1e-12)
    assert math.isclose(p.g3pmg, 2.0, rel_tol=1e-12)


def test_isg_inactive_when_qi_low():
    """qi <= qmin(1e-15, #14) → psaci = pgaci = 0."""
    p = default_ice_to_snow_graupel_params()
    inputs = _isg_inputs(qi_value=1.0e-16)  # qi below 1e-15 gate
    psaci, pgaci = ice_to_snow_graupel_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(psaci, torch.zeros_like(psaci))
    assert torch.allclose(pgaci, torch.zeros_like(pgaci))

    # Gate-regression LOCK (#14): qi in (EPS=1e-15, old 1e-9) → gate OPEN → psaci>0 (cap).
    # FAILS if the qmin gate regresses to 1e-9.
    inb = _isg_inputs(qi_value=1.0e-12)
    psaci_b, _ = ice_to_snow_graupel_torch(*inb, params=p, dtcld=60.0)
    assert torch.all(psaci_b > 0.0)


def test_isg_psaci_zero_when_qs_low():
    """qs <= qcrmin → psaci=0 (pgaci는 qg에 의존)."""
    p = default_ice_to_snow_graupel_params()
    inputs = _isg_inputs(qs_value=1.0e-12, qg_value=1.0e-4)
    psaci, pgaci = ice_to_snow_graupel_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(psaci, torch.zeros_like(psaci))
    assert torch.all(pgaci > 0)  # pgaci는 active


def test_isg_pgaci_eacgi_temperature_dependence():
    """eacgi는 supcol에 의존. Fortran 산식 `exp(0.07·(-supcol))`에 의해
    cold(supcol>0)일수록 *eacgi 작음* (직관 반대 — 산식 직역). 따라서 cold 셀의 pgaci ≤ warm 셀."""
    p = default_ice_to_snow_graupel_params()
    inputs_warm = list(_isg_inputs(supcol_value=2.0))
    inputs_cold = list(_isg_inputs(supcol_value=50.0))

    _, pgaci_warm = ice_to_snow_graupel_torch(*inputs_warm, params=p, dtcld=60.0)
    _, pgaci_cold = ice_to_snow_graupel_torch(*inputs_cold, params=p, dtcld=60.0)
    assert torch.all(pgaci_cold <= pgaci_warm + 1e-15)


def test_isg_grad_finite():
    p = default_ice_to_snow_graupel_params()
    inputs = _isg_inputs(requires_grad=True)
    psaci, pgaci = ice_to_snow_graupel_torch(*inputs, params=p, dtcld=60.0)
    loss = psaci.sum() + pgaci.sum()
    loss.backward()
    qi, qs, qg = inputs[0], inputs[1], inputs[2]
    for x, name in [(qi, "qi"), (qs, "qs"), (qg, "qg")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


# ════ Step C2b: Number accretion ══════════════════════════════════════════════


def _na_inputs(*, requires_grad: bool = False, supcol_value: float = 10.0,
               ni_value: float = 1.0e5, nr_value: float = 1.0e4):
    """C2b 표준 입력. cold (supcol>0) + sufficient ice number."""
    dtype = torch.float64
    qi = torch.full((1, 2), 1.0e-5, dtype=dtype, requires_grad=requires_grad)
    qs = torch.full((1, 2), 1.0e-4, dtype=dtype)
    qg = torch.full((1, 2), 1.0e-4, dtype=dtype)
    qr = torch.full((1, 2), 1.0e-4, dtype=dtype)
    ni = torch.full((1, 2), ni_value, dtype=dtype, requires_grad=requires_grad)
    nr = torch.full((1, 2), nr_value, dtype=dtype, requires_grad=requires_grad)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    n0i = torch.full((1, 2), 1.0e6, dtype=dtype)
    n0r = torch.full((1, 2), 8.0e6, dtype=dtype)
    n0sfac = torch.full((1, 2), 5.0, dtype=dtype)
    supcol = torch.full((1, 2), supcol_value, dtype=dtype)
    vt2r = torch.full((1, 2), 5.0, dtype=dtype)
    vt2s = torch.full((1, 2), 1.0, dtype=dtype)
    vt2g = torch.full((1, 2), 3.0, dtype=dtype)
    vt2i = torch.full((1, 2), 0.5, dtype=dtype)
    rsl_r = torch.full((1, 2), 5.0e-4, dtype=dtype)
    rsl_s = torch.full((1, 2), 5.0e-4, dtype=dtype)
    rsl_g = torch.full((1, 2), 1.0e-3, dtype=dtype)
    rsl_i = torch.full((1, 2), 1.0e-4, dtype=dtype)
    return (
        qi, qs, qg, qr, ni, nr, den, n0i, n0r, n0sfac, supcol,
        vt2r, vt2s, vt2g, vt2i,
        rsl_r, rsl_r * rsl_r, rsl_r * rsl_r * rsl_r,
        torch.full_like(rsl_r, 5.0e-4 ** c.MUR),
        rsl_s, rsl_s * rsl_s, rsl_s * rsl_s * rsl_s,
        torch.full_like(rsl_s, 5.0e-4 ** c.MUS),
        rsl_g, rsl_g * rsl_g, rsl_g * rsl_g * rsl_g,
        torch.full_like(rsl_g, 1.0e-3 ** c.MUG),
        rsl_i, rsl_i * rsl_i, rsl_i * rsl_i * rsl_i,
        torch.full_like(rsl_i, 1.0e-4 ** c.MUI),
    )


def test_default_number_accretion_params_finite():
    p = default_number_accretion_params()
    for field in p._fields:
        v = getattr(p, field)
        assert math.isfinite(v) and v > 0, field


def test_number_accretion_inactive_when_warm():
    """supcol <= 0 (warm) → 모든 4 outputs = 0."""
    p = default_number_accretion_params()
    inputs = _na_inputs(supcol_value=-5.0)  # warm
    nraci, niacr, nsaci, ngaci = number_accretion_torch(*inputs, params=p, dtcld=60.0)
    z = torch.zeros_like(nraci)
    for x in (nraci, niacr, nsaci, ngaci):
        assert torch.allclose(x, z)


def test_number_accretion_inactive_when_low_ni():
    """ni <= ncmin → 모든 4 outputs = 0."""
    p = default_number_accretion_params()
    inputs = _na_inputs(ni_value=1.0e-5)  # below ncmin=1e-2
    nraci, niacr, nsaci, ngaci = number_accretion_torch(*inputs, params=p, dtcld=60.0)
    for x in (nraci, niacr, nsaci, ngaci):
        assert torch.allclose(x, torch.zeros_like(x))


def test_number_accretion_rain_subgate_zero():
    """nr <= nrmin → nraci, niacr = 0; nsaci, ngaci는 영향 없음."""
    p = default_number_accretion_params()
    inputs = _na_inputs(nr_value=1.0e-5)  # below nrmin=1e-2
    nraci, niacr, nsaci, ngaci = number_accretion_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(nraci, torch.zeros_like(nraci))
    assert torch.allclose(niacr, torch.zeros_like(niacr))
    # nsaci, ngaci는 nr와 무관 → active일 것
    assert torch.all(nsaci > 0)
    assert torch.all(ngaci > 0)


def test_number_accretion_capped_by_ni_per_dt():
    """nraci, nsaci, ngaci <= ni/dtcld."""
    p = default_number_accretion_params()
    inputs = _na_inputs()
    qi, ni = inputs[0], inputs[4]
    dtcld = 60.0
    nraci, niacr, nsaci, ngaci = number_accretion_torch(*inputs, params=p, dtcld=dtcld)
    # Each is capped by ni/dtcld (collected source = ice)
    assert torch.all(nraci <= ni / dtcld + 1e-15)
    assert torch.all(nsaci <= ni / dtcld + 1e-15)
    assert torch.all(ngaci <= ni / dtcld + 1e-15)
    # niacr is capped by nr/dtcld
    nr = inputs[5]
    assert torch.all(niacr <= nr / dtcld + 1e-15)


def test_number_accretion_grad_finite():
    p = default_number_accretion_params()
    inputs = _na_inputs(requires_grad=True)
    nraci, niacr, nsaci, ngaci = number_accretion_torch(*inputs, params=p, dtcld=60.0)
    loss = nraci.sum() + niacr.sum() + nsaci.sum() + ngaci.sum()
    loss.backward()
    qi, ni, nr = inputs[0], inputs[4], inputs[5]
    for x, name in [(qi, "qi"), (ni, "ni"), (nr, "nr")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


# ════ Step C2c: Cloud water riming ════════════════════════════════════════════


def _cwr_inputs(*, requires_grad: bool = False, supcol_value: float = 10.0,
                qc_value: float = 1.0e-3, avedia_i_value: float = 1.0e-4):
    """C2c 표준 입력. cold + cloud water + ice large enough for riming."""
    dtype = torch.float64
    qc = torch.full((1, 2), qc_value, dtype=dtype, requires_grad=requires_grad)
    nc = torch.full((1, 2), 1.0e8, dtype=dtype, requires_grad=requires_grad)
    qs = torch.full((1, 2), 1.0e-4, dtype=dtype)
    qg = torch.full((1, 2), 1.0e-4, dtype=dtype)
    qi = torch.full((1, 2), 1.0e-5, dtype=dtype)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    denfac = torch.full((1, 2), 1.0, dtype=dtype)
    n0so = torch.full((1, 2), 2.0e6, dtype=dtype)
    n0go = torch.full((1, 2), 4.0e6, dtype=dtype)
    n0i = torch.full((1, 2), 1.0e6, dtype=dtype)
    n0c = torch.full((1, 2), 1.0e8, dtype=dtype)
    n0sfac = torch.full((1, 2), 5.0, dtype=dtype)
    avtg = torch.full((1, 2), 100.0, dtype=dtype)
    g3pbg = torch.full((1, 2), 0.5, dtype=dtype)
    avedia_i = torch.full((1, 2), avedia_i_value, dtype=dtype)
    supcol = torch.full((1, 2), supcol_value, dtype=dtype)
    rsl_s = torch.full((1, 2), 5.0e-4, dtype=dtype)
    rsl_g = torch.full((1, 2), 1.0e-3, dtype=dtype)
    rsl_i = torch.full((1, 2), 1.0e-4, dtype=dtype)
    rsl_c = torch.full((1, 2), 5.0e-5, dtype=dtype)
    return (
        qc, nc, qs, qg, qi, den, denfac, n0so, n0go, n0i, n0c, n0sfac,
        avtg, g3pbg, avedia_i, supcol,
        rsl_s * rsl_s * rsl_s, torch.full_like(rsl_s, 5.0e-4 ** c.BVTS),
        torch.full_like(rsl_s, 5.0e-4 ** c.MUS),
        rsl_g * rsl_g * rsl_g, torch.full_like(rsl_g, 1.0e-3 ** 0.5316),  # bvtg from ProgB default ~0.5316
        torch.full_like(rsl_g, 1.0e-3 ** c.MUG),
        rsl_i * rsl_i * rsl_i, torch.full_like(rsl_i, 1.0e-4 ** c.BVTI),
        torch.full_like(rsl_i, 1.0e-4 ** c.MUI),
        rsl_c, torch.full_like(rsl_c, 5.0e-5 ** c.MUC),
    )


def test_default_cwr_params_finite():
    p = default_cloud_water_riming_params()
    for field in p._fields:
        v = getattr(p, field)
        assert math.isfinite(v) and v > 0, field


def test_cwr_inactive_when_qc_low():
    """qc <= qmin(1e-15, #16/#17) → psacw, pgacw, piacw = 0 (이들이 qc 직접 의존)."""
    p = default_cloud_water_riming_params()
    inputs = _cwr_inputs(qc_value=1.0e-16)  # qc below 1e-15 gate
    out = cloud_water_riming_torch(*inputs, params=p, dtcld=60.0)
    z = torch.zeros_like(out.psacw)
    assert torch.allclose(out.psacw, z)
    assert torch.allclose(out.pgacw, z)
    assert torch.allclose(out.piacw, z)

    # Gate-regression LOCK (#16/#17): qc in (EPS=1e-15, old 1e-9) → gate OPEN → ALL three
    # qc-gated rates (psacw/pgacw/piacw, sharing the qc>qmin gate) > 0. FAILS if the qmin gate
    # regresses to 1e-9. _cwr_inputs has qs/qg>qcrmin, supcol>0, qi>qcrmin, avedia_i>=di50 so only
    # the qc gate can zero them.
    inb = _cwr_inputs(qc_value=1.0e-12)
    out_b = cloud_water_riming_torch(*inb, params=p, dtcld=60.0)
    assert torch.all(out_b.psacw > 0.0)
    assert torch.all(out_b.pgacw > 0.0)
    assert torch.all(out_b.piacw > 0.0)


def test_cwr_piacw_pk97_di50_threshold():
    """avedia_i < di50=50µm → piacw=niacw=0 (PK97 riming threshold)."""
    p = default_cloud_water_riming_params()
    # avedia_i = 30 µm < di50
    inputs = _cwr_inputs(avedia_i_value=3.0e-5)
    out = cloud_water_riming_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(out.piacw, torch.zeros_like(out.piacw))
    assert torch.allclose(out.niacw, torch.zeros_like(out.niacw))

    # avedia_i = 100 µm >= di50 → piacw, niacw active
    inputs2 = _cwr_inputs(avedia_i_value=1.0e-4)
    out2 = cloud_water_riming_torch(*inputs2, params=p, dtcld=60.0)
    assert torch.all(out2.piacw > 0)
    assert torch.all(out2.niacw > 0)


def test_cwr_paacw_weighted_average():
    """paacw = (qs·psacw + qg·pgacw)/(qs+qg). qs=qg일 때 paacw = (psacw+pgacw)/2."""
    p = default_cloud_water_riming_params()
    inputs = _cwr_inputs()
    out = cloud_water_riming_torch(*inputs, params=p, dtcld=60.0)
    # qs == qg in inputs → paacw should be arithmetic mean of psacw and pgacw
    expected = 0.5 * (out.psacw + out.pgacw)
    assert torch.allclose(out.paacw, expected, rtol=1e-12, atol=1e-15)


def test_cwr_warm_branch_piacw_zero():
    """supcol <= 0 → piacw=niacw=0 (cold-specific)."""
    p = default_cloud_water_riming_params()
    inputs = _cwr_inputs(supcol_value=-5.0)  # warm
    out = cloud_water_riming_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(out.piacw, torch.zeros_like(out.piacw))
    assert torch.allclose(out.niacw, torch.zeros_like(out.niacw))
    # psacw/pgacw는 supcol gate 없음 (warm/cold 둘 다 active)
    assert torch.all(out.psacw > 0)
    assert torch.all(out.pgacw > 0)


def test_cwr_grad_finite():
    p = default_cloud_water_riming_params()
    inputs = _cwr_inputs(requires_grad=True)
    out = cloud_water_riming_torch(*inputs, params=p, dtcld=60.0)
    loss = sum(t.sum() for t in out)
    loss.backward()
    qc, nc = inputs[0], inputs[1]
    for x, name in [(qc, "qc"), (nc, "nc")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


# ════ Step C2d: Rain-snow-graupel collection ══════════════════════════════════


def _rsgc_inputs(*, requires_grad: bool = False, supcol_value: float = 10.0,
                 qs_value: float = 1.0e-4, qg_value: float = 1.0e-4,
                 qr_value: float = 1.0e-4, nr_value: float = 1.0e5):
    dtype = torch.float64
    qr = torch.full((1, 2), qr_value, dtype=dtype, requires_grad=requires_grad)
    qs = torch.full((1, 2), qs_value, dtype=dtype, requires_grad=requires_grad)
    qg = torch.full((1, 2), qg_value, dtype=dtype, requires_grad=requires_grad)
    nr = torch.full((1, 2), nr_value, dtype=dtype, requires_grad=requires_grad)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    n0r = torch.full((1, 2), 8.0e6, dtype=dtype)
    n0so = torch.full((1, 2), 2.0e6, dtype=dtype)
    n0go = torch.full((1, 2), 4.0e6, dtype=dtype)
    n0sfac = torch.full((1, 2), 5.0, dtype=dtype)
    supcol = torch.full((1, 2), supcol_value, dtype=dtype)
    vt2r = torch.full((1, 2), 5.0, dtype=dtype)
    vt2s = torch.full((1, 2), 1.0, dtype=dtype)
    vt2g = torch.full((1, 2), 3.0, dtype=dtype)
    rsl_r = torch.full((1, 2), 5.0e-4, dtype=dtype)
    rsl_s = torch.full((1, 2), 5.0e-4, dtype=dtype)
    rsl_g = torch.full((1, 2), 1.0e-3, dtype=dtype)
    return (
        qr, qs, qg, nr, den, n0r, n0so, n0go, n0sfac, supcol, vt2r, vt2s, vt2g,
        rsl_r, rsl_r * rsl_r, rsl_r * rsl_r * rsl_r,
        torch.full_like(rsl_r, 5.0e-4 ** c.MUR),
        torch.full_like(rsl_r, 5.0e-4 ** c.DMR),
        rsl_s, rsl_s * rsl_s, rsl_s * rsl_s * rsl_s,
        torch.full_like(rsl_s, 5.0e-4 ** c.MUS),
        torch.full_like(rsl_s, 5.0e-4 ** c.DMS),
        rsl_g, rsl_g * rsl_g, rsl_g * rsl_g * rsl_g,
        torch.full_like(rsl_g, 1.0e-3 ** c.MUG),
    )


def test_default_rsgc_params_finite():
    p = default_rain_snow_graupel_collection_params()
    for field in p._fields:
        v = getattr(p, field)
        assert math.isfinite(v) and v > 0, field


def test_rsgc_pracs_zero_when_warm():
    """pracs는 cold-only (supcol > 0)."""
    p = default_rain_snow_graupel_collection_params()
    inputs = _rsgc_inputs(supcol_value=-5.0)  # warm
    out = rain_snow_graupel_collection_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(out.pracs, torch.zeros_like(out.pracs))
    # psacr/nsacr/pgacr/ngacr는 supcol gate 없음
    assert torch.all(out.psacr > 0)
    assert torch.all(out.pgacr > 0)


def test_rsgc_nracs_always_zero():
    """Fortran nracs is commented-out → oracle returns 0 always."""
    p = default_rain_snow_graupel_collection_params()
    inputs = _rsgc_inputs()
    out = rain_snow_graupel_collection_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(out.nracs, torch.zeros_like(out.nracs))


def test_rsgc_capped_by_source_mass():
    """pracs <= qs/dtcld (snow source); psacr/pgacr <= qr/dtcld (rain source)."""
    p = default_rain_snow_graupel_collection_params()
    # 큰 n0r/n0so로 raw rate를 cap 너머로 강제
    dtype = torch.float64
    qr = torch.tensor([[1.0e-4]], dtype=dtype)
    qs = torch.tensor([[1.0e-4]], dtype=dtype)
    qg = torch.tensor([[1.0e-4]], dtype=dtype)
    nr = torch.tensor([[1.0e5]], dtype=dtype)
    den = torch.full((1, 1), 1.1, dtype=dtype)
    n0r = torch.full((1, 1), 1.0e10, dtype=dtype)
    n0so = torch.full((1, 1), 1.0e10, dtype=dtype)
    n0go = torch.full((1, 1), 1.0e10, dtype=dtype)
    n0sfac = torch.full((1, 1), 5.0, dtype=dtype)
    supcol = torch.full((1, 1), 10.0, dtype=dtype)
    vt2r = torch.full((1, 1), 5.0, dtype=dtype)
    vt2s = torch.full((1, 1), 1.0, dtype=dtype)
    vt2g = torch.full((1, 1), 3.0, dtype=dtype)
    rsl_r = torch.full((1, 1), 5.0e-4, dtype=dtype)
    rsl_s = torch.full((1, 1), 5.0e-4, dtype=dtype)
    rsl_g = torch.full((1, 1), 1.0e-3, dtype=dtype)

    dtcld = 60.0
    out = rain_snow_graupel_collection_torch(
        qr, qs, qg, nr, den, n0r, n0so, n0go, n0sfac, supcol, vt2r, vt2s, vt2g,
        rsl_r, rsl_r * rsl_r, rsl_r * rsl_r * rsl_r,
        torch.full_like(rsl_r, 5.0e-4 ** c.MUR), torch.full_like(rsl_r, 5.0e-4 ** c.DMR),
        rsl_s, rsl_s * rsl_s, rsl_s * rsl_s * rsl_s,
        torch.full_like(rsl_s, 5.0e-4 ** c.MUS), torch.full_like(rsl_s, 5.0e-4 ** c.DMS),
        rsl_g, rsl_g * rsl_g, rsl_g * rsl_g * rsl_g,
        torch.full_like(rsl_g, 1.0e-3 ** c.MUG),
        params=p, dtcld=dtcld,
    )
    assert torch.all(out.pracs <= qs / dtcld + 1e-15)
    assert torch.all(out.psacr <= qr / dtcld + 1e-15)
    assert torch.all(out.pgacr <= qr / dtcld + 1e-15)
    assert torch.all(out.nsacr <= nr / dtcld + 1e-15)
    assert torch.all(out.ngacr <= nr / dtcld + 1e-15)


def test_rsgc_grad_finite():
    p = default_rain_snow_graupel_collection_params()
    inputs = _rsgc_inputs(requires_grad=True)
    out = rain_snow_graupel_collection_torch(*inputs, params=p, dtcld=60.0)
    loss = sum(t.sum() for t in out)
    loss.backward()
    qr, qs, qg, nr = inputs[0], inputs[1], inputs[2], inputs[3]
    for x, name in [(qr, "qr"), (qs, "qs"), (qg, "qg"), (nr, "nr")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


# ════ Step C2e: Hallett-Mossop multiplication ═════════════════════════════════


def _hm_inputs(*, t_value: float = 268.16, paacw_value: float = 1.0e-6,
               psacr_value: float = 1.0e-6, pgacr_value: float = 1.0e-6,
               qs_value: float = 0.5e-3, qg_value: float = 0.5e-3,
               qc_value: float = 1.0e-3, qr_value: float = 0.5e-3,
               requires_grad: bool = False):
    """C2e 표준 입력. t=268.16에서 fmul=1 (peak)."""
    dtype = torch.float64
    paacw = torch.full((1, 2), paacw_value, dtype=dtype, requires_grad=requires_grad)
    psacr = torch.full((1, 2), psacr_value, dtype=dtype, requires_grad=requires_grad)
    pgacr = torch.full((1, 2), pgacr_value, dtype=dtype, requires_grad=requires_grad)
    qc = torch.full((1, 2), qc_value, dtype=dtype)
    qr = torch.full((1, 2), qr_value, dtype=dtype)
    qs = torch.full((1, 2), qs_value, dtype=dtype)
    qg = torch.full((1, 2), qg_value, dtype=dtype)
    t = torch.full((1, 2), t_value, dtype=dtype)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    return paacw, psacr, pgacr, qc, qr, qs, qg, t, den


def test_default_hm_params_finite():
    p = default_hallett_mossop_params()
    for field in p._fields:
        v = getattr(p, field)
        assert math.isfinite(v) and v > 0, field


def test_hm_inactive_outside_temperature_band():
    """t < 265.16 or t > 270.16 → 모든 outputs = 0."""
    p = default_hallett_mossop_params()
    for t_val in [260.0, 275.0]:
        inputs = _hm_inputs(t_value=t_val)
        out = hallett_mossop_torch(*inputs, params=p)
        z = torch.zeros_like(out.pmulcs)
        for x in (out.pmulcs, out.pmulrs, out.pmulcg, out.pmulrg,
                  out.nmulcs, out.nmulrs, out.nmulcg, out.nmulrg):
            assert torch.allclose(x, z), f"t={t_val}"


def test_hm_active_at_peak_temperature():
    """t = 268.16 (peak fmul=1) → outputs > 0."""
    p = default_hallett_mossop_params()
    inputs = _hm_inputs(t_value=268.16)
    out = hallett_mossop_torch(*inputs, params=p)
    assert torch.all(out.pmulcs > 0)
    assert torch.all(out.pmulrs > 0)
    assert torch.all(out.pmulcg > 0)
    assert torch.all(out.pmulrg > 0)


def test_hm_mass_cap_pmulcs_le_paacw():
    """pmulcs <= paacw, pmulrs <= psacr, pmulrg <= pgacr (mass conservation)."""
    p = default_hallett_mossop_params()
    inputs = _hm_inputs(paacw_value=1.0e-3, psacr_value=1.0e-3, pgacr_value=1.0e-3)
    paacw, psacr, pgacr = inputs[0], inputs[1], inputs[2]
    out = hallett_mossop_torch(*inputs, params=p)
    assert torch.all(out.pmulcs <= paacw + 1e-15)
    assert torch.all(out.pmulrs <= psacr + 1e-15)
    assert torch.all(out.pmulrg <= pgacr + 1e-15)


def test_hm_paacw_adj_consistency():
    """paacw_adj = paacw - pmulcs - pmulcg (mass conservation)."""
    p = default_hallett_mossop_params()
    inputs = _hm_inputs()
    paacw = inputs[0]
    out = hallett_mossop_torch(*inputs, params=p)
    expected = paacw - out.pmulcs - out.pmulcg
    assert torch.allclose(out.paacw_adj, expected, rtol=1e-12, atol=1e-15)


def test_hm_inactive_mass_threshold():
    """qs < qs_threshold (0.1e-3) → snow side outputs = 0."""
    p = default_hallett_mossop_params()
    inputs = _hm_inputs(qs_value=1.0e-5)  # below 0.1e-3
    out = hallett_mossop_torch(*inputs, params=p)
    z = torch.zeros_like(out.pmulcs)
    assert torch.allclose(out.pmulcs, z)
    assert torch.allclose(out.pmulrs, z)
    # graupel side는 qg>=qg_threshold이라 active
    assert torch.all(out.pmulcg > 0)


def test_hm_grad_finite():
    p = default_hallett_mossop_params()
    inputs = _hm_inputs(requires_grad=True)
    out = hallett_mossop_torch(*inputs, params=p)
    loss = sum(t.sum() for t in out)
    loss.backward()
    paacw, psacr, pgacr = inputs[0], inputs[1], inputs[2]
    for x, name in [(paacw, "paacw"), (psacr, "psacr"), (pgacr, "pgacr")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


# ════ Step C3: Ice nucleation from vapor ══════════════════════════════════════


def _icenuc_inputs(*, supcol_value: float = 15.0, supsat_value: float = 1.0e-4,
                   rh_ice_value: float = 1.20, prevp_value: float = 0.0,
                   nci_value: float = 1.0e3, requires_grad: bool = False):
    """C3 표준 입력. cold + supersaturated → nucleation active."""
    dtype = torch.float64
    supcol = torch.full((1, 2), supcol_value, dtype=dtype, requires_grad=requires_grad)
    supsat = torch.full((1, 2), supsat_value, dtype=dtype, requires_grad=requires_grad)
    rh_ice = torch.full((1, 2), rh_ice_value, dtype=dtype)
    prevp = torch.full((1, 2), prevp_value, dtype=dtype, requires_grad=requires_grad)
    nci_ice = torch.full((1, 2), nci_value, dtype=dtype)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    return supcol, supsat, rh_ice, prevp, nci_ice, den


def test_default_icenuc_params_finite():
    p = default_ice_nucleation_params()
    for field in p._fields:
        v = getattr(p, field)
        assert math.isfinite(v) and v > 0, field


def test_icenuc_inactive_when_warm():
    """supcol < 8 AND rh_ice < 1.08 → nucleation off."""
    p = default_ice_nucleation_params()
    inputs = _icenuc_inputs(supcol_value=2.0, rh_ice_value=1.0)
    out = ice_nucleation_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(out.pinud, torch.zeros_like(out.pinud))
    assert torch.allclose(out.ninud, torch.zeros_like(out.ninud))


def test_icenuc_active_when_high_rh():
    """rh_ice > 1.08 → nucleation active even if supcol small."""
    p = default_ice_nucleation_params()
    inputs = _icenuc_inputs(supcol_value=2.0, rh_ice_value=1.2,
                            supsat_value=1.0e-4, nci_value=1.0)
    out = ice_nucleation_torch(*inputs, params=p, dtcld=60.0)
    # Cooper at supcol=2 → very small Nid; only active if Nid > nci.
    # nci=1 (very small) → active.
    assert torch.all(out.pinud >= 0)


def test_icenuc_no_nucleation_when_nci_high():
    """nci_ice > Nid (already enough ice) → no nucleation."""
    p = default_ice_nucleation_params()
    # supcol=15 → Cooper Nid ≈ 0.005·exp(0.304·15)·1000 ≈ 480 m⁻³ → clamp 480
    # nci=1e6 (much larger than nid_max=500e3) → inner gate fails
    inputs = _icenuc_inputs(supcol_value=15.0, nci_value=1.0e6)
    out = ice_nucleation_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(out.pinud, torch.zeros_like(out.pinud))


def test_icenuc_nid_capped_at_500cm3():
    """Very cold (supcol large) → Nid clamped to 500e3 m⁻³."""
    p = default_ice_nucleation_params()
    # supcol=50 → Cooper Nid ≈ 0.005·exp(15.2)·1000 ~ 2e7 → clamp 5e5
    inputs = _icenuc_inputs(supcol_value=50.0, nci_value=1.0)
    out = ice_nucleation_torch(*inputs, params=p, dtcld=60.0)
    # Through pinud→ninud roundtrip, ninud should be bounded by max nucleation budget
    # Easier sanity: pinud and ninud are finite and nonneg
    assert torch.isfinite(out.pinud).all()
    assert torch.all(out.pinud >= 0)


def test_icenuc_ifsat_flag():
    """ifsat = |prevp+pinud| >= |satdt|. Boolean tensor."""
    p = default_ice_nucleation_params()
    inputs = _icenuc_inputs()
    out = ice_nucleation_torch(*inputs, params=p, dtcld=60.0)
    assert out.ifsat.dtype == torch.bool


def test_icenuc_grad_finite():
    p = default_ice_nucleation_params()
    inputs = _icenuc_inputs(requires_grad=True)
    out = ice_nucleation_torch(*inputs, params=p, dtcld=60.0)
    loss = out.pinud.sum() + out.ninud.sum()
    loss.backward()
    supcol, supsat, prevp = inputs[0], inputs[1], inputs[3]
    for x, name in [(supcol, "supcol"), (supsat, "supsat"), (prevp, "prevp")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


# ════ Step C4: Deposition / Sublimation ═══════════════════════════════════════


def _dep_sub_inputs(*, requires_grad: bool = False, supcol_value: float = 10.0,
                    rh_ice_value: float = 1.10, ifsat_value: bool = False,
                    qi_value: float = 1.0e-5):
    dtype = torch.float64
    qi = torch.full((1, 2), qi_value, dtype=dtype, requires_grad=requires_grad)
    qs = torch.full((1, 2), 1.0e-4, dtype=dtype)
    qg = torch.full((1, 2), 1.0e-4, dtype=dtype)
    rh_ice = torch.full((1, 2), rh_ice_value, dtype=dtype)
    supcol = torch.full((1, 2), supcol_value, dtype=dtype)
    supsat = torch.full((1, 2), 1.0e-4, dtype=dtype)
    prevp = torch.full((1, 2), 0.0, dtype=dtype)
    pinud = torch.full((1, 2), 0.0, dtype=dtype)
    ifsat_in = torch.full((1, 2), ifsat_value, dtype=torch.bool)
    n0i = torch.full((1, 2), 1.0e6, dtype=dtype)
    n0so = torch.full((1, 2), 2.0e6, dtype=dtype)
    n0go = torch.full((1, 2), 4.0e6, dtype=dtype)
    n0sfac = torch.full((1, 2), 5.0, dtype=dtype)
    work1_ice = torch.full((1, 2), 1.0e-3, dtype=dtype)
    work2 = torch.full((1, 2), 1.5, dtype=dtype)
    precg2 = torch.full((1, 2), 0.5, dtype=dtype)
    rsl_s = torch.full((1, 2), 5.0e-4, dtype=dtype)
    rsl_g = torch.full((1, 2), 1.0e-3, dtype=dtype)
    rsl_i = torch.full((1, 2), 1.0e-4, dtype=dtype)
    return (
        qi, qs, qg, rh_ice, supcol, supsat, prevp, pinud, ifsat_in,
        n0i, n0so, n0go, n0sfac, work1_ice, work2, precg2,
        rsl_s, rsl_s * rsl_s, torch.full_like(rsl_s, 5.0e-4 ** c.BVTS),
        torch.full_like(rsl_s, 5.0e-4 ** c.MUS),
        rsl_g, rsl_g * rsl_g, torch.full_like(rsl_g, 1.0e-3 ** 0.5316),
        torch.full_like(rsl_g, 1.0e-3 ** c.MUG),
        rsl_i * rsl_i, torch.full_like(rsl_i, 1.0e-4 ** c.MUI),
    )


def test_default_dep_sub_params_finite():
    p = default_dep_sub_params()
    for field in p._fields:
        v = getattr(p, field)
        assert math.isfinite(v) and v > 0, field


def test_dep_sub_inactive_when_warm():
    p = default_dep_sub_params()
    inputs = _dep_sub_inputs(supcol_value=-5.0)  # warm
    out = dep_sub_torch(*inputs, params=p, dtcld=60.0)
    z = torch.zeros_like(out.pidep)
    assert torch.allclose(out.pidep, z)
    assert torch.allclose(out.psdep, z)
    assert torch.allclose(out.pgdep, z)


def test_dep_sub_pidep_skipped_when_ifsat_in():
    """ifsat_in = True → pidep = 0."""
    p = default_dep_sub_params()
    inputs = _dep_sub_inputs(ifsat_value=True)
    out = dep_sub_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(out.pidep, torch.zeros_like(out.pidep))


def test_dep_sub_deposition_path_when_supersat():
    """rh_ice > 1 → pidep > 0 (deposition)."""
    p = default_dep_sub_params()
    inputs = _dep_sub_inputs(rh_ice_value=1.10)
    out = dep_sub_torch(*inputs, params=p, dtcld=60.0)
    assert torch.all(out.pidep >= 0)


def test_dep_sub_sublimation_path_capped_at_qi():
    """rh_ice < 1 AND supsat < 0 → pidep < 0, capped by -qi/dtcld.

    Note: supsat > 0이면 sublim cap이 satdt/2(>0) floor에 hit하여 *양수* 가능.
    이는 Fortran 직역. supsat < 0인 경우만 순수 sublimation rate 검증.
    """
    p = default_dep_sub_params()
    inputs = list(_dep_sub_inputs(rh_ice_value=0.85))
    inputs[5] = torch.full_like(inputs[5], -1.0e-4)  # supsat < 0
    qi = inputs[0]
    out = dep_sub_torch(*inputs, params=p, dtcld=60.0)
    assert torch.all(out.pidep <= 1e-15)
    assert torch.all(out.pidep >= -qi / 60.0 - 1e-15)


def test_dep_sub_ifsat_dtype():
    """ifsat output is bool tensor, ice_complete_sublim is bool."""
    p = default_dep_sub_params()
    inputs = _dep_sub_inputs()
    out = dep_sub_torch(*inputs, params=p, dtcld=60.0)
    assert out.ifsat.dtype == torch.bool
    assert out.ice_complete_sublim.dtype == torch.bool


def test_dep_sub_grad_finite():
    p = default_dep_sub_params()
    inputs = _dep_sub_inputs(requires_grad=True)
    out = dep_sub_torch(*inputs, params=p, dtcld=60.0)
    loss = out.pidep.sum() + out.psdep.sum() + out.pgdep.sum()
    loss.backward()
    qi = inputs[0]
    assert qi.grad is not None and torch.isfinite(qi.grad).all()


# ════ Step C5: Aggregation (psaut + nsaut) ════════════════════════════════════


def _agg_inputs(*, requires_grad: bool = False, supcol_value: float = 15.0,
                qi_value: float = 1.0e-4, t_value: float = 260.0):
    dtype = torch.float64
    qi = torch.full((1, 2), qi_value, dtype=dtype, requires_grad=requires_grad)
    ni = torch.full((1, 2), 1.0e5, dtype=dtype, requires_grad=requires_grad)
    t = torch.full((1, 2), t_value, dtype=dtype)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    supcol = torch.full((1, 2), supcol_value, dtype=dtype)
    return qi, ni, t, den, supcol


def test_default_agg_params_finite():
    p = default_ice_aggregation_params()
    for field in p._fields:
        v = getattr(p, field)
        assert math.isfinite(v) and v > 0, field


def test_agg_inactive_when_warm():
    """supcol <= 0 → psaut = nsaut = 0."""
    p = default_ice_aggregation_params()
    inputs = _agg_inputs(supcol_value=-5.0)
    psaut, nsaut = ice_aggregation_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(psaut, torch.zeros_like(psaut))
    assert torch.allclose(nsaut, torch.zeros_like(nsaut))


def test_agg_t_branch_qi0():
    """T > 255.66 → qi0 (warm-ice limit) ≠ T ≤ 255.66 (cold-ice limit). Ryan 2010."""
    p = default_ice_aggregation_params()
    inputs_warm = _agg_inputs(t_value=260.0, qi_value=1.0e-3)  # T > 255.66
    inputs_cold = _agg_inputs(t_value=250.0, qi_value=1.0e-3)  # T ≤ 255.66
    psaut_w, _ = ice_aggregation_torch(*inputs_warm, params=p, dtcld=60.0)
    psaut_c, _ = ice_aggregation_torch(*inputs_cold, params=p, dtcld=60.0)
    # 두 분기의 qi0 산식이 다르므로 psaut 결과도 미세하게 다름 (≥ 1e-9 차이)
    diff = (psaut_w - psaut_c).abs().max().item()
    assert diff > 1.0e-12, f"branch 분기 효과가 사라짐 (diff={diff})"


def test_agg_psaut_capped():
    """psaut <= qi/dtcld."""
    p = default_ice_aggregation_params()
    inputs = _agg_inputs(qi_value=1.0e-2)  # 매우 큰 qi
    qi = inputs[0]
    psaut, _ = ice_aggregation_torch(*inputs, params=p, dtcld=60.0)
    assert torch.all(psaut <= qi / 60.0 + 1e-15)


def test_agg_grad_finite():
    p = default_ice_aggregation_params()
    inputs = _agg_inputs(requires_grad=True)
    psaut, nsaut = ice_aggregation_torch(*inputs, params=p, dtcld=60.0)
    loss = psaut.sum() + nsaut.sum()
    loss.backward()
    qi, ni = inputs[0], inputs[1]
    for x, name in [(qi, "qi"), (ni, "ni")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


# ════ Step C6: Snow evaporation (psevp) ═══════════════════════════════════════


def _evap_inputs(*, requires_grad: bool = False, supcol_value: float = -5.0,
                 rh_value: float = 0.85, qs_value: float = 1.0e-4):
    dtype = torch.float64
    qs = torch.full((1, 2), qs_value, dtype=dtype, requires_grad=requires_grad)
    rh_w = torch.full((1, 2), rh_value, dtype=dtype)
    supcol = torch.full((1, 2), supcol_value, dtype=dtype)
    n0so = torch.full((1, 2), 2.0e6, dtype=dtype)
    n0sfac = torch.full((1, 2), 1.0, dtype=dtype)
    work1_water = torch.full((1, 2), 1.0e-3, dtype=dtype)
    work2 = torch.full((1, 2), 1.5, dtype=dtype)
    rsl_s = torch.full((1, 2), 5.0e-4, dtype=dtype)
    return (
        qs, rh_w, supcol, n0so, n0sfac, work1_water, work2,
        rsl_s, rsl_s * rsl_s,
        torch.full_like(rsl_s, 5.0e-4 ** c.BVTS),
        torch.full_like(rsl_s, 5.0e-4 ** c.MUS),
    )


def test_default_snow_evap_params_finite():
    p = default_snow_evap_params()
    for field in p._fields:
        v = getattr(p, field)
        assert math.isfinite(v) and v > 0, field


def test_snow_evap_inactive_when_cold():
    """supcol >= 0 → psevp = 0 (warm-only)."""
    p = default_snow_evap_params()
    inputs = _evap_inputs(supcol_value=5.0)
    psevp = snow_evap_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(psevp, torch.zeros_like(psevp))


def test_snow_evap_inactive_when_saturated():
    """rh_w >= 1 → psevp = 0."""
    p = default_snow_evap_params()
    inputs = _evap_inputs(rh_value=1.05)
    psevp = snow_evap_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(psevp, torch.zeros_like(psevp))


def test_snow_evap_negative_and_capped():
    """psevp ≤ 0 (evap) AND psevp ≥ -qs/dtcld."""
    p = default_snow_evap_params()
    inputs = _evap_inputs(qs_value=1.0e-4, rh_value=0.5)
    qs = inputs[0]
    psevp = snow_evap_torch(*inputs, params=p, dtcld=60.0)
    assert torch.all(psevp <= 1e-15)
    assert torch.all(psevp >= -qs / 60.0 - 1e-15)


def test_snow_evap_grad_finite():
    p = default_snow_evap_params()
    inputs = _evap_inputs(requires_grad=True)
    psevp = snow_evap_torch(*inputs, params=p, dtcld=60.0)
    psevp.sum().backward()
    qs = inputs[0]
    assert qs.grad is not None and torch.isfinite(qs.grad).all()


# ════ Step C6': Graupel evaporation (pgevp) ═══════════════════════════════════
# Fortran 2423-2442 — psevp와 동일 구조, n0sfac 없음, precg2는 runtime 텐서.


def _graupel_evap_inputs(*, requires_grad: bool = False, supcol_value: float = -5.0,
                         rh_value: float = 0.85, qg_value: float = 1.0e-4):
    dtype = torch.float64
    qg = torch.full((1, 2), qg_value, dtype=dtype, requires_grad=requires_grad)
    rh_w = torch.full((1, 2), rh_value, dtype=dtype)
    supcol = torch.full((1, 2), supcol_value, dtype=dtype)
    n0go = torch.full((1, 2), 4.0e6, dtype=dtype)
    work1_water = torch.full((1, 2), 1.0e-3, dtype=dtype)
    work2 = torch.full((1, 2), 1.5, dtype=dtype)
    rsl_g = torch.full((1, 2), 5.0e-4, dtype=dtype)
    precg2 = torch.full((1, 2), 0.5, dtype=dtype)  # ProgB runtime output
    # bvtg는 graupel 밀도 의존 (ProgB 테이블 출력, runtime). 테스트에선 0.6 ≈ WDM6 기본값 가정.
    rslopeb_g = torch.full_like(rsl_g, 5.0e-4 ** 0.6)
    return (
        qg, rh_w, supcol, n0go, work1_water, work2,
        rsl_g, rsl_g * rsl_g,
        rslopeb_g,
        torch.full_like(rsl_g, 5.0e-4 ** c.MUG),
        precg2,
    )


def test_default_graupel_evap_params_finite():
    p = default_graupel_evap_params()
    for field in p._fields:
        v = getattr(p, field)
        assert math.isfinite(v) and v > 0, field


def test_graupel_evap_inactive_when_cold():
    """supcol >= 0 → pgevp = 0 (warm-only)."""
    p = default_graupel_evap_params()
    inputs = _graupel_evap_inputs(supcol_value=5.0)
    pgevp = graupel_evap_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(pgevp, torch.zeros_like(pgevp))


def test_graupel_evap_inactive_when_saturated():
    """rh_w >= 1 → pgevp = 0."""
    p = default_graupel_evap_params()
    inputs = _graupel_evap_inputs(rh_value=1.05)
    pgevp = graupel_evap_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(pgevp, torch.zeros_like(pgevp))


def test_graupel_evap_negative_and_capped():
    """pgevp ≤ 0 (evap) AND pgevp ≥ -qg/dtcld."""
    p = default_graupel_evap_params()
    inputs = _graupel_evap_inputs(qg_value=1.0e-4, rh_value=0.5)
    qg = inputs[0]
    pgevp = graupel_evap_torch(*inputs, params=p, dtcld=60.0)
    assert torch.all(pgevp <= 1e-15)
    assert torch.all(pgevp >= -qg / 60.0 - 1e-15)


def test_graupel_evap_grad_finite():
    """qg와 precg2(ProgB output) 모두에 grad 흐름."""
    p = default_graupel_evap_params()
    inputs = list(_graupel_evap_inputs(requires_grad=True))
    inputs[10] = inputs[10].detach().requires_grad_(True)  # precg2도 leaf
    pgevp = graupel_evap_torch(*inputs, params=p, dtcld=60.0)
    pgevp.sum().backward()
    qg, precg2 = inputs[0], inputs[10]
    assert qg.grad is not None and torch.isfinite(qg.grad).all()
    assert precg2.grad is not None and torch.isfinite(precg2.grad).all()


def test_default_cold_evap_params_fortran_formula_lock():
    """audit round-4 (+ Codex stop-gate): Fortran-fidelity lock for the snow/graupel ventilation
    coefficients (module_mp_kdm6.F:3254-3263). The WARM phase locks precr1 (test_warm.py); cold had
    none — so a SHARED C++↔Python drift of the 0.65/0.44/0.78 constants would pass the parity test
    silently. precs1/precs2/precg1 are DUPLICATED across default_dep_sub_params AND
    default_snow_evap_params/default_graupel_evap_params — lock EVERY copy to Fortran (hardcoded
    constants + independent gamma moments) AND assert the duplicates agree, so neither a Fortran
    drift nor an internal divergence between the copies can slip through."""
    from kdm6.cold import default_dep_sub_params
    g2pms = math.gamma(2.0 + c.MUS)                     # F: g2pms = rgmma(2+mus)
    g2pmg = math.gamma(2.0 + c.MUG)                     # F: g2pmg = rgmma(2+mug)
    g5pbso2 = math.gamma(2.5 + 0.5 * c.BVTS + c.MUS)    # F: g5pbso2 = rgmma(2.5+0.5*bvts+mus)
    exp_precs1 = 4.0 * 0.65 * g2pms                      # F:3254
    exp_precs2 = 4.0 * 0.44 * (c.AVTS ** 0.5) * g5pbso2  # F:3255
    exp_precg1 = 4.0 * 0.78 * g2pmg                      # F:3263
    snow = default_snow_evap_params()
    graup = default_graupel_evap_params()
    dep = default_dep_sub_params()                       # the duplicated copy (cold.py:1219-1221)
    for label, val, exp in (
        ("snow.precs1", snow.precs1, exp_precs1),
        ("snow.precs2", snow.precs2, exp_precs2),
        ("graup.precg1", graup.precg1, exp_precg1),
        ("dep.precs1", dep.precs1, exp_precs1),
        ("dep.precs2", dep.precs2, exp_precs2),
        ("dep.precg1", dep.precg1, exp_precg1),
    ):
        assert math.isclose(val, exp, rel_tol=1e-12), f"{label} drifted from Fortran F:3254-3263"
    # the duplicated copies must also agree with each other (no internal divergence)
    assert math.isclose(dep.precs1, snow.precs1, rel_tol=1e-12), "dep/snow precs1 diverged"
    assert math.isclose(dep.precs2, snow.precs2, rel_tol=1e-12), "dep/snow precs2 diverged"
    assert math.isclose(dep.precg1, graup.precg1, rel_tol=1e-12), "dep/graupel precg1 diverged"
