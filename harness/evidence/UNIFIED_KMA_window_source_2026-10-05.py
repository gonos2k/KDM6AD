#!/usr/bin/env python3
"""Run a bounded full-domain KMA v3.0 analysis on the retained C5 column."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import time
import sys

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OMP_THREAD_LIMIT"] = "1"

import netCDF4
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "oracle"))
from kdm6.io.frame_reader import read_wrfout_frame
from kdm6.obs.gk2a_l1b import _read_ami_bt, load_cal_table
from kdm6.obs.obs_ingest import ColumnObs
from kdm6.da_fulldomain import run_fulldomain_analysis
from kdm6.da_fulldomain import make_fulldomain_obs_eval, QTOT_MIN
from kdm6.da_driver import OsseObsConfig
from kdm6.da_window import WindowConfig, collect_window_trajectory, run_da_window
from kdm6.runtime import make_parameters
from kdm6.state import State, Forcing
from kdm6.obs.model_profile_builder import RttovProfileConfig
from kdm6.obs.rttov_input_builder import RttovInputConfig
from kdm6.obs.rttov_case_writer import make_live_run_k, _resolve_coef_path
from kdm6.rttov_bridge import freeze_dry_air_density

PROFILE = ROOT / "harness/evidence/C5_supported_profile_2026-10-03.npz"
OBS_RECORD = ROOT / "harness/evidence/C5_matched_observation_diagnostic_2026-10-03.json"
OLD_CAL = ROOT / "harness/evidence/AMI_legacy_nominal_calibration_202507190000.json"
KMA_CAL = ROOT / "oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json"
PREP_RECEIPT = Path("/private/tmp/KDM6AD-c5-native39-sea-supported-retry1-20261003/evidence/selected_profile_preparation_receipt_20261003.json")
FORECAST = Path("/private/tmp/KDM6AD-nccn-zero-merge603ea4a-host-confirm/case/runs/mp337_merge603ea4a_off_0min40s_hist0_20261003_102038_p26153/klfs_lc05_fcst.202507190000")
FIXTURE = Path("/private/tmp/KDM6AD-c5-dom32-fixture-20261003")
CHANNELS = tuple(range(8, 17))
F64 = dict(dtype=torch.float64)
SOURCE_SET = (
    "oracle/kdm6/runtime.py", "oracle/kdm6/da_window.py",
    "oracle/kdm6/da_linearization.py", "oracle/kdm6/da_parallel.py",
    "oracle/kdm6/da_fulldomain.py", "oracle/kdm6/da_dual.py",
    "oracle/kdm6/obs/allsky_shard.py")


def bit_equal(left, right):
    a, b = np.asarray(left), np.asarray(right)
    return a.shape == b.shape and np.array_equal(
        np.ascontiguousarray(a).view(np.uint64),
        np.ascontiguousarray(b).view(np.uint64))


def run_independent_window(frame, b, co, profile, geometry, surface, root, horizon):
    """BASE/± run_da_window directional check through one frozen obs callback."""
    x0 = State(*(field[b:b+1].clone() for field in frame.state))
    fc = Forcing(*(field[b:b+1].clone() for field in frame.forcing))
    xland = frame.xland[b:b+1].clone()
    params = make_parameters()
    cfg = WindowConfig(dt=20.0, params=params, xland=xland,
                       ncmin_land=10.0, ncmin_sea=10.0, normalized_dry=True)
    forcings = [fc] * horizon
    slot = collect_window_trajectory(x0, forcings, cfg, {horizon})[horizon]
    cloud = ((slot.qc + slot.qi + slot.qs).sum(-1) > QTOT_MIN)
    cloudy, clear = torch.where(cloud)[0], torch.where(~cloud)[0]
    if cloudy.numel() != 1 or clear.numel() != 0:
        raise ValueError(f"expected one cloudy endpoint column at {horizon}: "
                         f"cloudy={cloudy.tolist()}, clear={clear.tolist()}")
    p_lay = torch.as_tensor(profile["extended_p_center_hPa"], **F64)
    p_half = torch.as_tensor(profile["extended_p_half_hPa"], **F64)
    t_ref = torch.as_tensor(profile["extended_temperature_K"], **F64)
    q_ref = torch.as_tensor(profile["extended_q_ppmv_moist"], **F64)
    clear_cfg = OsseObsConfig(
        run_k=make_live_run_k(root / "clear", fixture_case_dir=FIXTURE,
                              ami_kma_bt=True),
        profile_cfg=RttovProfileConfig(2, "mixing_ratio_kgkg_dry",
            rttov_layer_pressure=p_lay, rttov_level_pressure=p_half),
        input_cfg=RttovInputConfig("retained-C5-AMI", CHANNELS,
                                   geometry=geometry, surface=surface),
        obs_sigma=1.0, t_ref=t_ref, q_ref=q_ref)
    rho_d = freeze_dry_air_density(x0, fc)
    rttov_cfg = dict(t_ref=t_ref.numpy(), q_ref=q_ref.numpy(),
        p_lay=p_lay.numpy(), p_half=p_half.numpy(), channels=CHANNELS,
        coef_id="retained-C5-AMI", geometry=geometry, surface=surface,
        ncmin_land=10.0, ncmin_sea=10.0, oracle_root=str(ROOT / "oracle"),
        rho_d=rho_d.numpy(), dry_number=True, ami_kma_bt=True,
        fixture_case_dir=str(FIXTURE))
    fixed_eval = make_fulldomain_obs_eval(
        x0, fc, co.bt[b:b+1], co.obs_quality[b:b+1], xland,
        cloudy, clear, clear_cfg, rttov_cfg, str(root / "eval"),
        n_workers=1, pool=None, obs_time=horizon, huber_delta=1.0,
        x_slot_bg=slot, channel_gate=co.channel_gate[b:b+1])
    direction = 0.01 * x0.qv
    cases = {}
    for label, offset in (("base", 0.0), ("plus", 1.0e-4), ("minus", -1.0e-4)):
        initial = x0 if label == "base" else x0._replace(qv=x0.qv + offset * direction)
        costs, signatures, masks = [], [], []
        def callback(t, state_t, capture_adjoint=(label == "base")):
            value = fixed_eval(t, state_t)
            if value is None:
                return None
            costs.append(float(value.j))
            signatures.append(value.signature)
            masks.append(int(value.n_valid))
            return value.adj if capture_adjoint else None
        window = run_da_window(initial, forcings, callback, cfg)
        if len(costs) != 1 or not math.isfinite(costs[0]):
            raise RuntimeError(f"{label} window produced no single finite objective")
        cases[label] = dict(cost=costs[0], signature=signatures[0], n_valid=masks[0],
                            final_state=np.stack([f.detach().numpy() for f in window.state_final]))
        if label == "base":
            cases[label]["qv_adjoint"] = window.adj_x0.qv.detach().numpy()
            cases[label]["vjp_directional_cost"] = float(
                (window.adj_x0.qv * direction).sum())
    ad = cases["base"]["vjp_directional_cost"]
    fd = (cases["plus"]["cost"] - cases["minus"]["cost"]) / (2.0e-4)
    rel = abs(ad - fd) / max(abs(ad), abs(fd), 1.0e-30)
    stable = len({v["signature"] for v in cases.values()}) == 1 and all(
        v["n_valid"] == 7 for v in cases.values())
    if not stable or not math.isfinite(rel) or rel > 1.0e-5:
        raise RuntimeError(f"{horizon}-step window FD/support failed: {rel:g}")
    return dict(horizon_steps=horizon, modeled_seconds=horizon*20,
        direction="0.01*initial qv, 39 levels; h=1e-4", sigma_K=1.0,
        huber_delta=1.0, fixed_frozen_density=True,
        same_frozen_obs_eval=True, same_support_signature=stable,
        costs={key:value["cost"] for key,value in cases.items()},
        vjp_directional_cost=ad, fd_directional_cost=fd,
        relative_error=rel, cases=cases)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    torch.set_num_threads(1)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-root", type=Path, required=True)
    a = ap.parse_args()
    if a.output_root.exists():
        raise FileExistsError(a.output_root)
    a.output_root.mkdir(parents=True)

    if sha(PROFILE) != "7915ef9bc9fab4983ab47776c1a3345384c21f09bddc2a6d540d36c4755194d4":
        raise ValueError("pinned C5 profile changed")
    if sha(OBS_RECORD) != "ce445a0c7908793eb4388a235bdabaf922138c210093c67c45b813f74367fc3b":
        raise ValueError("pinned C5 observation receipt changed")
    prep = json.loads(PREP_RECEIPT.read_text())
    source_hashes_start = {name: sha(ROOT / name) for name in SOURCE_SET}
    if not prep["engine_executed"] is False:
        raise ValueError("selected profile preparation unexpectedly claims RTTOV")
    if sha(FORECAST) != prep["source"]["forecast_sha256"]:
        raise ValueError("retained native forecast changed")
    if sha(prep["profile_npz"]) != prep["profile_npz_sha256"]:
        raise ValueError("selected profile does not match its preparation receipt")
    if sha(PROFILE) != prep["profile_npz_sha256"]:
        raise ValueError("public profile copy differs from the private selected profile")
    fixture_ref = json.loads((ROOT / "harness/evidence/C5_nc_bt_dom32_result_2026-10-03.json").read_text())
    fixture_hashes = {str(p.relative_to(FIXTURE)): sha(p)
                      for p in sorted(FIXTURE.rglob("*")) if p.is_file()}
    if fixture_hashes != fixture_ref["fixture_source_hashes"]:
        raise ValueError("C5 RTTOV fixture changed")

    with np.load(PROFILE) as z:
        p = {k: z[k].copy() for k in z.files}
    with np.load(prep["profile_npz"]) as z:
        private_profile = {k: z[k].copy() for k in z.files}
    if not np.array_equal(p["native_p8w_real4_Pa"].view(np.uint32),
                          private_profile["native_p8w_real4_Pa"].view(np.uint32)):
        raise ValueError("native P8W real4 interface vector differs from selected source profile")
    if not np.array_equal(p["extended_p_center_hPa"][-39:], p["native_p_center_hPa"]):
        raise ValueError("optical native center-pressure suffix differs from retained profile")
    optical_half_from_native = p["native_p8w_real4_Pa"][::-1].astype(np.float64) / 100.0
    if not np.array_equal(p["extended_p_half_hPa"][-40:], optical_half_from_native):
        raise ValueError("optical native interface suffix differs from source real4 P8W values")
    fr = read_wrfout_frame(str(FORECAST), time_idx=1, nccn_policy="as_stored")
    b = int(prep["winner"]["flat_b"])
    native_state = np.stack([getattr(fr.state, k)[b].numpy() for k in fr.state._fields])
    native_forcing = np.stack([getattr(fr.forcing, k)[b].numpy() for k in fr.forcing._fields])
    if not bit_equal(native_state, p["native_state_bottom_up"]):
        raise ValueError("frame-reader native state differs from retained C5 column")
    if not bit_equal(native_forcing, p["native_forcing_bottom_up"]):
        raise ValueError("frame-reader forcing differs from retained C5 column")
    if fr.meta.get("valid_time_utc") != "2025-07-19_00:00:20":
        raise ValueError("unexpected frame valid time")

    rec = json.loads(OBS_RECORD.read_text())
    if sha(KMA_CAL) != "a6f830aa04e19f6982aa6ff36e832464a5b32fdcf8200211956969d5eb48325d":
        raise ValueError("KMA v3.0 paired-wavenumber calibration changed")
    if sha(KMA_CAL) != "a6f830aa04e19f6982aa6ff36e832464a5b32fdcf8200211956969d5eb48325d":
        raise ValueError("current paired-wavenumber KMA v3.0 table changed")
    if rec["pixel_zero_based"] != [411, 338]:
        raise ValueError("pinned KO pixel changed")
    if rec["combined_mask"] != [[0, 0, 1, 1, 1, 1, 1, 1, 1]]:
        raise ValueError("predeclared seven-channel support changed")
    current_cal = load_cal_table(KMA_CAL)["channels"]
    old_cal = load_cal_table(OLD_CAL)["channels"]
    obs_bt, obs_q, old_bt = [], [], []
    row, col = rec["pixel_zero_based"]
    for item in rec["channels"]:
        if sha(item["path"]) != item["sha256"]:
            raise ValueError(f"pinned KO raw file changed: {item['path']}")
        with netCDF4.Dataset(item["path"]) as ds:
            current, quality = _read_ami_bt(ds["image_pixel_values"], current_cal[item["channel"]])
            legacy, _ = _read_ami_bt(ds["image_pixel_values"], old_cal[item["channel"]])
        if not np.isclose(float(legacy[row, col]), float(item["bt_K"]), rtol=0., atol=2.e-12):
            raise ValueError(f"legacy receipt decode mismatch for {item['channel']}")
        obs_bt.append(float(current[row, col]))
        obs_q.append(float(quality[row, col]))
        old_bt.append(float(legacy[row, col]))
    if any(q != 0.0 for q in obs_q):
        raise ValueError("the selected raw KO pixel has a nonzero quality flag")

    B = fr.state.th.shape[0]
    y = torch.zeros((B, 9), **F64)
    rq = torch.ones_like(y)
    gate = torch.zeros_like(y)
    y[b] = torch.as_tensor(obs_bt, **F64)
    rq[b] = torch.as_tensor(obs_q, **F64)
    gate[b] = torch.as_tensor(rec["combined_mask"][0], **F64)
    co = ColumnObs(y, rq, 1, 0, 0, torch.tensor([b], dtype=torch.int64),
                   "202507190000", torch.zeros_like(y), gate)
    ob = prep["observation"]
    sf = prep["surface"]
    geometry = dict(zenangle=ob["view_zenith_deg"],
        azangle=ob["view_azimuth_deg_clockwise_from_north"],
        sunzenangle=ob["solar_zenith_deg"], sunazangle=ob["solar_azimuth_deg"],
        latitude=ob["pixel_latitude_deg"], longitude=ob["pixel_longitude_deg"],
        elevation=sf["same_c2_frame_surface"]["HGT"] / 1000.)
    surface = {"skin": dict(sf["RTTOV_skin"]),
               "near_surface": dict(sf["RTTOV_near_surface"])}
    grids = dict(p_lay=p["extended_p_center_hPa"], p_half=p["extended_p_half_hPa"],
        t_ref=p["extended_temperature_K"], q_ref=p["extended_q_ppmv_moist"],
        cloud_fixture_case_dir=str(FIXTURE), clear_fixture_case_dir=str(FIXTURE))
    before_state = native_state.copy()
    before_forcing = native_forcing.copy()
    fields_path = a.output_root / "fulldomain_fields.npz"
    started = time.monotonic()
    report = run_fulldomain_analysis(fr, co, grids, str(a.output_root / "full_domain"),
        boundary=10, n_workers=1, max_iter=2, max_cloudy=1, max_clear=0,
        coef_clear="retained-C5-AMI", coef_cloud="retained-C5-AMI",
        channels=CHANNELS, geometry=geometry, surface=surface,
        obs_time=1, dt=20., time_tolerance_s=40., ncmin_land=10., ncmin_sea=10.,
        qv_levels=39, huber_delta=1., pseudo_rh=False, save_fields=str(fields_path),
        normalized_dry=True, observation_coordinate="kma_v3_0")
    if (report["n_subspace"] != 1 or report["n_model_cloudy"] != 1
            or report["n_valid"] != 7 or report["bt_coordinate"] != "kma_v3_0"
            or report["model_number_basis"] != "per_kg_dry_air"
            or report["optical_number_basis"] != "per_kg_dry_air"):
        raise RuntimeError("full-domain selection/basis differs from the bounded C5 contract")
    after_state = np.stack([getattr(fr.state, k)[b].numpy() for k in fr.state._fields])
    after_forcing = np.stack([getattr(fr.forcing, k)[b].numpy() for k in fr.forcing._fields])
    if not bit_equal(before_state, after_state) or not bit_equal(before_forcing, after_forcing):
        raise RuntimeError("full-domain analysis mutated its input frame")

    window20 = run_independent_window(fr, b, co, p, geometry, surface,
                                     a.output_root / "window20", horizon=1)
    window3600 = run_independent_window(fr, b, co, p, geometry, surface,
                                        a.output_root / "window3600", horizon=180)

    source_hashes_end = {name: sha(ROOT / name) for name in SOURCE_SET}
    if source_hashes_end != source_hashes_start:
        raise RuntimeError("a production source changed during the acceptance run")
    exe_match = re.search(r"(?m)^exec\s+(\S+\.exe)\s*$", (FIXTURE / "out/run.sh").read_text())
    if exe_match is None:
        raise ValueError("cannot resolve RTTOV executable from pinned fixture runner")
    exe_path = Path(exe_match.group(1)).resolve()
    coef_path = _resolve_coef_path(FIXTURE)
    fixture_runtime = dict(rttov_executable_path=str(exe_path),
        rttov_executable_sha256=sha(exe_path), consumed_coefficient_path=str(coef_path),
        consumed_coefficient_sha256=sha(coef_path),
        hydro_tables={name: sha(FIXTURE / "in/profiles/001/atm" / name)
                      for name in ("hydro.txt", "hydro_deff.txt", "hydro_frac.txt")})
    result = dict(
        status="UNIFIED_KMA_WINDOW_NUMERICAL_PASS",
        source_sha256=sha(__file__), profile_sha256=sha(PROFILE),
        observation_record_sha256=sha(OBS_RECORD), legacy_calibration_sha256=sha(OLD_CAL),
        kma_calibration_sha256=sha(KMA_CAL), prep_receipt_sha256=sha(PREP_RECEIPT),
        forecast_sha256=sha(FORECAST), fixture_source_hashes=fixture_hashes,
        source_hashes_start=source_hashes_start, source_hashes_end=source_hashes_end,
        fixture_runtime=fixture_runtime,
        optical_native_center_suffix_exact=True,
        optical_native_half_suffix_matches_real4_P8W=True,
        selected_column=dict(flat_b=b, i_1based=73, j_1based=157,
            valid_time=fr.meta["valid_time_utc"], xland=float(fr.xland[b]),
            native_state=native_state.tolist(), native_forcing=native_forcing.tolist()),
        observation=dict(pixel_zero_based=[row,col], current_kma_v3_0_bt=obs_bt,
            legacy_receipt_bt=old_bt, decode_delta=(np.asarray(obs_bt)-old_bt).tolist(),
            raw_quality=obs_q, predeclared_gate=rec["combined_mask"],
            nominal_obs_time="2025-07-19_00:00:00", frame_time=fr.meta["valid_time_utc"],
            data_derived_offset_s=-20., alignment_error_s=40., tolerance_s=40.),
        full_domain_report=report,
        full_domain_fields_path=str(fields_path),
        full_domain_fields_sha256=sha(fields_path),
        independent_window_20s=window20,
        independent_window_3600s=window3600,
        full_domain_input_state_unchanged=bit_equal(before_state,after_state),
        full_domain_input_forcing_unchanged=bit_equal(before_forcing,after_forcing),
        full_domain_elapsed_s=time.monotonic()-started,
        runtime_threads=dict(torch_num_threads=torch.get_num_threads(),
            OMP_NUM_THREADS=os.environ.get("OMP_NUM_THREADS"),
            MKL_NUM_THREADS=os.environ.get("MKL_NUM_THREADS"),
            OMP_THREAD_LIMIT=os.environ.get("OMP_THREAD_LIMIT")),
        approvals=dict(accepted_observation_cost=False, physical_srf_compatibility_approved=False,
            physical_number_basis_resolved=False, scientific_observation_approval=False,
            operational_approval=False, host_writeback=False),
        scope="One full-domain max_iter=2 single-step analysis on one selected native column. Fixed nominal 00:00 target is 20s earlier than frame and differs by 40s from obs_time=1 slot; tolerance explicitly set to 40s. Diagnostic sigma=1K/Huber delta=1. No collocated observing sequence, forecast test, host writeback, cycling or science approval.",
        python=platform.python_version(), torch=str(torch.__version__), netcdf4=netCDF4.__version__)
    arrays_path = ROOT / "harness/evidence/UNIFIED_KMA_window_arrays_2026-10-05.npz"
    array_data = dict(initial_state=native_state, initial_forcing=native_forcing,
                      observation_bt=np.asarray(obs_bt), observation_quality=np.asarray(obs_q),
                      channel_gate=np.asarray(rec["combined_mask"]))
    for horizon, payload in (("20s", window20), ("3600s", window3600)):
        for label, case in payload["cases"].items():
            for name, value in case.items():
                if isinstance(value, np.ndarray):
                    array_data[f"window_{horizon}_{label}_{name}"] = value
        payload["cases"] = {label: {key: value for key,value in case.items()
                                    if not isinstance(value, np.ndarray)}
                             for label,case in payload["cases"].items()}
    np.savez_compressed(arrays_path, **array_data)
    result["arrays_sha256"] = sha(arrays_path)
    result["arrays_path"] = str(arrays_path)
    (ROOT / "harness/evidence/UNIFIED_KMA_window_result_2026-10-05.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status":result["status"],"n_valid":report["n_valid"],
        "j_trace":report["j_trace"],
        "relative_decode_delta_ir105":result["observation"]["decode_delta"][5]},indent=2))


if __name__ == "__main__":
    main()
