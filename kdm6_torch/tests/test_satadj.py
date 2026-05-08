"""saturation adjustment oracle 검증 (Step B5)."""
from __future__ import annotations

import math

import torch

from kdm6.satadj import (
    SatAdjParams,
    default_satadj_params,
    saturation_adjustment_torch,
)


def _base_inputs(*, rh_value: float = 1.05, qc_value: float = 1.0e-4, requires_grad: bool = False):
    """rh > 1이면 supersaturated (응결), rh < 1이면 subsaturated (증발)."""
    dtype = torch.float64
    qs1 = 1.0e-2  # 5g/kg saturation mixing ratio
    t = torch.full((1, 2), 290.0, dtype=dtype)
    q = torch.full((1, 2), qs1 * rh_value, dtype=dtype, requires_grad=requires_grad)
    qc = torch.full((1, 2), qc_value, dtype=dtype, requires_grad=requires_grad)
    qs1_t = torch.full((1, 2), qs1, dtype=dtype)
    xl = torch.full((1, 2), 2.5e6, dtype=dtype)
    cpm = torch.full((1, 2), 1004.0, dtype=dtype)
    return t, q, qc, qs1_t, xl, cpm


def test_default_satadj_params_finite():
    p = default_satadj_params()
    assert math.isfinite(p.rv) and p.rv > 0
    assert math.isfinite(p.qmin) and p.qmin > 0


def test_satadj_zero_when_balanced_and_no_cloud():
    """rh==1 (work1=0) AND qc=0 → pcond=0."""
    p = default_satadj_params()
    t, q, qc, qs1, xl, cpm = _base_inputs(rh_value=1.0, qc_value=0.0)
    pcond = saturation_adjustment_torch(t, q, qc, qs1, xl, cpm, params=p, dtcld=60.0)
    assert torch.allclose(pcond, torch.zeros_like(pcond), atol=1e-15)


def test_satadj_condensation_path():
    """rh > 1 → pcond > 0, capped by q/dtcld."""
    p = default_satadj_params()
    t, q, qc, qs1, xl, cpm = _base_inputs(rh_value=1.05, qc_value=0.0)
    dtcld = 60.0
    pcond = saturation_adjustment_torch(t, q, qc, qs1, xl, cpm, params=p, dtcld=dtcld)
    assert torch.all(pcond > 0)
    assert torch.all(pcond <= q / dtcld + 1e-15)


def test_satadj_evaporation_path():
    """rh < 1 with available qc → pcond < 0, capped by -qc/dtcld."""
    p = default_satadj_params()
    t, q, qc, qs1, xl, cpm = _base_inputs(rh_value=0.95, qc_value=1.0e-4)
    dtcld = 60.0
    pcond = saturation_adjustment_torch(t, q, qc, qs1, xl, cpm, params=p, dtcld=dtcld)
    assert torch.all(pcond < 0)
    assert torch.all(pcond >= -qc / dtcld - 1e-15)


def test_satadj_no_evaporation_without_cloud():
    """rh < 1 BUT qc=0 → pcond=0 (subsaturation 흡수 못함)."""
    p = default_satadj_params()
    t, q, qc, qs1, xl, cpm = _base_inputs(rh_value=0.7, qc_value=0.0)
    pcond = saturation_adjustment_torch(t, q, qc, qs1, xl, cpm, params=p, dtcld=60.0)
    assert torch.allclose(pcond, torch.zeros_like(pcond))


def test_satadj_latent_heat_feedback_reduces_pcond():
    """Latent heat feedback (denom > 1) → |pcond| < naive (q-qs)/dtcld."""
    p = default_satadj_params()
    t, q, qc, qs1, xl, cpm = _base_inputs(rh_value=1.05, qc_value=0.0)
    dtcld = 60.0
    pcond = saturation_adjustment_torch(t, q, qc, qs1, xl, cpm, params=p, dtcld=dtcld)
    naive_rate = (q - qs1) / dtcld
    # latent heat feedback이 있으니 pcond는 naive rate보다 작아야 함
    assert torch.all(pcond < naive_rate)


def test_satadj_grad_finite():
    """q, qc에 대해 backward 통과."""
    p = default_satadj_params()
    t, q, qc, qs1, xl, cpm = _base_inputs(rh_value=1.05, qc_value=1.0e-4, requires_grad=True)
    pcond = saturation_adjustment_torch(t, q, qc, qs1, xl, cpm, params=p, dtcld=60.0)
    pcond.sum().backward()
    assert q.grad is not None and torch.isfinite(q.grad).all()
    assert qc.grad is not None and torch.isfinite(qc.grad).all()
