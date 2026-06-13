"""M2 gates for the P2 model->RTTOV profile builder (design 5, 14.3-units).

Two things are load-bearing: (1) the unit/extraction math (T=th*pii, qv->Q
ppmv-moist, explicit gas_units/qv_convention) matches the scalar reference, and
(2) the WHOLE path is autograd-correct -- grad must flow from t_lay/q_lay back
to the th/qv leaves (a numpy/.item break would silently zero it). Compile +
run-green != autograd-correct, so an explicit gradient anchor is included.
"""
from __future__ import annotations

import math

import pytest
import torch

from kdm6.state import State, Forcing
from kdm6.obs.model_profile_builder import (
    RttovProfileConfig,
    RttovProfileTensors,
    extract_model_columns,
    interp_log_pressure,
    model_to_rttov_tensors,
    qv_to_q_ppmv_moist,
)
from kdm6.obs._rttov_reference.humidity_unit_conversion import (
    kgkg_mixing_ratio_to_ppmv_moist,
    kgkg_specific_humidity_to_ppmv_moist,
)

F64 = torch.float64
# Model column (ascending pressure TOA->surface), 5 levels.
P_MODEL = torch.tensor([100.0, 300.0, 500.0, 700.0, 900.0], dtype=F64)
PII = torch.tensor([0.80, 0.85, 0.90, 0.95, 1.00], dtype=F64)
P_TARGET = torch.tensor([200.0, 400.0, 600.0, 800.0], dtype=F64)  # 4 RTTOV layers


def _leaves(th=None, qv=None, requires_grad=False):
    n = P_MODEL.shape[0]
    if th is None:
        th = torch.full((n,), 300.0, dtype=F64)
    if qv is None:
        qv = torch.full((n,), 0.01, dtype=F64)
    th = th.clone().requires_grad_(requires_grad)
    qv = qv.clone().requires_grad_(requires_grad)
    z = torch.zeros(n, dtype=F64)
    return State(th=th, qv=qv, qc=z, qr=z, qi=z, qs=z, qg=z,
                 nccn=z, nc=z, ni=z, nr=z, bg=z)


def _forcing():
    n = P_MODEL.shape[0]
    return Forcing(rho=torch.ones(n, dtype=F64), pii=PII.clone(),
                   p=P_MODEL.clone(), delz=torch.ones(n, dtype=F64))


def _cfg(layer_p=P_TARGET, level_p=None, gas_units=2, qv_convention="mixing_ratio_kgkg_dry"):
    return RttovProfileConfig(gas_units=gas_units, qv_convention=qv_convention,
                              rttov_layer_pressure=layer_p, rttov_level_pressure=level_p)


# --- extraction: T = th * pii -----------------------------------------------

def test_temperature_from_th_pii():
    leaves, f = _leaves(), _forcing()
    t, qv, p = extract_model_columns(leaves, f)
    assert torch.allclose(t, leaves.th * f.pii)
    assert torch.allclose(qv, leaves.qv)
    assert torch.allclose(p, f.p)


# --- qv -> Q ppmv moist parity vs scalar reference --------------------------

@pytest.mark.parametrize("w", [0.0, 1.0e-4, 0.005, 0.02])
def test_qv_to_ppmv_mixing_ratio_matches_reference(w):
    q = qv_to_q_ppmv_moist(torch.tensor([w], dtype=F64),
                           gas_units=2, qv_convention="mixing_ratio_kgkg_dry")
    assert math.isclose(q.item(), kgkg_mixing_ratio_to_ppmv_moist(w), rel_tol=1e-12, abs_tol=1e-9)


@pytest.mark.parametrize("q_in", [0.0, 1.0e-4, 0.005, 0.02])
def test_qv_to_ppmv_specific_humidity_matches_reference(q_in):
    q = qv_to_q_ppmv_moist(torch.tensor([q_in], dtype=F64),
                           gas_units=2, qv_convention="specific_humidity_kgkg_moist")
    assert math.isclose(q.item(), kgkg_specific_humidity_to_ppmv_moist(q_in), rel_tol=1e-12, abs_tol=1e-9)


# --- units gate (design 5/4.2; M2 test_units) -------------------------------

def test_units_gate_wrong_gas_units_raises():
    with pytest.raises(ValueError, match="gas_units must be 2"):
        qv_to_q_ppmv_moist(torch.tensor([0.01], dtype=F64),
                           gas_units=1, qv_convention="mixing_ratio_kgkg_dry")


def test_units_gate_unspecified_convention_raises():
    with pytest.raises(ValueError, match="qv_convention must be explicit"):
        qv_to_q_ppmv_moist(torch.tensor([0.01], dtype=F64),
                           gas_units=2, qv_convention=None)


def test_model_to_rttov_propagates_units_gate():
    with pytest.raises(ValueError, match="gas_units must be 2"):
        model_to_rttov_tensors(_leaves(), _forcing(), _cfg(gas_units=99))


# --- qv clip: negative qv -> 0, subgradient 0 (not a graph break) -----------

def test_negative_qv_clipped_and_grad_zero():
    qv = torch.tensor([-0.01], dtype=F64, requires_grad=True)
    q = qv_to_q_ppmv_moist(qv, gas_units=2, qv_convention="mixing_ratio_kgkg_dry")
    assert q.item() == 0.0
    q.sum().backward()
    assert qv.grad is not None and float(qv.grad) == 0.0  # one-sided subgradient


def test_qv_dQdqv_matches_analytic_fd():
    """dQ/dqv (one-sided FD on the active qv>0 side) matches autograd."""
    w0 = 0.01
    qv = torch.tensor([w0], dtype=F64, requires_grad=True)
    q = qv_to_q_ppmv_moist(qv, gas_units=2, qv_convention="mixing_ratio_kgkg_dry")
    q.sum().backward()
    h = 1.0e-8
    fd = (kgkg_mixing_ratio_to_ppmv_moist(w0 + h) - kgkg_mixing_ratio_to_ppmv_moist(w0)) / h
    assert math.isclose(float(qv.grad), fd, rel_tol=1e-5)


def test_qv_dQdqv_specific_humidity_matches_fd():
    """dQ/dq for the specific-humidity convention (extra w=q/(1-q) chain factor)
    matches one-sided FD -- the mixing-ratio test cannot reach this branch."""
    q0 = 0.01
    qv = torch.tensor([q0], dtype=F64, requires_grad=True)
    q = qv_to_q_ppmv_moist(qv, gas_units=2, qv_convention="specific_humidity_kgkg_moist")
    q.sum().backward()
    h = 1.0e-9
    fd = (kgkg_specific_humidity_to_ppmv_moist(q0 + h)
          - kgkg_specific_humidity_to_ppmv_moist(q0)) / h
    assert math.isclose(float(qv.grad), fd, rel_tol=1e-5)


# --- interpolation ----------------------------------------------------------

def test_interp_identity_on_same_grid():
    field = torch.tensor([1.0, 2.0, 3.0, 4.0, 5.0], dtype=F64)
    out = interp_log_pressure(field, P_MODEL, P_MODEL)
    assert torch.allclose(out, field)


def test_interp_no_extrapolation_clamps_to_endpoints():
    field = torch.tensor([10.0, 20.0, 30.0, 40.0, 50.0], dtype=F64)
    # targets straddle the source range -> clamp to first/last (no extrapolation).
    p_out = torch.tensor([50.0, 100.0, 900.0, 2000.0], dtype=F64)
    out = interp_log_pressure(field, P_MODEL, p_out)
    assert out[0].item() == 10.0   # below src min -> endpoint
    assert out[1].item() == 10.0   # == src min
    assert out[3].item() == 50.0   # above src max -> endpoint


def test_interp_batched_field_shares_grid():
    field = torch.arange(10, dtype=F64).reshape(2, 5)
    out = interp_log_pressure(field, P_MODEL, P_TARGET)
    assert out.shape == (2, 4)


def test_interp_descending_src_raises():
    field = torch.tensor([1.0, 2.0, 3.0, 4.0, 5.0], dtype=F64)
    with pytest.raises(ValueError, match="strictly ascending"):
        interp_log_pressure(field, torch.flip(P_MODEL, [0]), P_TARGET)


def test_interp_grad_flows_to_field_not_pressure():
    field = torch.tensor([1.0, 2.0, 3.0, 4.0, 5.0], dtype=F64, requires_grad=True)
    p_src = P_MODEL.clone().requires_grad_(True)  # forcing -- must stay constant
    out = interp_log_pressure(field, p_src, P_TARGET)
    out.sum().backward()
    assert field.grad is not None and torch.isfinite(field.grad).all()
    assert p_src.grad is None  # weights are constant (computed under no_grad)


# --- model_to_rttov_tensors orchestration -----------------------------------

def test_profile_shapes_on_target_grid():
    out = model_to_rttov_tensors(_leaves(), _forcing(), _cfg(level_p=torch.tensor(
        [150.0, 250.0, 450.0, 650.0, 850.0], dtype=F64)))
    assert isinstance(out, RttovProfileTensors)
    assert out.t_lay.shape == (4,)
    assert out.q_lay.shape == (4,)
    assert out.p_lay.shape == (4,)
    assert out.p_half.shape == (5,)


def test_no_target_grid_passes_through():
    level_p = torch.tensor([150.0, 250.0, 450.0, 650.0, 850.0], dtype=F64)
    leaves = _leaves(requires_grad=True)
    out = model_to_rttov_tensors(leaves, _forcing(), _cfg(layer_p=None, level_p=level_p))
    assert out.t_lay.shape == (5,)        # model grid, no interpolation
    assert out.p_lay is None
    assert torch.equal(out.p_half, level_p) and out.p_half.requires_grad is False
    # the 14.3 grad contract must still hold on the un-interpolated path
    (out.t_lay.sum() + out.q_lay.sum()).backward()
    assert float(leaves.th.grad.abs().sum()) > 0.0
    assert float(leaves.qv.grad.abs().sum()) > 0.0


def test_none_passthrough_rejects_descending_column():
    """The passthrough path must reject a WRF-descending column as loudly as the
    interp path (no silent wrong-grid passthrough; review HIGH finding)."""
    f = _forcing()._replace(p=torch.flip(P_MODEL, [0]))  # descending
    with pytest.raises(ValueError, match="strictly ascending"):
        model_to_rttov_tensors(_leaves(), f, _cfg(layer_p=None))


def test_none_passthrough_rejects_multicolumn():
    """The multi-column reject is shared by both paths (hoisted above the split)."""
    leaves, f = _leaves(), _forcing()
    f2 = f._replace(p=f.p.unsqueeze(0).repeat(3, 1))
    leaves2 = leaves._replace(th=leaves.th.unsqueeze(0).repeat(3, 1),
                              qv=leaves.qv.unsqueeze(0).repeat(3, 1))
    with pytest.raises(ValueError, match="1-D column grid"):
        model_to_rttov_tensors(leaves2, f2, _cfg(layer_p=None))


def test_pa_hpa_unit_mismatch_raises():
    """Disjoint src/dst pressure ranges (Pa column vs hPa grid) raise instead of
    silently clamping to an endpoint (review MEDIUM finding)."""
    field = torch.tensor([1.0, 2.0, 3.0, 4.0, 5.0], dtype=F64)
    p_src_pa = torch.tensor([10000.0, 30000.0, 50000.0, 70000.0, 90000.0], dtype=F64)
    p_dst_hpa = torch.tensor([200.0, 400.0, 600.0, 800.0], dtype=F64)
    with pytest.raises(ValueError, match="Pa/hPa unit mismatch"):
        interp_log_pressure(field, p_src_pa, p_dst_hpa)


def test_nlayers_nlevels_mismatch_raises():
    """Nlayers must equal Nlevels-1 (design 5; profile.py:124) -- mismatched
    cfg grids raise rather than emit an inconsistent profile."""
    bad = _cfg(layer_p=P_TARGET,  # 4 layers
               level_p=torch.tensor([150.0, 250.0, 450.0, 650.0], dtype=F64))  # 4 levels (need 5)
    with pytest.raises(ValueError, match="Nlayers must equal Nlevels-1"):
        model_to_rttov_tensors(_leaves(), _forcing(), bad)


def test_grid_tensors_are_constant_not_grad_leaves():
    """p_lay/p_half are constant forcing (design 5): a grad-tracking input grid is
    detached so it cannot leak requires_grad into the graph."""
    layer_p = P_TARGET.clone().requires_grad_(True)
    level_p = torch.tensor([150.0, 250.0, 450.0, 650.0, 850.0], dtype=F64, requires_grad=True)
    out = model_to_rttov_tensors(_leaves(), _forcing(), _cfg(layer_p=layer_p, level_p=level_p))
    assert out.p_lay.requires_grad is False
    assert out.p_half.requires_grad is False


def test_pressure_monotonic_target_required():
    bad = _cfg(layer_p=torch.tensor([200.0, 600.0, 400.0, 800.0], dtype=F64))
    with pytest.raises(ValueError, match="strictly ascending"):
        model_to_rttov_tensors(_leaves(), _forcing(), bad)


def test_multicolumn_pressure_rejected():
    leaves, f = _leaves(), _forcing()
    f2 = f._replace(p=f.p.unsqueeze(0).repeat(3, 1))  # [3, 5] multi-column
    leaves2 = leaves._replace(th=leaves.th.unsqueeze(0).repeat(3, 1),
                              qv=leaves.qv.unsqueeze(0).repeat(3, 1))
    with pytest.raises(ValueError, match="1-D column grid"):
        model_to_rttov_tensors(leaves2, f2, _cfg())


# --- GRADIENT ANCHOR: grad flows leaves -> t_lay/q_lay (design 14.3) --------

def test_grad_anchor_th_qv_through_full_pipeline():
    leaves = _leaves(requires_grad=True)
    out = model_to_rttov_tensors(leaves, _forcing(), _cfg())
    (out.t_lay.sum() + out.q_lay.sum()).backward()
    # th drives T=th*pii (interpolated); qv drives Q=ppmv(qv) (interpolated).
    assert leaves.th.grad is not None and torch.isfinite(leaves.th.grad).all()
    assert leaves.qv.grad is not None and torch.isfinite(leaves.qv.grad).all()
    assert float(leaves.th.grad.abs().sum()) > 0.0
    assert float(leaves.qv.grad.abs().sum()) > 0.0


def test_grad_t_only_isolates_th():
    """t_lay depends on th (not qv); q_lay depends on qv (not th)."""
    leaves = _leaves(requires_grad=True)
    out = model_to_rttov_tensors(leaves, _forcing(), _cfg())
    out.t_lay.sum().backward()
    assert float(leaves.th.grad.abs().sum()) > 0.0
    assert leaves.qv.grad is None or float(leaves.qv.grad.abs().sum()) == 0.0


def test_grad_dTlay_dth_equals_interpolated_pii():
    """For T=th*pii then linear interp, dT_lay/d th_k is constant (= interp
    weight * pii_k); autograd matches a one-sided FD on th (no kinks here)."""
    leaves = _leaves(requires_grad=True)
    out = model_to_rttov_tensors(leaves, _forcing(), _cfg())
    g = torch.autograd.grad(out.t_lay.sum(), leaves.th)[0]
    # FD: perturb th, recompute t_lay.sum()
    h = 1.0e-6
    base = model_to_rttov_tensors(_leaves(), _forcing(), _cfg()).t_lay.sum().item()
    fd = torch.zeros_like(leaves.th)
    for k in range(leaves.th.shape[0]):
        th2 = torch.full_like(leaves.th, 300.0)
        th2[k] += h
        lv = State(th=th2, qv=torch.full_like(leaves.th, 0.01),
                   qc=th2 * 0, qr=th2 * 0, qi=th2 * 0, qs=th2 * 0, qg=th2 * 0,
                   nccn=th2 * 0, nc=th2 * 0, ni=th2 * 0, nr=th2 * 0, bg=th2 * 0)
        fd[k] = (model_to_rttov_tensors(lv, _forcing(), _cfg()).t_lay.sum().item() - base) / h
    assert torch.allclose(g, fd, rtol=1e-5, atol=1e-6)
