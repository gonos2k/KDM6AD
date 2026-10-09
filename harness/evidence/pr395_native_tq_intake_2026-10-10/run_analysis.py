#!/usr/bin/env python3
"""Run the predeclared one-shot PR395 seven-channel T/Q analysis.

This driver refuses to run until the fresh accepted-native intake manifest and
private NPZ pass their hash and exact-time gates. It calls the existing
``capture_tq_state.run_capture`` adapter once with one 20 s forcing and the
fixed max_iter=3 contract. It creates a private copied RTTOV template whose
pressure and gas files are regenerated from the validated intake, and supplies
native surface and candidate-derived geometry overrides on every H call.
There is no retry path.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
from pathlib import Path
import re
import shutil
import sys
import uuid

import netCDF4
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "oracle"))
from kdm6.da_driver import OsseObsConfig  # noqa: E402
from kdm6.da_window import WindowConfig  # noqa: E402
from kdm6.obs.model_profile_builder import (  # noqa: E402
    RttovProfileConfig, qv_to_q_ppmv_moist,
)
from kdm6.obs.rttov_case_writer import _resolve_coef_path, make_live_run_k  # noqa: E402
from kdm6.obs.rttov_input_builder import RttovInputConfig  # noqa: E402
from kdm6.obs.rttov_runner import DEFAULT_RTTOV_TIMEOUT  # noqa: E402
from kdm6.state import Forcing, State  # noqa: E402

INTAKE_MANIFEST = ROOT / "harness/evidence/pr395_native_tq_intake_2026-10-10/INTAKE.json"
INTAKE_NPZ = ROOT / "graphify-out/pr395-native-tq-intake-2026-10-10/private/native_column_8frame.npz"
OBS_RECEIPT = ROOT / "harness/evidence/pr395_observation_matchup_2026-10-10/RECEIPT.json"
CAPTURE_HELPER = ROOT / "harness/evidence/pr395_tq_state_capture_2026-10-10/capture_tq_state.py"
NATIVE_READER = ROOT / "harness/evidence/native358_artifact_diag_2026-10-08/recipe/run_native_kma_bt_frames.py"
TEMPLATE_FIXTURE = Path("/private/tmp/KDM6AD-viirs-native-run-20261007/comparison/results_failed_native_artifact_diag_055540_055800_retry2/case_00")
ANALYSIS_ROOT = ROOT / "graphify-out/pr395-native-tq-analysis-2026-10-10"
ONCE_LOCK = ANALYSIS_ROOT / "RUN_STARTED_ONCE.json"
RESULT_DIR = ROOT / "harness/evidence/pr395_tq_state_capture_2026-10-10"
EXPECTED_TIMES = [f"2025-07-19_05:{m:02d}:{s:02d}" for m, s in
                  ((55, 40), (56, 0), (56, 20), (56, 40),
                   (57, 0), (57, 20), (57, 40), (58, 0))]
CHANNELS = tuple(range(10, 17))
F64 = {"dtype": torch.float64}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_valid_intake(manifest_path: Path, npz_path: Path) -> tuple[dict, dict[str, np.ndarray]]:
    if not manifest_path.is_file() or not npz_path.is_file():
        raise FileNotFoundError("valid fresh-native intake manifest and private NPZ are required before H/RTTOV")
    manifest = json.loads(manifest_path.read_text())
    native_run = manifest.get("native_run", {})
    if (manifest.get("schema") != "pr395_native_tq_intake_v1"
            or manifest.get("status") != "READY_VALID_NATIVE_INTAKE"
            or native_run.get("exit_code") != 0
            or native_run.get("experiment_valid") is not True
            or native_run.get("model_completed_flag") is not True
            or native_run.get("actual_saved_times") != EXPECTED_TIMES
            or native_run.get("expected_saved_times") != EXPECTED_TIMES
            or native_run.get("run_id") != "mp337_viirs_norm2_dry1_055540_055800_358min_hist0_20261010_052612_p99148"
            or manifest.get("selected_column") != {"j": 86, "i": 48, "levels": 39}
            or manifest.get("analysis_executed") is not False
            or manifest.get("science_approved") is not False):
        raise ValueError("intake manifest does not meet the fixed pre-analysis native contract")
    if manifest["npz"].get("path") != str(npz_path.resolve()):
        raise ValueError("intake manifest names a different private NPZ path")
    npz_sha = sha256(npz_path)
    manifest_sha = sha256(manifest_path)
    if manifest["npz"].get("sha256") != npz_sha:
        raise ValueError("private NPZ SHA differs from the native intake manifest")
    with np.load(npz_path, allow_pickle=False) as archive:
        arrays = {key: archive[key].copy() for key in archive.files}
    return {"manifest": manifest, "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": manifest_sha, "npz_path": str(npz_path.resolve()),
            "npz_sha256": npz_sha}, arrays


def _read_scalar_fields(path: Path, prefix: str) -> dict:
    text = path.read_text()
    result = {}
    for name in ("surftype", "watertype", "salinity", "foam_fraction", "snow_fraction"):
        match = re.search(rf"(?im)^\s*{prefix}%{name}\s*=\s*([^,!\s]+)", text)
        if match is None:
            raise ValueError(f"static sea-surface template lacks {prefix}%{name}")
        value = float(match.group(1))
        result[name] = int(value) if name in ("surftype", "watertype") else value
    fastem = []
    for index in range(1, 6):
        match = re.search(rf"(?im)^\s*{prefix}%fastem\({index}\)\s*=\s*([^,!\s]+)", text)
        if match is None:
            raise ValueError(f"static sea-surface template lacks FASTEM({index})")
        fastem.append(float(match.group(1)))
    result["fastem"] = fastem
    return result


def _write_vector(path: Path, values) -> None:
    a = np.asarray(values, dtype=np.float64).reshape(-1)
    if not np.isfinite(a).all():
        raise ValueError(f"non-finite profile values for {path}")
    path.write_text("".join(f"{value:.17E}\n" for value in a))


def _prepare_fixture_copy(source: Path, target: Path, arrays: dict[str, np.ndarray]) -> dict:
    if not source.is_dir() or target.exists():
        raise FileNotFoundError(f"template must exist and new isolated fixture must not: {source} -> {target}")
    shutil.copytree(source, target)
    for path in (target, *target.rglob("*")):
        if path.is_dir():
            path.chmod(0o700)
        else:
            path.chmod(0o600 | (path.stat().st_mode & 0o111))
    out_dir = target / "out"
    for path in list(out_dir.iterdir()):
        if path.name in ("direct", "k") and path.is_dir():
            for child in path.iterdir():
                shutil.rmtree(child) if child.is_dir() else child.unlink()
            continue
        if path.name not in ("run.sh", "env.sh", "rttov_test.txt"):
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    atm = target / "in/profiles/001/atm"
    expected_layers = 66
    vectors = {
        "p.txt": arrays["p_lay_rttov_topdown_hPa"],
        "p_half.txt": arrays["p_half_rttov_topdown_hPa"],
        "t.txt": arrays["t_rttov_topdown_K"],
        "q.txt": arrays["q_rttov_topdown_ppmv"],
        "o3.txt": arrays["o3_rttov_topdown_ppmv"],
        "co2.txt": arrays["co2_rttov_topdown_ppmv"],
    }
    if any(np.asarray(v).size != expected_layers + (name == "p_half.txt")
           for name, v in vectors.items()):
        raise ValueError("native intake must provide the 66-layer/67-interface RTTOV grid")
    for name, values in vectors.items():
        _write_vector(atm / name, values)
    # Remove the prior paired profile's cloud state from the template. The
    # all-sky writer will generate current State cloud fields on every H call.
    hydro = np.loadtxt(atm / "hydro.txt", dtype=np.float64)
    if hydro.shape != (expected_layers, 8):
        raise ValueError("copied AMI cloud template hydro layout must be [66,8]")
    np.savetxt(atm / "hydro.txt", np.zeros_like(hydro), fmt="%.17E")
    hydro_frac = atm / "hydro_frac.txt"
    if not hydro_frac.is_file():
        raise FileNotFoundError("copied all-sky template must include hydro_frac.txt")
    np.loadtxt(hydro_frac, dtype=np.float64, skiprows=1)
    hydro_frac.write_text("0.000000E+00\n" + "".join("0.000000E+00\n" for _ in range(expected_layers)))
    (atm / "hydro_deff.txt").unlink(missing_ok=True)
    (target / "in/channels.txt").write_text("\n".join(str(channel) for channel in CHANNELS) + "\n")
    # The copied pair is only a coefficient/template and static sea-surface
    # source. Ensure no fixture simple-cloud fallback can contribute to H.
    simple_path = atm / "simple_cloud.txt"
    simple = simple_path.read_text()
    simple, count = re.subn(r"(?im)^(\s*cfraction\s*=\s*)[^!\n]+$",
                            lambda m: m.group(1) + "0.0", simple)
    if count != 1:
        raise ValueError("copied simple_cloud fixture must have exactly one CFraction field")
    simple_path.write_text(simple)
    nml = target / "out/rttov_test.txt"
    solar = re.findall(r"(?im)^\s*defn%opts%rt_all%solar\s*=\s*([^!\n]+)", nml.read_text())
    if [s.strip().rstrip(",").upper() for s in solar] != [".FALSE."]:
        raise ValueError("thermal AMI H requires the copied RTTOV fixture to be solar-disabled")
    files = [atm / name for name in (*vectors.keys(), "simple_cloud.txt", "hydro.txt", "hydro_frac.txt")]
    files.extend((nml, target / "in/channels.txt", source / "in/profiles/001/sfc/01/skin.txt"))
    coefficient = _resolve_coef_path(target)
    if not coefficient.is_file():
        raise FileNotFoundError(f"paired AMI coefficient is not available: {coefficient}")
    run_script = target / "out/run.sh"
    executable_matches = re.findall(r"(?m)^\s*(/[^\s]+rttov_test\.exe)\b", run_script.read_text())
    if len(executable_matches) != 1:
        raise ValueError("paired RTTOV run.sh must identify one absolute rttov_test.exe")
    rttov_executable = Path(executable_matches[0]).resolve()
    if not rttov_executable.is_file():
        raise FileNotFoundError(f"paired RTTOV executable is not available: {rttov_executable}")
    return {"source_template": str(source), "source_template_sha256": sha256(source / "out/rttov_test.txt"),
            "prepared_fixture_copy": str(target), "prepared_files_sha256": {
                str(path.relative_to(target) if path.is_relative_to(target) else path): sha256(path)
                for path in files},
            "ami_coefficient": {"path": str(coefficient), "sha256": sha256(coefficient)},
            "rttov_executable": {"path": str(rttov_executable), "sha256": sha256(rttov_executable)},
            "pressure_grid_replaced_from_native_intake": True,
            "T_Q_and_cloud_replaced_on_each_H_call": True,
            "O3_CO2_replaced_from_fixed_upper_reference_on_intake_grid": True,
            "simple_cloud_fraction": 0.0,
            "solar": False,
            "geometry_and_dynamic_surface": "supplied from fixed AMI candidate and fresh native selected column on each H input"}


def build_run_inputs(arrays: dict[str, np.ndarray], manifest: dict,
                     observation_receipt: dict, fixture_copy: Path) -> dict:
    if (observation_receipt.get("schema") != "pr395_observation_matchup_receipt_v1"
            or observation_receipt.get("physical_matchup_approved") is not False
            or observation_receipt.get("external_model_or_reanalysis_acquired") is not False):
        raise ValueError("observation receipt identity or science-limit fields differ")
    candidate = observation_receipt["ami_candidate_result"]
    if candidate.get("row_col_zero_based") != [320, 48]:
        raise ValueError("AMI candidate changed from fixed row/column 320/48")
    if observation_receipt["fixed_candidate"]["native_j_i_zero_based"] != [86, 48]:
        raise ValueError("native candidate changed from fixed j/i 86/48")
    if observation_receipt["fixed_candidate"]["viirs_row_col_zero_based"] != [205, 27]:
        raise ValueError("VIIRS candidate changed from fixed row/column 205/27")
    if observation_receipt["channel_order"][2:9] != [
            "wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133"]:
        raise ValueError("AMI physical channel names 10..16 changed")
    y_bt_np = np.asarray(candidate["bt_K"][2:9], dtype=np.float64)
    y_rq_np = np.asarray(candidate["dqf"][2:9], dtype=np.float64)
    if y_bt_np.shape != (7,) or y_rq_np.shape != (7,) or not np.isfinite(y_bt_np).all():
        raise ValueError("AMI physical channels 10..16 must contain finite BT and DQF values")

    state = State(*(torch.as_tensor(arrays[f"background_initial_state__{name}"], **F64)
                    for name in State._fields))
    forcing = Forcing(**{name: torch.as_tensor(arrays[f"forcing_window_0__{name}"], **F64)
                         for name in Forcing._fields})
    if tuple(state.th.shape) != (1, 39) or tuple(forcing.p.shape) != (1, 39):
        raise ValueError("validated native State and Forcing must be [1,39]")
    xland = torch.as_tensor(arrays["native_surface__xland"][0:1], **F64)
    if not torch.equal(xland, torch.tensor([2.0], **F64)):
        raise ValueError("selected fresh native column must remain open ocean XLAND=2")
    if "native_surface__seaice" in arrays and float(arrays["native_surface__seaice"][0]) != 0.0:
        raise ValueError("selected fresh native column is sea ice")
    rho_d = arrays["rho_d_native_bottomup_kg_m3"].copy()
    if not np.isfinite(rho_d).all() or rho_d.shape != (1, 39):
        raise ValueError("frozen optical dry density must be finite [1,39]")

    p_lay = np.asarray(arrays["p_lay_rttov_topdown_hPa"], dtype=np.float64)
    p_half = np.asarray(arrays["p_half_rttov_topdown_hPa"], dtype=np.float64)
    t_ref = np.asarray(arrays["t_rttov_topdown_K"], dtype=np.float64)
    q_ref = np.asarray(arrays["q_rttov_topdown_ppmv"], dtype=np.float64)
    if (p_lay.shape != (66,) or p_half.shape != (67,)
            or t_ref.shape != p_lay.shape or q_ref.shape != p_lay.shape
            or not np.array_equal(forcing.p.detach().cpu().numpy()[0, ::-1] / 100.0, p_lay[-39:])):
        raise ValueError("RTTOV grid must preserve the exact native pressure suffix without remapping")
    p8w_bottom = arrays["p_half_native_bottomup_Pa"]
    if p8w_bottom.dtype != np.float32 or p8w_bottom.shape != (40,):
        raise ValueError("native P8W must remain the explicitly transcribed REAL(4) interface vector")
    if not np.array_equal(p8w_bottom[::-1].astype(np.float64) / 100.0, p_half[-40:]):
        raise ValueError("RTTOV interface grid does not retain the exact native P8W suffix")

    reader = load_module(NATIVE_READER, "pr395_native_geometry_reader")
    ami = {"ami_lat_lon": candidate["latitude_longitude"],
           "ami_metadata": {"geos": candidate["geos"]}}
    hgt_m = float(arrays["native_surface__HGT"][0])
    geometry, geometry_context = reader.ami_geometry(ami, candidate["geos"], hgt_m / 1000.0)
    skin_path = TEMPLATE_FIXTURE / "in/profiles/001/sfc/01/skin.txt"
    static_skin = _read_scalar_fields(skin_path, "k0")
    static_skin["t"] = float(arrays["native_surface__TSK"][0])
    q2 = torch.as_tensor([float(arrays["native_surface__Q2"][0])], **F64)
    q2_ppmv = float(qv_to_q_ppmv_moist(
        q2, gas_units=2, qv_convention="mixing_ratio_kgkg_dry")[0])
    surface = {
        "skin": static_skin,
        "near_surface": {
            "t2m": float(arrays["native_surface__T2"][0]),
            "q2m": q2_ppmv,
            "wind_u10m": float(arrays["native_surface__U10"][0]),
            "wind_v10m": float(arrays["native_surface__V10"][0]),
            "wind_fetch": 0.0,
        },
    }
    input_cfg = RttovInputConfig("paired-case_00-GK2A-AMI", CHANNELS,
                                 surface=surface, geometry=geometry)
    profile_cfg = RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=torch.as_tensor(p_lay, **F64),
        rttov_level_pressure=torch.as_tensor(p_half, **F64),
        cloud=False, dry_number=True)
    clear_cfg = OsseObsConfig(
        run_k=None, profile_cfg=profile_cfg, input_cfg=input_cfg,
        obs_sigma=1.0, t_ref=torch.as_tensor(t_ref, **F64),
        q_ref=torch.as_tensor(q_ref, **F64), t_blend_octaves=0.0,
        q_blend_octaves=0.0)
    rttov_cfg = {
        "channels": CHANNELS,
        "coef_id": "paired-case_00-GK2A-AMI",
        "fixture_case_dir": str(fixture_copy),
        "p_lay": p_lay.copy(), "p_half": p_half.copy(),
        "t_ref": t_ref.copy(), "q_ref": q_ref.copy(), "rho_d": rho_d,
        "dry_number": True, "ami_kma_bt": True,
        "ncmin_land": 10.0, "ncmin_sea": 10.0,
        "t_blend_octaves": 0.0, "q_blend_octaves": 0.0,
        "geometry": geometry, "surface": surface,
    }
    window_config = WindowConfig(
        dt=20.0, xland=xland, ncmin_land=10.0, ncmin_sea=10.0,
        normalized_dry=True, active_fields=("th", "qv"), params=None)
    run_manifest = {
        "obs_time": 1, "dt_s": 20, "max_iter": 3,
        "observation_sigma_K": 1.0, "observation_bias_K": 0.0,
        "huber_delta_K": 1.0, "th_sigma_K": 0.8,
        "qv_sigma_log": 0.08, "qv_levels_from_bottom": 12,
        "non_tq_state_sigmas_zero": True, "parameter_prior_active": [],
        "partition_control": False, "pseudo_rh": False,
        "warm_start": False, "automatic_retry": False,
        "ncmin_land": 10.0, "ncmin_sea": 10.0,
        "background_time": EXPECTED_TIMES[0],
        "nominal_observation_slot": EXPECTED_TIMES[1],
        "observation_slot_pixel_time_verified": False,
        "fixed_candidate": {"viirs_row_col_zero_based": [205, 27],
                             "ami_row_col_zero_based": [320, 48],
                             "native_j_i_zero_based": [86, 48]},
        "observation_receipt_sha256": sha256(OBS_RECEIPT),
        "observation_bt_K_channels_10_16": y_bt_np.tolist(),
        "observation_dqf_channels_10_16": y_rq_np.tolist(),
        "new_geometry_candidate": geometry,
        "geometry_derivation": geometry_context,
        "new_native_surface_candidate": surface,
        "surface_sources": {
            "dynamic_skin_temperature_and_near_surface": "fresh 05:55:40 native selected column",
            "native_q2_conversion": "qv_to_q_ppmv_moist, mixing_ratio_kgkg_dry, gas_units=2",
            "static_surface_parameters": str(skin_path),
            "static_surface_parameters_sha256": sha256(skin_path),
            "wind_fetch_m": 0.0,
            "wind_fetch_reason": "thermal-only H; copied RTTOV namelist asserts solar=false",
        },
        "template_usage": "copied paired case is only a coefficient/namelist and static sea-surface template; pressure, interfaces, T/Q, O3/CO2 and geometry/dynamic surface are replaced from current native/observation inputs; H regenerates cloud profiles from current State",
        "science_accepted": False,
        "analysis_environment": {"python": sys.executable,
                                  "torch_version": torch.__version__,
                                  "netcdf4_version": netCDF4.__version__,
                                  "threads": 1},
        "rttov_timeout_s": DEFAULT_RTTOV_TIMEOUT,
    }
    return {"xb": state, "forcing": forcing, "xland": xland,
            "y_bt": torch.as_tensor(y_bt_np, **F64).reshape(1, 7),
            "y_rq": torch.as_tensor(y_rq_np, **F64).reshape(1, 7),
            "clear_cfg": clear_cfg, "rttov_cfg": rttov_cfg,
            "window_config": window_config, "run_manifest": run_manifest,
            "surface": surface, "geometry": geometry,
            "native_intake": manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake-manifest", type=Path, default=INTAKE_MANIFEST)
    parser.add_argument("--intake-npz", type=Path, default=INTAKE_NPZ)
    parser.add_argument("--observation-receipt", type=Path, default=OBS_RECEIPT)
    parser.add_argument("--template-fixture", type=Path, default=TEMPLATE_FIXTURE)
    parser.add_argument("--rttov-timeout", type=float, default=DEFAULT_RTTOV_TIMEOUT)
    args = parser.parse_args()
    if args.rttov_timeout != DEFAULT_RTTOV_TIMEOUT:
        raise ValueError("RTTOV timeout must stay at the existing bounded default")
    if args.template_fixture.resolve() != TEMPLATE_FIXTURE.resolve():
        raise ValueError("only the declared fixed paired case template is allowed")
    os.environ.update(OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                      OMP_THREAD_LIMIT="1", VECLIB_MAXIMUM_THREADS="1")
    torch.set_num_threads(1)

    intake_binding, arrays = require_valid_intake(args.intake_manifest, args.intake_npz)
    if args.observation_receipt.resolve() != OBS_RECEIPT.resolve():
        raise ValueError("this bounded driver is pinned to the evidence-backed fixed PR395 observation packet")
    observation_receipt = json.loads(args.observation_receipt.read_text())
    token = uuid.uuid4().hex[:10]
    ANALYSIS_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    ANALYSIS_ROOT.chmod(0o700)
    run_root = ANALYSIS_ROOT / f"run-{token}"
    run_root.mkdir(parents=True, exist_ok=False)
    run_root.chmod(0o700)
    fixture_copy = run_root / "rttov_fixture"
    fixture_info = _prepare_fixture_copy(args.template_fixture.resolve(), fixture_copy, arrays)
    ctx = build_run_inputs(arrays, intake_binding["manifest"], observation_receipt, fixture_copy)
    ctx["rttov_cfg"]["rttov_timeout"] = args.rttov_timeout
    ctx["run_manifest"]["native_intake_manifest_sha256"] = intake_binding["manifest_sha256"]
    ctx["run_manifest"]["native_intake_npz_sha256"] = intake_binding["npz_sha256"]
    run_root_manifest = {
        "schema": "pr395_native_tq_analysis_preflight_v1",
        "status": "READY_TO_CALL_EXISTING_CAPTURE_HELPER",
        "run_root": str(run_root),
        "intake_binding": intake_binding,
        "observation_receipt_sha256": sha256(args.observation_receipt),
        "template_fixture": fixture_info,
        "fixed_run_contract": ctx["run_manifest"],
        "state_shape": list(ctx["xb"].th.shape),
        "forcing_shape": list(ctx["forcing"].p.shape),
        "rttov_layer_grid_shape": list(ctx["rttov_cfg"]["p_lay"].shape),
        "rttov_interface_grid_shape": list(ctx["rttov_cfg"]["p_half"].shape),
        "all_inputs_finite": all(np.isfinite(a).all() for a in arrays.values()),
        "H_and_analysis_executed": False,
        "retries_configured": False,
    }
    preflight = run_root / "preflight.json"
    preflight.write_text(json.dumps(run_root_manifest, indent=2, sort_keys=True) + "\n")
    preflight.chmod(0o600)

    # A durable exclusive marker prevents a second CLI invocation from making a
    # second analysis if the caller or this process is restarted after launch.
    try:
        fd = os.open(ONCE_LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"the single permitted PR395 analysis was already claimed: {ONCE_LOCK}") from exc
    with os.fdopen(fd, "w") as stream:
        stream.write(json.dumps({"status": "RUN_STARTED_ONCE", "run_root": str(run_root),
                                 "run_token": token, "native_run_id": ctx["native_intake"]["native_run"]["run_id"],
                                 "intake_manifest_sha256": intake_binding["manifest_sha256"],
                                 "intake_npz_sha256": intake_binding["npz_sha256"]},
                                sort_keys=True) + "\n")

    capture = load_module(CAPTURE_HELPER, "pr395_tq_state_capture")
    case_root = run_root / "h_cases"
    private_checkpoint = ROOT / (
        f"graphify-out/pr395-tq-state-capture-2026-10-10/private/accepted-final-{token}.npz")
    public_receipt = RESULT_DIR / f"RESULT_{token}.json"
    driver_receipt = RESULT_DIR / f"DRIVER_{token}.json"
    source_fixture_hash_before = {rel: sha256(fixture_copy / rel) for rel in (
        "in/profiles/001/atm/p.txt", "in/profiles/001/atm/p_half.txt",
        "in/profiles/001/atm/o3.txt", "in/profiles/001/atm/co2.txt",
        "in/profiles/001/atm/simple_cloud.txt", "out/rttov_test.txt",
        "out/run.sh", "out/env.sh")}
    coefficient_path = _resolve_coef_path(fixture_copy)
    executable_path = Path(fixture_info["rttov_executable"]["path"])
    execution_assets_before = {
        "run_sh": {"path": str(fixture_copy / "out/run.sh"),
                   "sha256": sha256(fixture_copy / "out/run.sh")},
        "env_sh": {"path": str(fixture_copy / "out/env.sh"),
                   "sha256": sha256(fixture_copy / "out/env.sh")},
        "executable": {"path": str(executable_path), "sha256": sha256(executable_path)},
        "coefficient": {"path": str(coefficient_path), "sha256": sha256(coefficient_path)},
    }
    pool = None
    try:
        pool = mp.get_context("spawn").Pool(1)
        result = capture.run_capture(
            xb=ctx["xb"], forcings=(ctx["forcing"],),
            y_bt=ctx["y_bt"], y_rq=ctx["y_rq"], xland=ctx["xland"],
            clear_cfg=ctx["clear_cfg"], rttov_cfg=ctx["rttov_cfg"],
            window_config=ctx["window_config"], obs_time=1, pool=pool,
            private_checkpoint=private_checkpoint, public_receipt=public_receipt,
            case_root=case_root,
            native_intake_context_path=args.intake_manifest,
            native_intake_context_sha256=intake_binding["manifest_sha256"],
            native_intake_npz_path=args.intake_npz,
            native_intake_npz_sha256=intake_binding["npz_sha256"],
            run_manifest=ctx["run_manifest"], max_iter=3, n_workers=1,
            rttov_timeout=args.rttov_timeout)
    finally:
        if pool is not None:
            pool.close()
            pool.join()
    source_fixture_hash_after = {rel: sha256(fixture_copy / rel) for rel in source_fixture_hash_before}
    execution_assets_after = {
        "run_sh": {"path": str(fixture_copy / "out/run.sh"),
                   "sha256": sha256(fixture_copy / "out/run.sh")},
        "env_sh": {"path": str(fixture_copy / "out/env.sh"),
                   "sha256": sha256(fixture_copy / "out/env.sh")},
        "executable": {"path": str(executable_path), "sha256": sha256(executable_path)},
        "coefficient": {"path": str(coefficient_path), "sha256": sha256(coefficient_path)},
    }
    logical_calls = result.get("logical_h_calls", [])
    background_probe = next((call for call in logical_calls if call.get("grad") is False), None)
    background_probe_hash_matches = bool(
        background_probe is not None
        and background_probe.get("state_sha256")
        == result.get("state_array_sha256", {}).get("background_slot"))
    driver_result = {
        "schema": "pr395_native_tq_analysis_driver_v1",
        "status": result.get("status"),
        "preflight_path": str(preflight),
        "capture_receipt_path": str(public_receipt),
        "capture_receipt_sha256": sha256(public_receipt) if public_receipt.exists() else None,
        "private_checkpoint": result.get("private_checkpoint"),
        "intake_manifest_sha256": intake_binding["manifest_sha256"],
        "intake_npz_sha256": intake_binding["npz_sha256"],
        "rttov_fixture_immutable_during_analysis": source_fixture_hash_before == source_fixture_hash_after,
        "fixture_hashes_before": source_fixture_hash_before,
        "fixture_hashes_after": source_fixture_hash_after,
        "rttov_execution_assets_stable_during_analysis": execution_assets_before == execution_assets_after,
        "rttov_execution_assets_before": execution_assets_before,
        "rttov_execution_assets_after": execution_assets_after,
        "background_probe": {
            "status": ("CAPTURED" if background_probe is not None else "NOT_CAPTURED"),
            "state_hash_matches_recorded_background_slot": background_probe_hash_matches,
            "Jo0_huber": None if background_probe is None else background_probe.get("J_huber"),
            "BT_K": None if background_probe is None else background_probe.get("BT_K"),
            "rad_quality": None if background_probe is None else background_probe.get("rad_quality"),
            "state_sha256": None if background_probe is None else background_probe.get("state_sha256"),
            "forcing_sha256": None if background_probe is None else background_probe.get("forcing_sha256"),
            "time": "2025-07-19_05:56:00",
            "state_semantics": "H applied to the existing one-step M(xb) observation-slot state at obs_time=1",
            "native_055540_direct_H_executed": False,
        },
        "analysis_result": result,
        "physical_matchup_and_science_acceptance": "NOT_ASSESSED",
        "pixel_time_verified": False,
        "science_accepted": False,
        "automatic_retry": False,
    }
    with driver_receipt.open("x") as stream:
        stream.write(json.dumps(driver_result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result.get("status"), "capture_receipt": str(public_receipt),
                      "driver_receipt": str(driver_receipt),
                      "checkpoint": result.get("private_checkpoint")}, indent=2))
    return 0 if (result.get("status") == "RETURNED_DIAGNOSTIC_ONLY"
                 and background_probe_hash_matches) else 1


if __name__ == "__main__":
    raise SystemExit(main())
