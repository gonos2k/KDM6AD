#!/usr/bin/env python3
"""Consume a ready case core with the unchanged one-column T/Q analysis.

No native launcher, archive search, retry or external-observation fallback.
The core is one saved native background and one frozen 20-second forcing.
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import sys

import numpy as np
import torch

PACKET = Path(__file__).resolve().parent
ROOT = PACKET.parents[2]
sys.path.insert(0, str(PACKET))
from case_capture_adapter import load_module, prepare_capture_module, sha  # noqa: E402

LEGACY_DRIVER = ROOT / "harness/evidence/pr395_native_tq_intake_2026-10-10/run_analysis.py"
INTAKE_SOURCE = PACKET / "intake_native_case_v2.py"
CHANNELS = tuple(range(10, 17))
F64 = {"dtype": torch.float64}


def observation_values(manifest):
    """Read already-decoded L1B point values; do not reacquire/decode a scene."""
    obs = manifest["observation"]
    if obs["binding_status"] != "BOUND_GK2A_L1B_SCENE":
        raise ValueError("a native-only intake cannot authorize an observation-linked analysis")
    point = obs["nearest_pixel"]
    date = obs["scene_date"]
    with np.load(obs["payload_path"], allow_pickle=False) as payload:
        bt = payload[date + "_patch_bt_K"][2, 2, 2:].copy()
        dqf = payload[date + "_patch_reader_dqf"][2, 2, 2:].copy()
        lat = float(payload[date + "_patch_latitude_deg"][2, 2])
        lon = float(payload[date + "_patch_longitude_deg"][2, 2])
    names = ("wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133")
    expected_bt = np.array([point["bt_K_by_channel"][n] for n in names])
    expected_q = np.array([point["reader_dqf_by_channel"][n] for n in names])
    if (bt.shape != (7,) or not np.isfinite(bt).all() or not np.array_equal(bt, expected_bt)
            or not np.array_equal(dqf, expected_q) or np.any(dqf != 0)
            or lat != point["latitude_deg"] or lon != point["longitude_deg"]):
        raise ValueError("original decoded payload differs from the bound seven-channel point")
    return bt, dqf


def build_inputs(manifest, arrays, fixture_copy, template_fixture, legacy):
    """Value-only configuration; production M/H/minimizer remain unchanged."""
    from kdm6.state import State, Forcing

    bt, dqf = observation_values(manifest)
    obs = manifest["observation"]
    point = obs["nearest_pixel"]
    lat, lon = (float(arrays[f"native_surface__{n}"][0]) for n in ("latitude_deg", "longitude_deg"))
    # Same declared 2.5km admission radius, not a residual-based candidate move.
    a, b = math.radians(lat), math.radians(point["latitude_deg"])
    dlon = math.radians(lon - point["longitude_deg"])
    distance = 2 * 6371008.77 * math.asin(min(1.0, math.sqrt(
        math.sin((a - b) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dlon / 2) ** 2)))
    if distance > 2500:
        raise ValueError("case native background is outside the declared L1B point radius")
    xb = State(*(torch.as_tensor(arrays[f"background_initial_state__{f}"], **F64) for f in State._fields))
    forcing = Forcing(**{f: torch.as_tensor(arrays[f"forcing_window_0__{f}"], **F64) for f in Forcing._fields})
    xland = torch.as_tensor(arrays["native_surface__xland"][0:1], **F64)
    if not torch.equal(xland, torch.tensor([2.0], **F64)):
        raise ValueError("this bounded paired sea-surface configuration requires ocean XLAND=2")
    if "native_surface__seaice" in arrays and float(arrays["native_surface__seaice"][0]) != 0:
        raise ValueError("the declared sea-surface case is not sea ice")
    p_lay = arrays["p_lay_rttov_topdown_hPa"]
    p_half = arrays["p_half_rttov_topdown_hPa"]
    reader = legacy.load_module(legacy.NATIVE_READER, "case_native_geometry_reader")
    geometry, geometry_context = reader.ami_geometry(
        {"ami_lat_lon": [point["latitude_deg"], point["longitude_deg"]],
         "ami_metadata": {"geos": obs["reader_geos"]}}, {}, float(arrays["native_surface__HGT"][0]) / 1000)
    skin_path = template_fixture / "in/profiles/001/sfc/01/skin.txt"
    skin = legacy._read_scalar_fields(skin_path, "k0")
    skin["t"] = float(arrays["native_surface__TSK"][0])
    q2 = legacy.qv_to_q_ppmv_moist(torch.as_tensor(arrays["native_surface__Q2"][0:1], **F64),
                                  gas_units=2, qv_convention="mixing_ratio_kgkg_dry")
    surface = {"skin": skin, "near_surface": {"t2m": float(arrays["native_surface__T2"][0]),
               "q2m": float(q2[0]), "wind_u10m": float(arrays["native_surface__U10"][0]),
               "wind_v10m": float(arrays["native_surface__V10"][0]), "wind_fetch": 0.0}}
    input_cfg = legacy.RttovInputConfig("paired-case_00-GK2A-AMI", CHANNELS, surface=surface, geometry=geometry)
    profile_cfg = legacy.RttovProfileConfig(gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=torch.as_tensor(p_lay, **F64), rttov_level_pressure=torch.as_tensor(p_half, **F64),
        cloud=False, dry_number=True)
    clear_cfg = legacy.OsseObsConfig(run_k=None, profile_cfg=profile_cfg, input_cfg=input_cfg,
        obs_sigma=1.0, t_ref=torch.as_tensor(arrays["t_rttov_topdown_K"], **F64),
        q_ref=torch.as_tensor(arrays["q_rttov_topdown_ppmv"], **F64), t_blend_octaves=0.0, q_blend_octaves=0.0)
    rttov_cfg = {"channels": CHANNELS, "coef_id": "paired-case_00-GK2A-AMI", "fixture_case_dir": str(fixture_copy),
        "p_lay": p_lay.copy(), "p_half": p_half.copy(), "t_ref": arrays["t_rttov_topdown_K"].copy(),
        "q_ref": arrays["q_rttov_topdown_ppmv"].copy(), "rho_d": arrays["rho_d_native_bottomup_kg_m3"].copy(),
        "dry_number": True, "ami_kma_bt": True, "ncmin_land": 10.0, "ncmin_sea": 10.0,
        "t_blend_octaves": 0.0, "q_blend_octaves": 0.0, "surface": surface, "geometry": geometry}
    window = legacy.WindowConfig(dt=20.0, xland=xland, ncmin_land=10.0, ncmin_sea=10.0,
                                  normalized_dry=True, active_fields=("th", "qv"), params=None)
    run_manifest = {"case_id": manifest["case_id"], "obs_time": 1, "dt_s": 20, "max_iter": 3,
        "observation_sigma_K": 1.0, "observation_bias_K": 0.0, "huber_delta_K": 1.0,
        "th_sigma_K": 0.8, "qv_sigma_log": 0.08, "qv_levels_from_bottom": 12,
        "non_tq_state_sigmas_zero": True, "parameter_prior_active": [], "partition_control": False,
        "pseudo_rh": False, "warm_start": False, "automatic_retry": False, "ncmin_land": 10.0, "ncmin_sea": 10.0,
        "background_time": manifest["native_run"]["background_valid_time"],
        "nominal_observation_slot": manifest["native_run"]["nominal_obs_model_time"],
        "observation_slot_pixel_time_verified": False, "observation_sigma_bias_prior_assumptions": "unchanged exploration contract",
        "forcing_hypothesis": "one saved BG forcing held for a local20s KDM step, not a full host integration",
        "geometry_derivation": geometry_context, "native_L1B_distance_m": distance,
        "host_slot_comparison": "optional diagnostics only; no saved host slot required"}
    return {"xb": xb, "forcing": forcing, "y_bt": torch.as_tensor(bt, **F64).reshape(1, 7),
            "y_rq": torch.as_tensor(dqf, **F64).reshape(1, 7), "xland": xland,
            "clear_cfg": clear_cfg, "rttov_cfg": rttov_cfg, "window_config": window, "run_manifest": run_manifest}


def execute(manifest_path, npz_path, output_root, template_fixture):
    legacy = load_module(LEGACY_DRIVER, "case_analysis_pr395_primitives")
    if Path(template_fixture).resolve() != legacy.TEMPLATE_FIXTURE.resolve():
        raise ValueError("this bounded consumer requires the declared GK2A-AMI template fixture")
    intake = load_module(INTAKE_SOURCE, "case_analysis_intake")
    manifest, arrays = intake.load_bound_intake(manifest_path, npz_path)
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise FileExistsError("case analysis output root must be fresh; no retry/overwrite")
    source_paths = [Path(__file__), INTAKE_SOURCE, PACKET / "case_capture_adapter.py", LEGACY_DRIVER, legacy.CAPTURE_HELPER]
    pinned = {str(p): sha(p) for p in source_paths}
    output_root.mkdir(parents=True, mode=0o700)
    output_root.chmod(0o700)
    fixture_copy = output_root / "rttov_fixture"
    fixture = legacy._prepare_fixture_copy(Path(template_fixture), fixture_copy, arrays)
    ctx = build_inputs(manifest, arrays, fixture_copy, Path(template_fixture), legacy)
    source_before = {p: sha(Path(p)) for p in pinned}
    if source_before != pinned:
        raise ValueError("case sources changed during preparation")
    preflight = {"case_id": manifest["case_id"], "intake_manifest_sha256": sha(manifest_path),
                 "intake_npz_sha256": sha(npz_path), "source_bindings": pinned,
                 "fixture": fixture, "run_contract": ctx["run_manifest"], "analysis_executed": False}
    (output_root / "PREFLIGHT.json").write_text(json.dumps(preflight, indent=2) + "\n")
    with (output_root / "RUN_STARTED_ONCE.json").open("x") as stream:
        stream.write(json.dumps(preflight) + "\n")
    capture = prepare_capture_module()
    source_snapshot = capture._source_snapshot()
    fixture_paths = [fixture_copy / rel for rel in ("in/profiles/001/atm/p.txt", "in/profiles/001/atm/p_half.txt",
                     "in/profiles/001/atm/t.txt", "in/profiles/001/atm/q.txt", "in/channels.txt",
                     "in/profiles/001/atm/o3.txt", "in/profiles/001/atm/co2.txt",
                     "in/profiles/001/atm/simple_cloud.txt", "in/profiles/001/atm/hydro.txt",
                     "in/profiles/001/atm/hydro_frac.txt", "in/profiles/001/sfc/01/skin.txt",
                     "out/rttov_test.txt", "out/run.sh", "out/env.sh")]
    fixture_paths += [Path(fixture["ami_coefficient"]["path"]), Path(fixture["rttov_executable"]["path"])]
    asset_before = {str(p): sha(p) for p in fixture_paths}
    with mp.get_context("spawn").Pool(1) as pool:
        result = capture.run_capture(xb=ctx["xb"], forcings=(ctx["forcing"],), y_bt=ctx["y_bt"], y_rq=ctx["y_rq"],
            xland=ctx["xland"], clear_cfg=ctx["clear_cfg"], rttov_cfg=ctx["rttov_cfg"],
            window_config=ctx["window_config"], obs_time=1, pool=pool, max_iter=3, n_workers=1,
            private_checkpoint=output_root / "private/accepted_state.npz", public_receipt=output_root / "CAPTURE.json",
            case_root=output_root / "h_cases", native_intake_context_path=manifest_path,
            native_intake_context_sha256=preflight["intake_manifest_sha256"], native_intake_npz_path=npz_path,
            native_intake_npz_sha256=preflight["intake_npz_sha256"], run_manifest=ctx["run_manifest"])
    asset_after = {str(p): sha(p) for p in fixture_paths}
    audit = legacy._audit_initial_objectives(result, ctx["y_bt"])
    passed = (result.get("status") == "RETURNED_DIAGNOSTIC_ONLY" and audit["status"] == "CROSSCHECKED"
              and asset_before == asset_after and capture._source_snapshot() == source_snapshot)
    summary = {"schema": "kdm6ad_native_case_analysis_v1", "case_id": manifest["case_id"],
               "status": "RETURNED_CASE_DIAGNOSTIC" if passed else "FAILED_CASE_AUDIT",
               "capture": result, "objective_audit": audit, "case_sources": pinned,
               "execution_assets_before": asset_before, "execution_assets_after": asset_after,
               "physical_matchup_and_science_acceptance": "NOT_ASSESSED", "automatic_retry": False}
    with (output_root / "DRIVER_RESULT.json").open("x") as stream:
        json.dump(summary, stream, indent=2)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake-manifest", type=Path, required=True)
    parser.add_argument("--intake-npz", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--template-fixture", type=Path, required=True)
    args = parser.parse_args()
    os.environ.update(OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OMP_THREAD_LIMIT="1", VECLIB_MAXIMUM_THREADS="1")
    torch.set_num_threads(1)
    result = execute(args.intake_manifest, args.intake_npz, args.output_root, args.template_fixture)
    print(json.dumps({"case_id": result["case_id"], "status": result["status"]}))
    return 0 if result["status"] == "RETURNED_CASE_DIAGNOSTIC" else 1


if __name__ == "__main__":
    raise SystemExit(main())
