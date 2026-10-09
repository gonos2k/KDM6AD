"""Narrow normalized-dry single-column all-sky dual-analysis adapter.

This module composes the existing full-domain frozen-support observation
factory, diagonal state CVT builder, fixed default parameter prior, and dual
minimizer for one caller-supplied native column. It does not acquire data,
build an executable, create a worker pool, or add a solver/physics path. The
caller-configured H callback may launch RTTOV when the real worker is used.
"""
from __future__ import annotations

import dataclasses
import math
from typing import Sequence

import torch

from .da_cvt import make_default_cvt
from .da_dual import default_param_prior, params_from_vtheta, run_dual_minimizer
from .da_fulldomain import QTOT_MIN, make_fulldomain_obs_eval
from .da_window import WindowConfig, collect_window_trajectory
from .obs.rttov_runner import DEFAULT_RTTOV_TIMEOUT
from .state import Forcing, State

_F64 = {"dtype": torch.float64}
_CHANNELS = tuple(range(10, 17))
_ACTIVE_FIELDS = ("th", "qv")
_NON_TQ_FIELDS = tuple(f for f in State._fields if f not in _ACTIVE_FIELDS)


def _one_column_state(state: State, *, name: str) -> tuple[int, int]:
    shape = None
    for field in State._fields:
        value = getattr(state, field)
        if not isinstance(value, torch.Tensor) or value.ndim != 2:
            raise ValueError(f"{name}.{field} must be a native [1,K] tensor")
        if value.shape[0] != 1:
            raise ValueError(f"{name}.{field} must contain exactly one column")
        if shape is None:
            shape = tuple(value.shape)
        elif tuple(value.shape) != shape:
            raise ValueError(f"{name} fields must share one native [1,K] shape")
    assert shape is not None
    return shape


def _one_column_forcing(forcing: Forcing, *, name: str, expected_shape):
    for field in Forcing._fields:
        value = getattr(forcing, field)
        if not isinstance(value, torch.Tensor) or tuple(value.shape) != expected_shape:
            raise ValueError(f"{name}.{field} must preserve native shape {expected_shape}")


def _callback_with_counter(obs_eval, counter):
    """Count callback results while preserving the evaluator's audit metadata."""
    def counted(t: int, state_t: State):
        result = obs_eval(t, state_t)
        if result is not None:
            counter["results"] += 1
        return result

    counted.__dict__.update(vars(obs_eval))
    return counted


def run_single_column_analysis(
    xb: State,
    forcings: Sequence[Forcing],
    y_bt,
    y_rq,
    xland,
    clear_cfg,
    rttov_cfg: dict,
    case_root: str,
    *,
    window_config: WindowConfig,
    obs_time: int,
    pool,
    n_workers: int = 1,
    max_iter: int = 3,
    rttov_timeout: float = DEFAULT_RTTOV_TIMEOUT,
) -> dict:
    """Run the bounded one-column T/qv dual analysis on an existing native column.

    ``forcings`` remains the full ordered model window used by ``run_da_window``.
    The H forcing is selected from that sequence at ``obs_time`` (or its final
    interval forcing when ``obs_time == len(forcings)``). The observation is
    always routed through all-sky H at position zero, including when the
    physical background is clear; the slot-background cloud classification is
    returned as metadata only.

    The callback requires all seven AMI 10..16 channels to be supported by the
    background mask. It raises on any loss of that fixed support during a
    trial. The existing minimizer owns the zero-initialized control and
    full-window pullback; ``active_fields`` projects only the initial-state
    adjoint to th/qv after the complete M transpose.
    """
    if not isinstance(window_config, WindowConfig):
        raise TypeError("window_config must be a WindowConfig")
    if window_config.normalized_dry is not True:
        raise ValueError("single-column research adapter requires normalized_dry=True")
    if window_config.params is not None:
        raise ValueError("window_config.params must be None; the fixed default parameter prior owns theta_b")
    if window_config.eta is not None or window_config.eta_pre is not None:
        raise ValueError("single-column adapter does not accept eta or eta_pre weak-constraint increments")
    if isinstance(obs_time, bool) or not isinstance(obs_time, int):
        raise TypeError("obs_time must be a plain integer window index")
    forcings = tuple(forcings)
    if not forcings:
        raise ValueError("single-column analysis requires a nonempty full forcing window")
    if not 1 <= obs_time <= len(forcings):
        raise ValueError(
            f"obs_time must be in [1, {len(forcings)}] for the T/Q-through-M study")
    if isinstance(n_workers, bool) or not isinstance(n_workers, int) or n_workers < 1:
        raise ValueError("n_workers must be a positive integer")
    if isinstance(max_iter, bool) or not isinstance(max_iter, int) or max_iter < 1:
        raise ValueError("max_iter must be a positive integer")
    if pool is None:
        raise ValueError("pool must be passed explicitly; this adapter does not create workers")
    if not isinstance(rttov_cfg, dict):
        raise TypeError("rttov_cfg must be the caller-supplied configuration dictionary")

    shape = _one_column_state(xb, name="xb")
    for i, forcing in enumerate(forcings):
        _one_column_forcing(forcing, name=f"forcings[{i}]", expected_shape=shape)
    forcing_h = forcings[min(obs_time, len(forcings) - 1)]

    xland_f = torch.as_tensor(xland, dtype=torch.float64).detach().clone()
    if (tuple(xland_f.shape) != (1,) or not bool(torch.isfinite(xland_f).all())
            or not bool(((xland_f == 1.0) | (xland_f == 2.0)).all())):
        raise ValueError("xland must be a finite one-element land/sea code [1] or [2]")
    if window_config.xland is not None:
        config_xland = torch.as_tensor(window_config.xland, dtype=torch.float64)
        if tuple(config_xland.shape) != (1,) or not torch.equal(config_xland, xland_f):
            raise ValueError("explicit xland must match window_config.xland when it is set")

    y_bt = torch.as_tensor(y_bt, dtype=torch.float64)
    y_rq = torch.as_tensor(y_rq, dtype=torch.float64)
    expected_obs_shape = (1, len(_CHANNELS))
    if tuple(y_bt.shape) != expected_obs_shape:
        raise ValueError(f"y_bt must have exact shape {expected_obs_shape} for AMI 10..16")
    if tuple(y_rq.shape) != expected_obs_shape:
        raise ValueError(f"y_rq must have exact shape {expected_obs_shape} for AMI 10..16")
    if not bool(torch.isfinite(y_bt).all()):
        raise ValueError("all seven fixed-support y_bt values must be finite")
    if not bool(torch.isfinite(y_rq).all()) or bool((y_rq < 0.0).any()):
        raise ValueError("y_rq must contain finite non-negative quality flags")
    if tuple(rttov_cfg.get("channels", ())) != _CHANNELS:
        raise ValueError("rttov_cfg.channels must be exactly AMI 10..16 in order")
    if rttov_cfg.get("dry_number") is not True:
        raise ValueError("normalized-dry single-column analysis requires dry_number=True")
    if rttov_cfg.get("ami_kma_bt") is not True:
        raise ValueError("normalized-dry single-column analysis requires ami_kma_bt=True")

    for name, blend_default in (("t_blend_octaves", 1.0),
                                ("q_blend_octaves", 4.0)):
        h_blend = rttov_cfg.get(name, blend_default)
        clear_blend = getattr(clear_cfg, name, blend_default)
        if (isinstance(h_blend, bool) or not isinstance(h_blend, (int, float))
                or float(h_blend) != 0.0 or float(clear_blend) != 0.0):
            raise ValueError(
                f"normalized-dry native profiles require {name}=0 in both H configurations")
    for name in ("ncmin_land", "ncmin_sea"):
        h_value = rttov_cfg.get(name, 0.0)
        m_value = getattr(window_config, name)
        if (isinstance(h_value, bool) or not isinstance(h_value, (int, float))
                or not math.isfinite(float(h_value))
                or float(h_value) != float(m_value)):
            raise ValueError(
                f"rttov_cfg.{name} must exactly match WindowConfig.{name}")

    # Match the native model centers to the retained suffix of the optical grid,
    # as in the public full-domain normalized-dry path. No profile remapping is
    # performed here.
    p_lay = torch.as_tensor(rttov_cfg.get("p_lay"), dtype=torch.float64)
    native_p = forcing_h.p.flip(-1) / 100.0
    nlev = shape[1]
    if (p_lay.ndim != 1 or p_lay.numel() < nlev
            or not torch.equal(native_p, p_lay[-nlev:].expand_as(native_p))):
        raise ValueError(
            "rttov_cfg.p_lay must retain every native center pressure in its final K entries")
    p_half = torch.as_tensor(rttov_cfg.get("p_half"), dtype=torch.float64)
    if p_half.ndim != 1 or p_half.numel() != p_lay.numel() + 1:
        raise ValueError("rttov_cfg.p_half must have exactly one more interface than its p_lay grid")
    for name in ("t_ref", "q_ref"):
        reference = torch.as_tensor(rttov_cfg.get(name), dtype=torch.float64)
        if reference.ndim != 1 or reference.shape != p_lay.shape:
            raise ValueError(f"rttov_cfg.{name} must match the caller's p_lay grid")

    # Preserve the full model-window config; only replace static xland and the
    # initial-state control projection. Weak increments and custom theta_b were
    # rejected above so none can be silently discarded by the fixed dual setup.
    model_config = dataclasses.replace(
        window_config, xland=xland_f, active_fields=_ACTIVE_FIELDS,
        normalized_dry=True)
    param_prior = default_param_prior(active=())
    theta_b = params_from_vtheta(
        param_prior, torch.zeros(4, **_F64), live=False)
    model_config = dataclasses.replace(model_config, params=theta_b)

    # Freeze the physical background classification at the actual observation
    # slot. It is reported, but never changes the all-sky operator routing.
    slot_background = collect_window_trajectory(
        xb, forcings, model_config, {obs_time})[obs_time]
    slot_condensate = (slot_background.qc + slot_background.qi
                       + slot_background.qs).sum(-1)
    physical_background_cloudy = bool((slot_condensate > QTOT_MIN)[0])

    cvt, b_sigma = make_default_cvt(
        xb, th_sigma=0.8, qv_sigma=0.08, qv_levels=12,
        sigma_overrides={field: 0.0 for field in _NON_TQ_FIELDS})
    if any(bool((getattr(b_sigma, field) != 0.0).any()) for field in _NON_TQ_FIELDS):
        raise RuntimeError("non-T/Q state controls must be exactly zero")

    allsky_pos = torch.tensor([0], dtype=torch.int64)
    clear_pos = torch.empty(0, dtype=torch.int64)
    channel_gate = torch.ones(expected_obs_shape, dtype=torch.float64)
    obs_eval = make_fulldomain_obs_eval(
        xb, forcing_h, y_bt, y_rq, xland_f, allsky_pos, clear_pos,
        clear_cfg, rttov_cfg, case_root, n_workers=n_workers, pool=pool,
        obs_time=obs_time, huber_delta=1.0,
        x_slot_bg=slot_background, pseudo=None, rttov_timeout=rttov_timeout,
        channel_gate=channel_gate, require_frozen_quality=True)
    obs_eval.normalized_dry = True

    background_mask = obs_eval.mask.detach().clone()
    if tuple(background_mask.shape) != expected_obs_shape:
        raise ValueError(
            f"frozen background support shape {tuple(background_mask.shape)} "
            f"!= required {expected_obs_shape}")
    n_valid_background = int(background_mask.sum())
    if n_valid_background != len(_CHANNELS):
        raise ValueError(
            "the declared seven-channel support is incomplete at the background: "
            f"n_valid={n_valid_background}, required=7; do not shrink S")

    callback_counter = {"results": 0}
    counted_obs_eval = _callback_with_counter(obs_eval, callback_counter)
    result = run_dual_minimizer(
        xb, forcings, counted_obs_eval, model_config, b_sigma, param_prior,
        max_iter=max_iter, cvt=cvt)

    active_counts = {
        field: int((getattr(b_sigma, field) > 0.0).sum())
        for field in State._fields
    }
    metadata = {
        "normalized_dry": True,
        "obs_time": obs_time,
        "h_forcing_index": min(obs_time, len(forcings) - 1),
        "n_forcings": len(forcings),
        "native_state_shape": list(shape),
        "physical_background_cloudy_at_obs_time": physical_background_cloudy,
        "physical_background_condensate_unweighted_level_sum_kgkg":
            float(slot_condensate[0]),
        "physical_background_classifier": {
            "definition": "sum over native levels of qc+qi+qs exceeds QTOT_MIN",
            "threshold": QTOT_MIN,
        },
        "caller_pressure_grids": {
            "native_center_suffix_matches_forcing": True,
            "p_half_passed_unchanged": True,
            "p_half_native_interface_identity_independently_verified": False,
        },
        "operator_routing": {"allsky_pos": [0], "clear_pos": []},
        "operator_routing_policy": "all-sky always; physical background class is metadata only",
        "channels_ami_physical_ids": list(_CHANNELS),
        "background_mask": background_mask.tolist(),
        "n_valid_background": n_valid_background,
        "require_frozen_quality": True,
        "huber_delta_K": 1.0,
        "observation_sigma_K": 1.0,
        "observation_bias_K": 0.0,
        "state_prior": {
            "th_sigma_K": 0.8,
            "qv_sigma_log": 0.08,
            "qv_levels_from_bottom": 12,
            "active_fields_at_initial_state": list(_ACTIVE_FIELDS),
            "active_counts_from_built_sigma": active_counts,
            "non_tq_fields_fixed_zero": list(_NON_TQ_FIELDS),
        },
        "parameter_prior": {
            "active": [],
            "theta_b": [float(param_prior.theta_b[i]) for i in range(4)],
            "sigma_log": [float(param_prior.sigma_log[i]) for i in range(4)],
        },
        "initial_state_control": "zero initialized by existing dual minimizer",
        "window_config_projection": list(_ACTIVE_FIELDS),
        "partition_control": False,
        "pseudo_rh": False,
        "n_successful_obs_callback_results": callback_counter["results"],
        "callback_count_note": (
            "counts non-None evaluator results only; exceptional/failed attempts "
            "are not included"),
        "n_window_evals": result.n_window_evals,
        "n_audit_evals": result.n_audit_evals,
        "runtime_kdm6_step_calls": None,
        "runtime_rttov_launches": None,
        "runtime_call_count_note": "underlying step/RTTOV calls are not instrumented by this adapter",
    }
    return {
        "result": result,
        "obs_eval": counted_obs_eval,
        "background_slot_state": slot_background,
        "b_sigma": b_sigma,
        "cvt": cvt,
        "param_prior": param_prior,
        "metadata": metadata,
    }


__all__ = ["run_single_column_analysis"]
