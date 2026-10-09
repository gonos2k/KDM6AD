#!/usr/bin/env python3
"""Bounded seven-channel RTTOV cost for the PR391 native T/Q response cases.

This consumes a private selected-column checkpoint and the already paired
case_00 RTTOV fixture. It does not inspect the forecast file. Full RTTOV runs
and copied profiles belong in graphify-out scratch; only a compact receipt is
written to harness/evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "oracle"))
from kdm6.state import State, Forcing  # noqa: E402
from kdm6.obs.model_profile_builder import (  # noqa: E402
    RttovProfileConfig, model_to_rttov_tensors,
)
from kdm6.obs.rttov_input_builder import RttovInputConfig  # noqa: E402
from kdm6.obs.rttov_case_writer import make_live_run_k, _resolve_coef_path  # noqa: E402
from kdm6.obs.rttov_obs_operator import RttovObsOp, _build_mask  # noqa: E402
from kdm6.obs.obs_loss import compute_obs_loss  # noqa: E402
from kdm6.runtime import kdm6_step, make_parameters  # noqa: E402

PAIRED = Path("/private/tmp/KDM6AD-viirs-native-run-20261007/comparison/results_failed_native_artifact_diag_055540_055800_retry2/case_00")
FRAME_RESULT = PAIRED.parent / "native8frame_failed_run_artifact_diagnostic_enriched.json"
RTTOV_SOURCE_ROOT = Path("/Users/yhlee/AD-RTTOV/external/rttov14/src")
CHANNELS = tuple(range(10, 17))
SCENARIOS = ("baseline", "T_minus_0p5K", "T_minus_1p0K", "qv_plus_2pct", "qv_plus_6pct",
             "T_minus_0p8K")
F64 = dict(dtype=torch.float64)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def as_t(a):
    return torch.as_tensor(np.asarray(a).copy(), **F64)


def array_sha(a) -> str:
    x = np.ascontiguousarray(a, dtype=np.float64)
    return hashlib.sha256(x.tobytes()).hexdigest()


def load_pair():
    atm = PAIRED / "in/profiles/001/atm"
    data = {name: np.loadtxt(atm / name, dtype=np.float64)
            for name in ("p.txt", "p_half.txt", "t.txt", "q.txt", "o3.txt", "co2.txt")}
    hydro = np.loadtxt(atm / "hydro.txt", dtype=np.float64)
    deff = np.loadtxt(atm / "hydro_deff.txt", dtype=np.float64)
    frac = np.loadtxt(atm / "hydro_frac.txt", dtype=np.float64)
    if data["p.txt"].shape != (66,) or data["p_half.txt"].shape != (67,):
        raise ValueError("paired profile must contain 27 reference + 39 native layers")
    if hydro.shape != (66, 8) or deff.shape != (66, 7) or frac.shape != (67,):
        raise ValueError("paired hydro profile shape differs from the locked AMI fixture")
    if not np.all(data["p.txt"][1:] > data["p.txt"][:-1]):
        raise ValueError("paired RTTOV pressures are not top-to-surface ascending")
    return atm, data, hydro, deff, frac


def make_case_profile(archive, scenario, pair):
    atm, ref, hydro_ref, deff_ref, frac_ref = pair
    state_names = list(State._fields)
    state = State(*(as_t(archive[f"state_out_{scenario}_{name}"]).flip(0)
                    for name in state_names))
    forcing = Forcing(
        rho=as_t(archive["rho_m_forcing_native_bottomup_kg_m3"]).flip(0),
        pii=as_t(archive["pii_native_bottomup"]).flip(0),
        p=as_t(archive["p_center_native_bottomup_Pa"]).flip(0),
        delz=as_t(archive["delz_native_bottomup_m"]).flip(0),
    )
    rho_d = as_t(archive["rho_d_optical_reference_native_bottomup_kg_m3"]).flip(0)
    xland = as_t(archive["xland"]).reshape(())
    p_native_pa = as_t(archive["p_center_native_bottomup_Pa"][::-1])
    ph_native_pa = as_t(archive["p_interface_wrf_native_bottomup_Pa"][::-1])
    rho_d_top = rho_d
    pcfg = RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=p_native_pa, rttov_level_pressure=ph_native_pa,
        cloud=True, rho_d=rho_d_top, dry_number=True,
    )
    profile = model_to_rttov_tensors(
        state, forcing, pcfg, xland=xland, ncmin_land=10.0, ncmin_sea=10.0)
    # The paired case defines the 27 above-model-top atmosphere and every gas.
    # Preserve those inputs exactly, replacing only the 39 native T/Q centers.
    t_all = as_t(ref["t.txt"])
    q_all = as_t(ref["q.txt"])
    t_all = torch.cat((t_all[:27], profile.t_lay))
    q_all = torch.cat((q_all[:27], profile.q_lay))
    if (not torch.equal(profile.p_lay, p_native_pa)
            or not torch.equal(profile.p_half, ph_native_pa)):
        raise ValueError("model-profile builder changed native center/interface pressures")
    p_native = p_native_pa / 100.0
    ph_native = ph_native_pa / 100.0
    if not np.array_equal(ref["p.txt"][-39:], p_native.numpy()):
        raise ValueError("paired RTTOV native center pressures differ from checkpoint")
    if not np.array_equal(ref["p_half.txt"][-40:], ph_native.numpy()):
        raise ValueError("paired RTTOV native interfaces differ from checkpoint")

    # Keep reference-background hydro values in the upper 27 layers. Replace the
    # native cloud liquid and ice slots with the executed KDM endpoint optics.
    hydro = as_t(hydro_ref)
    deff = as_t(deff_ref)
    frac = as_t(frac_ref[1:])
    hydro[27:, 5] = profile.clw
    hydro[27:, 6] = profile.ciw
    deff[27:, 5] = profile.deff_liq
    deff[27:, 6] = profile.deff_ice
    frac[27:] = profile.cfrac
    return state, forcing, profile, t_all, q_all, hydro, deff, frac


def weak_composed_eval(state_in, forcing_native, archive, pair, obs, input_cfg,
                       fixture_case, run_dir):
    """Fresh endpoint profile from one state, then actual RTTOV KMA BT and Huber cost."""
    atm, ref, hydro_ref, deff_ref, frac_ref = pair
    state_td = State(*(v[0].flip(0) for v in state_in))
    forcing_td = Forcing(*(v[0].flip(0) for v in forcing_native))
    p_native_pa = as_t(archive["p_center_native_bottomup_Pa"][::-1])
    ph_native_pa = as_t(archive["p_interface_wrf_native_bottomup_Pa"][::-1])
    p_lay, p_half = as_t(ref["p.txt"])[None, :], as_t(ref["p_half.txt"])[None, :]
    rho_d = as_t(archive["rho_d_optical_reference_native_bottomup_kg_m3"][::-1])
    cfg = RttovProfileConfig(gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=p_native_pa, rttov_level_pressure=ph_native_pa,
        cloud=True, rho_d=rho_d, dry_number=True)
    xland = as_t(archive["xland"]).reshape(())
    prof = model_to_rttov_tensors(state_td, forcing_td, cfg, xland=xland,
                                  ncmin_land=10.0, ncmin_sea=10.0)
    t_full = torch.cat((as_t(ref["t.txt"][:27]), prof.t_lay))[None, :]
    q_full = torch.cat((as_t(ref["q.txt"][:27]), prof.q_lay))[None, :]
    cloud_fields = (
        torch.cat((as_t(hydro_ref[:27, 5]), prof.clw))[None, :],
        torch.cat((as_t(hydro_ref[:27, 6]), prof.ciw))[None, :],
        torch.cat((as_t(deff_ref[:27, 5]), prof.deff_liq))[None, :],
        torch.cat((as_t(deff_ref[:27, 6]), prof.deff_ice))[None, :],
        torch.cat((as_t(frac_ref[1:28]), prof.cfrac))[None, :],
    )
    run_k = make_live_run_k(run_dir, fixture_case_dir=fixture_case, ami_kma_bt=True)
    bt, quality = RttovObsOp.apply(run_k, input_cfg, t_full, q_full, p_lay, p_half,
                                   *cloud_fields)
    mask = _build_mask(obs, quality)
    loss = compute_obs_loss(bt, obs, mask, 1.0, delta=1.0)
    return bt, quality, mask, loss, prof


def full_hm_directional_cost(state0, forcing_bottomup, xland, archive, pair, obs,
                             input_cfg, fixture_case, base_quality, base_mask,
                             expected_output, scratch_root):
    """First-order full KDM-step -> optical profile -> RTTOV K cost JVP and FD."""
    k_wrf = 3
    th_leaf = state0.th.detach().clone().requires_grad_(True)
    qv_leaf = state0.qv.detach().clone().requires_grad_(True)
    leaves = state0._replace(th=th_leaf, qv=qv_leaf)
    # The private weak-point checkpoint contains the exact predeclared T−0.8 K
    # initial State as well as the baseline input. Treat that saved weak input as
    # the local control point; this avoids rebuilding its rounded theta offset.
    weak_input = leaves
    params = make_parameters(dtype=torch.float64)
    xland_tensor = torch.as_tensor([float(xland)], **F64)
    out, handle = kdm6_step(weak_input, forcing_bottomup, params=params, dt=20.0,
        value_only=False, xland=xland_tensor, ncmin_land=10.0, ncmin_sea=10.0,
        normalized_dry=True)
    names = list(State._fields)
    for n in names:
        cached = expected_output[n]
        actual = out._asdict()[n].detach().cpu().numpy()[0]
        if not np.array_equal(actual, cached):
            handle.close()
            raise ValueError(f"fresh T−0.8 K KDM output differs from cached endpoint: {n}")
    # All six case profile fields are generated from this fresh full-runtime graph;
    # the frozen optical dry-density measure is supplied from the baseline checkpoint.
    bt, quality, mask, loss, _ = weak_composed_eval(
        out, forcing_bottomup, archive, pair, obs, input_cfg, fixture_case,
        scratch_root / "composed_base")
    if (int(mask.sum()) != 7 or not torch.equal(quality, base_quality)
            or not np.array_equal(mask.detach().cpu().numpy(), base_mask)):
        handle.close()
        return {"status": "NO_SEVEN_CHANNEL_DERIVATIVE_SUPPORT",
                "fresh_full_runtime_endpoint_cost": float(loss.detach()),
                "fresh_full_runtime_quality": quality.detach().cpu().numpy()[0].tolist(),
                "fresh_full_runtime_mask": mask.detach().cpu().numpy()[0].tolist()}
    grad_th, grad_qv = torch.autograd.grad(loss, (th_leaf, qv_leaf))
    dth = torch.zeros_like(th_leaf); dth[0, k_wrf] = 1.0 / forcing_bottomup.pii[0, k_wrf]
    dqv = torch.zeros_like(qv_leaf); dqv[0, k_wrf] = 0.01
    ad = {"T": float((grad_th*dth).sum()), "qv": float((grad_qv*dqv).sum())}
    base_cloud_mask = (out.qc.detach() + out.qi.detach() + out.qs.detach()) > 0.0
    base_cloud_mask_np = base_cloud_mask.cpu().numpy()
    handle.close()

    cases = {}
    for field_name, direction, h in (("T", dth, 1.0e-4), ("qv", dqv, 1.0e-5)):
        costs, qualities, cloud_masks = [], [], []
        for sign, side in ((-1.0, "minus"), (1.0, "plus")):
            trial = State(*(v.detach().clone() for v in state0))
            trial_th = trial.th.clone(); trial_qv = trial.qv.clone()
            if field_name == "T":
                trial_th = trial_th + sign*h*direction
            else:
                trial_qv = trial_qv + sign*h*direction
            trial = trial._replace(th=trial_th, qv=trial_qv)
            trial_out, _ = kdm6_step(trial, forcing_bottomup, params=params, dt=20.0,
                value_only=True, xland=xland_tensor, ncmin_land=10.0, ncmin_sea=10.0,
                normalized_dry=True)
            cloud_masks.append(((trial_out.qc + trial_out.qi + trial_out.qs) > 0.0).cpu().numpy())
            if not all(torch.isfinite(v).all() for v in trial_out):
                raise ValueError(f"weak full-runtime {field_name} {side} output is not finite")
            run_dir = scratch_root / f"composed_{field_name}_{side}"
            tbt, tq, tm, tloss, _ = weak_composed_eval(
                trial_out, forcing_bottomup, archive, pair, obs, input_cfg,
                fixture_case, run_dir)
            if (int(tm.sum()) != 7 or not torch.equal(tq, base_quality)
                    or not np.array_equal(tm.detach().cpu().numpy(), base_mask)):
                raise ValueError(f"weak full-runtime {field_name} FD changed RTTOV support")
            costs.append(float(tloss.detach()))
            qualities.append(tq.detach().cpu().numpy()[0].tolist())
        if not np.array_equal(cloud_masks[0], base_cloud_mask_np) or not np.array_equal(cloud_masks[1], base_cloud_mask_np):
            raise ValueError(f"weak full-runtime {field_name} FD crossed a cloud activation branch")
        fd = (costs[1] - costs[0]) / (2.0*h)
        cases[field_name] = {"direction": "+1 K physical T at WRF k=3" if field_name == "T"
                             else "+0.01 kg/kg dry qv at WRF k=3",
                             "fd_step": h, "cost_ad_directional": ad[field_name],
                             "absolute_input_perturbation": h * (1.0 if field_name == "T" else 0.01),
                             "cost_central_fd": fd,
                             "relative_error": abs(ad[field_name]-fd)/max(abs(ad[field_name]),abs(fd),1e-30),
                             "plus_minus_cost": costs,
                             "quality_by_side": qualities,
                             "cloud_branch_identical_to_base": True}
    return {"status": "FULL_H_COMPOSED_KDM_RTTOV_K_DIRECTIONAL_CHECKS_COMPLETE",
            "fresh_kdm_output_all_12_state_fields_bitwise_match_checkpoint": True,
            "fresh_full_runtime_endpoint_cost": float(loss.detach()),
            "fresh_endpoint_BT_K": bt.detach().cpu().numpy()[0].tolist(),
            "quality": quality.detach().cpu().numpy()[0].tolist(),
            "mask": mask.detach().cpu().numpy()[0].tolist(),
            "executed_run_directories": {
                "base": str((scratch_root / "composed_base").resolve()),
                "T_minus": str((scratch_root / "composed_T_minus").resolve()),
                "T_plus": str((scratch_root / "composed_T_plus").resolve()),
                "qv_minus": str((scratch_root / "composed_qv_minus").resolve()),
                "qv_plus": str((scratch_root / "composed_qv_plus").resolve()),
            },
            "directions": cases,
            "scope": "Cost covectors chain through the unchanged f64 normalized_dry 20 s kdm6_step, native profile conversion/cloud mapping with frozen baseline optical rho_d, fresh RTTOV KMA BT/K and Huber cost. Directional FD independently reruns KDM and RTTOV with fixed pressures, gas/surface/geometry, sigma/bias/delta and mask."}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--weak-checkpoint", type=Path, required=True)
    ap.add_argument("--scratch", type=Path, required=True)
    ap.add_argument("--result", type=Path, required=True)
    args = ap.parse_args()
    if args.scratch.exists() or args.result.exists():
        raise FileExistsError("scratch or result path already exists")
    if (not args.checkpoint.is_file() or not args.weak_checkpoint.is_file()
            or not PAIRED.is_dir() or not FRAME_RESULT.is_file()):
        raise FileNotFoundError("private checkpoint or paired RTTOV case is missing")
    args.scratch.mkdir(parents=True)
    pair = load_pair()
    frame = json.loads(FRAME_RESULT.read_text())
    obs_all = np.asarray(frame["observation_bt_K"], dtype=np.float64)
    obsq_all = np.asarray(frame["observation_dqf"], dtype=np.float64)
    if tuple(frame["rttov_channel_ids"]) != tuple(range(8, 17)):
        raise ValueError("paired observation receipt channel order changed")
    obs = {"bt": as_t(obs_all[2:])[None, :], "obs_quality": as_t(obsq_all[2:])[None, :]}
    obs["channel_gate"] = torch.ones((1, 7), **F64)
    input_cfg = RttovInputConfig("paired-case_00-GK2A-AMI", CHANNELS)
    p_lay = as_t(pair[1]["p.txt"])[None, :]
    p_half = as_t(pair[1]["p_half.txt"])[None, :]
    with np.load(args.checkpoint) as z:
        archive = {k: z[k].copy() for k in z.files}
    with np.load(args.weak_checkpoint) as z:
        weak_archive = {k: z[k].copy() for k in z.files}
    for name in State._fields:
        archive[f"state_out_T_minus_0p8K_{name}"] = weak_archive[f"state_out_{name}"].copy()
    for main_key, weak_key in (
        ("rho_m_forcing_native_bottomup_kg_m3", "rho_m_forcing"),
        ("pii_native_bottomup", "pii"),
        ("p_center_native_bottomup_Pa", "p_center_Pa"),
        ("delz_native_bottomup_m", "delz_m"),
        ("p_interface_wrf_native_bottomup_Pa", "p_interface_wrf_Pa"),
        ("rho_d_optical_reference_native_bottomup_kg_m3", "rho_d_optical_reference"),
    ):
        if not np.array_equal(archive[main_key], weak_archive[weak_key]):
            raise ValueError(f"weak-point checkpoint changed fixed input {main_key}")
    expected_fixed = ("rho_m_forcing_native_bottomup_kg_m3", "pii_native_bottomup",
                     "p_center_native_bottomup_Pa", "delz_native_bottomup_m",
                     "p_interface_wrf_native_bottomup_Pa",
                     "rho_d_optical_reference_native_bottomup_kg_m3")
    if any(k not in archive for k in expected_fixed):
        raise ValueError("checkpoint lacks fixed native pressure/forcing/density inputs")

    details = []
    base_covectors = None
    base_mask = None
    base_cost = None
    for scenario in SCENARIOS:
        state, forcing, prof, t_full, q_full, hydro, deff, frac = make_case_profile(
            archive, scenario, pair)
        # Preserve exact paired upper reference T/Q; output arrays are checked at
        # the writer boundary below. Original geometry/surface/gases are copied.
        case_fixture = args.scratch / f"fixture_{scenario}"
        shutil.copytree(PAIRED, case_fixture)
        # Constrain the copied fixture to the same thermal-only, no simple-cloud
        # contract observed on the original paired execution.
        namelist = (case_fixture / "out/rttov_test.txt").read_text()
        if ".TRUE." not in namelist or "rt_all%solar" not in namelist:
            raise ValueError("paired RTTOV namelist is missing its solar option")
        solar = re.findall(r"(?im)^\s*defn%opts%rt_all%solar\s*=\s*([^!\n]+)", namelist)
        simple = (case_fixture / "in/profiles/001/atm/simple_cloud.txt").read_text()
        cf = re.findall(r"(?im)^\s*cfraction\s*=\s*([^!\n]+)", simple)
        if [v.strip().rstrip(",").upper() for v in solar] != [".FALSE."] or len(cf) != 1 or float(cf[0]) != 0.0:
            raise ValueError("paired case is not thermal-only with simple cloud disabled")
        # The writer's profile boundary reads named channel arrays. Run RTTOV
        # through the current AMI/KMA BT conversion and source K in one execution.
        cloud_keys = ("HYDRO6", "HYDRO7", "HYDRO_DEFF6", "HYDRO_DEFF7", "CFRAC")
        cloud_fields = (hydro[:, 5], hydro[:, 6], deff[:, 5], deff[:, 6], frac)
        run_k = make_live_run_k(args.scratch / f"run_{scenario}",
                                fixture_case_dir=case_fixture, ami_kma_bt=True)
        bt, quality = RttovObsOp.apply(
            run_k, input_cfg,
            t_full[None, :], q_full[None, :], p_lay, p_half,
            *(v[None, :] for v in cloud_fields),
        )
        mask = _build_mask(obs, quality)
        loss = compute_obs_loss(bt, obs, mask, 1.0, delta=1.0)
        if not all(torch.isfinite(v).all() for v in (bt, quality, loss)):
            raise ValueError(f"{scenario}: RTTOV returned a non-finite result; "
                             f"bt={bt.detach().cpu().numpy().tolist()}, "
                             f"rad_quality={quality.detach().cpu().numpy().tolist()}, "
                             f"mask={mask.detach().cpu().numpy().tolist()}, "
                             f"cost={float(loss.detach())}")
        run_case = args.scratch / f"run_{scenario}"
        executed_atm = run_case / "in/profiles/001/atm"
        executed = {name: np.loadtxt(executed_atm / name, dtype=np.float64)
                    for name in ("p.txt", "p_half.txt", "t.txt", "q.txt", "o3.txt", "co2.txt")}
        declared = {"p.txt": p_lay.numpy()[0], "p_half.txt": p_half.numpy()[0],
                    "t.txt": t_full.detach().cpu().numpy(), "q.txt": q_full.detach().cpu().numpy(),
                    "o3.txt": pair[1]["o3.txt"], "co2.txt": pair[1]["co2.txt"]}
        if any(not np.array_equal(executed[n], declared[n]) for n in declared):
            raise ValueError(f"{scenario}: executed RTTOV profile differs from declared inputs")
        unchanged = ("atm/o3.txt", "atm/co2.txt", "angles.txt",
                     "sfc/01/skin.txt", "sfc/01/near_surface.txt")
        base_profile_dir = PAIRED / "in/profiles/001"
        run_profile_dir = run_case / "in/profiles/001"
        if any(sha(run_profile_dir / n) != sha(base_profile_dir / n) for n in unchanged):
            raise ValueError(f"{scenario}: paired gas, geometry or surface input changed")
        run_script = run_case / "out/run.sh"
        config = run_case / "out/rttov_test.txt"
        if not run_script.is_file() or not config.is_file():
            raise FileNotFoundError(f"{scenario}: executed RTTOV runner artifacts are missing")
        solar = re.findall(r"(?im)^\s*defn%opts%rt_all%solar\s*=\s*([^!\n]+)", config.read_text())
        if [v.strip().rstrip(",").upper() for v in solar] != [".FALSE."]:
            raise ValueError(f"{scenario}: executed RTTOV namelist enabled solar")
        executed_channels = tuple(int(v) for v in (run_case / "in/channels.txt").read_text().split())
        if executed_channels != CHANNELS:
            raise ValueError(f"{scenario}: executed RTTOV channel list differs from frozen 10–16")
        executed_simple = (run_case / "in/profiles/001/atm/simple_cloud.txt").read_text()
        executed_cf = re.findall(r"(?im)^\s*cfraction\s*=\s*([^!\n]+)", executed_simple)
        if len(executed_cf) != 1 or float(executed_cf[0]) != 0.0:
            raise ValueError(f"{scenario}: executed simple_cloud cfraction is not zero")
        exec_match = re.search(r"(?m)^\s*(?:exec\s+)?(\S+\.exe)(?:\s+>.*)?\s*$", run_script.read_text())
        if exec_match is None:
            raise ValueError(f"{scenario}: cannot identify the RTTOV executable in run.sh")
        executable = Path(exec_match.group(1)).resolve()
        from kdm6.obs.rttov_case_writer import _resolve_coef_path
        coefficient = _resolve_coef_path(run_case)
        signature = (quality.detach().cpu().numpy().astype(np.float64).tolist(), mask.cpu().numpy().tolist())
        bt_values = bt.detach().cpu().numpy()[0]
        obs_values = obs["bt"].cpu().numpy()[0]
        residual = bt_values - obs_values
        normalized_residual = residual  # fixed sigma = 1 K
        abs_r = np.abs(normalized_residual)
        huber_each = np.where(abs_r <= 1.0, 0.5*normalized_residual**2,
                              abs_r - 0.5)
        details.append({"scenario": scenario, "model_bt_K": bt_values.tolist(),
                        "observation_bt_K": obs["bt"].cpu().numpy()[0].tolist(),
                        "residual_K": residual.tolist(),
                        "normalized_residual_sigma_units": normalized_residual.tolist(),
                        "unmasked_per_channel_huber": huber_each.tolist(),
                        "quality_masked_per_channel_contribution": (huber_each * mask.cpu().numpy()[0]).tolist(),
                        "rad_quality": quality.detach().cpu().numpy()[0].tolist(),
                        "mask": mask.cpu().numpy()[0].tolist(), "valid_channel_count": int(mask.sum()),
                        "huber_cost": float(loss.detach()),
                        "profile_identity": {
                            "run_case_directory": str(run_case.resolve()),
                            "native_center_pressure_exact": bool(np.array_equal(pair[1]["p.txt"][-39:], p_lay.numpy()[0, -39:])),
                            "native_interface_pressure_exact": bool(np.array_equal(pair[1]["p_half.txt"][-40:], p_half.numpy()[0, -40:])),
                            "native_profile_arrays_sha256": {
                                "p_hPa": array_sha(executed["p.txt"][-39:]),
                                "p_half_hPa": array_sha(executed["p_half.txt"][-40:]),
                                "T_K": array_sha(executed["t.txt"][-39:]),
                                "Q_ppmv_moist": array_sha(executed["q.txt"][-39:]),
                                "hydro6_g_m3": array_sha(hydro[27:, 5].cpu().numpy()),
                                "hydro7_g_m3": array_sha(hydro[27:, 6].cpu().numpy()),
                            },
                            "native_T_range_K": [float(executed["t.txt"][-39:].min()), float(executed["t.txt"][-39:].max())],
                            "native_Q_range_ppmv_moist": [float(executed["q.txt"][-39:].min()), float(executed["q.txt"][-39:].max())],
                            "k3_wrf_zero_based_temperature_K": float(executed["t.txt"][-1-(3)]),
                            "k3_wrf_zero_based_q_ppmv_moist": float(executed["q.txt"][-1-(3)]),
                            "cloudy_native_layer_count": int(torch.count_nonzero((hydro[27:, 5] + hydro[27:, 6]) > 0)),
                            "unchanged_gases_geometry_surface_verified": True,
                            "executed_profile_hashes": {name: sha(executed_atm / name) for name in declared},
                            "executed_namelist_sha256": sha(config),
                            "executed_run_script_sha256": sha(run_script),
                            "executed_channels_1based": list(executed_channels),
                            "executed_simple_cloud_fraction": float(executed_cf[0]),
                            "rttov_executable_path": str(executable),
                            "rttov_executable_sha256": sha(executable),
                            "coefficient_path": str(coefficient),
                            "coefficient_sha256": sha(coefficient),
                        }})
        if scenario == "T_minus_0p8K":
            initial = State(*(as_t(weak_archive[f"state_in_{name}"]).reshape(1, -1)
                              for name in State._fields))
            forcing_bottomup = Forcing(
                rho=as_t(archive["rho_m_forcing_native_bottomup_kg_m3"]).reshape(1, -1),
                pii=as_t(archive["pii_native_bottomup"]).reshape(1, -1),
                p=as_t(archive["p_center_native_bottomup_Pa"]).reshape(1, -1),
                delz=as_t(archive["delz_native_bottomup_m"]).reshape(1, -1),
            )
            expected_output = {name: archive[f"state_out_T_minus_0p8K_{name}"]
                               for name in State._fields}
            details[-1]["full_H_M_directional_checks"] = full_hm_directional_cost(
                initial, forcing_bottomup, float(np.asarray(archive["xland"]).reshape(-1)[0]),
                archive, pair, obs,
                input_cfg, case_fixture, quality.detach(), mask.detach().cpu().numpy(),
                expected_output, args.scratch / "composed_directional")
        if scenario == "baseline":
            base_cost = float(loss.detach())
            base_mask = mask.cpu().numpy().copy()
            if int(mask.sum()) != 7:
                raise ValueError("fresh baseline does not have the frozen seven-channel support")
            # Local-profile H derivative through profile conversion + fresh RTTOV K.
            # Keep the baseline cloud optics, geometry, pressures, gases and weights fixed.
            th = state.th.detach().clone().requires_grad_(True)
            qv = state.qv.detach().clone().requires_grad_(True)
            state_leaf = state._replace(th=th, qv=qv)
            local_cfg = RttovProfileConfig(
                gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
                rttov_layer_pressure=as_t(archive["p_center_native_bottomup_Pa"][::-1]),
                rttov_level_pressure=as_t(archive["p_interface_wrf_native_bottomup_Pa"][::-1]),
                cloud=False,
            )
            local_prof = model_to_rttov_tensors(
                state_leaf, forcing, local_cfg,
                xland=as_t(archive["xland"]), ncmin_land=10.0, ncmin_sea=10.0)
            # Use extended profile arrays with differentiable native T/Q. Upper
            # reference values are constants and this is a local H sensitivity.
            t_leaf = torch.cat((as_t(pair[1]["t.txt"][:27]), local_prof.t_lay))[None, :]
            q_leaf = torch.cat((as_t(pair[1]["q.txt"][:27]), local_prof.q_lay))[None, :]
            bt_leaf, q_leaf_rq = RttovObsOp.apply(
                run_k, input_cfg, t_leaf, q_leaf, p_lay, p_half,
                *(v[None, :] for v in cloud_fields))
            mask_leaf = _build_mask(obs, q_leaf_rq)
            loss_leaf = compute_obs_loss(bt_leaf, obs, mask_leaf, 1.0, delta=1.0)
            gt, gq = torch.autograd.grad(loss_leaf, (th, qv))
            # Physical T direction: +0.1 K in WRF k=3; Q direction: +1% of
            # baseline qv in the same predeclared layer. RTTOV index is 62 zero-based.
            k_wrf = 3
            i_rttov = 27 + (38 - k_wrf)
            dth = torch.zeros_like(th); dth[38-k_wrf] = 1.0 / forcing.pii[38-k_wrf]
            dq = torch.zeros_like(qv); dq[38-k_wrf] = 0.1 * state.qv[38-k_wrf]
            h = 1.0e-2
            local_cases = {}
            for name, field, direction in (("T", th, dth), ("qv", qv, dq)):
                vals = []
                for sign in (-1.0, 1.0):
                    trial = state._replace(**({"th": field + sign*h*direction} if name == "T"
                                              else {"qv": field + sign*h*direction}))
                    trial_prof = model_to_rttov_tensors(
                        trial, forcing, local_cfg,
                        xland=as_t(archive["xland"]), ncmin_land=10.0, ncmin_sea=10.0)
                    tt = torch.cat((as_t(pair[1]["t.txt"][:27]), trial_prof.t_lay))[None, :]
                    qq = torch.cat((as_t(pair[1]["q.txt"][:27]), trial_prof.q_lay))[None, :]
                    bt_fd, rq_fd = RttovObsOp.apply(
                        run_k, input_cfg, tt, qq, p_lay, p_half,
                        *(v[None, :] for v in cloud_fields))
                    mk = _build_mask(obs, rq_fd)
                    if (int(mk.sum()) != 7 or not torch.equal(rq_fd, q_leaf_rq)
                            or not np.array_equal(mk.cpu().numpy(), base_mask)):
                        raise ValueError(f"local {name} perturbation changed RTTOV quality support")
                    vals.append(float(compute_obs_loss(bt_fd, obs, mk, 1.0, delta=1.0).detach()))
                ad = float((gt * direction).sum()) if name == "T" else float((gq * direction).sum())
                fd = (vals[1] - vals[0]) / (2.0*h)
                local_cases[name] = {"direction": "1 K at WRF k3" if name == "T" else "0.1*qv at WRF k3",
                                     "directional_cost_covector": ad,
                                     "central_fd": fd,
                                     "relative_error": abs(ad-fd)/max(abs(ad),abs(fd),1e-30),
                                     "h": h, "plus_minus_cost": vals}
            details[-1]["local_profile_H_directional_checks"] = local_cases

    common_mask = len({json.dumps((d["rad_quality"], d["mask"])) for d in details}) == 1
    common_channel_mask = np.logical_and.reduce(
        [np.asarray(d["mask"], dtype=bool) for d in details])
    common_support = [CHANNELS[i] for i, keep in enumerate(common_channel_mask) if keep]
    common_support_costs = {
        d["scenario"]: float(np.asarray(d["unmasked_per_channel_huber"])[common_channel_mask].sum())
        for d in details
    }
    result = {
        "study": "PR391 native T/Q -> KDM endpoint cloud optics -> seven-channel KMA BT/Huber diagnostic",
        "status": "DIAGNOSTIC_FORWARD_COST_AND_TQ_DERIVATIVES_COMPLETE",
        "scenarios": details,
        "cost_contract": {"channels_1based": list(CHANNELS), "sigma_K": 1.0,
                          "bias_K": 0.0, "huber_delta": 1.0,
                          "support_is_same_across_all_predeclared_cases": common_mask,
                          "cost_is_sum_over_each_scenario_supported_channel": True,
                          "common_seven_channel_cost_comparison_is_valid": common_mask,
                          "intersection_of_all_case_quality_support_1based": common_support,
                          "intersection_support_huber_costs_diagnostic_only": common_support_costs,
                          "intersection_support_interpretation": "All six actual RTTOV QC masks retain only this common subset; these sums support a conditional within-set comparison and do not replace the frozen seven-channel reporting contract."},
        "derivative_scope": "Fresh baseline RTTOV source K gives local profile T/Q-to-cost covectors with baseline cloud optics fixed. At the predeclared weak-cloud T−0.8 K point, the separate full H∘M check chains through the f64 normalized-dry KDM step, profile/cloud mapping with frozen baseline optical rho_d, fresh RTTOV K and Huber loss; independent FD reruns the full KDM+RTTOV path on fixed mask/branch pairs. No higher derivatives or parameter identifiability.",
        "limits": ["This is a new diagnostic calculation on the saved output of a failed historical native forecast.",
                  "Not an accepted observation cost, forecast score, DA analysis, optimizer result, or operational validation.",
                  "First-order RTTOV K scope only; no higher derivatives or parameter identifiability.",
                  "Gas channels 8 and 9 are excluded by predeclared quality warning; channels 10 through 16 are the fixed seven-channel support."],
        "inputs": {"checkpoint_sha256": sha(args.checkpoint),
                   "scratch_root": str(args.scratch.resolve()),
                   "weak_cloud_checkpoint_sha256": sha(args.weak_checkpoint),
                   "weak_cloud_runtime_jvp_receipt_path": str(ROOT / "harness/evidence/pr391_tq_response_2026-10-09/RESULT_weak_cloud_Tminus0p8.json"),
                   "weak_cloud_runtime_jvp_receipt_sha256": sha(ROOT / "harness/evidence/pr391_tq_response_2026-10-09/RESULT_weak_cloud_Tminus0p8.json"),
                   "paired_case_atm_files": {k: sha(pair[0] / k) for k in (
                       "p.txt", "p_half.txt", "t.txt", "q.txt", "o3.txt", "co2.txt",
                       "hydro.txt", "hydro_deff.txt", "hydro_frac.txt")},
                   "paired_case_namelist_sha256": sha(PAIRED / "out/rttov_test.txt"),
                   "paired_geometry_sha256": sha(PAIRED / "in/profiles/001/angles.txt"),
                   "paired_surface_sha256": {"skin": sha(PAIRED / "in/profiles/001/sfc/01/skin.txt"),
                                              "near_surface": sha(PAIRED / "in/profiles/001/sfc/01/near_surface.txt")},
                   "paired_observation_result_sha256": sha(FRAME_RESULT),
                   "source_sha256": {name: sha(ROOT / name) for name in (
                       "oracle/kdm6/obs/model_profile_builder.py",
                       "oracle/kdm6/obs/rttov_case_writer.py",
                       "oracle/kdm6/obs/rttov_input_builder.py",
                       "oracle/kdm6/obs/rttov_obs_operator.py",
                       "oracle/kdm6/obs/ami_bt_coordinate.py",
                       "oracle/kdm6/obs/obs_loss.py")},
                   "rttov_quality_flag_definitions": {
                       "source_path": str(RTTOV_SOURCE_ROOT / "src/main/rttov_const.F90"),
                       "source_sha256": sha(RTTOV_SOURCE_ROOT / "src/main/rttov_const.F90"),
                       "print_source_path": str(RTTOV_SOURCE_ROOT / "src/other/rttov_print_radiance_quality.F90"),
                       "print_source_sha256": sha(RTTOV_SOURCE_ROOT / "src/other/rttov_print_radiance_quality.F90"),
                       "32768_interpretation": "1<<15; qflag_delta_edd_ext_limits (Delta-Eddington extinction limit exceeded)"},
                   "runner_source_sha256": sha(Path(__file__))},
        "runtime": {"python": platform.python_version(), "torch": str(torch.__version__),
                    "numpy": str(np.__version__)},
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
