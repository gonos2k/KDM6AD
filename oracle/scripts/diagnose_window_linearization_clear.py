"""Bounded A6 two-step retained-window check for pinned clear column 20004.

The probe uses a small scalar CVT displacement of the initial qv state, a fixed
``0.5*z**2`` prior, and one frozen GK2A quality mask / Huber observation loss.
It compares ``WindowLinearization`` JVP/VJP products with an independent
two-step unroll and central finite differences through the real RTTOV writer.
This is first-order evidence only; RTTOV K is frozen in the backward product.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
import torch

try:
    from .diagnose_clear_gradient_boundary import (
        DEFAULT_CAL, DEFAULT_COLUMN, DEFAULT_EPS, DEFAULT_GK2A, DEFAULT_KDM,
        DEFAULT_STAMP, _configs, _pinned_case, _relative_positive_direction,
    )
except ImportError:
    from diagnose_clear_gradient_boundary import (
        DEFAULT_CAL, DEFAULT_COLUMN, DEFAULT_EPS, DEFAULT_GK2A, DEFAULT_KDM,
        DEFAULT_STAMP, _configs, _pinned_case, _relative_positive_direction,
    )

DEFAULT_OUT = Path("graphify-out/goal-completion-20260906/window/clear.json")
DT_SECONDS = 20.0
Z0 = 0.05

try:
    from .v3_live_gradient_evidence import build_provenance
except ImportError:
    from v3_live_gradient_evidence import build_provenance


def _dot(a, b):
    return sum((x * y).sum() for x, y in zip(a, b))


def _zero_like(s):
    return type(s)(*(torch.zeros_like(x) for x in s))


def _state_with_qv_direction(state, direction, scalar):
    return state._replace(qv=state.qv + scalar * direction)


def _run_two_steps_value(state, forcings, xland):
    from kdm6.runtime import kdm6_step
    x = state
    for forcing in forcings:
        x, handle = kdm6_step(x, forcing, dt=DT_SECONDS, value_only=True, xland=xland)
        handle.close()
    return x


def _observe_state(state, forcing, cfg, obs, obs_quality, mask, case_root,
                   *, need_grad):
    from kdm6.obs.obs_loss import compute_obs_loss
    from kdm6.obs.rttov_case_writer import make_live_run_k
    try:
        from .v3_live_gradient_evidence import _profile_and_obs, _radiance_text_resolution
    except ImportError:
        from v3_live_gradient_evidence import _profile_and_obs, _radiance_text_resolution

    leaves = type(state)(*(x.detach().clone().to(torch.float64)
                           .requires_grad_(need_grad) for x in state))
    seen = {}
    live = make_live_run_k(case_root)

    def recording(rin):
        seen["input"] = rin
        result = live(rin)
        seen["result"] = result
        return result

    _, _, _, q_lay, bt, rq = _profile_and_obs(
        leaves, forcing, cfg, run_k=recording, xland=None, detach_state=False)
    candidate_mask = ((obs_quality == 0) & (rq == 0)).to(torch.float64)
    if mask is None:
        mask = candidate_mask
    j = compute_obs_loss(bt, {"bt": obs}, mask, sigma=1.0, delta=1.0)
    grad = torch.autograd.grad(j, tuple(leaves), allow_unused=True) if need_grad else None
    result = {
        "J_obs": float(j.detach()),
        "bt_values": bt.detach().cpu().tolist(),
        "rad_quality_values": rq.detach().cpu().tolist(),
        "mask_values": mask.detach().cpu().tolist(),
        "candidate_mask_values": candidate_mask.detach().cpu().tolist(),
        "mask_kept": int(mask.sum()),
        "qv_min": float(leaves.qv.detach().min()),
        "qv_negative_count": int((leaves.qv.detach() < 0).sum()),
        "q_profile_min": float(q_lay.detach().min()),
        "radiance_output": _radiance_text_resolution(case_root / "out/k/radiance.txt"),
        "gradient": (type(state)(*(g.detach() if g is not None else torch.zeros_like(x)
                                    for g, x in zip(grad, leaves))) if grad is not None else None),
    }
    return result, mask


def _state_fd_metrics(plus, minus, eps, tangent):
    rows = {}
    for name, p, m, t in zip(plus._fields, plus, minus, tangent):
        fd = (p - m) / (2.0 * eps)
        err = (fd - t).abs()
        rows[name] = {"max_abs_error": float(err.max()),
                      "max_error_index": int(err.reshape(-1).argmax()),
                      "fd_max_abs": float(fd.abs().max()),
                      "tangent_max_abs": float(t.abs().max())}
    return rows


def run_diagnostic(kdm_path=DEFAULT_KDM, gk2a_root=DEFAULT_GK2A,
                   cal_path=DEFAULT_CAL, stamp=DEFAULT_STAMP, *,
                   column=DEFAULT_COLUMN, stride=8, max_dist_km=4.0,
                   eps=(0.2, 0.3), out_path=None):
    from kdm6.da_linearization import WindowLinearization
    from kdm6.runtime import kdm6_step
    from kdm6.state import State

    frame, columns, payload, state, forcing, xland, obs_index = _pinned_case(
        Path(kdm_path), Path(gk2a_root), Path(cal_path), stamp, column=column,
        stride=stride, max_dist_km=max_dist_km)
    cfg, _, _ = _configs()
    obs = columns.bt[column:column + 1]
    obs_quality = columns.obs_quality[column:column + 1]
    direction = _relative_positive_direction(state.qv, seed=60410, fractional_max=0.1)
    x_ref = _state_with_qv_direction(state, direction, Z0)
    forcings = [forcing, forcing]

    if out_path is None:
        out_path = DEFAULT_OUT
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="a6-clear-", dir=out_path.parent) as scratch:
        scratch = Path(scratch)
        # Build the retained two-step linearization at the same CVT point used
        # by the direct unroll.  Only KDM handles are retained here.
        with WindowLinearization(x_ref, forcings, dt=DT_SECONDS, xland=xland) as lin:
            final_ref = lin.state_final
            baseline, mask = _observe_state(
                final_ref, forcing, cfg, obs, obs_quality, None, scratch / "base",
                need_grad=True)
            u_final = baseline["gradient"]
            tangent_v = State(*(direction if n == "qv" else torch.zeros_like(getattr(x_ref, n))
                                for n in State._fields))
            retained_tangent = lin.apply_tangent(tangent_v, obs_times=[2])["final"]
            retained_vjp = lin.apply_adjoint({2: u_final})
            jvp_scalar = float(_dot(u_final, retained_tangent))
            vjp_scalar = float(_dot(retained_vjp, tangent_v))
            direct_leaves = type(x_ref)(*(x.detach().clone().requires_grad_(True)
                                          for x in x_ref))
            direct_x = direct_leaves
            direct_handles = []
            for f in forcings:
                direct_x, direct_handle = kdm6_step(
                    direct_x, f, dt=DT_SECONDS, xland=xland)
                direct_handles.append(direct_handle)
            direct_vjp = torch.autograd.grad(_dot(direct_x, u_final),
                                             tuple(direct_leaves), allow_unused=True)
            direct_vjp_state = type(x_ref)(*(g if g is not None else torch.zeros_like(x)
                                             for g, x in zip(direct_vjp, direct_leaves)))
            direct_vjp_scalar = float(_dot(direct_vjp_state, tangent_v))
            for h in direct_handles:
                h.close()
            direct = {}
            plus_states, minus_states = {}, {}
            for e in eps:
                plus_state = _run_two_steps_value(
                    _state_with_qv_direction(state, direction, Z0 + e), forcings, xland)
                minus_state = _run_two_steps_value(
                    _state_with_qv_direction(state, direction, Z0 - e), forcings, xland)
                plus_states[e], minus_states[e] = plus_state, minus_state
                plus, _ = _observe_state(plus_state, forcing, cfg, obs, obs_quality,
                                         mask, scratch / f"plus-{e:g}", need_grad=False)
                minus, _ = _observe_state(minus_state, forcing, cfg, obs, obs_quality,
                                          mask, scratch / f"minus-{e:g}", need_grad=False)
                fd_total = ((0.5 * (Z0 + e) ** 2 + plus["J_obs"])
                            - (0.5 * (Z0 - e) ** 2 + minus["J_obs"])) / (2.0 * e)
                direct[e] = {
                    "central_fd_total_J": fd_total,
                    "central_fd_obs_J": (plus["J_obs"] - minus["J_obs"]) / (2.0 * e),
                    "predicted_total_derivative": Z0 + jvp_scalar,
                    "abs_error_vs_retained": abs(fd_total - (Z0 + jvp_scalar)),
                    "same_mask": plus["candidate_mask_values"] == baseline["candidate_mask_values"] == minus["candidate_mask_values"],
                    "plus": {k: v for k, v in plus.items() if k != "gradient"},
                    "minus": {k: v for k, v in minus.items() if k != "gradient"},
                    "output_rounding_bound": max(
                        plus["radiance_output"].get("bt_decimal_quantum_upper_bound", 0.0),
                        minus["radiance_output"].get("bt_decimal_quantum_upper_bound", 0.0))
                    * baseline["mask_kept"] / (2.0 * e),
                }

            # Independent state FD uses the same direct unroll, with no RTTOV.
            state_fd = {}
            for e in eps:
                p, m = plus_states[e], minus_states[e]
                state_fd[str(e)] = _state_fd_metrics(p, m, e, retained_tangent)

    report = {
        "evidence_id": "A6-clear-column-20004-retained-window-v1",
        "status": "measurement_complete",
        "derivative_certification": "not_claimed",
        "inputs": {"kdm": str(kdm_path), "gk2a_root": str(gk2a_root),
                   "calibration": str(cal_path), "stamp": stamp, "column": column,
                   "obs_index": obs_index, "window_steps": 2,
                   "dt_seconds": DT_SECONDS, "z0": Z0, "eps": list(eps),
                   "direction": "qv relative-positive, |delta qv| <= 0.1*qv"},
        "provenance": build_provenance(Path(cal_path), all_sky=False),
        "initial_domain": {
            "qv_min": float(state.qv.min()), "qv_negative_count": int((state.qv < 0).sum()),
            "qc_min": float(state.qc.min()), "qc_negative_count": int((state.qc < 0).sum()),
            "admissible_qv_qc": bool((state.qv >= 0).all() and (state.qc >= 0).all()),
        },
        "observation_contract": {"mask": "fixed baseline obs_quality==0 & rad_quality==0",
                                  "sigma": 1.0, "units": "K", "bias": 0.0,
                                  "huber_delta": 1.0, "prior": "0.5*z**2"},
        "baseline": {k: v for k, v in baseline.items() if k != "gradient"},
        "retained": {"vjp_directional": vjp_scalar, "jvp_directional": jvp_scalar,
                     "direct_two_step_vjp_directional": direct_vjp_scalar,
                     "duality_abs_error": abs(vjp_scalar - jvp_scalar),
                     "retained_vs_direct_vjp_abs_error": abs(vjp_scalar - direct_vjp_scalar),
                     "cached_K_contract": "baseline RTTOV BT-space K^T lambda; no dK/dx"},
        "direct_unroll": direct,
        "state_jvp_fd": state_fd,
        "conclusion": "Two-step retained and direct measurements are recorded; interpret derivative validity only for rows with admissible inputs, fixed masks, and rounding bounds below signal.",
    }
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kdm", type=Path, default=DEFAULT_KDM)
    parser.add_argument("--gk2a-root", type=Path, default=DEFAULT_GK2A)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CAL)
    parser.add_argument("--stamp", default=DEFAULT_STAMP)
    parser.add_argument("--column", type=int, default=DEFAULT_COLUMN)
    parser.add_argument("--stride", type=int, default=8)
    parser.add_argument("--max-dist-km", type=float, default=4.0)
    parser.add_argument("--eps", type=float, nargs="+", default=[0.2, 0.3])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    run_diagnostic(args.kdm, args.gk2a_root, args.calibration, args.stamp,
                   column=args.column, stride=args.stride, max_dist_km=args.max_dist_km,
                   eps=tuple(args.eps), out_path=args.out)
    print(json.dumps({"status": "measurement_complete", "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
