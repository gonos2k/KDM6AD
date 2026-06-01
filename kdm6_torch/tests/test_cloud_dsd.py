"""cloud DSD diagnostics 검증."""
from __future__ import annotations

import math

import torch

from kdm6 import constants as c
from kdm6.cloud_dsd import (
    CloudDsdParams,
    default_cloud_dsd_params,
    diag_avedia_cloud_torch,
    diag_avedia_rain_torch,
    diag_cloud_slope_torch,
    diag_lencon_torch,
    diag_qcr_torch,
    diag_sigma_cloud_torch,
)


def test_default_cloud_dsd_params_finite_and_positive():
    p = default_cloud_dsd_params()
    for field in p._fields:
        v = getattr(p, field)
        assert math.isfinite(v) and v > 0, field


def test_default_cloud_dsd_params_qc0_qc1():
    """qc0 (continental) < qc1 (maritime), since xncr0 < xncr1."""
    p = default_cloud_dsd_params()
    assert p.qc0 < p.qc1
    # qc_base = 4/3 * pi * denr * r0^3 / den0
    qc_base = (4.0 / 3.0) * math.pi * c.DENR * (c.R0 ** 3) / c.DEN0
    assert math.isclose(p.qc0, qc_base * c.XNCR0, rel_tol=1e-12)
    assert math.isclose(p.qc1, qc_base * c.XNCR1, rel_tol=1e-12)


def test_diag_cloud_slope_clamped():
    """rslopec ∈ [1/lamdacmax, 1/lamdacmin]. Item #6: the clamp is a structurally-required
    numerical guard (tensor mask-multiply turns an unclamped Inf into Inf×0=NaN, which
    Fortran's branchy structure avoids) — see parity tracker #6."""
    p = default_cloud_dsd_params()
    dtype = torch.float64
    qc = torch.tensor([[1.0e-3, 1.0e-7]], dtype=dtype)  # high qc, very low qc
    nc = torch.tensor([[1.0e8, 1.0e8]], dtype=dtype)
    den = torch.full((1, 2), 1.1, dtype=dtype)

    rslopec = diag_cloud_slope_torch(qc, nc, den, params=p)
    assert torch.all(rslopec >= 1.0 / p.lamdacmax - 1e-30)
    assert torch.all(rslopec <= 1.0 / p.lamdacmin + 1e-30)


def test_diag_avedia_formulas():
    """avedia_c = rslopec * g3pmc^(1/3); avedia_r = rslope_r * (g4pmr/g1pmr)^0.3333333 (F:1671 literal, #4)."""
    p = default_cloud_dsd_params()
    dtype = torch.float64
    rslopec = torch.tensor([[1.0e-5]], dtype=dtype)
    rslope_r = torch.tensor([[5.0e-4]], dtype=dtype)

    avedia_c = diag_avedia_cloud_torch(rslopec, params=p)
    avedia_r = diag_avedia_rain_torch(rslope_r, params=p)

    expected_c = 1.0e-5 * p.g3pmc ** (1.0 / 3.0)          # cloud: F:1670 uses 1./3.
    expected_r = 5.0e-4 * p.g4pmr_over_g1pmr ** 0.3333333  # rain: F:1671 truncated literal (#4)
    assert torch.allclose(avedia_c, torch.full_like(avedia_c, expected_c), rtol=1e-12)
    assert torch.allclose(avedia_r, torch.full_like(avedia_r, expected_r), rtol=1e-12)


def test_diag_sigma_cloud_finite_and_nonnegative():
    """sigma_c is finite (not NaN) and >= 0.

    review6 audit 후 `rgmma = Γ` 직역 적용. muc=2에서:
        g3pmc = Γ(2) = 1.0,  g6pmc = Γ(3) = 2.0
        var_factor = g6pmc - g3pmc² = 2.0 - 1.0 = 1.0 (positive)
    이전 docstring의 "NaN 우려"는 reciprocal-gamma 버그의 잔재였음. 현재
    Fortran의 (var_factor)^(1/6) = 1.0^(1/6) = 1.0으로 정상 동작.
    """
    p = default_cloud_dsd_params()
    dtype = torch.float64
    rslopec = torch.tensor([[1.0e-5, 5.0e-5]], dtype=dtype)
    sigma_c = diag_sigma_cloud_torch(rslopec, params=p)
    assert torch.all(torch.isfinite(sigma_c))
    assert torch.all(sigma_c >= 0)
    # var_factor는 이제 양수 (Fortran 직역 일치).
    assert p.g6pmc - p.g3pmc ** 2 > 0


def test_diag_lencon_lenconcr_floor():
    """lenconcr = max(1.2*lencon, qcrmin) — floor 보장."""
    p = default_cloud_dsd_params()
    dtype = torch.float64
    qc = torch.full((1, 2), 1.0e-9, dtype=dtype)  # very low qc → lencon ≈ 0
    den = torch.full((1, 2), 1.1, dtype=dtype)
    avedia_c = torch.full((1, 2), 5.0e-5, dtype=dtype)
    sigma_c = torch.full((1, 2), 2.0e-5, dtype=dtype)

    lencon, lenconcr = diag_lencon_torch(qc, den, avedia_c, sigma_c)
    assert torch.all(lenconcr >= c.QCRMIN - 1e-30)


def test_diag_qcr_sea_land_branch():
    """Mirrors Fortran module_mp_kdm6.F:840-847: sea(slmsk==2)→qc0, land→qc1.
    Physical reasoning: clean ocean air = low CCN = low qcr threshold = qc0;
    dusty land air = high CCN = high qcr threshold = qc1."""
    p = default_cloud_dsd_params()
    sea_mask = torch.tensor([[True, False, True]])
    qcr = diag_qcr_torch(sea_mask, params=p)
    expected = torch.tensor([[p.qc0, p.qc1, p.qc0]], dtype=torch.float64)
    assert torch.allclose(qcr, expected, rtol=1e-12)


def test_cloud_slope_grad_finite():
    p = default_cloud_dsd_params()
    dtype = torch.float64
    qc = torch.tensor([[1.0e-4, 5.0e-4]], dtype=dtype, requires_grad=True)
    nc = torch.tensor([[1.0e8, 2.0e8]], dtype=dtype, requires_grad=True)
    den = torch.full((1, 2), 1.1, dtype=dtype)

    rslopec = diag_cloud_slope_torch(qc, nc, den, params=p)
    rslopec.sum().backward()
    assert qc.grad is not None and torch.isfinite(qc.grad).all()
    assert nc.grad is not None and torch.isfinite(nc.grad).all()


# review7#3 hardcoded regression: rgmma=Γ 부호 영구 보호 (1/Γ로 회귀 방지).


def test_g4pmr_over_g1pmr_is_24():
    """MUR=1 ⇒ g4pmr = Γ(5) = 24, g1pmr = Γ(2) = 1, ratio = 24 (review7#3)."""
    assert c.MUR == 1.0, "MUR default must be 1 for this regression test"
    p = default_cloud_dsd_params()
    assert math.isclose(p.g4pmr_over_g1pmr, 24.0, rel_tol=1e-12)


def test_avedia_rain_hardcoded():
    """avedia_r = rslope_r · (g4pmr/g1pmr)^0.3333333 — Fortran F:1671 truncated literal (#4)."""
    p = default_cloud_dsd_params()
    rslope_r = torch.tensor([[1.0e-4, 5.0e-4]], dtype=torch.float64)
    out = diag_avedia_rain_torch(rslope_r, params=p)
    expected = rslope_r * (p.g4pmr_over_g1pmr ** 0.3333333)
    assert torch.allclose(out, expected, rtol=1e-12)


def test_g3pmc_g6pmc_hardcoded():
    """MUC=2: g3pmc = Γ(2) = 1, g6pmc = Γ(3) = 2 (review7#3)."""
    assert c.MUC == 2.0, "MUC default must be 2 for this regression test"
    p = default_cloud_dsd_params()
    assert math.isclose(p.g3pmc, 1.0, rel_tol=1e-12)
    assert math.isclose(p.g6pmc, 2.0, rel_tol=1e-12)
    # var_factor positive (이전 reciprocal-gamma 버그 시 -0.5 였음)
    assert p.g6pmc - p.g3pmc ** 2 > 0
