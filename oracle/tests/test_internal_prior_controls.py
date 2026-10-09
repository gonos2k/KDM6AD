"""Narrow normalized-mode pass-through for existing state-prior controls."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
import torch

import kdm6.da_fulldomain as fd
import kdm6.da_dual as dual
import kdm6.da_window as window
import kdm6.obs.rttov_case_writer as case_writer
from kdm6.da_dual import ObsEvalResult
from kdm6.state import Forcing, State, zeros_like_state

F64 = {"dtype": torch.float64}


def _inputs():
    z = torch.zeros((1, 2), **F64)
    state = State(*(z.clone() for _ in State._fields))._replace(
        th=z + 290.0, qv=z + 0.01, qc=z + 2.0e-4,
        nc=z + 1.0e8, nccn=z + 1.0e9)
    forcing = Forcing(
        rho=z + 1.0, pii=z + 0.95,
        p=torch.tensor([[90000.0, 70000.0]], **F64), delz=z + 500.0)
    frame = SimpleNamespace(
        state=state, forcing=forcing, xland=torch.tensor([2.0], **F64),
        meta=dict(nx=1, ny=1, valid_time_utc="2025-07-19_00:00:00"))
    observations = SimpleNamespace(
        bt=torch.full((1, 16), 280.0, **F64),
        obs_quality=torch.zeros((1, 16), **F64),
        valid_time_utc=None, bias=None, channel_gate=None)
    grids = dict(
        p_lay=[700.0, 900.0], p_half=[600.0, 800.0, 1000.0],
        t_ref=[250.0, 290.0], q_ref=[100.0, 10000.0],
        cloud_fixture_case_dir="native-cloud")
    return frame, observations, grids


def _install_lightweight_observation_boundary(monkeypatch, captured):
    import multiprocessing as mp

    monkeypatch.setattr(case_writer, "_validate_geometry", lambda *a, **kw: None)
    monkeypatch.setattr(case_writer, "_validate_surface", lambda *a, **kw: None)

    def make_runner(*args, **kwargs):
        def runner(_):
            raise AssertionError("the synthetic evaluator must not call RTTOV")
        runner.bt_coordinate = "kma_v3_0"
        return runner

    monkeypatch.setattr(case_writer, "make_live_run_k", make_runner)
    # Keep the slot-background selection probe fixed. The real dual minimizer
    # and its normalized one-step window still run in this integration test.
    monkeypatch.setattr(window, "collect_window_trajectory",
                        lambda x, forcings, cfg, times: {t: x for t in times})

    class _Pool:
        def close(self):
            pass

        def join(self):
            pass

    monkeypatch.setattr(
        mp, "get_context",
        lambda _: SimpleNamespace(Pool=lambda _n: _Pool()))
    original_cvt = fd.make_default_cvt

    def capture_cvt(xb, **kwargs):
        captured["builder_kwargs"].append(deepcopy(kwargs))
        return original_cvt(xb, **kwargs)

    monkeypatch.setattr(fd, "make_default_cvt", capture_cvt)
    original_minimize = dual.run_dual_minimizer

    def capture_minimizer(xb, forcings, obs_eval, cfg, b_sigma, prior, **kwargs):
        captured["minimizer_sigma"].append(b_sigma.nc.detach().clone())
        return original_minimize(xb, forcings, obs_eval, cfg, b_sigma, prior,
                                 **kwargs)

    monkeypatch.setattr(fd, "run_dual_minimizer", capture_minimizer)

    def make_eval(xb, _forcing, y_bt, _y_rq, _xland, cloudy, clear,
                  _clear_cfg, _rttov_cfg, _case_root, **kwargs):
        mask = torch.ones_like(y_bt)
        require_frozen_quality = kwargs["require_frozen_quality"]
        captured.setdefault("require_frozen_quality", []).append(
            require_frozen_quality)

        def evaluate(t, x_t):
            if t != 1:
                return None
            residual = x_t.nc / xb.nc - 1.01
            adj = zeros_like_state(x_t)._replace(nc=residual / xb.nc)
            return ObsEvalResult(j=0.5 * residual.square().sum(), adj=adj,
                                 n_valid=9, signature="fixed-synthetic-slot")

        evaluate.mask = mask
        evaluate.require_frozen_quality = require_frozen_quality
        evaluate.connected_fields = ("nc",)
        evaluate.connected_fields_by_position = {0: ("nc",)}
        evaluate.connected_fields_by_partition = {
            "allsky": ("nc",), "clear": (),
            "allsky_pos": cloudy.clone(), "clear_pos": clear.clone()}
        return evaluate

    monkeypatch.setattr(fd, "make_fulldomain_obs_eval", make_eval)
    monkeypatch.setattr(
        fd, "sharded_allsky",
        lambda x, forcing, pos, y, mask, *_a, **_kw: {
            "bt": torch.full((int(pos.numel()), y.shape[1]), 280.0, **F64),
            "rq": torch.zeros((int(pos.numel()), y.shape[1]), **F64),
            "j": 0.0,
            "adj": torch.zeros((len(State._fields), int(pos.numel()),
                                x.th.shape[-1]), **F64),
        })


def _run(frame, observations, grids, **options):
    return fd.run_fulldomain_analysis(
        frame, observations, grids, "unused", boundary=0, n_workers=1,
        max_iter=1, channels=tuple(range(8, 17)), obs_time=1, dt=20.0,
        obs_offset_s=20.0, time_tolerance_s=1.0, huber_delta=1.0,
        qv_levels=2, normalized_dry=True,
        observation_coordinate="kma_v3_0", **options)


def test_state_sigma_overrides_reach_real_dual_minimizer_and_default_is_unchanged(
        monkeypatch):
    frame, observations, grids = _inputs()
    captured = {"builder_kwargs": [], "minimizer_sigma": []}
    _install_lightweight_observation_boundary(monkeypatch, captured)

    legacy = _run(frame, observations, grids)
    assert captured["builder_kwargs"][0] == {
        "qv_levels": 2, "sigma_overrides": None}
    assert "background_sigma_overrides" not in legacy
    assert legacy["require_frozen_quality"] is True
    assert legacy["cvt"]["n_controlled"]["nc"] == 2

    nc_pinned = _run(
        frame, observations, grids,
        background_sigma_overrides={"nc": 0.0},
        background_error_source="predeclared NC-off comparison")
    assert captured["builder_kwargs"][1] == {
        "qv_levels": 2, "sigma_overrides": {"nc": 0.0}}
    assert torch.equal(captured["minimizer_sigma"][1], torch.zeros((1, 2), **F64))
    assert nc_pinned["cvt"]["n_controlled"]["nc"] == 0
    assert nc_pinned["background_control_counts"]["nc"] == 0
    assert nc_pinned["require_frozen_quality"] is True

    nc_enabled = _run(
        frame, observations, grids,
        background_sigma_overrides={"nc": 0.15},
        background_error_source="predeclared NC-enabled comparison")
    assert captured["builder_kwargs"][2] == {
        "qv_levels": 2, "sigma_overrides": {"nc": 0.15}}
    assert bool((captured["minimizer_sigma"][2] > 0).all())
    assert nc_enabled["cvt"]["n_controlled"]["nc"] == 2
    assert nc_enabled["background_control_counts"]["nc"] == 2
    assert nc_enabled["background_sigma_overrides"] == {"nc": 0.15}
    assert nc_enabled["background_error_source"] == "predeclared NC-enabled comparison"
    assert nc_enabled["require_frozen_quality"] is True
    assert captured["require_frozen_quality"] == [True, True, True]
    assert nc_enabled["prior_is_calibrated"] is False
    assert "four warm theta priors unchanged" in nc_enabled["background_prior_scope"]
    assert nc_enabled["theta_b"] == nc_pinned["theta_b"] == legacy["theta_b"]


@pytest.mark.parametrize(
    "options, conserving, match",
    [
        ({"background_sigma_overrides": {"not_a_state": 0.1},
          "background_error_source": "synthetic"}, False, "unknown"),
        ({"background_sigma_overrides": {"nc": True},
          "background_error_source": "synthetic"}, False, "real finite"),
        ({"background_sigma_overrides": {"nc": -0.1},
          "background_error_source": "synthetic"}, False, "real finite"),
        ({"background_sigma_overrides": {"nc": 10**400},
          "background_error_source": "synthetic"}, False, "real finite"),
        ({"background_sigma_overrides": {"nc": float("nan")},
          "background_error_source": "synthetic"}, False, "real finite"),
        ({"background_sigma_overrides": {"nc": 0.1}}, False, "source label"),
        *[({"background_sigma_overrides": {field: 0.1},
            "background_error_source": "synthetic"}, True,
           "forces mass hydrometeor/volume")
          for field in ("qc", "qr", "qi", "qs", "qg", "bg")],
    ])
def test_bad_state_sigma_overrides_fail_before_membership_or_runner(
        monkeypatch, options, conserving, match):
    frame, observations, grids = _inputs()
    monkeypatch.setattr(fd, "select_membership",
                        lambda *a, **kw: pytest.fail("membership ran before validation"))
    monkeypatch.setattr(case_writer, "make_live_run_k",
                        lambda *a, **kw: pytest.fail("runner built before validation"))
    with pytest.raises(ValueError, match=match):
        _run(frame, observations, grids, conserving=conserving, **options)


def test_state_sigma_overrides_are_restricted_to_normalized_mode():
    frame, observations, grids = _inputs()
    with pytest.raises(ValueError, match="require normalized_dry"):
        fd.run_fulldomain_analysis(
            frame, observations, grids, "unused",
            background_sigma_overrides={"nc": 0.1},
            background_error_source="synthetic")
