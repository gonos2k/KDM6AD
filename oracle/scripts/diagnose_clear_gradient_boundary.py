"""Bounded A1 probe for the pinned clear-sky qv gradient boundary.

This follows one collocated WRF column (default flattened column 20004) through
KDM6, the T/Q profile builder, and optionally the live RTTOV BT/cost.  The
central differences are deliberately reported at several step sizes: a failed
large step is useful evidence when it crosses a positivity branch, and is not
silently converted into a pass by a wider tolerance.

The live mode uses the same fixture writer/operator and shared direction helper
as ``v3_live_gradient_evidence.py``; it does not modify the installed RTTOV
runtime.  Temporary RTTOV cases are removed after each call; the JSON report
retains the numeric boundary evidence.
"""
from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import torch

try:  # package import from pytest
    from .v3_live_gradient_evidence import (
        DEFAULT_CAL, DEFAULT_EPS, DEFAULT_GK2A, DEFAULT_KDM, DEFAULT_STAMP,
        _direction, _finite_stats, _profile_and_obs, _radiance_text_resolution,
        _relative_positive_direction,
        _state_subset,
    )
except ImportError:  # direct ``python oracle/scripts/...py`` invocation
    from v3_live_gradient_evidence import (
        DEFAULT_CAL, DEFAULT_EPS, DEFAULT_GK2A, DEFAULT_KDM, DEFAULT_STAMP,
        _direction, _finite_stats, _profile_and_obs, _radiance_text_resolution,
        _relative_positive_direction,
        _state_subset,
    )


DEFAULT_OUT = Path("graphify-out/goal-resolution-20260906-2307/clear/diagnostic.json")
DEFAULT_COLUMN = 20004
DT_SECONDS = 20.0


def _configs():
    from kdm6.da_driver import OsseObsConfig
    from kdm6.obs.model_profile_builder import RttovProfileConfig
    from kdm6.obs.rttov_case_writer import fixture_layer_pressure
    from kdm6.obs.rttov_fixture import fixture_p_half, fixture_tq
    from kdm6.obs.rttov_input_builder import RttovInputConfig

    t_ref, q_ref = fixture_tq()
    p_half = torch.as_tensor(fixture_p_half(), dtype=torch.float64)
    p_lay = torch.as_tensor(fixture_layer_pressure(), dtype=torch.float64)
    profile = RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=p_lay, rttov_level_pressure=p_half, cloud=False)
    inputs = RttovInputConfig(coef_id="ami_501_test", channels=tuple(range(1, 17)))
    return OsseObsConfig(
        run_k=None, profile_cfg=profile, input_cfg=inputs, obs_sigma=1.0,
        t_ref=torch.as_tensor(t_ref, dtype=torch.float64),
        q_ref=torch.as_tensor(q_ref, dtype=torch.float64)), p_lay, p_half


def _pinned_case(kdm_path: Path, gk2a_root: Path, cal_path: Path, stamp: str,
                 *, column: int, stride: int, max_dist_km: float):
    from kdm6.io.frame_reader import read_wrfout_frame
    from kdm6.obs.gk2a_l1b import CLEAN_IR_CHANNELS, load_cal_table, read_ko_slot, slot_files
    from kdm6.obs.obs_ingest import payload_to_column_obs

    frame = read_wrfout_frame(str(kdm_path), 0, nccn_policy="init_profile")
    files = [Path(p) for p in slot_files(gk2a_root, stamp, channels=CLEAN_IR_CHANNELS)]
    payload = read_ko_slot(files, load_cal_table(cal_path), stride=stride)
    columns = payload_to_column_obs(
        payload, frame.meta["lat"], frame.meta["lon"], max_dist_km=max_dist_km)
    if column < 0 or column >= frame.state.th.shape[0]:
        raise ValueError(f"column {column} outside [0, {frame.state.th.shape[0]})")
    obs_indices = torch.where(columns.col_of_obs == column)[0].tolist()
    if not obs_indices:
        raise ValueError(f"pinned column {column} has no collocated GK2A observation")
    obs_index = int(obs_indices[0])
    state, forcing, xland = _state_subset(frame, [column])
    return frame, columns, payload, state, forcing, xland, obs_index


def _clone_state(state):
    from kdm6.state import State
    return State(*(getattr(state, n).detach().clone().to(torch.float64).requires_grad_(True)
                   for n in state._fields))


def _trace_case(state, forcing, xland):
    from kdm6.runtime import kdm6_step
    from kdm6.sensitivity_diagnostics import SensitivityTrace

    trace = SensitivityTrace()
    output, handle = kdm6_step(
        state, forcing, dt=DT_SECONDS, xland=xland, value_only=True,
        diagnostic_trace=trace)
    handle.close()
    stage_qv = {}
    for record in trace.records:
        q_in = getattr(record.state_in, "qv", None)
        q_out = getattr(record.state_out, "qv", None)
        if q_in is not None and q_out is not None:
            stage_qv[record.name] = {
                "in_min": float(q_in.min()),
                "out_min": float(q_out.min()),
                "in_zero_count": int((q_in == 0).sum()),
                "out_zero_count": int((q_out == 0).sum()),
                "in_zero_mask": (q_in == 0).detach().cpu().reshape(-1).tolist(),
                "out_zero_mask": (q_out == 0).detach().cpu().reshape(-1).tolist(),
            }
    return output, trace.signature(), trace.subcycles, stage_qv


def _first_signature_diff(left, right):
    for idx, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return {"index": idx, "left": a, "right": b}
    if len(left) != len(right):
        return {"index": min(len(left), len(right)), "left_len": len(left),
                "right_len": len(right)}
    return None


def _first_qv_boundary(base_stage_qv, candidate_stage_qv):
    """Locate the first exact qv zero-mask transition between two traces."""
    for stage, base in base_stage_qv.items():
        candidate = candidate_stage_qv.get(stage)
        if candidate is None:
            continue
        for side in ("in_zero_mask", "out_zero_mask"):
            if base[side] != candidate[side]:
                return {"stage": stage, "side": side,
                        "base_mask": base[side], "candidate_mask": candidate[side]}
    return None


def _classify_observed_boundary(boundaries):
    """Return a measurement classification without claiming derivative validity."""
    observed = [item for item in boundaries.values() if item is not None]
    if not observed:
        return {"classification": "cause_unresolved",
                "reason": "no exact qv zero-mask transition was observed in the requested traces"}
    first = next((item for item in observed
                  if item["stage"] == "state_update" and item["side"] == "out"),
                 observed[0])
    source = {"state_update": "oracle/kdm6/coordinator.py:1366"}.get(first["stage"])
    known_source = first["stage"] == "state_update" and first["side"] == "out_zero_mask"
    result = {"classification": ("expected_nonsmooth_boundary" if known_source
                                  else "observed_boundary_unattributed"),
              "first_changed_stage": first["stage"], "changed_side": first["side"]}
    if source is not None:
        result["source"] = source
    return result


def _isolated_profile_probe(state, forcing, xland, cfg, direction, eps):
    """Compare an independent linear profile functional through KDM + M->profile."""
    from kdm6.runtime import kdm6_step

    weights = torch.linspace(0.25, 1.25, 69, dtype=torch.float64)

    def analytic_run_k(rin):
        nlay = rin.nlayers
        w = np.linspace(0.25, 1.25, nlay, dtype=np.float64)
        t = np.asarray(rin.profile["T"], dtype=np.float64)
        q = np.asarray(rin.profile["Q"], dtype=np.float64)
        bt = (t * w[None, :] + q * (w * 1.0e-4)[None, :]).sum(axis=1)
        bt = np.repeat(bt[:, None], len(rin.config.channels), axis=1)
        return bt, {
            "T": np.broadcast_to(w, (rin.nprofiles, len(rin.config.channels), nlay)).copy(),
            "Q": np.broadcast_to(w * 1.0e-4,
                                 (rin.nprofiles, len(rin.config.channels), nlay)).copy(),
        }, np.zeros((rin.nprofiles, len(rin.config.channels)), dtype=np.int32)

    def evaluate(s):
        leaves = _clone_state(s)
        evolved, handle = kdm6_step(leaves, forcing, dt=DT_SECONDS, xland=xland)
        _, _, t_lay, q_lay, _, _ = _profile_and_obs(
            evolved, forcing, cfg, run_k=analytic_run_k, xland=xland, detach_state=False)
        objective = (t_lay * weights).sum() + (q_lay * weights * 1.0e-4).sum()
        grad = torch.autograd.grad(objective, leaves.qv, allow_unused=False)[0]
        result = {
            "objective": float(objective.detach()),
            "ad_directional": float((grad * direction).sum().detach()),
            "qv_in_min": float(leaves.qv.detach().min()),
            "qv_in_negative_count": int((leaves.qv.detach() < 0).sum()),
            "qv_out_min": float(evolved.qv.detach().min()),
            "qv_out_zero_count": int((evolved.qv.detach() == 0).sum()),
            "qv_profile_min": float(q_lay.detach().min()),
        }
        handle.close()
        return result

    base = evaluate(state)
    rows = {}
    for e in eps:
        plus = evaluate(state._replace(qv=state.qv + e * direction))
        minus = evaluate(state._replace(qv=state.qv - e * direction))
        fd = (plus["objective"] - minus["objective"]) / (2.0 * e)
        rows[str(e)] = {
            "central_fd": fd,
            "abs_error": abs(fd - base["ad_directional"]),
            "plus": plus, "minus": minus,
        }
    return {"base": base, "eps": rows,
            "expectation": "analytic linear T/Q profile functional; no RTTOV or ASCII round-trip"}


def _live_case(s, forcing, xland, cfg, obs, obs_quality, direction, case_root):
    from kdm6.obs.obs_loss import compute_obs_loss
    from kdm6.obs.rttov_case_writer import make_live_run_k
    from kdm6.runtime import kdm6_step

    leaves = _clone_state(s)
    evolved, handle = kdm6_step(leaves, forcing, dt=DT_SECONDS, xland=xland)
    seen: dict[str, Any] = {}
    live = make_live_run_k(case_root)

    def recording(rin):
        seen["input"] = rin
        result = live(rin)
        seen["result"] = result
        return result

    _, _, _, q_lay, bt, rad_quality = _profile_and_obs(
        evolved, forcing, cfg, run_k=recording, xland=xland, detach_state=False)
    mask = ((obs_quality == 0) & (rad_quality == 0)).to(torch.float64)
    objective = compute_obs_loss(bt, {"bt": obs}, mask, sigma=1.0, delta=1.0)
    grad = torch.autograd.grad(objective, leaves.qv, allow_unused=False)[0]
    input_profile = seen["input"].profile
    q_path = case_root / "in/profiles/001/atm/q.txt"
    q_written = np.loadtxt(q_path).reshape(-1)
    q_expected = np.asarray(input_profile["Q"][0]).reshape(-1)
    serial_error = float(np.max(np.abs(q_written - q_expected)))
    result = {
        "J": float(objective.detach()),
        "ad_directional": float((grad * direction).sum().detach()),
        "mask_kept": int(mask.sum()),
        "mask_values": mask.detach().cpu().tolist(),
        "bt_values": bt.detach().cpu().tolist(),
        "rad_quality_values": rad_quality.detach().cpu().tolist(),
        "qv_in_min": float(leaves.qv.detach().min()),
        "qv_in_negative_count": int((leaves.qv.detach() < 0).sum()),
        "qv_out_min": float(evolved.qv.detach().min()),
        "qv_out_zero_count": int((evolved.qv.detach() == 0).sum()),
        "qv_profile_min": float(q_lay.detach().min()),
        "q_ascii_max_abs_error": serial_error,
        "q_ascii_changed_count": int(np.count_nonzero(q_written != q_expected)),
        "radiance_output": _radiance_text_resolution(case_root / "out/k/radiance.txt"),
        "config_hash": seen["input"].config_hash,
    }
    handle.close()
    return result


def run_diagnostic(kdm_path: Path = DEFAULT_KDM, gk2a_root: Path = DEFAULT_GK2A,
                   cal_path: Path = DEFAULT_CAL, stamp: str = DEFAULT_STAMP,
                   *, column: int = DEFAULT_COLUMN, stride: int = 8,
                   max_dist_km: float = 4.0, eps=DEFAULT_EPS, live=False,
                   out_path: Path | None = None) -> dict[str, Any]:
    frame, columns, payload, state, forcing, xland, obs_index = _pinned_case(
        kdm_path, gk2a_root, cal_path, stamp, column=column, stride=stride,
        max_dist_km=max_dist_km)
    cfg, _, _ = _configs()
    obs = columns.bt[column:column + 1]
    obs_quality = columns.obs_quality[column:column + 1]
    # Keep the historical absolute direction to reproduce the reported ε=.1/.03
    # boundary, but also run an independent positive tangent.  The latter is the
    # admissible first-order check: it cannot enter qv<0 for |eps|<=1.
    direction = _direction(tuple(state.qv.shape), seed=60410, max_abs=1.0e-4)
    positive_direction = _relative_positive_direction(
        state.qv, seed=60410, fractional_max=1.0e-2)

    trace_cases = {}
    trace_states = {"base": state}
    for e in eps:
        trace_states[f"plus-{e:g}"] = state._replace(qv=state.qv + e * direction)
        trace_states[f"minus-{e:g}"] = state._replace(qv=state.qv - e * direction)
    for name, s in trace_states.items():
        out, signature, subcycles, stage_qv = _trace_case(s, forcing, xland)
        trace_cases[name] = {"state_out_qv": _finite_stats(out.qv),
                             "signature": signature, "subcycles": subcycles,
                             "stage_qv": stage_qv,
                             "input_qv_negative_count": int((s.qv < 0).sum()),
                             "input_qv_negative_mask": (s.qv < 0).detach().cpu().reshape(-1).tolist()}
    base_sig = trace_cases["base"]["signature"]
    trace_compare = {name: _first_signature_diff(base_sig, value["signature"])
                     for name, value in trace_cases.items() if name != "base"}
    qv_boundaries = {
        name: _first_qv_boundary(trace_cases["base"]["stage_qv"], value["stage_qv"])
        for name, value in trace_cases.items() if name != "base"
    }
    boundary_conclusion = _classify_observed_boundary(qv_boundaries)

    isolated = _isolated_profile_probe(state, forcing, xland, cfg, direction, tuple(eps))
    positive_isolated = _isolated_profile_probe(
        state, forcing, xland, cfg, positive_direction, tuple(eps))
    report: dict[str, Any] = {
        "evidence_id": "A1-clear-column-20004-gradient-boundary-v1",
        "status": "measurement_complete",
        "inputs": {"kdm": str(kdm_path), "gk2a_root": str(gk2a_root),
                   "calibration": str(cal_path), "stamp": stamp, "dt_seconds": DT_SECONDS,
                   "column": column, "stride": stride, "max_dist_km": max_dist_km,
                   "eps": list(eps)},
        "pinned": {
            "frame_time": frame.meta.get("valid_time_utc"),
            "column_lat": float(frame.meta["lat"][column]),
            "column_lon": float(frame.meta["lon"][column]),
            "obs_index": obs_index,
            "obs_time": payload.valid_time_utc,
            "obs_quality_clean_count": int((obs_quality == 0).sum()),
            "model_qv_min": float(state.qv.min()),
            "model_qv_min_index": int(state.qv.argmin()),
            "direction_max_abs": float(direction.abs().max()),
            "direction_at_model_qv_min": float(direction.flatten()[int(state.qv.argmin())]),
            "direction_kind": "historical absolute random direction (boundary reproducer)",
            "positive_tangent_direction_max_fraction_of_qv": float(
                (positive_direction.abs() / state.qv.clamp_min(torch.finfo(torch.float64).tiny)).max()),
            "cloud_total": float((state.qc + state.qi + state.qs).sum()),
        },
        "independent_profile": isolated,
        "independent_profile_positive_tangent": positive_isolated,
        "branch_trace": {
            "cases": trace_cases,
            "first_signature_difference_from_base": trace_compare,
            "first_qv_zero_mask_boundary_from_base": qv_boundaries,
            "interpretation": {
                "profile_qv_clamp_source": "oracle/kdm6/obs/model_profile_builder.py:178",
                "phase_masks_and_mstep": "compared exactly for each requested trace",
            },
        },
        "conclusion": {
            **boundary_conclusion,
            "derivative_certification": "not_claimed",
            "acceptance": "The V3 gate requires admissible plus/minus state inputs, unchanged quality masks, changed serialized profiles, and a rounding bound below the directional signal.",
            "no_production_fix": "An observed qv positivity boundary is an expected nonsmooth branch; this diagnostic does not justify a tolerance or ABI change.",
        },
    }

    if live:
        if out_path is None:
            raise ValueError("live mode needs out_path so temporary cases have a bounded parent")
        live_report = {"base": None, "eps": {}}
        with tempfile.TemporaryDirectory(prefix="a1-clear-", dir=out_path.parent) as scratch:
            scratch_path = Path(scratch)
            cases = {"base": state}
            for e in eps:
                cases[f"plus-{e:g}"] = state._replace(qv=state.qv + e * direction)
                cases[f"minus-{e:g}"] = state._replace(qv=state.qv - e * direction)
            raw = {}
            for name, s in cases.items():
                raw[name] = _live_case(s, forcing, xland, cfg, obs, obs_quality,
                                       direction, scratch_path / name)
            live_report["base"] = raw.pop("base")
            base_ad = live_report["base"]["ad_directional"]
            for e in eps:
                plus, minus = raw[f"plus-{e:g}"], raw[f"minus-{e:g}"]
                fd = (plus["J"] - minus["J"]) / (2.0 * e)
                quantum = max(
                    plus["radiance_output"].get("bt_decimal_quantum_upper_bound", 0.0),
                    minus["radiance_output"].get("bt_decimal_quantum_upper_bound", 0.0))
                live_report["eps"][str(e)] = {
                    "central_fd_J": fd,
                    "abs_error_vs_AD": abs(fd - base_ad),
                    "output_rounding_bound": quantum * live_report["base"]["mask_kept"] / (2.0 * e),
                    "plus": plus, "minus": minus,
                    "same_mask": plus["mask_values"] == live_report["base"]["mask_values"] == minus["mask_values"],
                    "same_qv_output_branch": plus["qv_out_zero_count"] == live_report["base"]["qv_out_zero_count"] == minus["qv_out_zero_count"],
                }
        report["live_rttov"] = live_report
        report["conclusion"]["live_measurement"] = "completed"
        report["conclusion"]["live_qv_fd_rows"] = {
            key: {
                "input_admissible": value["plus"]["qv_in_negative_count"] == 0
                and value["minus"]["qv_in_negative_count"] == 0,
                "same_output_zero_mask": value["same_qv_output_branch"],
                "rounding_bound": value["output_rounding_bound"],
                "abs_error_vs_AD": value["abs_error_vs_AD"],
            }
            for key, value in live_report["eps"].items()
        }
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kdm", type=Path, default=DEFAULT_KDM)
    parser.add_argument("--gk2a-root", type=Path, default=DEFAULT_GK2A)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CAL)
    parser.add_argument("--stamp", default=DEFAULT_STAMP)
    parser.add_argument("--column", type=int, default=DEFAULT_COLUMN)
    parser.add_argument("--stride", type=int, default=8)
    parser.add_argument("--max-dist-km", type=float, default=4.0)
    parser.add_argument("--eps", type=float, nargs="+", default=list(DEFAULT_EPS))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    values = vars(args).copy()
    values["out_path"] = values.pop("out")
    values["kdm_path"] = values.pop("kdm")
    values["cal_path"] = values.pop("calibration")
    result = run_diagnostic(**values)
    print(json.dumps({"status": result["status"], "out": str(args.out)}, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
