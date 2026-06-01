"""thermodynamics 진단 검증 — Step F0."""
from __future__ import annotations

import math

import torch

from kdm6 import constants as c
from kdm6.thermo import (
    ThermoParams,
    compute_cpm,
    compute_denfac,
    compute_qs_ice,
    compute_qs_water,
    compute_rh,
    compute_supcol,
    compute_supsat,
    compute_work2_venfac,
    compute_xl,
    default_thermo_params,
)


def test_default_thermo_params_finite():
    p = default_thermo_params()
    for field in p._fields:
        v = getattr(p, field)
        assert math.isfinite(v), field


def test_default_thermo_params_xa_xb_consistency():
    """xa = -dldt/rv, xb = xa + hvap/(rv·ttp). Fortran module_mp_kdm6.F:901-905 uses
    dldt = cvap - cliq = cpv - cliq (cvap=cpv per line 901); the previous
    Python convention `cliq - cpv` had inverted sign of xa/xai/xb/xbi at
    T<200K. See [[feedback-dldt-sign-convention]]."""
    p = default_thermo_params()
    dldt = p.cpv - p.cliq                          # Fortran cvap - cliq
    expected_xa = -dldt / p.rv                     # = (cliq - cpv)/rv > 0
    expected_xb = expected_xa + p.xlv0 / (p.rv * p.ttp)
    assert math.isclose(p.xa, expected_xa, rel_tol=1e-12)
    assert math.isclose(p.xb, expected_xb, rel_tol=1e-12)
    assert p.xa > 0, "Fortran xa must be positive (cliq > cpv)"


def test_compute_cpm_dry_vs_moist():
    """q=0 → cpd; q=1 (impossible but limit) → cpv."""
    p = default_thermo_params()
    q_dry = torch.zeros((1,), dtype=torch.float64)
    q_wet = torch.full((1,), 0.5, dtype=torch.float64)  # high but finite
    assert torch.isclose(compute_cpm(q_dry, params=p), torch.tensor(p.cpd, dtype=torch.float64))
    cpm_wet = compute_cpm(q_wet, params=p)
    expected = p.cpd * (1.0 - 0.5) + 0.5 * p.cpv
    assert torch.isclose(cpm_wet, torch.tensor(expected, dtype=torch.float64))


def test_compute_xl_at_freezing():
    """t=t0c → xl = xlv0."""
    p = default_thermo_params()
    t = torch.full((1,), p.t0c, dtype=torch.float64)
    xl = compute_xl(t, params=p)
    assert torch.isclose(xl, torch.tensor(p.xlv0, dtype=torch.float64))


def test_compute_supcol_clamp():
    """t > 393.15 또는 t < 153.15 모두 clamp."""
    p = default_thermo_params()
    t = torch.tensor([100.0, 200.0, 300.0, 400.0], dtype=torch.float64)
    sc = compute_supcol(t, params=p)
    # t=100 → clamp 153.15 → supcol = 273.15-153.15 = 120
    assert torch.isclose(sc[0], torch.tensor(120.0, dtype=torch.float64))
    # t=400 → clamp 393.15 → supcol = -120
    assert torch.isclose(sc[3], torch.tensor(-120.0, dtype=torch.float64))


def test_compute_qs_water_at_273():
    """t=t0c+0.01=ttp, p=1e5 → es=psat → qs ≈ ep2·psat/(p-psat) ≈ 0.622·611/(1e5-611) ≈ 3.82e-3."""
    p = default_thermo_params()
    t = torch.tensor([p.ttp], dtype=torch.float64)
    pres = torch.tensor([1.0e5], dtype=torch.float64)
    qs = compute_qs_water(t, pres, params=p)
    expected = p.ep2 * p.psat / (1.0e5 - p.psat)
    assert torch.isclose(qs, torch.tensor(expected, dtype=torch.float64), rtol=1e-6)


def test_compute_qs_ice_below_freezing():
    """T < t0c → ice 식 (xa=xai, xb=xbi)."""
    p = default_thermo_params()
    t = torch.tensor([260.0], dtype=torch.float64)
    pres = torch.tensor([1.0e5], dtype=torch.float64)
    qs_w = compute_qs_water(t, pres, params=p)
    qs_i = compute_qs_ice(t, pres, params=p)
    # T<t0c일 때 ice 식 사용 → qs_ice ≠ qs_water
    assert not torch.isclose(qs_w, qs_i)
    # 일반적으로 ice saturation < water saturation (T<t0c)
    assert qs_i < qs_w


def test_compute_rh_basic():
    p = default_thermo_params()
    q = torch.tensor([1.0e-3], dtype=torch.float64)
    qs = torch.tensor([2.0e-3], dtype=torch.float64)
    rh = compute_rh(q, qs, params=p)
    assert torch.isclose(rh, torch.tensor(0.5, dtype=torch.float64))


def test_compute_denfac_at_reference():
    """den=den0 → denfac=1."""
    p = default_thermo_params()
    den = torch.tensor([p.den0], dtype=torch.float64)
    df = compute_denfac(den, params=p)
    assert torch.isclose(df, torch.tensor(1.0, dtype=torch.float64))


def test_compute_supsat_subsat():
    """q < qs → supsat < 0."""
    p = default_thermo_params()
    q = torch.tensor([1.0e-3], dtype=torch.float64)
    qs1 = torch.tensor([2.0e-3], dtype=torch.float64)
    ss = compute_supsat(q, qs1, params=p)
    assert torch.all(ss < 0)


def test_compute_work2_venfac_finite():
    p = default_thermo_params()
    pres = torch.tensor([8.0e4], dtype=torch.float64)
    t = torch.tensor([280.0], dtype=torch.float64)
    den = torch.tensor([1.1], dtype=torch.float64)
    w2 = compute_work2_venfac(pres, t, den, params=p)
    assert torch.isfinite(w2).all()
    assert torch.all(w2 > 0)


def test_thermo_grad_finite():
    """t, q, p, den에 대해 backward 통과."""
    p = default_thermo_params()
    t = torch.tensor([280.0], dtype=torch.float64, requires_grad=True)
    q = torch.tensor([5.0e-3], dtype=torch.float64, requires_grad=True)
    pres = torch.tensor([1.0e5], dtype=torch.float64, requires_grad=True)
    den = torch.tensor([1.1], dtype=torch.float64, requires_grad=True)

    cpm = compute_cpm(q, params=p)
    xl = compute_xl(t, params=p)
    sc = compute_supcol(t, params=p)
    qs1 = compute_qs_water(t, pres, params=p)
    qs2 = compute_qs_ice(t, pres, params=p)
    rh = compute_rh(q, qs1, params=p)
    df = compute_denfac(den, params=p)
    w2 = compute_work2_venfac(pres, t, den, params=p)

    loss = cpm.sum() + xl.sum() + sc.sum() + qs1.sum() + qs2.sum() + rh.sum() + df.sum() + w2.sum()
    loss.backward()
    for x, name in [(t, "t"), (q, "q"), (pres, "p"), (den, "den")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name
