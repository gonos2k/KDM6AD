#!/usr/bin/env python3
"""Bounded one-column f64 KDM6 T/Q response capture for PR391 review.

Reads only ti=0, WRF column (j=86,i=48) zero-based through the archived native reader.
Writes derived/private run detail to the caller-selected JSON path. It does not
modify source, native inputs, production installs, or model output.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import netCDF4
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from oracle.kdm6 import coordinator as coord
from oracle.kdm6.runtime import kdm6_step, make_parameters
from oracle.kdm6.state import State, Forcing
from oracle.kdm6.thermo import compute_qs_water, default_thermo_params
from oracle.kdm6.satadj import default_satadj_params

SELECTOR = Path("/private/tmp/KDM6AD-viirs-native-run-20261007/comparison/run_native_kma_bt_frames.py")
DEFAULT_INPUT = Path("/private/tmp/KDM6AD-viirs-native-run-20261007/target_case_055540_055800/runs/mp337_viirs_norm2_dry1_055540_055800_358min_hist0_20261008_064206_p28793/klfs_lc05_fcst.202507190000")
PINNED_INPUT_SHA256 = "ac73e382b3102a9fdad3cd5c9e4ec46b6b25a5997dba53aa1b369b0b9ac8153e"
DT = {"dtype": torch.float64}
K0 = 3  # selected water-RH maximum; zero-based WRF bottom-up index


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_selector():
    spec = importlib.util.spec_from_file_location("native_frame_selector", SELECTOR)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load pinned native reader: {SELECTOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def as_np(t):
    return t.detach().cpu().contiguous().numpy()


def rawbit_equal(a, b):
    return all(as_np(x).dtype == as_np(y).dtype and as_np(x).tobytes() == as_np(y).tobytes()
               for x, y in zip(a, b))


def state_from_native(n):
    s = n["state"]
    return State(
        th=torch.as_tensor(n["th"], **DT).reshape(1, -1),
        qv=torch.as_tensor(s["QVAPOR"], **DT).reshape(1, -1),
        qc=torch.as_tensor(s["QCLOUD"], **DT).reshape(1, -1),
        qr=torch.as_tensor(s["QRAIN"], **DT).reshape(1, -1),
        qi=torch.as_tensor(s["QICE"], **DT).reshape(1, -1),
        qs=torch.as_tensor(s["QSNOW"], **DT).reshape(1, -1),
        qg=torch.as_tensor(s["QGRAUP"], **DT).reshape(1, -1),
        nccn=torch.as_tensor(s["QNCCN"], **DT).reshape(1, -1),
        nc=torch.as_tensor(s["QNCLOUD"], **DT).reshape(1, -1),
        ni=torch.as_tensor(s["QNICE"], **DT).reshape(1, -1),
        nr=torch.as_tensor(s["QNRAIN"], **DT).reshape(1, -1),
        bg=torch.as_tensor(s["QIB"], **DT).reshape(1, -1),
    )


def forcing_from_native(n):
    return Forcing(**{
        name: torch.as_tensor(n[key], **DT).reshape(1, -1)
        for name, key in (("rho", "rho_m"), ("pii", "pii"), ("p", "p_pa"), ("delz", "delz"))
    })


def entry_diagnostics(s, f, k):
    t = s.th * f.pii
    qs = compute_qs_water(t, f.p, params=default_thermo_params())
    q = s.qv
    rh = q / qs
    return {"T_K": float(t[0, k]), "theta_K": float(s.th[0, k]), "qv_kgkg_dry": float(q[0, k]),
            "p_Pa": float(f.p[0, k]), "qs_water_kgkg_dry": float(qs[0, k]),
            "q_over_qs": float(rh[0, k]), "sw_percent": float((rh[0, k] - 1.0) * 100.0)}


def output_diagnostics(sin, sout, f, k):
    fin = as_np(sin.qv)
    rho_d = f.rho / (1.0 + sin.qv)
    rho_d_np = as_np(rho_d)[0]
    fields = {name: as_np(getattr(sout, name))[0] for name in State._fields}
    finite = {name: bool(np.isfinite(v).all()) for name, v in fields.items()}
    qc = fields["qc"]
    qi = fields["qi"]
    ctot_gm3 = (qc + qi) * rho_d_np * 1000.0
    cfrac = np.where(ctot_gm3 > 1.0e-6, 1.0 - 1.0e-6, 0.0)
    active = {"qc_positive_levels_1based": (np.flatnonzero(qc > 0.0) + 1).tolist(),
              "qi_positive_levels_1based": (np.flatnonzero(qi > 0.0) + 1).tolist(),
              "cloud_fraction_binary_levels_1based": (np.flatnonzero(cfrac > 0.0) + 1).tolist(),
              "cloud_fraction_definition": "RTTOV builder content gate: (qc+qi)*rho_dry*1000 > 1e-6 g m-3; cfrac=0.999999 else 0"}
    per_level = {name: float(v[k]) for name, v in fields.items()}
    return {"finite_by_state_field": finite, "all_output_fields_finite": all(finite.values()),
            "selected_layer_output": per_level, "selected_layer_rho_dry_runtime_kg_m3": float(rho_d_np[k]),
            "selected_layer_condensate_g_m3": float(ctot_gm3[k]),
            "selected_layer_cloud_fraction": float(cfrac[k]), "active_masks": active,
            "whole_column_qc_max_kgkg_dry": float(np.max(qc)),
            "whole_column_qi_max_kgkg_dry": float(np.max(qi)),
            "whole_column_cloudy_liquid_levels": int(np.count_nonzero(qc > 0.0)),
            "whole_column_cloudy_ice_levels": int(np.count_nonzero(qi > 0.0))}


def invoke(s, f, xland, dt, observe):
    records = []
    original = coord.apply_satadj_step_torch
    if observe:
        def wrapper(state, forcing, xl, cpm, satadj_params, thermo_params, **kwargs):
            result = original(state, forcing, xl, cpm, satadj_params, thermo_params, **kwargs)
            out, nccn_out = result if isinstance(result, tuple) else (result, None)
            qs = compute_qs_water(state.t, forcing.p, params=thermo_params).clamp(min=1.0e-15)
            sw = (state.qv / qs - 1.0) * 100.0
            rec = {"dtcld_s": float(kwargs["dtcld"]), "k0": K0,
                   "qv_in": float(state.qv[0, K0]), "qc_in": float(state.qc[0, K0]),
                   "T_in_K": float(state.t[0, K0]), "nc_volume_in": float(state.nc[0, K0]),
                   "nccn_volume_in": (float(kwargs["nccn"][0, K0]) if kwargs.get("nccn") is not None else None),
                   "sw_percent_pre_activation": float(sw[0, K0]),
                   "activation_gate_sw_gt_zero": bool(sw[0, K0] > 0.0),
                   "qv_out": float(out.qv[0, K0]), "qc_out": float(out.qc[0, K0]),
                   "T_out_K": float(out.t[0, K0]), "nc_volume_out": float(out.nc[0, K0]),
                   "nccn_volume_out": (float(nccn_out[0, K0]) if nccn_out is not None else None),
                   "den_moist_kg_m3": float(forcing.den[0, K0]),
                   "dend_dry_kg_m3": float(forcing.dend[0, K0]),
                   "xl_J_kg": float(xl[0, K0]), "cpm_J_kg_K": float(cpm[0, K0])}
            rec["_stage_input_private"] = {
                "state": {name: as_np(getattr(state, name))[0].tolist() for name in state._fields},
                "forcing": {name: as_np(getattr(forcing, name))[0].tolist() for name in forcing._fields},
                "nccn": (as_np(kwargs["nccn"])[0].tolist() if kwargs.get("nccn") is not None else None),
                "xl": as_np(xl)[0].tolist(), "cpm": as_np(cpm)[0].tolist(),
                "dtcld_s": float(kwargs["dtcld"]),
            }
            records.append(rec)
            return result
        coord.apply_satadj_step_torch = wrapper
    try:
        out, _ = kdm6_step(s, f, params=make_parameters(dtype=torch.float64), dt=dt,
                           value_only=True, xland=torch.tensor([2.0], **DT),
                           ncmin_land=10.0, ncmin_sea=10.0, normalized_dry=True)
    finally:
        coord.apply_satadj_step_torch = original
    return out, records


def local_satadj_jvp_fd(stage, case_name):
    """Independent central differences on one captured coordinator-stage input."""
    st = coord.CoordinatorState(**{
        name: torch.tensor(values, **DT).reshape(1, -1)
        for name, values in stage["state"].items()
    })
    ff = coord.CoordinatorForcing(**{
        name: torch.tensor(values, **DT).reshape(1, -1)
        for name, values in stage["forcing"].items()
    })
    nccn = torch.tensor(stage["nccn"], **DT).reshape(1, -1)
    xl = torch.tensor(stage["xl"], **DT).reshape(1, -1)
    cpm = torch.tensor(stage["cpm"], **DT).reshape(1, -1)
    tp = default_thermo_params()
    sp = default_satadj_params(rv=tp.rv)
    dtcld = stage["dtcld_s"]

    def target(qv, t):
        out, nccn_out = coord.apply_satadj_step_torch(
            st._replace(qv=qv, t=t), ff, xl, cpm, sp, tp,
            dtcld=dtcld, nccn=nccn)
        return torch.stack((out.qv[0, K0], out.qc[0, K0], out.t[0, K0],
                            out.nc[0, K0], nccn_out[0, K0]))

    qs = compute_qs_water(st.t, ff.p, params=tp).clamp(min=1.0e-15)
    gate0 = bool(((st.qv / qs - 1.0) * 100.0)[0, K0] > 0.0)
    records = []
    for name, eps, dqi, dti in (
            ("physical_T_K", 1.0e-4, False, True),
            ("dry_qv_kgkg", 1.0e-7, True, False)):
        dq = torch.zeros_like(st.qv)
        dT = torch.zeros_like(st.t)
        if dqi:
            dq[0, K0] = 1.0
        if dti:
            dT[0, K0] = 1.0
        y, dy = torch.autograd.functional.jvp(target, (st.qv, st.t), (dq, dT))
        yp = target(st.qv + eps * dq, st.t + eps * dT)
        ym = target(st.qv - eps * dq, st.t - eps * dT)
        fd = (yp - ym) / (2.0 * eps)
        seed = torch.ones_like(y)
        _, vjp = torch.autograd.functional.vjp(target, (st.qv, st.t), v=seed)
        dual_jvp = torch.sum(seed * dy)
        dual_vjp = torch.sum(vjp[0] * dq) + torch.sum(vjp[1] * dT)
        qs_p = compute_qs_water(st.t + eps*dT, ff.p, params=tp).clamp(min=1.0e-15)
        qs_m = compute_qs_water(st.t - eps*dT, ff.p, params=tp).clamp(min=1.0e-15)
        gate_p = bool((((st.qv + eps*dq) / qs_p - 1.0) * 100.0)[0, K0] > 0.0)
        gate_m = bool((((st.qv - eps*dq) / qs_m - 1.0) * 100.0)[0, K0] > 0.0)
        dy_np, fd_np = as_np(dy), as_np(fd)
        records.append({"direction": name, "epsilon": eps, "output_order": ["qv", "qc", "T", "nc_volume", "nccn_volume"],
                        "jvp": dy_np.tolist(), "central_fd": fd_np.tolist(),
                        "max_abs_jvp_fd_error": float(np.max(np.abs(dy_np-fd_np))),
                        "max_abs_fd": float(np.max(np.abs(fd_np))),
                        "relative_inf_error_scaled_by_max_1": float(np.max(np.abs(dy_np-fd_np))/max(1.0,float(np.max(np.abs(fd_np))))),
                        "vjp_seed": seed.tolist(), "jvp_dot_seed": float(dual_jvp),
                        "vjp_dot_direction": float(dual_vjp),
                        "jvp_vjp_duality_abs_error": float(abs(float(dual_jvp-dual_vjp))),
                        "activation_gate_base_plus_minus": [gate0, gate_p, gate_m],
                        "branch_scope": "captured apply_satadj_step_torch stage only; selected layer; local tangent/FD, not full runtime or cloud-cost derivative"})
    return {"fresh_stage_case": case_name, "selected_k0": K0,
            "entry_sw_percent": float(((st.qv / qs - 1.0)*100.0)[0,K0]),
            "activation_gate_base": gate0, "directions": records}


def local_full_runtime_jvp_fd(s0, forcing, xland, k, case_name):
    """Whole 20-second unobserved normalized_dry runtime, same state coordinates."""
    leaves = State(*(x.detach().clone().requires_grad_(True) for x in s0))
    out, handle = kdm6_step(leaves, forcing, params=make_parameters(dtype=torch.float64),
                            dt=20.0, value_only=False, xland=xland,
                            ncmin_land=10.0, ncmin_sea=10.0, normalized_dry=True)
    result = []
    for name, eps, is_q in (("physical_T_K", 1.0e-4, False), ("dry_qv_kgkg", 1.0e-7, True)):
        tangent = State(*(torch.zeros_like(x) for x in leaves))
        if is_q:
            tangent = tangent._replace(qv=torch.nn.functional.one_hot(
                torch.tensor(k), num_classes=leaves.qv.shape[-1]).to(dtype=torch.float64).reshape(1,-1))
        else:
            dth = torch.zeros_like(leaves.th)
            dth[0,k] = 1.0 / forcing.pii[0,k]
            tangent = tangent._replace(th=dth)
        jt = handle.jvp(tangent)
        jvec = torch.stack((jt.qv[0,k], jt.qc[0,k], jt.th[0,k]*forcing.pii[0,k], jt.nc[0,k], jt.nccn[0,k]))
        # VJP dual check for the selected qc output covector, using the same graph.
        seed = State(*(torch.zeros_like(x) for x in out))
        uq = torch.zeros_like(out.qc); uq[0,k] = 1.0
        seed = seed._replace(qc=uq)
        vg = handle.vjp(seed, retain_graph=True)
        jdot = jt.qc[0,k]
        vdot = sum((getattr(vg, fld)*getattr(tangent,fld)).sum() for fld in State._fields)

        def perturbed(sign):
            sv = State(*(x.detach().clone() for x in s0))
            if is_q:
                sv = sv._replace(qv=sv.qv.clone())
                sv.qv[0,k] += sign*eps
            else:
                sv = sv._replace(th=sv.th.clone())
                sv.th[0,k] += sign*eps/forcing.pii[0,k]
            ov, _ = kdm6_step(sv, forcing, params=make_parameters(dtype=torch.float64),
                              dt=20.0, value_only=True, xland=xland,
                              ncmin_land=10.0, ncmin_sea=10.0, normalized_dry=True)
            return torch.stack((ov.qv[0,k], ov.qc[0,k], ov.th[0,k]*forcing.pii[0,k],
                                ov.nc[0,k], ov.nccn[0,k]))
        yp, ym = perturbed(1.0), perturbed(-1.0)
        fd = (yp-ym)/(2.0*eps)
        a, b = as_np(jvec), as_np(fd)
        result.append({"direction": name, "epsilon": eps,
                       "output_order": ["qv", "qc", "T", "nc_dry_specific", "nccn_dry_specific"],
                       "jvp": a.tolist(), "central_fd": b.tolist(),
                       "max_abs_jvp_fd_error": float(np.max(np.abs(a-b))),
                       "max_abs_fd": float(np.max(np.abs(b))),
                       "relative_inf_error_scaled_by_max_1": float(np.max(np.abs(a-b))/max(1.0,float(np.max(np.abs(b))))),
                       "selected_qc_vjp_jvp_duality_abs_error": float(abs(float(jdot-vdot))),
                       "fd_output_all_finite": bool(np.isfinite(b).all()),
                       "limitation": "whole one-call State JVP/FD, but internal non-satadj branch masks are not comprehensively recorded"})
    handle.close()
    return {"fresh_initial_state": case_name, "dt_s": 20, "k0": k,
            "runtime": "unchanged unobserved kdm6_step normalized_dry=True f64; no observer/diagnostic_trace/budget on AD or FD calls",
            "directions": result}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--forecast", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--checkpoint-npz", type=Path, default=None)
    args = ap.parse_args()
    module = load_selector()
    input_stat_before = args.forecast.stat()
    with netCDF4.Dataset(args.forecast) as ds:
        native = module.selected_frame(ds, 0)
    input_stat_after = args.forecast.stat()
    if native["time"] != "2025-07-19_05:55:40":
        raise SystemExit(f"wrong saved time {native['time']}")
    baseline = state_from_native(native)
    forcing = forcing_from_native(native)
    t0 = baseline.th * forcing.pii
    qs0 = compute_qs_water(t0, forcing.p, params=default_thermo_params())
    warm = (t0[0].numpy() > 273.15)
    rh = (baseline.qv / qs0)[0].numpy()
    k = int(np.flatnonzero(warm)[np.argmax(rh[warm])])
    if k != K0:
        raise SystemExit(f"warm-layer RH max moved from predeclared k0={K0} to {k}")
    xland = torch.tensor([native["xland"]], **DT)
    cases = [("baseline", 0.0, 1.0), ("T_minus_0p5K", -0.5, 1.0),
             ("T_minus_1p0K", -1.0, 1.0), ("qv_plus_2pct", 0.0, 1.02),
             ("qv_plus_6pct", 0.0, 1.06)]
    result = {"input_sha256": PINNED_INPUT_SHA256,
              "input_hash_source": "pre-existing independently verified identity; deliberately not rehashed during diagnostic",
              "input_size_bytes": args.forecast.stat().st_size,
              "input_stat_before_read": {"size_bytes": input_stat_before.st_size, "mtime_ns": input_stat_before.st_mtime_ns},
              "input_stat_after_read": {"size_bytes": input_stat_after.st_size, "mtime_ns": input_stat_after.st_mtime_ns},
              "native_reader_path": str(SELECTOR), "native_reader_sha256": sha256(SELECTOR),
              "worktree_head": __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "selection": {"time": native["time"], "j_0based": 86, "i_0based": 48,
                            "j_1based": 87, "i_1based": 49,
                            "k0_bottom_up_0based": k, "wrf_layer_1based": k+1,
                            "nccn_policy": "stored QNCCN; no profile initialization",
                            "xland": native["xland"], "forcing": "fixed native rho_m, pii, p, delz",
                            "delz_recipe": "archived selected_frame; PH+PHB divided by float64(float32(9.81))"},
              "baseline_layer_diagnostics": entry_diagnostics(baseline, forcing, k),
              "predeclared_scenarios": [{"name": n, "delta_T_K": dt, "qv_factor": qf,
                                          "theta_delta_K": dt/float(forcing.pii[0,k])}
                                         for n, dt, qf in cases],
              "runs": []}
    private_arrays = {"p_center_native_bottomup_Pa": as_np(forcing.p)[0],
                      "pii_native_bottomup": as_np(forcing.pii)[0],
                      "delz_native_bottomup_m": as_np(forcing.delz)[0],
                      "rho_m_forcing_native_bottomup_kg_m3": as_np(forcing.rho)[0],
                      "rho_d_optical_reference_native_bottomup_kg_m3": torch.as_tensor(native["rho_d"], **DT).numpy(),
                      "p_interface_wrf_native_bottomup_Pa": np.asarray(native["p8w_pa"], dtype=np.float64),
                      "xland": np.asarray([native["xland"]], dtype=np.float64)}
    private_arrays.update({f"state_in_baseline_{name}": as_np(getattr(baseline,name))[0] for name in State._fields})
    for name, delta_t, qfactor in cases:
        s = baseline._replace(th=baseline.th.clone(), qv=baseline.qv.clone())
        s.th[0, k] = s.th[0, k] + delta_t / forcing.pii[0, k]
        s.qv[0, k] = s.qv[0, k] * qfactor
        inp = entry_diagnostics(s, forcing, k)
        out0, _ = invoke(s, forcing, xland, 20.0, observe=False)
        out1, obs = invoke(s, forcing, xland, 20.0, observe=True)
        run = {"name": name, "entry_layer_diagnostics": inp,
               "output_rawbit_identical_observer_vs_uninstrumented": rawbit_equal(out0, out1),
               "output": output_diagnostics(s, out1, forcing, k),
               "satadj_value_only_observer_calls": obs,
               "satadj_observer_scope": "wrapper around coordinator.apply_satadj_step_torch only; restored after call; direct returned state/nccn; volume-number basis inside captured kernel stage; no built-in diagnostic_trace"}
        result["runs"].append(run)
        private_arrays.update({f"state_in_{name}_{fld}": as_np(getattr(s,fld))[0] for fld in State._fields})
        private_arrays.update({f"state_out_{name}_{fld}": as_np(getattr(out1,fld))[0] for fld in State._fields})
    # A same-final-physical-time split experiment uses the cloudy T-1 K case
    # and constant native forcing. It is a local oracle study, not host dynamics.
    wet = baseline._replace(th=baseline.th.clone(), qv=baseline.qv.clone())
    wet.th[0, k] = wet.th[0, k] - 1.0 / forcing.pii[0, k]
    time_runs = []
    for name, subdt, nsteps in (("20s_once", 20.0, 1), ("10s_twice", 10.0, 2), ("5s_four_times", 5.0, 4)):
        def sequence(observe):
            cur = wet
            calls = []
            for _ in range(nsteps):
                cur, records = invoke(cur, forcing, xland, subdt, observe=observe)
                calls.extend(records)
            return cur, calls
        plain, _ = sequence(False)
        watched, calls = sequence(True)
        time_runs.append({"name": name, "dt_s": subdt, "calls": nsteps,
                          "final_physical_time_s": subdt*nsteps,
                          "observer_output_rawbit_identical": rawbit_equal(plain, watched),
                          "output": output_diagnostics(wet, watched, forcing, k),
                          "satadj_activation_gates_at_selected_layer": [c["activation_gate_sw_gt_zero"] for c in calls],
                          "satadj_selected_layer_calls": [{key: c[key] for key in
                              ("sw_percent_pre_activation", "activation_gate_sw_gt_zero", "qv_in", "qc_in", "qv_out", "qc_out", "T_in_K", "T_out_K", "nc_volume_in", "nc_volume_out", "nccn_volume_in", "nccn_volume_out", "den_moist_kg_m3", "dend_dry_kg_m3", "xl_J_kg", "cpm_J_kg_K")} for c in calls]})
    result["equal_final_time_fixed_forcing"] = {"initial_case": "T_minus_1p0K",
        "forcing": "same native rho_m, pii, p, delz for all calls; no time-varying host forcing",
        "runs": time_runs}
    result["coordinator_satadj_local_jvp_fd"] = [
        local_satadj_jvp_fd(result["runs"][idx]["satadj_value_only_observer_calls"][0]["_stage_input_private"], case)
        for idx, case in ((0, "baseline_clear"), (2, "T_minus_1p0K_supersaturated"))]
    result["whole_runtime_local_jvp_fd"] = [
        local_full_runtime_jvp_fd(baseline if case == "baseline_clear" else
                                  baseline._replace(th=baseline.th.clone()-1.0/forcing.pii),
                                  forcing, xland, k, case)
        for case in ("baseline_clear", "T_minus_1p0K_wet_initial_state")]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    if args.checkpoint_npz is not None:
        args.checkpoint_npz.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(args.checkpoint_npz, **private_arrays)
    print(json.dumps({"output": str(args.output), "warm_max_layer": k+1,
                      "runs": len(result["runs"]),
                      "checkpoint_npz": str(args.checkpoint_npz) if args.checkpoint_npz else None,
                      "observer_rawbit_equal": [r["output_rawbit_identical_observer_vs_uninstrumented"] for r in result["runs"]]}, indent=2))


if __name__ == "__main__":
    main()
