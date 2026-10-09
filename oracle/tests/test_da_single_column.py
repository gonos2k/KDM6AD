"""Bounded composition tests for the one-column normalized-dry adapter."""
from __future__ import annotations

import dataclasses
import math
from types import SimpleNamespace

import pytest
import torch

import kdm6.da_fulldomain as fd
import kdm6.da_single_column as single
from kdm6.da_cvt import cvt_apply
from kdm6.da_dual import default_param_prior, params_from_vtheta, run_dual_minimizer
from kdm6.da_fulldomain import make_fulldomain_obs_eval
from kdm6.da_window import WindowConfig, collect_window_trajectory, run_da_window
from kdm6.rttov_bridge import freeze_dry_air_density
from kdm6.state import Forcing, State

F64 = {"dtype": torch.float64}
CHANNELS = tuple(range(10, 17))


class InlinePool:
    """Keep the existing H callback boundary local for one synthetic profile."""
    def map(self, fn, jobs):
        return [fn(job) for job in jobs]


def _inputs(k=13):
    p = torch.linspace(100000.0, 50000.0, k, **F64).reshape(1, k)
    pii = (p / 100000.0).pow(0.2854)
    z = torch.zeros((1, k), **F64)
    qv = torch.logspace(-6.0, -3.0, k, **F64).flip(-1).reshape(1, k)
    xb = State(
        th=z + 290.0, qv=qv, qc=z, qr=z, qi=z, qs=z, qg=z,
        nccn=z + 1.0e8, nc=z + 1.0e7, ni=z + 1.0e6,
        nr=z + 1.0e4, bg=z)
    forcing = Forcing(rho=z + 1.0, pii=pii, p=p, delz=z + 500.0)
    xland = torch.tensor([2.0], **F64)
    p_lay = forcing.p.flip(-1)[0] / 100.0
    p_half = torch.linspace(450.0, 1050.0, k + 1, **F64)
    rho_d = freeze_dry_air_density(xb, forcing)
    rttov_cfg = dict(
        rho_d=rho_d,
        channels=CHANNELS,
        coef_id="synthetic-single-column",
        p_lay=p_lay,
        p_half=p_half,
        t_ref=torch.full((k,), 250.0, **F64),
        q_ref=torch.full((k,), 100.0, **F64),
        dry_number=True,
        ami_kma_bt=True,
        ncmin_land=0.0,
        ncmin_sea=0.0,
        t_blend_octaves=0.0,
        q_blend_octaves=0.0)
    clear_cfg = SimpleNamespace(
        input_cfg=SimpleNamespace(), t_blend_octaves=0.0,
        q_blend_octaves=0.0)
    window_config = WindowConfig(
        dt=20.0, xland=xland, ncmin_land=0.0, ncmin_sea=0.0,
        normalized_dry=True)
    y_bt = torch.full((1, 7), 279.2, **F64)
    y_rq = torch.zeros((1, 7), **F64)
    return (xb, (forcing, forcing), y_bt, y_rq, xland, clear_cfg, rttov_cfg,
            window_config)


def _install_synthetic_allsky(monkeypatch, *, trial_qc_flag=False,
                               background_qc_flag=False, inputs=None):
    xb, forcings, y_bt, _, _, _, _, _ = _inputs() if inputs is None else inputs
    forcing = forcings[0]
    ref_t = (xb.th * forcing.pii).mean(-1, keepdim=True)
    ref_qv = xb.qv.mean(-1, keepdim=True)
    observed = []

    def fake_sharded_allsky(state, fc, positions, target, mask, xland, cfg,
                            case_root, *, grad, **kwargs):
        assert positions.tolist() == [0]
        assert tuple(target.shape) == (1, 7)
        assert tuple(mask.shape) == (1, 7)
        assert tuple(cfg["channels"]) == CHANNELS
        observed.append(dict(grad=grad, qc=float(state.qc.sum())))

        # This synthetic H converts potential temperature to physical
        # temperature through Exner and retains a direct all-sky qc path.
        t_delta = (state.th * fc.pii).mean(-1, keepdim=True) - ref_t
        qv_delta = state.qv.mean(-1, keepdim=True) - ref_qv
        qc_mean = state.qc.mean(-1, keepdim=True)
        bt = (280.0 + t_delta + 0.05 * qv_delta + 20.0 * qc_mean).expand(1, 7)
        residual = bt - target
        j_t = fd._part_loss(bt[0], target[0], mask[0], 1.0)
        d_bt = torch.where(residual.abs() < 1.0, residual, residual.sign()) * mask
        dsum = d_bt.sum(-1, keepdim=True)
        k = state.th.shape[-1]
        adj = {field: torch.zeros_like(state.th) for field in State._fields}
        adj["th"] = dsum * fc.pii / k
        adj["qv"] = torch.ones_like(state.qv) * (dsum * (0.05 / k))
        adj["qc"] = torch.ones_like(state.qc) * (dsum * (20.0 / k))
        rq = torch.zeros_like(target)
        if grad and trial_qc_flag:
            rq[0, 0] = 32768.0
        if not grad and background_qc_flag:
            rq[0, 0] = 32768.0
        return {
            "bt": bt,
            "rq": rq,
            "j": float(j_t.detach()),
            "adj": tuple(adj[field] for field in State._fields),
        }

    monkeypatch.setattr(fd, "sharded_allsky", fake_sharded_allsky)
    return observed


def _run(monkeypatch, tmp_path, *, inputs=None, **kwargs):
    inputs = _inputs() if inputs is None else inputs
    xb, forcings, y_bt, y_rq, xland, clear_cfg, rttov_cfg, cfg = inputs
    return single.run_single_column_analysis(
        xb, forcings, y_bt, y_rq, xland, clear_cfg, rttov_cfg,
        str(tmp_path), window_config=cfg, obs_time=2,
        pool=InlinePool(), n_workers=1, max_iter=1, **kwargs)


def test_clear_background_uses_allsky_dual_path_and_preserves_full_window_pullback(
        monkeypatch, tmp_path):
    operator_calls = _install_synthetic_allsky(monkeypatch)
    monkeypatch.setattr(
        fd, "batched_clear_bt",
        lambda *a, **kw: pytest.fail("empty clear partition must not call clear H"))
    analysis = _run(monkeypatch, tmp_path)

    meta = analysis["metadata"]
    result = analysis["result"]
    assert meta["physical_background_cloudy_at_obs_time"] is False
    assert meta["operator_routing"] == {"allsky_pos": [0], "clear_pos": []}
    assert meta["n_valid_background"] == 7
    assert meta["require_frozen_quality"] is True
    assert meta["parameter_prior"]["active"] == []
    assert meta["parameter_prior"]["sigma_log"] == [0.0] * 4
    assert meta["partition_control"] is False and meta["pseudo_rh"] is False
    assert meta["window_config_projection"] == ["th", "qv"]
    assert result.cvt["n_controlled"] == {
        **{field: 0 for field in State._fields}, "th": 13, "qv": 12}
    assert torch.equal(analysis["b_sigma"].th,
                       torch.full_like(_inputs()[0].th, 0.8))
    assert bool((analysis["b_sigma"].qv[0, :12] == 0.08).all())
    assert analysis["b_sigma"].qv[0, 12] == 0.0
    assert all(bool((getattr(analysis["b_sigma"], f) == 0.0).all())
               for f in State._fields if f not in ("th", "qv"))
    assert result.jb_final == pytest.approx(0.5 * float(result.v_state.square().sum()))
    assert result.jtheta_final == 0.0
    assert float(result.v_state.norm()) > 0.0
    assert result.jb_final > 0.0
    assert result.jobs_final > 0.0
    assert result.j_trace[-1]["total"] == pytest.approx(
        result.jb_final + result.jtheta_final + result.jobs_final,
        rel=1.0e-12, abs=1.0e-14)
    xb = _inputs()[0]
    decoded, _ = cvt_apply(xb, analysis["b_sigma"], result.v_state,
                           analysis["cvt"])
    th_control = result.v_state[State._fields.index("th")]
    qv_control = result.v_state[State._fields.index("qv")]
    assert torch.allclose(decoded.th - xb.th, 0.8 * th_control)
    assert torch.allclose(decoded.qv, xb.qv * torch.exp(0.08 * qv_control))
    assert meta["n_successful_obs_callback_results"] == sum(
        call["grad"] for call in operator_calls)
    assert meta["n_window_evals"] == result.n_window_evals
    assert meta["n_audit_evals"] == result.n_audit_evals
    assert len(operator_calls) == 1 + meta["n_successful_obs_callback_results"]  # probe + successful trials

    # A cloudy trial state changes Jo and has a direct qc adjoint even though
    # the slot background is physically clear; only all-sky H is called.
    slot = analysis["background_slot_state"]
    trial = slot._replace(qc=slot.qc + 0.002)
    trial_result = analysis["obs_eval"](2, trial)
    assert trial_result.n_valid == 7
    assert float(trial_result.j) > 0.0
    assert float(trial_result.adj.qc.norm()) > 0.0
    assert float(trial_result.adj.th.norm()) > 0.0
    assert operator_calls[-1]["grad"] is True

    # th is an additive potential-temperature control; the synthetic H
    # derivative includes the physical-temperature Exner factor.
    trial_t = slot._replace(th=slot.th + 0.1, qc=slot.qc + 0.002)
    expner = _inputs()[1][0].pii
    xb = _inputs()[0]
    base_t = (xb.th * expner).mean(-1, keepdim=True)
    trial_t_mean = (trial_t.th * expner).mean(-1, keepdim=True)
    trial_qv_mean = trial_t.qv.mean(-1, keepdim=True)
    base_qv_mean = xb.qv.mean(-1, keepdim=True)
    residual = 0.8 + float((trial_t_mean - base_t).mean()) \
        + 0.05 * float((trial_qv_mean - base_qv_mean).mean()) \
        + 20.0 * float(trial_t.qc.mean())
    expected_j = 0.5 * 7.0 * residual * residual
    t_result = analysis["obs_eval"](2, trial_t)
    assert float(t_result.j) == pytest.approx(expected_j, rel=1.0e-12, abs=1.0e-14)
    expected_th_adj = 7.0 * residual * expner / expner.shape[-1]
    assert torch.allclose(t_result.adj.th, expected_th_adj, rtol=1.0e-12, atol=1.0e-14)
    assert analysis["obs_eval"].normalized_dry is True
    assert analysis["obs_eval"].require_frozen_quality is True


def test_background_six_of_seven_rejects_before_dual_minimization(
        monkeypatch, tmp_path):
    _install_synthetic_allsky(monkeypatch, background_qc_flag=True)
    monkeypatch.setattr(
        single, "run_dual_minimizer",
        lambda *a, **kw: pytest.fail("minimizer reached with only six background channels"))

    with pytest.raises(ValueError, match="n_valid=6, required=7"):
        _run(monkeypatch, tmp_path)


def test_frozen_support_trial_quality_loss_aborts_real_dual_call(
        monkeypatch, tmp_path):
    _install_synthetic_allsky(monkeypatch, trial_qc_flag=True)

    with pytest.raises(ValueError, match="flags a frozen-support"):
        _run(monkeypatch, tmp_path)


def test_obs_time_zero_rejected_for_tq_through_m_study(monkeypatch, tmp_path):
    _install_synthetic_allsky(monkeypatch)
    data = _inputs()
    xb, forcings, y_bt, y_rq, xland, clear_cfg, rttov_cfg, cfg = data
    with pytest.raises(ValueError, match="obs_time must be in \\[1,"):
        single.run_single_column_analysis(
            xb, forcings, y_bt, y_rq, xland, clear_cfg, rttov_cfg,
            str(tmp_path), window_config=cfg, obs_time=0, pool=InlinePool())


def test_adapter_preserves_synthetic_39_level_native_shape_and_51_cvts(
        monkeypatch, tmp_path):
    data = _inputs(k=39)
    calls = _install_synthetic_allsky(monkeypatch, inputs=data)
    analysis = _run(monkeypatch, tmp_path, inputs=data)

    assert analysis["metadata"]["native_state_shape"] == [1, 39]
    counts = analysis["result"].cvt["n_controlled"]
    assert counts["th"] == 39 and counts["qv"] == 12
    assert sum(counts.values()) == 51
    assert calls[0]["grad"] is False  # background support probe
    assert any(item["grad"] is True for item in calls[1:])


def test_cvt_to_real_window_to_synthetic_h_total_cost_directional_difference(
        monkeypatch, tmp_path):
    """One bounded T/Q direction checks Jb+Jo through actual KDM M and CVT."""
    _install_synthetic_allsky(monkeypatch)
    analysis = _run(monkeypatch, tmp_path)
    xb, forcings, *_rest, xland, _clear_cfg, _rttov_cfg, cfg = _inputs()
    result = analysis["result"]
    v0 = torch.zeros_like(result.v_state)
    direction = torch.zeros_like(v0)
    th_i, qv_i = State._fields.index("th"), State._fields.index("qv")
    v0[th_i, 0, 0] = 0.03
    v0[qv_i, 0, 2] = -0.02
    direction[th_i, 0, 0] = 0.6
    direction[qv_i, 0, 2] = -0.8
    prior = analysis["param_prior"]
    cfg_m = dataclasses.replace(
        cfg, xland=xland, active_fields=("th", "qv"), normalized_dry=True,
        params=params_from_vtheta(prior, torch.zeros(4, **F64), live=False))

    x0, jac_x = cvt_apply(xb, analysis["b_sigma"], v0, analysis["cvt"])
    def obs_adjoint(t, state_t):
        if t != 2:
            return None
        return analysis["obs_eval"](t, state_t).adj

    window = run_da_window(x0, forcings, obs_adjoint, cfg_m)
    adj_stack = torch.stack([getattr(window.adj_x0, f) for f in State._fields])
    grad_v = v0 + jac_x * adj_stack
    ad_directional = float((grad_v * direction).sum())

    def total_cost(v):
        state0, _ = cvt_apply(xb, analysis["b_sigma"], v, analysis["cvt"])
        slot = collect_window_trajectory(state0, forcings, cfg_m, {2})[2]
        jo = float(analysis["obs_eval"](2, slot).j)
        return 0.5 * float(v.square().sum()) + jo

    h = 1.0e-4
    fd_directional = (total_cost(v0 + h * direction)
                       - total_cost(v0 - h * direction)) / (2.0 * h)
    assert math.isfinite(ad_directional) and abs(ad_directional) > 1.0e-5
    assert fd_directional == pytest.approx(
        ad_directional, rel=2.0e-8, abs=1.0e-9)


def test_adapter_rejects_mismatched_h_and_m_ncmin_before_window(monkeypatch, tmp_path):
    _install_synthetic_allsky(monkeypatch)
    xb, forcings, y_bt, y_rq, xland, clear_cfg, rttov_cfg, cfg = _inputs()
    rttov_cfg["ncmin_land"] = 10.0
    monkeypatch.setattr(
        single, "collect_window_trajectory",
        lambda *a, **kw: pytest.fail("mismatched H/M number minimum reached M"))
    with pytest.raises(ValueError, match="ncmin_land must exactly match"):
        single.run_single_column_analysis(
            xb, forcings, y_bt, y_rq, xland, clear_cfg, rttov_cfg,
            str(tmp_path), window_config=cfg, obs_time=1, pool=InlinePool())


def test_adapter_rejects_explicit_xland_mismatch(monkeypatch, tmp_path):
    _install_synthetic_allsky(monkeypatch)
    xb, forcings, y_bt, y_rq, xland, clear_cfg, rttov_cfg, cfg = _inputs()
    cfg = dataclasses.replace(cfg, xland=torch.tensor([1.0], **F64))
    monkeypatch.setattr(
        single, "collect_window_trajectory",
        lambda *a, **kw: pytest.fail("mismatched xland reached M"))
    with pytest.raises(ValueError, match="match window_config.xland"):
        single.run_single_column_analysis(
            xb, forcings, y_bt, y_rq, xland, clear_cfg, rttov_cfg,
            str(tmp_path), window_config=cfg, obs_time=1, pool=InlinePool())


def test_existing_clear_factory_keeps_latent_temperature_h_of_m_response(monkeypatch):
    """The new forced-all-sky adapter does not invalidate the prior clear H path."""
    xb, forcings, y_bt, y_rq, xland, clear_cfg, rttov_cfg, cfg = _inputs()
    y_bt = torch.full((1, 7), 279.2, **F64)
    forcing = forcings[0]
    cfg = dataclasses.replace(cfg, active_fields=("th", "qv"))
    prior = default_param_prior(0.2)
    assert torch.equal(prior.sigma_log, torch.full((4,), 0.2, **F64))
    from kdm6.da_dual import params_from_vtheta
    cfg = dataclasses.replace(
        cfg, params=params_from_vtheta(prior, torch.zeros(4, **F64), live=False))
    from kdm6.da_window import collect_window_trajectory
    slot = collect_window_trajectory(xb, forcings, cfg, {2})[2]
    t_ref = (xb.th * forcing.pii).mean(-1, keepdim=True)
    q_ref = xb.qv.mean(-1, keepdim=True)
    observed = []

    def fake_clear(state, fc, _cfg):
        leaves = State(*(getattr(state, f).detach().clone().requires_grad_(
            f in ("th", "qv")) for f in State._fields))
        t_delta = (leaves.th * fc.pii).mean(-1, keepdim=True) - t_ref
        q_delta = leaves.qv.mean(-1, keepdim=True) - q_ref
        bt = (280.0 + t_delta + 2.0 * q_delta).expand(1, 7)
        observed.append(float(bt.detach().mean()))
        return bt, torch.zeros_like(bt), leaves

    monkeypatch.setattr(fd, "batched_clear_bt", fake_clear)
    allsky_sizes = []
    def empty_allsky(state, _fc, positions, _target, _mask, *_args, **_kwargs):
        allsky_sizes.append(int(positions.numel()))
        assert positions.numel() == 0
        empty = torch.empty((0, 7), **F64)
        return {"bt": empty, "rq": empty, "j": 0.0,
                "adj": tuple(torch.empty((0, state.th.shape[-1]), **F64)
                             for _ in State._fields)}
    monkeypatch.setattr(fd, "sharded_allsky", empty_allsky)
    obs = make_fulldomain_obs_eval(
        xb, forcing, y_bt, y_rq, xland,
        torch.empty(0, dtype=torch.int64), torch.tensor([0]),
        clear_cfg, rttov_cfg, "/tmp/single-column-clear-compat",
        n_workers=1, pool=InlinePool(), obs_time=2, huber_delta=1.0,
        x_slot_bg=slot, channel_gate=torch.ones((1, 7), **F64),
        require_frozen_quality=True)
    obs.normalized_dry = True
    result_at_slot = obs(2, slot)
    expected_bt = (280.0
                   + float(((slot.th * forcing.pii).mean() - t_ref).mean())
                   + 2.0 * float((slot.qv.mean() - q_ref).mean()))
    expected_residual = expected_bt - 279.2
    assert result_at_slot.n_valid == 7
    assert allsky_sizes and set(allsky_sizes) == {0}
    assert abs(expected_residual) < 1.0
    assert float(result_at_slot.j) == pytest.approx(
        0.5 * 7.0 * expected_residual ** 2, rel=1.0e-12, abs=1.0e-14)
    assert float(result_at_slot.adj.th.norm()) > 0.0
    assert float(result_at_slot.adj.qv.norm()) > 0.0
    assert obs.connected_fields == ("th", "qv")

    cvt, b_sigma = single.make_default_cvt(
        xb, th_sigma=0.8, qv_sigma=0.08, qv_levels=12,
        sigma_overrides={f: 0.0 for f in single._NON_TQ_FIELDS})
    dual_result = run_dual_minimizer(
        xb, forcings, obs, cfg, b_sigma, prior, max_iter=1, cvt=cvt)
    assert dual_result.jobs_final > 0.0
    assert dual_result.n_window_evals >= 1
    assert observed  # the clear H callback remains active through the window.


@pytest.mark.parametrize("field, value, message", [
    ("normalized_dry", False, "normalized_dry=True"),
    ("params", object(), "params must be None"),
    ("eta", (), "does not accept eta"),
])
def test_adapter_rejects_misleading_model_config_before_operator(
        monkeypatch, tmp_path, field, value, message):
    _install_synthetic_allsky(monkeypatch)
    xb, forcings, y_bt, y_rq, xland, clear_cfg, rttov_cfg, cfg = _inputs()
    cfg = dataclasses.replace(cfg, **{field: value})
    with pytest.raises(ValueError, match=message):
        single.run_single_column_analysis(
            xb, forcings, y_bt, y_rq, xland, clear_cfg, rttov_cfg,
            str(tmp_path), window_config=cfg, obs_time=1, pool=InlinePool())
