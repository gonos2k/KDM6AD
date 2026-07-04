"""Phase 1 (all-sky cloud) -- cloud tensors through model_to_rttov_tensors.

Mock-only (no RTTOV): the hydrometeor bridge is wired into the obs profile builder
so RttovProfileTensors carries cloud content [g/m^3] + effective DIAMETER [micron]
on the RTTOV layer grid, fully differentiable. Decisions under test (recommended):
qc->HYDRO6 liquid; qi+qs->HYDRO7 ice (content sum + content-weighted reff blend);
Deff=2*reff clipped to RTTOV windows; cfrac detached binary; clear-sky unchanged.
"""
import torch

from kdm6.state import Forcing, State
from kdm6.obs.model_profile_builder import (
    RttovProfileConfig, model_to_rttov_tensors,
    _DEFF_LIQ_MIN, _DEFF_LIQ_MAX, _DEFF_ICE_MIN, _DEFF_ICE_MAX, _CFRAC_MAX)
from kdm6.rttov_bridge import rttov_cloud_profile

torch.manual_seed(0)
_F64 = torch.float64


def _t(vals, rg=False):
    x = torch.tensor(vals, dtype=_F64)
    return x.requires_grad_(True) if rg else x


def _mk_col(rg=False):
    """Ascending (TOA->surface) 2-layer mixed-phase column: ice aloft, liquid below.
    Sizes chosen so deff_liq and deff_ice land strictly inside the RTTOV windows
    (so nc/ni gradients -- which reach BT only through Deff -- are nonzero)."""
    return State(
        th=_t([238.0, 290.0], rg), qv=_t([4.0e-4, 1.20e-2], rg),
        qc=_t([0.0, 1.2e-3], rg), qr=_t([0.0, 1.0e-4], rg),
        qi=_t([8.0e-4, 0.0], rg), qs=_t([3.0e-5, 0.0], rg),
        qg=_t([0.0, 0.0], rg), nccn=_t([1.0e9, 1.0e9], rg),
        nc=_t([0.0, 6.0e7], rg), ni=_t([5.0e5, 0.0], rg),  # interior ice-slope band -> live ni grad
        nr=_t([0.0, 1.0e4], rg), bg=_t([0.0, 0.0], rg))


def _mk_forcing():
    return Forcing(rho=_t([0.45, 1.05]), pii=_t([0.84, 0.97]),
                   p=_t([3.0e4, 9.0e4]), delz=_t([800.0, 500.0]))


def _cfg(cloud=True, layer_p=None):
    return RttovProfileConfig(gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
                              rttov_layer_pressure=layer_p, cloud=cloud)


def test_clear_sky_path_unchanged():
    """cfg.cloud=False emits NO cloud fields, and t_lay/q_lay match the cloud=True
    run (cloud is purely additive -- it must not perturb the clear-sky outputs)."""
    col, f = _mk_col(), _mk_forcing()
    clear = model_to_rttov_tensors(col, f, _cfg(cloud=False))
    assert clear.clw is None and clear.ciw is None and clear.deff_liq is None
    assert clear.deff_ice is None and clear.cfrac is None
    cloudy = model_to_rttov_tensors(col, f, _cfg(cloud=True))
    assert torch.equal(clear.t_lay, cloudy.t_lay)
    assert torch.equal(clear.q_lay, cloudy.q_lay)


def test_cloud_tensors_present_on_layer_grid():
    col, f = _mk_col(), _mk_forcing()
    # passthrough: cloud fields on the model grid (K=2).
    p = model_to_rttov_tensors(col, f, _cfg(cloud=True))
    for fld in (p.clw, p.ciw, p.deff_liq, p.deff_ice, p.cfrac):
        assert fld is not None and fld.shape == (2,)
    # interp: cloud fields ride the SAME target grid as t_lay (K=3).
    tgt = _t([4.0e4, 6.0e4, 8.0e4])
    pi = model_to_rttov_tensors(col, f, _cfg(cloud=True, layer_p=tgt))
    assert pi.t_lay.shape == (3,)
    for fld in (pi.clw, pi.ciw, pi.deff_liq, pi.deff_ice, pi.cfrac):
        assert fld.shape == (3,)


def test_content_and_deff_match_bridge():
    """Passthrough cloud fields equal the bridge's, mapped: clw=qc content;
    ciw=qi+qs content; deff=2*reff clipped to RTTOV windows."""
    col, f = _mk_col(), _mk_forcing()
    p = model_to_rttov_tensors(col, f, _cfg(cloud=True))
    col2 = State(*(x.unsqueeze(0) for x in col))
    f2 = Forcing(*(x.unsqueeze(0) for x in f))
    cp = rttov_cloud_profile(col2, f2)

    assert torch.allclose(p.clw, cp.clw.squeeze(0))
    assert torch.allclose(p.ciw, (cp.ciw + cp.snow).squeeze(0))          # qi+qs ice
    assert torch.allclose(p.deff_liq, torch.clamp(2.0 * cp.reff_liq.squeeze(0),
                                                  _DEFF_LIQ_MIN, _DEFF_LIQ_MAX))
    # ice: content-weighted reff blend then *2 then clip.
    ciw, snow = cp.ciw.squeeze(0), cp.snow.squeeze(0)
    denom = torch.clamp(ciw + snow, min=1.0e-12)
    blend = (ciw * cp.reff_ice.squeeze(0) + snow * cp.reff_snow.squeeze(0)) / denom
    assert torch.allclose(p.deff_ice, torch.clamp(2.0 * blend, _DEFF_ICE_MIN, _DEFF_ICE_MAX))


def test_deff_within_rttov_bounds_and_interior():
    """Deff is inside the RTTOV windows; for THIS column it is strictly interior
    (so the number-moment gradients below are not killed by the clamp)."""
    col, f = _mk_col(), _mk_forcing()
    p = model_to_rttov_tensors(col, f, _cfg(cloud=True))
    assert bool(((p.deff_liq >= _DEFF_LIQ_MIN) & (p.deff_liq <= _DEFF_LIQ_MAX)).all())
    assert bool(((p.deff_ice >= _DEFF_ICE_MIN) & (p.deff_ice <= _DEFF_ICE_MAX)).all())
    # the active liquid layer (idx 1) and active ice layer (idx 0) are interior:
    assert _DEFF_LIQ_MIN < float(p.deff_liq[1]) < _DEFF_LIQ_MAX
    assert _DEFF_ICE_MIN < float(p.deff_ice[0]) < _DEFF_ICE_MAX


def test_cfrac_detached_binary_clamped():
    col, f = _mk_col(), _mk_forcing()
    p = model_to_rttov_tensors(col, f, _cfg(cloud=True))
    assert not p.cfrac.requires_grad                        # detached weighting
    uniq = set(round(float(v), 6) for v in p.cfrac)
    assert uniq <= {0.0, round(_CFRAC_MAX, 6)}              # binary
    assert float(p.cfrac.max()) < 1.0                       # never exactly 1.0


def test_cloud_rejects_multicolumn_xland():
    """The obs path is one column; a numel!=1 xland would silently mis-mask the
    bridge's sea/land ncmin gate -> reject (Codex HIGH)."""
    import pytest
    col, f = _mk_col(), _mk_forcing()
    bad = torch.tensor([0.0, 2.0], dtype=_F64)        # 2-column xland on a 1-column path
    with pytest.raises(ValueError, match="single-column"):
        model_to_rttov_tensors(col, f, _cfg(cloud=True), xland=bad)


def test_cloud_single_column_xland_ok():
    col, f = _mk_col(), _mk_forcing()
    p = model_to_rttov_tensors(col, f, _cfg(cloud=True), xland=torch.tensor([2.0], dtype=_F64))
    assert p.clw is not None and torch.isfinite(p.clw).all()


def test_cloud_rejects_nonfinite_field():
    """A non-finite content from a degenerate column must be rejected, not masked
    (NaN > thresh is False -> cfrac=0 would hide NaN content; reject-don't-drop)."""
    import pytest
    col, f = _mk_col(), _mk_forcing()
    col = col._replace(qc=torch.tensor([0.0, float("nan")], dtype=_F64))
    with pytest.raises(ValueError, match="non-finite"):
        model_to_rttov_tensors(col, f, _cfg(cloud=True))


def test_cloud_content_nonnegative():
    """RTTOV content is clamped >= 0 (DA increments can drive q<0)."""
    col, f = _mk_col(), _mk_forcing()
    col = col._replace(qc=torch.tensor([0.0, -1.0e-5], dtype=_F64))   # negative liquid increment
    p = model_to_rttov_tensors(col, f, _cfg(cloud=True))
    assert bool((p.clw >= 0.0).all()) and bool((p.ciw >= 0.0).all())


def test_cloud_grad_flows_to_qc_qi_qs_nc_ni():
    """Cloud content + Deff carry gradient to the connected leaves: qc/qi/qs via
    content, nc/ni via Deff (the number-moment adjoint)."""
    col, f = _mk_col(rg=True), _mk_forcing()
    p = model_to_rttov_tensors(col, f, _cfg(cloud=True))
    loss = p.clw.sum() + p.ciw.sum() + p.deff_liq.sum() + p.deff_ice.sum()
    g = torch.autograd.grad(loss, (col.qc, col.qi, col.qs, col.nc, col.ni),
                            allow_unused=True, materialize_grads=True)
    for name, grad in zip(("qc", "qi", "qs", "nc", "ni"), g):
        assert torch.isfinite(grad).all(), f"{name} grad non-finite"
        assert float(grad.abs().sum()) > 0.0, f"{name} grad is zero (severed/clamped)"
