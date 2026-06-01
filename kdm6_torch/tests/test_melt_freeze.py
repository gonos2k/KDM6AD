"""melt/freeze oracle 검증 — Step D."""
from __future__ import annotations

import math

import torch

from kdm6 import constants as c
from kdm6.melt_freeze import (
    BiggCloudOutputs,
    BiggCloudParams,
    BiggRainOutputs,
    BiggRainParams,
    ContactFreezingOutputs,
    ContactFreezingParams,
    EnhancedMeltingOutputs,
    EnhancedMeltingParams,
    MeltingOutputs,
    MeltingParams,
    bigg_cloud_freezing_torch,
    bigg_rain_freezing_torch,
    contact_freezing_torch,
    default_bigg_cloud_params,
    default_bigg_rain_params,
    default_contact_freezing_params,
    default_enhanced_melting_params,
    default_melting_params,
    enhanced_melting_torch,
    melting_torch,
)


def _melt_inputs(*, requires_grad: bool = False, t_value: float = 280.0,
                 qs_value: float = 1.0e-4, qg_value: float = 1.0e-4,
                 qi_value: float = 1.0e-5):
    dtype = torch.float64
    qs = torch.full((1, 2), qs_value, dtype=dtype, requires_grad=requires_grad)
    qg = torch.full((1, 2), qg_value, dtype=dtype, requires_grad=requires_grad)
    qi = torch.full((1, 2), qi_value, dtype=dtype, requires_grad=requires_grad)
    ni = torch.full((1, 2), 1.0e5, dtype=dtype, requires_grad=requires_grad)
    t = torch.full((1, 2), t_value, dtype=dtype)
    p = torch.full((1, 2), 8.0e4, dtype=dtype)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    rhox = torch.full((1, 2), 400.0, dtype=dtype)
    n0so = torch.full((1, 2), 2.0e6, dtype=dtype)
    n0go = torch.full((1, 2), 4.0e6, dtype=dtype)
    n0sfac = torch.full((1, 2), 1.0, dtype=dtype)
    work2 = torch.full((1, 2), 1.5, dtype=dtype)
    precg2 = torch.full((1, 2), 0.5, dtype=dtype)
    rsl_s = torch.full((1, 2), 5.0e-4, dtype=dtype)
    rsl_g = torch.full((1, 2), 1.0e-3, dtype=dtype)
    return (
        qs, qg, qi, ni, t, p, den, rhox, n0so, n0go, n0sfac, work2, precg2,
        rsl_s, rsl_s * rsl_s,
        torch.full_like(rsl_s, 5.0e-4 ** c.BVTS),
        torch.full_like(rsl_s, 5.0e-4 ** c.MUS),
        rsl_g, rsl_g * rsl_g,
        torch.full_like(rsl_g, 1.0e-3 ** 0.5316),
        torch.full_like(rsl_g, 1.0e-3 ** c.MUG),
    )


def test_default_melting_params_finite():
    p = default_melting_params()
    for field in p._fields:
        v = getattr(p, field)
        assert math.isfinite(v) and v > 0, field


def test_melting_inactive_when_cold():
    """T <= T0c → psmlt = pgmlt = pimlt_qi = 0."""
    p = default_melting_params()
    inputs = _melt_inputs(t_value=270.0)  # T < 273.15
    out = melting_torch(*inputs, params=p, dtcld=60.0)
    z = torch.zeros_like(out.psmlt)
    assert torch.allclose(out.psmlt, z)
    assert torch.allclose(out.pgmlt, z)
    assert torch.allclose(out.pimlt_qi, z)
    assert torch.allclose(out.pimlt_ni, z)


def test_melting_warm_psmlt_negative():
    """T > T0c → psmlt < 0 (snow → rain)."""
    p = default_melting_params()
    inputs = _melt_inputs(t_value=280.0)
    out = melting_torch(*inputs, params=p, dtcld=60.0)
    assert torch.all(out.psmlt <= 1e-15)
    assert torch.all(out.pgmlt <= 1e-15)


def test_melting_psmlt_capped():
    """psmlt·dtcld ≥ -qs (mass conservation)."""
    p = default_melting_params()
    inputs = _melt_inputs(t_value=290.0, qs_value=1.0e-5)  # 큰 T-T0c, 작은 qs → cap에 잘 hit
    qs = inputs[0]
    dtcld = 60.0
    out = melting_torch(*inputs, params=p, dtcld=dtcld)
    assert torch.all(out.psmlt * dtcld >= -qs - 1e-15)


def test_melting_pimlt_full_transfer():
    """T > T0c AND qi > 0 → pimlt_qi = qi (전량 전이)."""
    p = default_melting_params()
    inputs = _melt_inputs(t_value=280.0, qi_value=2.0e-5)
    qi, ni = inputs[2], inputs[3]
    out = melting_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(out.pimlt_qi, qi)
    assert torch.allclose(out.pimlt_ni, ni)


def test_melting_delta_brs_consistent():
    """delta_brs = pgmlt / max(rhox, dens)."""
    p = default_melting_params()
    inputs = _melt_inputs(t_value=280.0)
    rhox = inputs[7]
    out = melting_torch(*inputs, params=p, dtcld=60.0)
    expected = out.pgmlt / torch.clamp(rhox, min=c.DENS)
    assert torch.allclose(out.delta_brs, expected, rtol=1e-12, atol=1e-15)


def test_melting_grad_finite():
    p = default_melting_params()
    inputs = _melt_inputs(requires_grad=True, t_value=280.0)
    out = melting_torch(*inputs, params=p, dtcld=60.0)
    loss = out.psmlt.sum() + out.pgmlt.sum() + out.pimlt_qi.sum() + out.pimlt_ni.sum()
    loss.backward()
    qs, qg, qi, ni = inputs[0], inputs[1], inputs[2], inputs[3]
    for x, name in [(qs, "qs"), (qg, "qg"), (qi, "qi"), (ni, "ni")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


# ════ Step D2: Contact freezing (Meyers) ══════════════════════════════════════


def _contact_inputs(*, supcol_value: float = 10.0, qc_value: float = 1.0e-3,
                    requires_grad: bool = False):
    dtype = torch.float64
    qc = torch.full((1, 2), qc_value, dtype=dtype, requires_grad=requires_grad)
    nc = torch.full((1, 2), 1.0e8, dtype=dtype, requires_grad=requires_grad)
    t = torch.full((1, 2), 263.15, dtype=dtype)
    p_ = torch.full((1, 2), 8.0e4, dtype=dtype)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    n0c = torch.full((1, 2), 1.0e8, dtype=dtype)
    rsl_c = torch.full((1, 2), 5.0e-5, dtype=dtype)
    rsl_c2 = rsl_c * rsl_c
    rsl_c3 = rsl_c2 * rsl_c
    rsl_cmu = torch.full_like(rsl_c, 5.0e-5 ** c.MUC)
    supcol = torch.full((1, 2), supcol_value, dtype=dtype)
    return qc, nc, t, p_, den, n0c, rsl_c, rsl_c2, rsl_c3, rsl_cmu, supcol


def test_contact_inactive_when_supcol_le_2():
    p = default_contact_freezing_params()
    inputs = _contact_inputs(supcol_value=1.5)
    out = contact_freezing_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(out.pinuc, torch.zeros_like(out.pinuc))
    assert torch.allclose(out.ninuc, torch.zeros_like(out.ninuc))


def test_contact_active_at_cold():
    p = default_contact_freezing_params()
    inputs = _contact_inputs(supcol_value=10.0)
    out = contact_freezing_torch(*inputs, params=p, dtcld=60.0)
    qc = inputs[0]
    assert torch.all(out.pinuc >= 0)
    assert torch.all(out.pinuc <= qc)


def test_contact_qc_gate_regression():
    """qc gate at EPS=1e-15 (#1): qc<gate → pinuc=0; qc in (1e-15,1e-9) → pinuc>0
    (gate-regression LOCK — fails if the qmin gate regresses to 1e-9)."""
    p = default_contact_freezing_params()
    out_lo = contact_freezing_torch(*_contact_inputs(supcol_value=10.0, qc_value=1.0e-16), params=p, dtcld=60.0)
    assert torch.allclose(out_lo.pinuc, torch.zeros_like(out_lo.pinuc))
    out_b = contact_freezing_torch(*_contact_inputs(supcol_value=10.0, qc_value=1.0e-12), params=p, dtcld=60.0)
    assert torch.all(out_b.pinuc > 0.0)


def test_contact_grad_finite():
    p = default_contact_freezing_params()
    inputs = _contact_inputs(supcol_value=10.0, requires_grad=True)
    out = contact_freezing_torch(*inputs, params=p, dtcld=60.0)
    loss = out.pinuc.sum() + out.ninuc.sum()
    loss.backward()
    qc, nc = inputs[0], inputs[1]
    for x, name in [(qc, "qc"), (nc, "nc")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


# ════ Step D3: Bigg cloud freezing ════════════════════════════════════════════


def _bigg_cloud_inputs(*, supcol_value: float = 10.0, qc_value: float = 1.0e-3, requires_grad: bool = False):
    dtype = torch.float64
    qc = torch.full((1, 2), qc_value, dtype=dtype, requires_grad=requires_grad)
    nc = torch.full((1, 2), 1.0e8, dtype=dtype, requires_grad=requires_grad)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    n0c = torch.full((1, 2), 1.0e8, dtype=dtype)
    rsl_c = torch.full((1, 2), 5.0e-5, dtype=dtype)
    rsl_cd = torch.full_like(rsl_c, 5.0e-5 ** c.DMC)
    rsl_cmu = torch.full_like(rsl_c, 5.0e-5 ** c.MUC)
    supcol = torch.full((1, 2), supcol_value, dtype=dtype)
    return qc, nc, den, n0c, rsl_c, rsl_cd, rsl_cmu, supcol


def test_bigg_cloud_inactive_when_warm():
    p = default_bigg_cloud_params()
    inputs = _bigg_cloud_inputs(supcol_value=-5.0)
    out = bigg_cloud_freezing_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(out.pfrzdtc, torch.zeros_like(out.pfrzdtc))


def test_bigg_cloud_capped_by_qc():
    p = default_bigg_cloud_params()
    inputs = _bigg_cloud_inputs(supcol_value=10.0)
    out = bigg_cloud_freezing_torch(*inputs, params=p, dtcld=60.0)
    qc = inputs[0]
    assert torch.all(out.pfrzdtc <= qc + 1e-15)
    assert torch.all(out.pfrzdtc >= 0)


def test_bigg_cloud_qc_gate_regression():
    """qc gate at EPS=1e-15 (#1): qc<gate → pfrzdtc=0; qc in (1e-15,1e-9) → pfrzdtc>0
    (gate-regression LOCK — fails if the qmin gate regresses to 1e-9)."""
    p = default_bigg_cloud_params()
    out_lo = bigg_cloud_freezing_torch(*_bigg_cloud_inputs(supcol_value=10.0, qc_value=1.0e-16), params=p, dtcld=60.0)
    assert torch.allclose(out_lo.pfrzdtc, torch.zeros_like(out_lo.pfrzdtc))
    out_b = bigg_cloud_freezing_torch(*_bigg_cloud_inputs(supcol_value=10.0, qc_value=1.0e-12), params=p, dtcld=60.0)
    assert torch.all(out_b.pfrzdtc > 0.0)


def test_bigg_cloud_grad_finite():
    p = default_bigg_cloud_params()
    inputs = _bigg_cloud_inputs(supcol_value=10.0, requires_grad=True)
    out = bigg_cloud_freezing_torch(*inputs, params=p, dtcld=60.0)
    loss = out.pfrzdtc.sum() + out.nfrzdtc.sum()
    loss.backward()
    qc, nc = inputs[0], inputs[1]
    for x, name in [(qc, "qc"), (nc, "nc")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


# ════ Step D4: Bigg rain freezing ═════════════════════════════════════════════


def _bigg_rain_inputs(*, supcol_value: float = 10.0, requires_grad: bool = False):
    dtype = torch.float64
    qr = torch.full((1, 2), 1.0e-4, dtype=dtype, requires_grad=requires_grad)
    nr = torch.full((1, 2), 1.0e5, dtype=dtype, requires_grad=requires_grad)
    den = torch.full((1, 2), 1.1, dtype=dtype)
    n0r = torch.full((1, 2), 8.0e6, dtype=dtype)
    rsl_r = torch.full((1, 2), 5.0e-4, dtype=dtype)
    rsl_rd = torch.full_like(rsl_r, 5.0e-4 ** c.DMR)
    rsl_rmu = torch.full_like(rsl_r, 5.0e-4 ** c.MUR)
    supcol = torch.full((1, 2), supcol_value, dtype=dtype)
    return qr, nr, den, n0r, rsl_r, rsl_rd, rsl_rmu, supcol


def test_bigg_rain_inactive_when_warm():
    p = default_bigg_rain_params()
    inputs = _bigg_rain_inputs(supcol_value=-5.0)
    out = bigg_rain_freezing_torch(*inputs, params=p, dtcld=60.0)
    assert torch.allclose(out.pfrzdtr, torch.zeros_like(out.pfrzdtr))
    assert torch.allclose(out.delta_brs, torch.zeros_like(out.delta_brs))


def test_bigg_rain_delta_brs_consistent():
    p = default_bigg_rain_params()
    inputs = _bigg_rain_inputs(supcol_value=10.0)
    out = bigg_rain_freezing_torch(*inputs, params=p, dtcld=60.0)
    expected = out.pfrzdtr / p.denr
    assert torch.allclose(out.delta_brs, expected, rtol=1e-12)


def test_bigg_rain_grad_finite():
    p = default_bigg_rain_params()
    inputs = _bigg_rain_inputs(supcol_value=10.0, requires_grad=True)
    out = bigg_rain_freezing_torch(*inputs, params=p, dtcld=60.0)
    loss = out.pfrzdtr.sum() + out.nfrzdtr.sum()
    loss.backward()
    qr, nr = inputs[0], inputs[1]
    for x, name in [(qr, "qr"), (nr, "nr")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


# ════ Step D5: Enhanced melting ═══════════════════════════════════════════════


def _enh_melt_inputs(*, supcol_value: float = -5.0, paacw_value: float = 1.0e-6,
                     requires_grad: bool = False):
    dtype = torch.float64
    qs = torch.full((1, 2), 1.0e-4, dtype=dtype, requires_grad=requires_grad)
    qg = torch.full((1, 2), 1.0e-4, dtype=dtype, requires_grad=requires_grad)
    paacw = torch.full((1, 2), paacw_value, dtype=dtype)
    psacr = torch.full((1, 2), 1.0e-7, dtype=dtype)
    pgacr = torch.full((1, 2), 1.0e-7, dtype=dtype)
    n0so = torch.full((1, 2), 2.0e6, dtype=dtype)
    n0go = torch.full((1, 2), 4.0e6, dtype=dtype)
    n0sfac = torch.full((1, 2), 1.0, dtype=dtype)
    rslope_s = torch.full((1, 2), 5.0e-4, dtype=dtype)
    rslope_g = torch.full((1, 2), 1.0e-3, dtype=dtype)
    supcol = torch.full((1, 2), supcol_value, dtype=dtype)
    return qs, qg, paacw, psacr, pgacr, n0so, n0go, n0sfac, rslope_s, rslope_g, supcol


def test_enhanced_melting_inactive_when_cold():
    p = default_enhanced_melting_params()
    inputs = _enh_melt_inputs(supcol_value=5.0)
    out = enhanced_melting_torch(*inputs, params=p, dtcld=60.0)
    z = torch.zeros_like(out.pseml)
    assert torch.allclose(out.pseml, z)
    assert torch.allclose(out.pgeml, z)


def test_enhanced_melting_negative_when_warm():
    """supcol < 0 → pseml/pgeml < 0 (snow/graupel sink, → rain)."""
    p = default_enhanced_melting_params()
    inputs = _enh_melt_inputs(supcol_value=-5.0)
    out = enhanced_melting_torch(*inputs, params=p, dtcld=60.0)
    assert torch.all(out.pseml <= 1e-15)
    assert torch.all(out.pgeml <= 1e-15)


def test_enhanced_melting_capped_by_qs():
    p = default_enhanced_melting_params()
    inputs = _enh_melt_inputs(supcol_value=-30.0, paacw_value=1.0e-3)  # 큰 cliq·supcol
    qs, qg = inputs[0], inputs[1]
    dtcld = 60.0
    out = enhanced_melting_torch(*inputs, params=p, dtcld=dtcld)
    assert torch.all(out.pseml >= -qs / dtcld - 1e-15)
    assert torch.all(out.pgeml >= -qg / dtcld - 1e-15)


def test_enhanced_melting_grad_finite():
    p = default_enhanced_melting_params()
    inputs = _enh_melt_inputs(requires_grad=True)
    out = enhanced_melting_torch(*inputs, params=p, dtcld=60.0)
    loss = out.pseml.sum() + out.nseml.sum() + out.pgeml.sum() + out.ngeml.sum()
    loss.backward()
    qs, qg = inputs[0], inputs[1]
    for x, name in [(qs, "qs"), (qg, "qg")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name
