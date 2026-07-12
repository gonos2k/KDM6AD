"""da_partition — conserving/bounded partition CVT stage (P1-1 design v1.1).

Contracts under test:
  1. bounded_delta: exact 0 at w=0 with derivative exactly 1 from both sides
     (C^1 — no kink at the optimizer start); saturates at +cap_fwd/-cap_rev;
     dead cells (either frozen donor cap == 0) give exact-0 value AND exact-0
     gradient from both sides (sigma=0 whole-dof death pattern) — never NaN.
  2. Channels conserve total water to fp64 roundoff for ANY signed w; theta
     moves only through the two latent channels, each matching its own frozen
     pre-op-coefficient budget bitwise (same latent constant both directions
     — the signed-channel symmetry claim).
  3. w=0 => chain output == input bitwise (torch.equal), untouched fields are
     the same tensors (identity adjoint pass-through in the local graph).
  4. Composition: liq->ice via vap2liq(-d) + vap2ice(+d) nets the freeze
     latent L_f = xls - xl(T) to O(d^2) — the reason v1 has no direct
     liq<->ice channel (no §37 branch-conditional constants in the CVT).
  5. Caps builder: per-DONOR alpha budget (qv and qc split across their two
     drainers), frozen from xb, detached, zero/negative background donor =>
     whole channel dead there.
  6. PartitionSpec validates alpha_total and fingerprints channel order.
"""
from __future__ import annotations

import pytest
import torch

from kdm6 import thermo
from kdm6.da_partition import (
    CHANNELS, PartitionCaps, PartitionSpec, apply_partition_chain,
    bounded_delta, build_partition_caps,
)
from kdm6.state import Forcing, State

_F64 = dict(dtype=torch.float64)


def _t2(a, b):
    return torch.tensor([[a, b]], **_F64)


def _mk_state() -> State:
    """Cell 0: fully stocked (all 4 channels active). Cell 1: qi=qr=0
    (vap2ice and cloud2rain dead there — both-donor-positive rule)."""
    return State(
        th=_t2(296.8, 282.4), qv=_t2(1.40e-2, 2.0e-3),
        qc=_t2(1.0e-3, 5.0e-4), qr=_t2(1.0e-4, 0.0),
        qi=_t2(2.0e-4, 0.0), qs=_t2(1.0e-4, 5.0e-5),
        qg=_t2(5.0e-5, 1.0e-5), nccn=_t2(1.0e9, 1.0e9),
        nc=_t2(1.0e8, 1.0e8), ni=_t2(5.0e7, 1.0e8),
        nr=_t2(1.0e4, 1.0e3), bg=_t2(0.0, 0.0),
    )


def _mk_forcing(ref: State) -> Forcing:
    shp = ref.th.shape
    return Forcing(
        rho=torch.full(shp, 1.1, **_F64), pii=torch.full(shp, 0.95, **_F64),
        p=torch.full(shp, 8.5e4, **_F64), delz=torch.full(shp, 500.0, **_F64))


def _total_water(s: State) -> torch.Tensor:
    return s.qv + s.qc + s.qr + s.qi + s.qs + s.qg


# ── 1. bounded_delta ─────────────────────────────────────────────────────────

def test_bounded_delta_zero_exact_bitwise():
    cap_f = torch.tensor([1.0e-3, 2.0e-3], **_F64)
    cap_r = torch.tensor([5.0e-4, 1.0e-3], **_F64)
    active = torch.ones(2, dtype=torch.bool)
    d = bounded_delta(torch.zeros(2, **_F64), cap_f, cap_r, active)
    assert torch.equal(d, torch.zeros(2, **_F64))


def test_bounded_delta_c1_at_zero_both_sides():
    cap_f = torch.tensor([1.0e-3], **_F64)
    cap_r = torch.tensor([4.0e-4], **_F64)   # asymmetric caps on purpose
    active = torch.ones(1, dtype=torch.bool)
    w = torch.zeros(1, **_F64, requires_grad=True)
    (g,) = torch.autograd.grad(
        bounded_delta(w, cap_f, cap_r, active).sum(), w)
    assert torch.equal(g, torch.ones(1, **_F64))       # derivative exactly 1
    h = 1.0e-9
    for s in (+1.0, -1.0):                             # one-sided secants -> 1
        d = bounded_delta(torch.tensor([s * h], **_F64), cap_f, cap_r, active)
        assert abs(float(d) / (s * h) - 1.0) < 1.0e-5


def test_bounded_delta_saturates_at_caps():
    cap_f = torch.tensor([1.0e-3], **_F64)
    cap_r = torch.tensor([4.0e-4], **_F64)
    active = torch.ones(1, dtype=torch.bool)
    d_pos = bounded_delta(torch.tensor([10.0], **_F64), cap_f, cap_r, active)
    d_neg = bounded_delta(torch.tensor([-10.0], **_F64), cap_f, cap_r, active)
    assert 0.0 < float(d_pos) < float(cap_f)
    assert float(d_pos) > 0.999 * float(cap_f)
    assert -float(cap_r) < float(d_neg) < 0.0
    assert float(d_neg) < -0.999 * float(cap_r)
    # strictly monotone across the origin
    ws = torch.tensor([-1.0e-4, -1.0e-6, 0.0, 1.0e-6, 1.0e-4], **_F64)
    ds = bounded_delta(ws, cap_f.expand(5), cap_r.expand(5),
                       active.expand(5))
    assert bool((ds[1:] > ds[:-1]).all())


def test_bounded_delta_dead_cell_zero_value_and_grad():
    """Either cap == 0 kills the WHOLE channel in that cell: exact 0 value,
    exact 0 gradient from both sides, no NaN (bare where masking is the
    0*inf backward trap — this pins the safe-cap substitution)."""
    cap_f = torch.tensor([1.0e-3, 0.0], **_F64)
    cap_r = torch.tensor([0.0, 1.0e-3], **_F64)
    active = (cap_f > 0) & (cap_r > 0)
    assert not bool(active.any())
    for wval in (0.0, 1.0e-3, -1.0e-3):
        w = torch.full((2,), wval, **_F64, requires_grad=True)
        d = bounded_delta(w, cap_f, cap_r, active)
        assert bool(torch.isfinite(d).all())
        assert torch.equal(d.detach().abs(), torch.zeros(2, **_F64))
        (g,) = torch.autograd.grad(d.sum(), w)
        assert bool(torch.isfinite(g).all())
        assert torch.equal(g.abs(), torch.zeros(2, **_F64))


# ── 2/3. channel chain ───────────────────────────────────────────────────────

def _mk_all():
    y = _mk_state()
    f = _mk_forcing(y)
    spec = PartitionSpec()
    caps = build_partition_caps(y, spec)
    return y, f, spec, caps


def test_chain_w_zero_identity_bitwise():
    y, f, _spec, caps = _mk_all()
    w = torch.zeros((len(CHANNELS),) + tuple(y.th.shape), **_F64)
    out = apply_partition_chain(y, f, w, caps)
    for name, a, b in zip(State._fields, out, y):
        assert torch.equal(a, b), name
    # untouched fields are the SAME tensors (identity adj pass-through)
    for name in ("nccn", "nc", "ni", "nr", "bg"):
        assert getattr(out, name) is getattr(y, name)


def test_chain_total_water_invariant_any_w():
    y, f, _spec, caps = _mk_all()
    torch.manual_seed(7)
    w = 2.0e-3 * torch.randn((len(CHANNELS),) + tuple(y.th.shape), **_F64)
    out = apply_partition_chain(y, f, w, caps)
    assert torch.allclose(_total_water(out), _total_water(y),
                          rtol=0.0, atol=1.0e-16)
    for name in ("nccn", "nc", "ni", "nr", "bg"):     # never touched
        assert torch.equal(getattr(out, name), getattr(y, name))


@pytest.mark.parametrize("sign", [+1.0, -1.0])
def test_vap2liq_latent_budget_exact(sign):
    """Channel 0 alone: dth == xl(T_pre)/(cpm_pre*pi) * delta bitwise — the
    SAME xl both directions (parametrized sign) is the symmetry claim.
    w is DIMENSIONLESS: the chain feeds u = sigma * w to the bounded map."""
    y, f, _spec, caps = _mk_all()
    w = torch.zeros((len(CHANNELS),) + tuple(y.th.shape), **_F64)
    w[0] = sign * 0.6
    out = apply_partition_chain(y, f, w, caps)
    tp = thermo.default_thermo_params()
    d = bounded_delta(caps.sigma[0] * w[0], caps.cap_fwd[0], caps.cap_rev[0],
                      caps.active[0])
    xl = thermo.compute_xl(y.th * f.pii, params=tp)
    cpm = thermo.compute_cpm(y.qv, params=tp)
    assert torch.equal(out.th, y.th + xl / (cpm * f.pii) * d)
    assert torch.equal(out.qv, y.qv - d)
    assert torch.equal(out.qc, y.qc + d)
    assert torch.equal(out.qi, y.qi)


@pytest.mark.parametrize("sign", [+1.0, -1.0])
def test_vap2ice_latent_budget_exact(sign):
    """Channel 1 alone: dth == xls/(cpm_pre*pi) * delta bitwise (constant
    sublimation latent, exactly the same both directions)."""
    y, f, _spec, caps = _mk_all()
    w = torch.zeros((len(CHANNELS),) + tuple(y.th.shape), **_F64)
    w[1] = sign * 0.6
    out = apply_partition_chain(y, f, w, caps)
    tp = thermo.default_thermo_params()
    d = bounded_delta(caps.sigma[1] * w[1], caps.cap_fwd[1], caps.cap_rev[1],
                      caps.active[1])
    cpm = thermo.compute_cpm(y.qv, params=tp)
    assert torch.equal(out.th, y.th + tp.xls / (cpm * f.pii) * d)
    assert torch.equal(out.qv, y.qv - d)
    assert torch.equal(out.qi, y.qi + d)
    assert torch.equal(out.qc, y.qc)
    # cell 1 has qi_bg = 0: channel dead there, nothing moved
    assert torch.equal(out.qi[0, 1], y.qi[0, 1])


def test_mass_only_channels_no_theta():
    y, f, _spec, caps = _mk_all()
    w = torch.zeros((len(CHANNELS),) + tuple(y.th.shape), **_F64)
    w[2], w[3] = 0.5, -0.3
    out = apply_partition_chain(y, f, w, caps)
    d2 = bounded_delta(caps.sigma[2] * w[2], caps.cap_fwd[2],
                       caps.cap_rev[2], caps.active[2])
    d3 = bounded_delta(caps.sigma[3] * w[3], caps.cap_fwd[3],
                       caps.cap_rev[3], caps.active[3])
    assert torch.equal(out.th, y.th)
    assert torch.equal(out.qv, y.qv)
    assert torch.equal(out.qc, y.qc - d2)
    assert torch.equal(out.qr, y.qr + d2)
    assert torch.equal(out.qs, y.qs - d3)
    assert torch.equal(out.qg, y.qg + d3)


def test_composed_liq_to_ice_nets_freeze_latent():
    """Evaporate d from qc (ch0, delta=-d) + deposit d to qi (ch1, delta=+d):
    net latent == (xls - xl(T)) * d / (cpm*pi) = the freeze operator's L_f,
    to O(d^2). This is why v1 drops the direct liq<->ice channel."""
    y, f, _spec, caps = _mk_all()
    d = 1.0e-5
    # invert the bounded map for the exact target deltas (u = sigma * w);
    # cell 0 only — cell 1 has sigma[1] = 0 (dead vap2ice)
    u0 = -d / (1.0 - d / caps.cap_rev[0])            # delta(u0) = -d
    u1 = d / (1.0 - d / caps.cap_fwd[1])             # delta(u1) = +d
    w = torch.zeros((len(CHANNELS),) + tuple(y.th.shape), **_F64)
    w[0, 0, 0] = float(u0[0, 0] / caps.sigma[0][0, 0])
    w[1, 0, 0] = float(u1[0, 0] / caps.sigma[1][0, 0])
    out = apply_partition_chain(y, f, w, caps)
    c = 0                                             # cell 0 (all active)
    # tolerances = a few ulp of the carrier fields (qc~1e-3, qv~1.4e-2)
    assert abs(float(out.qc[0, c] - y.qc[0, c]) + d) < 5.0e-19
    assert abs(float(out.qi[0, c] - y.qi[0, c]) - d) < 5.0e-19
    assert abs(float(out.qv[0, c] - y.qv[0, c])) < 5.0e-18
    tp = thermo.default_thermo_params()
    xl = thermo.compute_xl(y.th * f.pii, params=tp)
    cpm = thermo.compute_cpm(y.qv, params=tp)
    lf_dth = float(((tp.xls - xl) / (cpm * f.pii) * d)[0, c])
    assert abs(float(out.th[0, c] - y.th[0, c]) - lf_dth) < 1.0e-4 * abs(lf_dth)


def test_chain_rejects_wrong_w_shape():
    y, f, _spec, caps = _mk_all()
    w = torch.zeros((len(CHANNELS), 3, 3), **_F64)
    with pytest.raises(ValueError, match="shape"):
        apply_partition_chain(y, f, w, caps)


def test_chain_local_autograd_pullback_smoke():
    """The minimizer pullback contract: chain differentiable wrt w AND all
    y leaves; identity fields pass the covector through unchanged."""
    y0, f, _spec, caps = _mk_all()
    leaves = State(**{fl: getattr(y0, fl).detach().clone().requires_grad_(True)
                      for fl in State._fields})
    w = (0.5 * torch.ones((len(CHANNELS),) + tuple(y0.th.shape), **_F64)
         ).requires_grad_(True)
    out = apply_partition_chain(leaves, f, w, caps)
    torch.manual_seed(3)
    adj = State(*(torch.randn_like(t) for t in out))
    inner = sum((a * o).sum() for a, o in zip(adj, out))
    grads = torch.autograd.grad(inner, [*leaves, w])
    g_y, g_w = grads[:-1], grads[-1]
    assert all(bool(torch.isfinite(g).all()) for g in grads)
    # identity fields: adjoint passes through exactly
    for name, g in zip(State._fields, g_y):
        if name in ("nccn", "nc", "ni", "nr", "bg"):
            assert torch.equal(g, getattr(adj, name)), name
    # active cells carry observation gradient into w
    assert bool((g_w[caps.active] != 0).any())
    # dead cells (cell 1, channels 1 and 2) carry exactly zero
    assert bool((g_w[~caps.active] == 0).all())


# ── 5. caps builder ──────────────────────────────────────────────────────────

def test_caps_per_donor_budget_and_activation():
    y = _mk_state()
    caps = build_partition_caps(y, PartitionSpec(alpha_total=0.5))
    zeros = torch.zeros_like(y.qv)
    exp = lambda q, a: torch.where(q > 0, a * q, zeros)
    # qv drained by ch0-fwd and ch1-fwd; qc by ch0-rev and ch2-fwd -> 0.25
    assert torch.equal(caps.cap_fwd[0], exp(y.qv, 0.25))
    assert torch.equal(caps.cap_fwd[1], exp(y.qv, 0.25))
    assert torch.equal(caps.cap_rev[0], exp(y.qc, 0.25))
    assert torch.equal(caps.cap_fwd[2], exp(y.qc, 0.25))
    # single-drainer donors -> 0.5
    assert torch.equal(caps.cap_rev[1], exp(y.qi, 0.5))
    assert torch.equal(caps.cap_rev[2], exp(y.qr, 0.5))
    assert torch.equal(caps.cap_fwd[3], exp(y.qs, 0.5))
    assert torch.equal(caps.cap_rev[3], exp(y.qg, 0.5))
    assert torch.equal(caps.active, (caps.cap_fwd > 0) & (caps.cap_rev > 0))
    # dimensionless-control scale: sigma = sigma_scale * min(caps), so the
    # prior 1/2*||w||^2 states delta ~ N(0, sigma^2) near the origin
    assert torch.equal(caps.sigma,
                       0.25 * torch.minimum(caps.cap_fwd, caps.cap_rev))
    assert torch.equal(caps.active, caps.sigma > 0)
    # cell 1: qi=0, qr=0 -> vap2ice and cloud2rain dead there
    assert not bool(caps.active[1, 0, 1]) and not bool(caps.active[2, 0, 1])
    assert bool(caps.active[0, 0, 1]) and bool(caps.active[3, 0, 1])
    for t in (caps.cap_fwd, caps.cap_rev):
        assert not t.requires_grad


def test_caps_negative_background_donor_dead():
    y = _mk_state()._replace(qi=_t2(-1.0e-9, 1.0e-6))
    caps = build_partition_caps(y, PartitionSpec())
    assert float(caps.cap_rev[1][0, 0]) == 0.0        # no sign-flipped cap
    assert not bool(caps.active[1, 0, 0])


def test_caps_frozen_from_background_not_graph():
    y = _mk_state()
    y = State(*(t.requires_grad_(True) for t in y))
    caps = build_partition_caps(y, PartitionSpec())
    assert not caps.cap_fwd.requires_grad and not caps.cap_rev.requires_grad


def test_caps_rejects_nonfinite_background():
    y = _mk_state()._replace(qv=_t2(float("nan"), 2.0e-3))
    with pytest.raises(ValueError, match="finite"):
        build_partition_caps(y, PartitionSpec())


# ── 6. spec ──────────────────────────────────────────────────────────────────

def test_partition_spec_validation():
    PartitionSpec()
    PartitionSpec(alpha_total=1.0)
    for bad in (0.0, -0.1, 1.5, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="alpha_total"):
            PartitionSpec(alpha_total=bad)
    for bad in (0.0, -0.1, 1.5, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="sigma_scale"):
            PartitionSpec(sigma_scale=bad)
    # bool is an int subclass (True == 1.0): must be rejected for the
    # exact-schema gate comparisons to be meaningful
    with pytest.raises(ValueError, match="alpha_total"):
        PartitionSpec(alpha_total=True)
    with pytest.raises(ValueError, match="sigma_scale"):
        PartitionSpec(sigma_scale=True)
    with pytest.raises(ValueError, match="alpha_total"):
        PartitionSpec(alpha_total=10**309)      # isfinite OverflowError


def test_partition_spec_fingerprint():
    f1 = PartitionSpec().fingerprint()
    assert f1 == PartitionSpec(alpha_total=0.5).fingerprint()
    assert f1 != PartitionSpec(alpha_total=0.4).fingerprint()
    assert f1 != PartitionSpec(sigma_scale=0.1).fingerprint()
    d = PartitionSpec().as_dict()
    assert d["version"] == 2                # v2 = dimensionless-w metric
    assert d["alpha_total"] == 0.5
    assert d["sigma_scale"] == 0.25
    assert d["control_units"] == "dimensionless"
    assert d["channels"] == [c[0] for c in CHANNELS]


def test_channel_table_frozen():
    """The v1 channel set and ORDER are load-bearing (non-commuting through
    T; per-donor drainer counts) — pin them."""
    assert CHANNELS == (
        ("vap2liq", "qv", "qc", "xl"),
        ("vap2ice", "qv", "qi", "xls"),
        ("cloud2rain", "qc", "qr", None),
        ("snow2graupel", "qs", "qg", None),
    )


# ── minimizer integration (run_minimizer partition= seam) ────────────────────

from kdm6.da_cvt import cvt_apply, make_default_cvt
from kdm6.da_minimizer import run_minimizer
from kdm6.da_partition import (build_partition_record, chain_with_pullback,
                               validate_partition)
from kdm6.da_window import WindowConfig, run_da_window

from _cvt_test_util import fd_check

DT = 20.0


def _zeros_state(ref: State) -> State:
    return State(**{k: torch.zeros_like(v) for k, v in ref._asdict().items()})


def _obs_th_at(t_obs: int, y: torch.Tensor, sigma_o: float):
    def obs_eval(t: int, x_t: State):
        if t != t_obs:
            return None
        r = (x_t.th - y) / sigma_o
        return 0.5 * (r * r).sum(), _zeros_state(x_t)._replace(th=r / sigma_o)
    return obs_eval


def _conserving_cvt(xb: State, *, th_sigma=0.8, qv_sigma=0.08):
    """Conserving-mode diagonal stage: hydrometeor MASS sigma = 0 (species
    move only through partitions); th/qv/number controls stay."""
    return make_default_cvt(xb, th_sigma=th_sigma, qv_sigma=qv_sigma,
                            sigma_overrides={"qc": 0.0, "qi": 0.0,
                                             "qs": 0.0})


def test_minimizer_partition_none_is_legacy_bitwise():
    xb = _mk_state()
    forcings = [_mk_forcing(xb)] * 2
    cfg = WindowConfig(dt=DT)
    spec, b_sigma = _conserving_cvt(xb)
    truth = run_da_window(xb, forcings, lambda t, x: None, cfg).state_final
    obs = _obs_th_at(2, truth.th + 0.3, sigma_o=0.5)
    res_a = run_minimizer(xb, forcings, obs, cfg, b_sigma, max_iter=3,
                          cvt=spec)
    res_b = run_minimizer(xb, forcings, obs, cfg, b_sigma, max_iter=3,
                          cvt=spec, partition=None)
    assert res_a.j_trace == res_b.j_trace
    for k in State._fields:
        assert torch.equal(getattr(res_a.x_analysis, k),
                           getattr(res_b.x_analysis, k)), k
    assert res_b.w is None and res_b.partition is None
    assert res_b.grad_w_norm_final is None


def test_chain_pullback_matches_fd_through_window():
    """FD contrast of BOTH gradient blocks (g_v diagonal chain through the
    pullback, g_w local autograd) through a real 2-step oracle window."""
    xb = _mk_state()
    forcings = [_mk_forcing(xb)] * 2
    cfg = WindowConfig(dt=DT)
    spec, b_sigma = _conserving_cvt(xb)
    pspec = PartitionSpec()
    caps = build_partition_caps(xb, pspec)
    truth = run_da_window(xb, forcings, lambda t, x: None, cfg).state_final
    obs_eval = _obs_th_at(2, truth.th + 0.3, sigma_o=0.5)
    nch = len(CHANNELS)

    def run(x0):
        acc = []

        def obs_adjoint(t, x_t):
            out = obs_eval(t, x_t)
            if out is None:
                return None
            acc.append(out[0].detach())
            return out[1]

        res = run_da_window(x0, forcings, obs_adjoint, cfg)
        return res, torch.stack(acc).sum()

    # probe point away from the relu corner (|w0| >> fd h)
    v0 = torch.zeros((12,) + tuple(xb.th.shape), **_F64)
    v0[0, 0, 0], v0[1, 0, 1] = 0.2, -0.1
    # w is dimensionless (u = sigma*w, sigma = 0.25*min(caps)): |w| < ~1
    # keeps the probe well below the saturation knee (FD truncation gate)
    w0 = torch.zeros((nch,) + tuple(xb.th.shape), **_F64)
    w0[0], w0[1] = 0.3, -0.4

    with torch.no_grad():
        y, jac = cvt_apply(xb, b_sigma, v0, spec)
    x0, pullback = chain_with_pullback(y, forcings[0], w0, caps)
    res, _ = run(x0)
    adj_y, g_w_obs = pullback(res.adj_x0)
    g_v = v0 + jac * adj_y
    g_w = w0 + g_w_obs

    def j_of_v(vv):
        with torch.no_grad():
            yy, _ = cvt_apply(xb, b_sigma, vv, spec)
            xx = apply_partition_chain(yy, forcings[0], w0, caps)
        _, j_obs = run(xx)
        return float(0.5 * (vv * vv).sum() + 0.5 * (w0 * w0).sum() + j_obs)

    def j_of_w(ww):
        with torch.no_grad():
            yy, _ = cvt_apply(xb, b_sigma, v0, spec)
            xx = apply_partition_chain(yy, forcings[0], ww, caps)
        _, j_obs = run(xx)
        return float(0.5 * (v0 * v0).sum() + 0.5 * (ww * ww).sum() + j_obs)

    for idx in ((0, 0, 0), (1, 0, 1)):                    # th, qv controls
        fd_check(j_of_v, v0, idx, float(g_v[idx]))
    for idx in ((0, 0, 0), (1, 0, 0)):                    # vap channels
        fd_check(j_of_w, w0, idx, float(g_w[idx]))


def test_minimizer_conserving_e2e_water_invariant():
    """Twin reachable by partitions only: all diagonal sigma = 0, truth =
    chain(xb, w_true). J must fall through w alone; total water at x0 is
    invariant and no species leaves its cap floor."""
    xb = _mk_state()
    forcings = [_mk_forcing(xb)] * 2
    cfg = WindowConfig(dt=DT)
    spec, b_sigma = make_default_cvt(
        xb, th_sigma=0.0, qv_sigma=0.0,
        sigma_overrides={f: 0.0 for f in ("qc", "qi", "qs", "nc", "ni")})
    pspec = PartitionSpec()
    caps = build_partition_caps(xb, pspec)
    # w_true within the saturating range; sigma_o small enough that the obs
    # term dominates the w-prior DESPITE the supersaturated background's
    # satadj absorbing most of the t0 latent signal by t=2 (measured ~100x)
    w_true = torch.zeros((len(CHANNELS),) + tuple(xb.th.shape), **_F64)
    w_true[0], w_true[1] = 3.0, 2.0                        # dimensionless
    with torch.no_grad():
        x_true = apply_partition_chain(xb, forcings[0], w_true, caps)
    y = run_da_window(x_true, forcings, lambda t, x: None, cfg).state_final.th
    res = run_minimizer(xb, forcings, _obs_th_at(2, y, sigma_o=2.0e-4),
                        cfg, b_sigma, max_iter=10, cvt=spec, partition=pspec)
    assert res.j_trace[-1] < res.j_trace[0], res.j_trace
    assert res.w is not None and float(res.w.abs().max()) > 0.0
    assert res.grad_w_norm_final is not None and res.grad_w_norm_final >= 0.0
    # observable-space recovery gate: H(M(x_a)) approaches the truth
    # observable — w is the ONLY live control here (all diagonal sigma 0),
    # so the reduction is attributable to w (measured ratio 0.0029)
    assert res.jobs_final < 0.1 * res.j_trace[0], \
        (res.jobs_final, res.j_trace[0])
    xa = res.x_analysis
    assert torch.allclose(_total_water(xa), _total_water(xb),
                          rtol=0.0, atol=1.0e-16)
    for f in ("qv", "qc", "qr", "qi", "qs", "qg"):
        assert bool((getattr(xa, f) >= -1.0e-18).all()), f
    assert res.partition["fingerprint"] == pspec.fingerprint()
    assert set(res.partition["n_active"]) == {c[0] for c in CHANNELS}


def test_partition_requires_touched_fields_active():
    """V8: a live channel whose donor/receiver/th adjoint row is zero-masked
    by active_fields would get a silently-zero g_w — loud error instead."""
    xb = _mk_state()
    caps = build_partition_caps(xb, PartitionSpec())
    with pytest.raises(ValueError, match="active_fields"):
        validate_partition(caps, ("th", "qv"))
    validate_partition(caps, None)                        # no masking: fine
    validate_partition(caps, ("th", "qv", "qc", "qr", "qi", "qs", "qg"))
    # dead-everywhere channels impose nothing
    dead = PartitionCaps(cap_fwd=torch.zeros_like(caps.cap_fwd),
                         cap_rev=torch.zeros_like(caps.cap_rev),
                         sigma=torch.zeros_like(caps.sigma),
                         active=torch.zeros_like(caps.active))
    validate_partition(dead, ("th",))


def test_minimizer_partition_gate_wired():
    """run_minimizer must run the V8 gate itself (fail-fast before windows)."""
    xb = _mk_state()
    forcings = [_mk_forcing(xb)] * 2
    cfg = WindowConfig(dt=DT, active_fields=("th", "qv"))
    spec, b_sigma = _conserving_cvt(xb, th_sigma=0.8, qv_sigma=0.08)
    with pytest.raises(ValueError, match="active_fields"):
        run_minimizer(xb, forcings, lambda t, x: None, cfg, b_sigma,
                      max_iter=2, cvt=spec, partition=PartitionSpec())


def test_partition_no_obs_returns_background():
    xb = _mk_state()
    forcings = [_mk_forcing(xb)] * 2
    spec, b_sigma = _conserving_cvt(xb)
    res = run_minimizer(xb, forcings, lambda t, x: None, WindowConfig(dt=DT),
                        b_sigma, max_iter=5, cvt=spec,
                        partition=PartitionSpec())
    assert res.jobs_final == 0.0
    assert torch.equal(res.w.abs(), torch.zeros_like(res.w))
    for k in State._fields:
        assert torch.equal(getattr(res.x_analysis, k),
                           getattr(xb, k).to(torch.float64)), k


def test_partition_record_saturation_and_counts():
    xb = _mk_state()
    pspec = PartitionSpec()
    caps = build_partition_caps(xb, pspec)
    w = torch.zeros((len(CHANNELS),) + tuple(xb.th.shape), **_F64)
    w[0] = 1.0e6                                          # deep saturation
    rec = build_partition_record(pspec, caps, w)
    assert rec["fingerprint"] == pspec.fingerprint()
    assert rec["n_active"]["vap2liq"] == int(caps.active[0].sum())
    assert rec["sat_max"]["vap2liq"] > 0.999
    assert rec["sat_max"]["snow2graupel"] == 0.0
    assert len(rec["caps_sha256"]) == 64


# ── dual minimizer integration (run_dual_minimizer partition= seam) ──────────

from kdm6.da_dual import default_param_prior, run_dual_minimizer


def _P(**kw):
    from kdm6.da_dual import ObsGatePolicy
    return ObsGatePolicy(allow_tuple_returns=True, **kw)


def _quad_th_obs(t_obs: int, y_target: torch.Tensor, sigma_o: float = 1.0):
    """Synthetic dual obs term: J = 0.5*sum(((th_t - y)/sigma_o)^2)."""
    def obs_eval(t, x_t):
        if t != t_obs:
            return None
        r = (x_t.th - y_target) / sigma_o
        adj = _zeros_state(x_t)._replace(th=r / sigma_o)
        return float(0.5 * (r * r).sum()), adj, int(r.numel()), "synthetic-quad"
    return obs_eval


def test_dual_partition_none_is_legacy():
    xb = _mk_state()
    forcings = [_mk_forcing(xb)] * 2
    cfg = WindowConfig(dt=DT)
    spec, b_sigma = _conserving_cvt(xb)
    prior = default_param_prior(0.2)
    truth = run_da_window(xb, forcings, lambda t, x: None, cfg).state_final
    obs = _quad_th_obs(2, truth.th + 0.3)
    res_a = run_dual_minimizer(xb, forcings, obs, cfg, b_sigma, prior,
                               max_iter=3, cvt=spec, policy=_P())
    res_b = run_dual_minimizer(xb, forcings, obs, cfg, b_sigma, prior,
                               max_iter=3, cvt=spec, policy=_P(),
                               partition=None)
    assert [e["total"] for e in res_a.j_trace] == \
           [e["total"] for e in res_b.j_trace]
    for k in State._fields:
        assert torch.equal(getattr(res_a.x_analysis, k),
                           getattr(res_b.x_analysis, k)), k
    assert res_b.w is None and res_b.partition is None
    assert res_b.grad_w_norm_final is None


def test_dual_partition_e2e_water_invariant():
    """Dual W-ONLY twin: theta frozen (active=()) and every diagonal sigma 0,
    so the observable recovery is attributable to w ALONE (causal isolation
    — with theta active the J descent could be explained by parameters)."""
    xb = _mk_state()
    forcings = [_mk_forcing(xb)] * 2
    cfg = WindowConfig(dt=DT)
    spec, b_sigma = make_default_cvt(
        xb, th_sigma=0.0, qv_sigma=0.0,
        sigma_overrides={f: 0.0 for f in ("qc", "qi", "qs", "nc", "ni")})
    prior = default_param_prior(0.2, active=())          # theta pinned
    pspec = PartitionSpec()
    caps = build_partition_caps(xb, pspec)
    # obs-dominated twin (see the single-minimizer E2E note on satadj wash)
    w_true = torch.zeros((len(CHANNELS),) + tuple(xb.th.shape), **_F64)
    w_true[0], w_true[1] = 3.0, 2.0                        # dimensionless
    with torch.no_grad():
        x_true = apply_partition_chain(xb, forcings[0], w_true, caps)
    y = run_da_window(x_true, forcings, lambda t, x: None, cfg).state_final.th
    res = run_dual_minimizer(xb, forcings, _quad_th_obs(2, y, sigma_o=2.0e-4),
                             cfg, b_sigma, prior, max_iter=10, cvt=spec,
                             policy=_P(), partition=pspec)
    assert res.j_trace[-1]["total"] < res.j_trace[0]["total"]
    assert res.w is not None and float(res.w.abs().max()) > 0.0
    assert res.grad_w_norm_final is not None and res.grad_w_norm_final >= 0.0
    # w-only causal isolation: theta must not have moved at all
    assert float(res.v_theta.abs().max()) == 0.0
    # observable-space recovery gate (measured ratio 0.0029 — 34x margin)
    assert res.jobs_final < 0.1 * res.j_trace[0]["total"], \
        (res.jobs_final, res.j_trace[0]["total"])
    assert torch.allclose(_total_water(res.x_analysis), _total_water(xb),
                          rtol=0.0, atol=1.0e-16)
    assert res.partition["fingerprint"] == pspec.fingerprint()


def test_dual_partition_dead_channel_t0_only_rejected():
    """V7 analogue for channels: with t=0-only bearing slots and clear-sky
    connected_fields=(th,qv), the mass-only channels (qc/qr, qs/qg) have
    guaranteed-zero gradient — reject loudly instead of prior-pinning w."""
    xb = _mk_state()
    forcings = [_mk_forcing(xb)] * 2
    cfg = WindowConfig(dt=DT)
    # nc/ni sigma = 0 too so the pre-existing field-level V7 passes and the
    # CHANNEL gate is what fires
    spec, b_sigma = make_default_cvt(
        xb, sigma_overrides={f: 0.0 for f in ("qc", "qi", "qs", "nc", "ni")})
    obs = _quad_th_obs(0, xb.th + 0.3)
    obs.connected_fields = ("th", "qv")
    with pytest.raises(ValueError, match="cloud2rain"):
        run_dual_minimizer(xb, forcings, obs, cfg, b_sigma,
                           default_param_prior(0.2), max_iter=2, cvt=spec,
                           policy=_P(), partition=PartitionSpec())
    # a t>=1 bearing slot makes every channel M^T-reachable: no rejection
    obs2 = _quad_th_obs(2, xb.th + 0.3)
    obs2.connected_fields = ("th", "qv")
    run_dual_minimizer(xb, forcings, obs2, cfg, b_sigma,
                       default_param_prior(0.2), max_iter=2, cvt=spec,
                       policy=_P(), partition=PartitionSpec())


def test_dual_partition_composes_with_pseudo_rh():
    """Design v1.1 test 6: creation stays with the pseudo-RH bootstrap,
    refinement with the conserving channels — both opt-ins compose in one
    dual run (wrapper keeps n_valid/signature/connected contracts; channels
    stay alive because qv is in the composite connected set)."""
    from kdm6.da_dual import ObsEvalResult
    from kdm6.da_regime2 import (frozen_saturation_target,
                                 wrap_dual_obs_eval_with_pseudo_rh)

    xb = _mk_state()
    forcings = [_mk_forcing(xb)] * 2
    cfg = WindowConfig(dt=DT)
    spec, b_sigma = make_default_cvt(
        xb, sigma_overrides={f: 0.0 for f in ("qc", "qi", "qs", "nc", "ni")})
    prior = default_param_prior(0.2)
    truth = run_da_window(xb, forcings, lambda t, x: None, cfg).state_final

    def base_obs(t, x_t):
        if t != 2:
            return None
        d = x_t.th - (truth.th + 0.3)
        adj = _zeros_state(x_t)._replace(th=d.clone())
        return ObsEvalResult(j=float(0.5 * (d * d).sum()), adj=adj,
                             n_valid=int(d.numel()), signature="synthetic")
    base_obs.connected_fields = ("th", "qv")

    cols = torch.tensor([0])
    target = frozen_saturation_target(xb, forcings[0], cols)
    obs = wrap_dual_obs_eval_with_pseudo_rh(
        base_obs, t_obs=2, cols=cols, target=target, sigma_p=1.0e-3)
    res = run_dual_minimizer(xb, forcings, obs, cfg, b_sigma, prior,
                             max_iter=6, cvt=spec,
                             partition=PartitionSpec())
    assert res.j_trace[-1]["total"] < res.j_trace[0]["total"]
    assert res.w is not None
    # qv mul stays live here (moisture correction is the deliberate
    # non-conserving dof): total water changes EXACTLY by the diagonal qv
    # increment — the partition stage itself adds nothing
    y_a, _ = cvt_apply(xb, b_sigma, res.v_state, spec)
    assert torch.allclose(_total_water(res.x_analysis) - _total_water(xb),
                          y_a.qv - xb.qv, rtol=0.0, atol=1.0e-15)


# ── zero-step (t=0-only, 3D-Var-style) windows (Codex stop-review) ───────────

def _obs_th_t0(xb):
    def obs_eval(t, x_t):
        if t != 0:
            return None
        d = x_t.th - (xb.th + 0.3)
        return 0.5 * (d * d).sum(), _zeros_state(x_t)._replace(th=d.clone())
    return obs_eval


def test_partition_zero_step_window_explicit_forcing():
    """A zero-step window (obs at t=0 only) is valid in the legacy path and
    must stay valid with partition: the t0 forcing (Exner) is passed
    explicitly since forcings[] has no steps. The latent theta term gives
    the channels direct t0 sensitivity, so J falls through w too."""
    xb = _mk_state()
    f0 = _mk_forcing(xb)
    spec, b_sigma = make_default_cvt(
        xb, th_sigma=0.0, qv_sigma=0.0,
        sigma_overrides={f: 0.0 for f in ("qc", "qi", "qs", "nc", "ni")})
    res = run_minimizer(xb, [], _obs_th_t0(xb), WindowConfig(dt=DT), b_sigma,
                        max_iter=5, cvt=spec, partition=PartitionSpec(),
                        partition_forcing=f0)
    assert res.j_trace[-1] < res.j_trace[0], res.j_trace
    assert float(res.w.abs().max()) > 0.0
    assert torch.allclose(_total_water(res.x_analysis), _total_water(xb),
                          rtol=0.0, atol=1.0e-16)


def test_partition_zero_step_window_without_forcing_rejected():
    """No steps and no explicit t0 forcing: loud contract error, never an
    IndexError from forcings[0]."""
    xb = _mk_state()
    spec, b_sigma = _conserving_cvt(xb)
    with pytest.raises(ValueError, match="partition_forcing"):
        run_minimizer(xb, [], _obs_th_t0(xb), WindowConfig(dt=DT), b_sigma,
                      max_iter=2, cvt=spec, partition=PartitionSpec())


def test_partition_forcing_without_partition_rejected():
    """A stray partition_forcing with partition=None is a config error, not
    a silent no-op."""
    xb = _mk_state()
    spec, b_sigma = _conserving_cvt(xb)
    with pytest.raises(ValueError, match="partition_forcing"):
        run_minimizer(xb, [_mk_forcing(xb)], _obs_th_t0(xb),
                      WindowConfig(dt=DT), b_sigma, max_iter=2, cvt=spec,
                      partition_forcing=_mk_forcing(xb))


def test_dual_partition_zero_step_window():
    """Same contract on the dual path (obs term carries n_valid/signature;
    no connected_fields tag => the channel gate does not apply)."""
    xb = _mk_state()
    f0 = _mk_forcing(xb)
    spec, b_sigma = make_default_cvt(
        xb, th_sigma=0.0, qv_sigma=0.0,
        sigma_overrides={f: 0.0 for f in ("qc", "qi", "qs", "nc", "ni")})

    def obs(t, x_t):
        if t != 0:
            return None
        d = x_t.th - (xb.th + 0.3)
        adj = _zeros_state(x_t)._replace(th=d.clone())
        return float(0.5 * (d * d).sum()), adj, int(d.numel()), "synthetic"

    res = run_dual_minimizer(xb, [], obs, WindowConfig(dt=DT), b_sigma,
                             default_param_prior(0.2), max_iter=5, cvt=spec,
                             policy=_P(), partition=PartitionSpec(),
                             partition_forcing=f0)
    assert res.j_trace[-1]["total"] < res.j_trace[0]["total"]
    with pytest.raises(ValueError, match="partition_forcing"):
        run_dual_minimizer(xb, [], obs, WindowConfig(dt=DT), b_sigma,
                           default_param_prior(0.2), max_iter=2, cvt=spec,
                           policy=_P(), partition=PartitionSpec())


# ── forcing contract + conserving-sigma contract (review follow-ups) ─────────

def test_partition_forcing_pii_validated():
    """The zero-step path bypasses the model's own forcing validation: a
    wrong-shape pii would silently broadcast and 0/NaN pii makes non-finite
    theta increments — exact-shape/finite/positive contract enforced."""
    xb = _mk_state()
    spec, b_sigma = _conserving_cvt(xb)
    good = _mk_forcing(xb)
    bad_shape = good._replace(pii=torch.full((1, 1), 0.95, **_F64))
    bad_zero = good._replace(pii=torch.zeros_like(good.pii))
    bad_nan = good._replace(
        pii=good.pii.clone().index_fill_(1, torch.tensor([0]), float("nan")))
    for bad in (bad_shape, bad_zero, bad_nan):
        with pytest.raises(ValueError, match="pii"):
            run_minimizer(xb, [], _obs_th_t0(xb), WindowConfig(dt=DT),
                          b_sigma, max_iter=2, cvt=spec,
                          partition=PartitionSpec(), partition_forcing=bad)


def test_partition_forcing_must_match_step_forcing():
    """A non-zero window with an explicit partition_forcing whose pii differs
    from forcings[0].pii bifurcates the physics configuration — same dtype +
    exact elementwise value match enforced; a matching explicit forcing
    stays allowed."""
    xb = _mk_state()
    f0 = _mk_forcing(xb)
    spec, b_sigma = _conserving_cvt(xb)
    other = f0._replace(pii=f0.pii * 1.0001)
    with pytest.raises(ValueError, match="forcings\\[0\\]"):
        run_minimizer(xb, [f0, f0], _obs_th_t0(xb), WindowConfig(dt=DT),
                      b_sigma, max_iter=2, cvt=spec,
                      partition=PartitionSpec(), partition_forcing=other)
    run_minimizer(xb, [f0, f0], _obs_th_t0(xb), WindowConfig(dt=DT), b_sigma,
                  max_iter=2, cvt=spec, partition=PartitionSpec(),
                  partition_forcing=f0)


def test_partition_enforces_mass_hydro_sigma_zero():
    """Conserving contract is ENFORCED, not conventional: a live diagonal mul
    control on any of qc/qr/qi/qs/qg double-controls the species and breaks
    the total-water invariance the partition stage exists to provide."""
    xb = _mk_state()
    f0 = _mk_forcing(xb)
    spec, b_sigma = make_default_cvt(
        xb, sigma_overrides={"qc": 0.5, "qi": 0.0, "qs": 0.0,
                             "nc": 0.0, "ni": 0.0})
    with pytest.raises(ValueError, match="qc"):
        run_minimizer(xb, [f0, f0], _obs_th_t0(xb), WindowConfig(dt=DT),
                      b_sigma, max_iter=2, cvt=spec,
                      partition=PartitionSpec())
    with pytest.raises(ValueError, match="qc"):
        run_dual_minimizer(xb, [f0, f0], lambda t, x: None,
                           WindowConfig(dt=DT), b_sigma,
                           default_param_prior(0.2), max_iter=2, cvt=spec,
                           policy=_P(), partition=PartitionSpec())


# ── final-report authority + observable recovery (review round 3) ────────────

def test_final_report_is_authoritative_at_returned_controls():
    """Strong-Wolfe may reject the last trial and restore a previous bracket
    point WITHOUT re-calling the closure there — the reported *_final and
    j_trace[-1] must nevertheless be the values AT the returned controls
    (final audit evaluation). Checked by independent recomputation."""
    xb = _mk_state()
    forcings = [_mk_forcing(xb)] * 2
    cfg = WindowConfig(dt=DT)
    spec, b_sigma = make_default_cvt(
        xb, th_sigma=0.0, qv_sigma=0.0,
        sigma_overrides={f: 0.0 for f in ("qc", "qi", "qs", "nc", "ni")})
    pspec = PartitionSpec()
    caps = build_partition_caps(xb, pspec)
    w_true = torch.zeros((len(CHANNELS),) + tuple(xb.th.shape), **_F64)
    w_true[0], w_true[1] = 3.0, 2.0
    with torch.no_grad():
        x_true = apply_partition_chain(xb, forcings[0], w_true, caps)
    y = run_da_window(x_true, forcings, lambda t, x: None, cfg).state_final.th
    obs_eval = _obs_th_at(2, y, sigma_o=2.0e-4)
    res = run_minimizer(xb, forcings, obs_eval, cfg, b_sigma, max_iter=10,
                        cvt=spec, partition=pspec)

    # independent recomputation at the RETURNED controls
    with torch.no_grad():
        y_a, _ = cvt_apply(xb, b_sigma, res.v, spec)
        x0 = apply_partition_chain(y_a, forcings[0], res.w, caps)
    acc = []

    def obs_adjoint(t, x_t):
        out = obs_eval(t, x_t)
        if out is None:
            return None
        acc.append(out[0].detach())
        return out[1]

    run_da_window(x0, forcings, obs_adjoint, cfg)
    j_obs = float(torch.stack(acc).sum())
    j_b = float(0.5 * (res.v * res.v).sum() + 0.5 * (res.w * res.w).sum())
    assert res.jobs_final == j_obs, (res.jobs_final, j_obs)
    assert res.jb_final == j_b, (res.jb_final, j_b)
    assert res.j_trace[-1] == j_b + j_obs, (res.j_trace[-1], j_b + j_obs)
    assert res.n_audit_evals == 1


def test_dual_final_report_is_authoritative():
    """Dual analogue with FULL independence: J_obs is recomputed by re-running
    the window at the RETURNED (v_state, v_theta, w) — not read back from the
    audit cache — and every equality is exact float ==."""
    import dataclasses

    from kdm6.da_dual import params_from_vtheta

    xb = _mk_state()
    forcings = [_mk_forcing(xb)] * 2
    cfg = WindowConfig(dt=DT)
    spec, b_sigma = make_default_cvt(
        xb, sigma_overrides={f: 0.0 for f in ("qc", "qi", "qs", "nc", "ni")})
    pspec = PartitionSpec()
    caps = build_partition_caps(xb, pspec)
    prior = default_param_prior(0.2)
    truth = run_da_window(xb, forcings, lambda t, x: None, cfg).state_final
    obs_eval = _quad_th_obs(2, truth.th + 0.3, sigma_o=0.05)
    res = run_dual_minimizer(xb, forcings, obs_eval, cfg, b_sigma, prior,
                             max_iter=10, cvt=spec, policy=_P(),
                             partition=pspec)

    # independent recomputation at the RETURNED controls/parameters
    with torch.no_grad():
        y_a, _ = cvt_apply(xb, b_sigma, res.v_state, spec)
        x0 = apply_partition_chain(y_a, forcings[0], res.w, caps)
    cfg_a = dataclasses.replace(
        cfg, params=params_from_vtheta(prior, res.v_theta), param_grads=False)
    acc = []

    def obs_adjoint(t, x_t):
        out = obs_eval(t, x_t)
        if out is None:
            return None
        acc.append(float(out[0]))
        return out[1]

    run_da_window(x0, forcings, obs_adjoint, cfg_a)
    jobs = sum(acc)
    jb = float(0.5 * (res.v_state * res.v_state).sum()
               + 0.5 * (res.w * res.w).sum())
    jth = float(0.5 * (res.v_theta * res.v_theta).sum())
    assert res.jobs_final == jobs, (res.jobs_final, jobs)
    assert res.jb_final == jb, (res.jb_final, jb)
    assert res.jtheta_final == jth, (res.jtheta_final, jth)
    assert res.j_trace[-1]["total"] == jb + jth + jobs
    assert res.n_audit_evals == 1
    assert len(res.j_trace) == res.n_window_evals + res.n_audit_evals


@pytest.mark.parametrize("w0,w1,lo,hi", [(0.8, 0.5, 30.0, 500.0),
                                         (3.0, 2.0, 30.0, 500.0),
                                         (8.0, 5.0, 30.0, 500.0)])
def test_model_window_damping_ratio_regression(w0, w1, lo, hi):
    """Pins the measured MODEL-WINDOW damping the twin design relies on: the
    2-step window from this supersaturated-background fixture absorbs the t0
    partition latent signal by roughly two orders of magnitude by t=2
    (measured 137x/118x/109x at these three amplitudes; max-norm on th).
    NOTE: this is the whole-window damping ratio — saturation adjustment is
    the physically expected main absorber, but no single-process ablation is
    claimed here."""
    xb = _mk_state()
    f0 = _mk_forcing(xb)
    forcings = [f0] * 2
    cfg = WindowConfig(dt=DT)
    caps = build_partition_caps(xb, PartitionSpec())
    w = torch.zeros((len(CHANNELS),) + tuple(xb.th.shape), **_F64)
    w[0], w[1] = w0, w1
    with torch.no_grad():
        x_true = apply_partition_chain(xb, f0, w, caps)
    dth0 = float((x_true.th - xb.th).abs().max())
    th_t = run_da_window(x_true, forcings, lambda t, x: None, cfg).state_final.th
    th_b = run_da_window(xb, forcings, lambda t, x: None, cfg).state_final.th
    resid = float((th_t - th_b).abs().max())
    assert dth0 > 0.05                               # signal present at t0
    ratio = dth0 / resid
    assert lo < ratio < hi, (w0, w1, dth0, resid, ratio)


def test_composed_latent_second_order_and_order_dependent():
    """Completes the 'tested' claim on the composed-L_f statement: the energy
    error vs the freeze convention is GENUINELY second order (halving d
    quarters the error — an exactly-L_f implementation would fail the
    nonzero-error check) and the composition is order-dependent (deposit-
    then-evaporate differs from the chain's evaporate-then-deposit)."""
    y, f, _spec, caps = _mk_all()
    tp = thermo.default_thermo_params()
    xl = thermo.compute_xl(y.th * f.pii, params=tp)
    cpm = thermo.compute_cpm(y.qv, params=tp)
    c = 0

    def net_dth_err(d):
        u0 = -d / (1.0 - d / caps.cap_rev[0])
        u1 = d / (1.0 - d / caps.cap_fwd[1])
        w = torch.zeros((len(CHANNELS),) + tuple(y.th.shape), **_F64)
        w[0, 0, c] = float(u0[0, c] / caps.sigma[0][0, c])
        w[1, 0, c] = float(u1[0, c] / caps.sigma[1][0, c])
        out = apply_partition_chain(y, f, w, caps)
        lf_dth = float(((tp.xls - xl) / (cpm * f.pii) * d)[0, c])
        return float(out.th[0, c] - y.th[0, c]) - lf_dth, w

    d = 1.0e-5
    err_d, w_full = net_dth_err(d)
    err_d2, _ = net_dth_err(d / 2.0)
    assert err_d != 0.0                              # NOT exactly L_f
    ratio = err_d / err_d2
    assert 3.5 < ratio < 4.5, (err_d, err_d2, ratio)  # O(d^2) convergence
    # order dependence: deposit first (ch1), then evaporate (ch0) in a
    # second chain call — differs from the fixed-order single chain
    w_dep = torch.zeros_like(w_full)
    w_dep[1] = w_full[1]
    w_evap = torch.zeros_like(w_full)
    w_evap[0] = w_full[0]
    mid = apply_partition_chain(y, f, w_dep, caps)
    rev = apply_partition_chain(mid, f, w_evap, caps)
    fwd = apply_partition_chain(y, f, w_full, caps)
    assert float(fwd.th[0, c]) != float(rev.th[0, c])
    assert abs(float(fwd.th[0, c] - rev.th[0, c])) < 10.0 * abs(err_d)
