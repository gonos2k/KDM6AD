#!/usr/bin/env python3
"""Bounded PR394 actual RTTOV/T-Q integration diagnostic.

Only `--phase baseline` and `--phase analysis` are supported. Both use the
cached selected-column checkpoint and the immutable paired case_00 fixture;
neither reads the large forecast or launches the WRF host. The baseline phase
is a one-profile actual RTTOV H preflight and must be reviewed before the
one-iteration analysis phase is started.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import traceback
import uuid
from pathlib import Path

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "oracle"))

from kdm6.da_cvt import make_default_cvt  # noqa: E402
from kdm6.da_driver import (  # noqa: E402
    OsseObsConfig, _blend_above_model_top,
    batched_allsky_bt,
)
from kdm6.da_dual import default_param_prior, params_from_vtheta  # noqa: E402
from kdm6.da_single_column import run_single_column_analysis  # noqa: E402
from kdm6.da_window import WindowConfig, collect_window_trajectory  # noqa: E402
from kdm6.obs.model_profile_builder import (  # noqa: E402
    RttovProfileConfig, model_to_rttov_tensors,
)
from kdm6.obs.rttov_case_writer import (  # noqa: E402
    _resolve_coef_path, make_live_run_k,
)
from kdm6.obs.rttov_input_builder import RttovInputConfig  # noqa: E402
from kdm6.obs.rttov_obs_operator import _build_mask  # noqa: E402
from kdm6.obs.rttov_runner import DEFAULT_RTTOV_TIMEOUT  # noqa: E402
from kdm6.obs.obs_loss import compute_obs_loss  # noqa: E402
from kdm6.rttov_bridge import freeze_dry_air_density  # noqa: E402
from kdm6.state import Forcing, State  # noqa: E402

F64 = {"dtype": torch.float64}
CHANNELS = tuple(range(10, 17))
CHECKPOINT = ROOT / "graphify-out/pr391-red/selected_column_checkpoint.npz"
PAIRED = Path(
    "/private/tmp/KDM6AD-viirs-native-run-20261007/comparison/"
    "results_failed_native_artifact_diag_055540_055800_retry2/case_00")
FRAME_RESULT = PAIRED.parent / "native8frame_failed_run_artifact_diagnostic_enriched.json"
OLD_COST_RESULT = ROOT / "harness/evidence/pr391_tq_cost_2026-10-09/RESULT.json"
EXECUTION_PATH_RESULT = ROOT / "harness/evidence/pr391_tq_cost_2026-10-09/ExecutionPathIdentity.json"
RESULT_PATH = ROOT / "harness/evidence/pr394_real_tq_diagnostic_2026-10-10/RESULT.json"
EVIDENCE_DIR = RESULT_PATH.parent
RUNS_BASE = ROOT / "graphify-out/pr394-real-tq-diagnostic-2026-10-10"
SOURCE_FILES = (
    "oracle/kdm6/da_single_column.py",
    "oracle/kdm6/da_fulldomain.py",
    "oracle/kdm6/da_dual.py",
    "oracle/kdm6/da_window.py",
    "oracle/kdm6/da_cvt.py",
    "oracle/kdm6/da_driver.py",
    "oracle/kdm6/runtime.py",
    "oracle/kdm6/coordinator.py",
    "oracle/kdm6/thermo.py",
    "oracle/kdm6/fconst.py",
    "oracle/kdm6/rttov_bridge.py",
    "oracle/kdm6/obs/allsky_shard.py",
    "oracle/kdm6/obs/model_profile_builder.py",
    "oracle/kdm6/obs/rttov_input_builder.py",
    "oracle/kdm6/obs/rttov_obs_operator.py",
    "oracle/kdm6/obs/rttov_case_writer.py",
    "oracle/kdm6/obs/rttov_runner.py",
    "oracle/kdm6/obs/ami_bt_coordinate.py",
    "oracle/kdm6/obs/obs_loss.py",
)
PAIR_FILES = (
    "in/profiles/001/atm/p.txt",
    "in/profiles/001/atm/p_half.txt",
    "in/profiles/001/atm/t.txt",
    "in/profiles/001/atm/q.txt",
    "in/profiles/001/atm/o3.txt",
    "in/profiles/001/atm/co2.txt",
    "in/profiles/001/atm/hydro.txt",
    "in/profiles/001/atm/hydro_deff.txt",
    "in/profiles/001/atm/hydro_frac.txt",
    "in/profiles/001/atm/simple_cloud.txt",
    "in/profiles/001/gas_units.txt",
    "in/profiles/001/angles.txt",
    "in/profiles/001/sfc/01/skin.txt",
    "in/profiles/001/sfc/01/near_surface.txt",
    "in/channels.txt",
    "in/lprofiles.txt",
    "in/coef.txt",
    "out/rttov_test.txt",
    "out/run.sh",
)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def array_sha(values) -> str:
    arr = np.ascontiguousarray(values, dtype=np.float64)
    return hashlib.sha256(arr.tobytes()).hexdigest()


def state_hashes(state: State) -> dict:
    return {name: array_sha(getattr(state, name).detach().cpu().numpy())
            for name in State._fields}


def forcing_hashes(forcing: Forcing) -> dict:
    return {name: array_sha(getattr(forcing, name).detach().cpu().numpy())
            for name in Forcing._fields}


def source_snapshot() -> dict:
    return {name: sha(ROOT / name) for name in SOURCE_FILES}


def pair_snapshot() -> dict:
    return {name: sha(PAIRED / name) for name in PAIR_FILES}


def load_context() -> dict:
    if not CHECKPOINT.is_file() or not PAIRED.is_dir() or not FRAME_RESULT.is_file():
        raise FileNotFoundError("cached checkpoint, paired case_00, or observation receipt is missing")
    if not OLD_COST_RESULT.is_file() or not EXECUTION_PATH_RESULT.is_file():
        raise FileNotFoundError("PR391 cost or execution-path identity receipt is missing")
    with np.load(CHECKPOINT) as archive_npz:
        archive = {key: archive_npz[key].copy() for key in archive_npz.files}
    frame = json.loads(FRAME_RESULT.read_text())
    cost = json.loads(OLD_COST_RESULT.read_text())
    execution_path = json.loads(EXECUTION_PATH_RESULT.read_text())
    scenarios = {row["scenario"]: row for row in cost["scenarios"]}
    checkpoint_sha = sha(CHECKPOINT)
    frame_sha = sha(FRAME_RESULT)
    cost_sha = sha(OLD_COST_RESULT)
    if tuple(frame["rttov_channel_ids"]) != tuple(range(8, 17)):
        raise ValueError("paired frame receipt channel list changed")
    if cost["cost_contract"]["channels_1based"] != list(CHANNELS):
        raise ValueError("saved cost receipt does not use AMI 10..16")
    if (cost["cost_contract"]["sigma_K"] != 1.0
            or cost["cost_contract"]["bias_K"] != 0.0
            or cost["cost_contract"]["huber_delta"] != 1.0):
        raise ValueError("saved cost receipt does not match sigma=1/bias=0/Huber=1")
    y_bt = torch.as_tensor(frame["observation_bt_K"][2:9], **F64).reshape(1, 7)
    y_rq = torch.as_tensor(frame["observation_dqf"][2:9], **F64).reshape(1, 7)
    obs = {"bt": y_bt, "obs_quality": y_rq,
           "channel_gate": torch.ones((1, 7), **F64)}
    if not torch.equal(y_bt[0], torch.as_tensor(scenarios["baseline"]["observation_bt_K"], **F64)):
        raise ValueError("frame observation BT values differ from saved cost baseline")
    # Observation DQF and model-emitted RTTOV rad_quality are separate fields;
    # the old cost receipt records only the latter. Do not compare them as if
    # they had a shared meaning.

    xb = State(*(torch.as_tensor(archive[f"state_in_baseline_{name}"].copy(), **F64)
                 .reshape(1, -1) for name in State._fields))
    forcing = Forcing(
        rho=torch.as_tensor(archive["rho_m_forcing_native_bottomup_kg_m3"].copy(), **F64).reshape(1, -1),
        pii=torch.as_tensor(archive["pii_native_bottomup"].copy(), **F64).reshape(1, -1),
        p=torch.as_tensor(archive["p_center_native_bottomup_Pa"].copy(), **F64).reshape(1, -1),
        delz=torch.as_tensor(archive["delz_native_bottomup_m"].copy(), **F64).reshape(1, -1),
    )
    rho_d = torch.as_tensor(
        archive["rho_d_optical_reference_native_bottomup_kg_m3"].copy(), **F64).reshape(1, -1)
    xland = torch.as_tensor(archive["xland"].copy(), **F64).reshape(1)
    if xb.th.shape != (1, 39) or forcing.p.shape != (1, 39):
        raise ValueError("cached baseline is not the expected one-column 39-level state")
    if not torch.equal(rho_d, freeze_dry_air_density(xb, forcing)):
        raise ValueError("cached optical density is not frozen from the baseline/forcing")
    if not torch.equal(xland, torch.tensor([2.0], **F64)):
        raise ValueError("cached selected column is no longer sea XLAND=2")

    pair_atm = PAIRED / "in/profiles/001/atm"
    p_lay = torch.as_tensor(np.loadtxt(pair_atm / "p.txt"), **F64)
    p_half = torch.as_tensor(np.loadtxt(pair_atm / "p_half.txt"), **F64)
    t_ref = torch.as_tensor(np.loadtxt(pair_atm / "t.txt"), **F64)
    q_ref = torch.as_tensor(np.loadtxt(pair_atm / "q.txt"), **F64)
    if (p_lay.shape != (66,) or p_half.shape != (67,)
            or t_ref.shape != p_lay.shape or q_ref.shape != p_lay.shape):
        raise ValueError("immutable paired case_00 is not the 66/67 layer AMI profile")
    if not torch.equal(forcing.p.flip(-1) / 100.0, p_lay[-39:].expand(1, -1)):
        raise ValueError("checkpoint native center pressure suffix differs from paired case")
    p_half_native = torch.as_tensor(
        archive["p_interface_wrf_native_bottomup_Pa"][::-1].copy(), **F64) / 100.0
    if not torch.equal(p_half_native, p_half[-40:]):
        raise ValueError("checkpoint native interface pressure suffix differs from paired case")

    baseline_identity = scenarios["baseline"]["profile_identity"]
    for name in ("p.txt", "p_half.txt", "t.txt", "q.txt", "o3.txt", "co2.txt"):
        expected = baseline_identity["executed_profile_hashes"][name]
        if sha(pair_atm / name) != expected:
            raise ValueError(f"immutable paired {name} does not match the saved baseline execution")
    # The exact byte source for saved geometry/surface is part of the existing
    # execution-path receipt. Do not read the historical run_baseline scratch.
    pair_inputs = cost["inputs"]
    if sha(PAIRED / "in/profiles/001/angles.txt") != pair_inputs[
            "paired_geometry_sha256"]:
        raise ValueError("paired geometry does not match its immutable identity receipt")
    for key, rel in (("skin", "in/profiles/001/sfc/01/skin.txt"),
                     ("near_surface", "in/profiles/001/sfc/01/near_surface.txt")):
        if sha(PAIRED / rel) != pair_inputs["paired_surface_sha256"][key]:
            raise ValueError(f"paired surface {key} differs from its immutable identity receipt")

    namelist = (PAIRED / "out/rttov_test.txt").read_text()
    solar = re.findall(r"(?im)^\s*defn%opts%rt_all%solar\s*=\s*([^!\n]+)", namelist)
    simple_text = (pair_atm / "simple_cloud.txt").read_text()
    simple_cf = re.findall(r"(?im)^\s*cfraction\s*=\s*([^!\n]+)", simple_text)
    if ([value.strip().rstrip(",").upper() for value in solar] != [".FALSE."]
            or len(simple_cf) != 1 or float(simple_cf[0]) != 0.0):
        raise ValueError("paired case must remain thermal-only with simple-cloud fraction 0")
    from kdm6.obs.rttov_case_writer import _resolve_coef_path
    coefficient = _resolve_coef_path(PAIRED)
    exe = Path(baseline_identity["rttov_executable_path"])
    if not exe.is_file() or not coefficient.is_file():
        raise FileNotFoundError("saved RTTOV executable or AMI coefficient path is missing")
    if (sha(exe) != baseline_identity["rttov_executable_sha256"]
            or sha(coefficient) != baseline_identity["coefficient_sha256"]):
        raise ValueError("RTTOV executable or AMI coefficient differs from saved cost provenance")

    params = params_from_vtheta(default_param_prior(active=()),
                                torch.zeros(4, **F64), live=False)
    # The preflight M reproduces the cached baseline with this explicit default
    # theta. The public research adapter receives params=None and pins the same
    # default prior internally, so it can reject hidden/custom weak parameters.
    window_config = WindowConfig(
        dt=20.0, xland=xland, ncmin_land=10.0, ncmin_sea=10.0,
        normalized_dry=True, active_fields=("th", "qv"), params=None)
    preflight_window_config = WindowConfig(
        dt=20.0, xland=xland, ncmin_land=10.0, ncmin_sea=10.0,
        normalized_dry=True, active_fields=("th", "qv"), params=params)
    slot = collect_window_trajectory(xb, [forcing], preflight_window_config, {1})[1]
    state_output_exact = all(
        np.array_equal(getattr(slot, name).detach().cpu().numpy()[0],
                       archive[f"state_out_baseline_{name}"])
        for name in State._fields)
    if not state_output_exact:
        raise ValueError("fresh one-step KDM state differs from cached State_out_baseline")
    qtot = (slot.qc + slot.qi + slot.qs).sum(-1)
    physical_cloudy = bool((qtot > 1.0e-5)[0])

    # Rebuild the exact T/Q/cloud profile expected by the all-sky worker before
    # any RTTOV call; all profile inputs are compact hashes and finite ranges.
    state_top = State(*(getattr(slot, name)[0].flip(-1) for name in State._fields))
    forcing_top = Forcing(
        rho=forcing.rho[0].flip(-1), pii=forcing.pii[0].flip(-1),
        p=forcing.p[0].flip(-1) / 100.0, delz=forcing.delz[0].flip(-1))
    profile_cfg = RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=p_lay, rttov_level_pressure=p_half,
        cloud=True, rho_d=rho_d[0].flip(-1), dry_number=True)
    profile = model_to_rttov_tensors(
        state_top, forcing_top, profile_cfg, xland=xland[0],
        ncmin_land=10.0, ncmin_sea=10.0)
    p_top = forcing_top.p[0].reshape(1)
    t_full = _blend_above_model_top(
        profile.t_lay.unsqueeze(0), t_ref, profile.p_lay, p_top, octaves=0.0)[0]
    q_full = _blend_above_model_top(
        profile.q_lay.unsqueeze(0), q_ref, profile.p_lay, p_top, octaves=0.0)[0]
    profile_hashes = {
        "p_hPa": array_sha(p_lay), "p_half_hPa": array_sha(p_half),
        "t_K_full_66": array_sha(t_full), "q_ppmv_moist_full_66": array_sha(q_full),
        "hydro6_g_m3_full_66": array_sha(profile.clw),
        "hydro7_g_m3_full_66": array_sha(profile.ciw),
        "hydro_deff6_micron_full_66": array_sha(profile.deff_liq),
        "hydro_deff7_micron_full_66": array_sha(profile.deff_ice),
        "cfrac_full_66": array_sha(profile.cfrac),
    }
    native_hashes = {
        "p_hPa": array_sha(p_lay[-39:]), "p_half_hPa": array_sha(p_half[-40:]),
        "T_K": array_sha(t_full[-39:]), "Q_ppmv_moist": array_sha(q_full[-39:]),
        "hydro6_g_m3": array_sha(profile.clw[-39:]),
        "hydro7_g_m3": array_sha(profile.ciw[-39:]),
    }
    if native_hashes != baseline_identity["native_profile_arrays_sha256"]:
        raise ValueError("declared current H profile native suffix differs from saved baseline inputs")
    # The clear configuration is passed through the high-level adapter, whose
    # clear partition is empty by contract. The all-sky worker receives the
    # explicit frozen profile grids and fixture identity below.
    clear_cfg = OsseObsConfig(
        run_k=None,
        profile_cfg=RttovProfileConfig(
            gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
            rttov_layer_pressure=p_lay, rttov_level_pressure=p_half,
            cloud=False, dry_number=True),
        input_cfg=RttovInputConfig("paired-case_00-GK2A-AMI", CHANNELS),
        obs_sigma=1.0, t_ref=t_ref, q_ref=q_ref,
        t_blend_octaves=0.0, q_blend_octaves=0.0)
    rttov_cfg = {
        "channels": CHANNELS,
        "coef_id": "paired-case_00-GK2A-AMI",
        "fixture_case_dir": str(PAIRED),
        "p_lay": p_lay.detach().cpu().numpy().copy(),
        "p_half": p_half.detach().cpu().numpy().copy(),
        "t_ref": t_ref.detach().cpu().numpy().copy(),
        "q_ref": q_ref.detach().cpu().numpy().copy(),
        "rho_d": rho_d.detach().cpu().numpy().copy(),
        "dry_number": True,
        "ami_kma_bt": True,
        "ncmin_land": 10.0,
        "ncmin_sea": 10.0,
        "t_blend_octaves": 0.0,
        "q_blend_octaves": 0.0,
    }
    return {
        "archive": archive, "xb": xb, "forcing": forcing, "rho_d": rho_d,
        "xland": xland, "slot": slot, "physical_cloudy": physical_cloudy,
        "qtot_level_sum": float(qtot[0]), "profile_cfg": profile_cfg,
        "p_lay": p_lay, "p_half": p_half, "t_ref": t_ref, "q_ref": q_ref,
        "y_bt": y_bt, "y_rq": y_rq, "obs": obs,
        "window_config": window_config, "rttov_exe": exe,
        "clear_cfg": clear_cfg, "rttov_cfg": rttov_cfg,
        "coefficient": coefficient, "cost": cost, "cost_scenarios": scenarios,
        "baseline_identity": baseline_identity,
        "old_cost_jo": float(scenarios["baseline"]["huber_cost"]),
        "profile_hashes": profile_hashes, "native_hashes": native_hashes,
        "source_sha256": source_snapshot(), "pair_sha256": pair_snapshot(),
        "input_sha256": {
            "checkpoint": sha(CHECKPOINT), "frame_observations": sha(FRAME_RESULT),
            "saved_cost_result": sha(OLD_COST_RESULT),
            "paired_execution_identity": sha(EXECUTION_PATH_RESULT),
        },
    }


def _make_obs_cfg(ctx, run_k):
    input_cfg = RttovInputConfig("paired-case_00-GK2A-AMI", CHANNELS)
    profile_cfg = RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=ctx["p_lay"], rttov_level_pressure=ctx["p_half"],
        # batched_allsky_bt consumes frozen density on the MODEL [1,K]
        # bottom-up grid and flips it together with the state internally.
        cloud=True, rho_d=ctx["rho_d"], dry_number=True)
    return OsseObsConfig(
        run_k=run_k, profile_cfg=profile_cfg,
        input_cfg=input_cfg, obs_sigma=1.0,
        t_ref=ctx["t_ref"], q_ref=ctx["q_ref"],
        t_blend_octaves=0.0, q_blend_octaves=0.0)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")


def _new_run_root(user_path: Path | None, phase: str) -> Path:
    path = (user_path if user_path is not None else
            RUNS_BASE / f"runs-{phase}-{uuid.uuid4().hex[:12]}")
    if path.exists():
        raise FileExistsError(f"refusing to reuse diagnostic run root {path}")
    path.mkdir(parents=True, exist_ok=False)
    return path.resolve()


def build_preflight(run_root: Path) -> dict:
    # Bound CPU threads before the pure-Torch one-step M background probe.
    os.environ.update(OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                      OMP_THREAD_LIMIT="1", VECLIB_MAXIMUM_THREADS="1")
    torch.set_num_threads(1)
    ctx = load_context()
    preflight = {
        "schema": "pr394_real_tq_baseline_preflight_v1",
        "status": "PREPARED_FOR_BASELINE_H_NOT_YET_RUN",
        "review_head": __import__("subprocess").check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "run_root": str(run_root),
        "case_root_for_direct_baseline_h": str(run_root / "baseline_h_case"),
        "case_root_exists_before_run": (run_root / "baseline_h_case").exists(),
        "input_sha256": ctx["input_sha256"],
        "source_sha256_before_h": ctx["source_sha256"],
        "paired_case_sha256_before_h": ctx["pair_sha256"],
        "rttov_executable": {"path": str(ctx["rttov_exe"]),
                              "sha256": sha(ctx["rttov_exe"])},
        "coefficient": {"path": str(ctx["coefficient"]),
                        "sha256": sha(ctx["coefficient"])},
        "selected_input": {
            "checkpoint": str(CHECKPOINT),
            "state_basis": "cached `state_in_baseline_*` in the saved private diagnostic checkpoint",
            "forcing_shape": list(ctx["forcing"].p.shape),
            "state_shape": list(ctx["xb"].th.shape),
            "xland": float(ctx["xland"][0]),
            "dt_seconds": 20.0,
            "obs_time": 1,
            "pressure_centers_native_suffix_exact": True,
            "pressure_interfaces_native_suffix_exact": True,
            "frozen_optical_density_exactly_matches_baseline_forcing": True,
            "slot_M_matches_all_cached_state_out_baseline_fields_bitwise": True,
            "slot_physical_cloudy": ctx["physical_cloudy"],
            "slot_unweighted_hydrometeor_level_sum_kgkg": ctx["qtot_level_sum"],
        },
        "allsky_h": {
            "channels_1based": list(CHANNELS),
            "obs_sigma_K": 1.0,
            "obs_bias_K": 0.0,
            "huber_delta": 1.0,
            "ncmin_land": 10.0,
            "ncmin_sea": 10.0,
            "t_blend_octaves": 0.0,
            "q_blend_octaves": 0.0,
            "dry_number": True,
            "ami_kma_bt": True,
            "coefficient_id": "paired-case_00-GK2A-AMI",
            "fixture_case_dir": str(PAIRED),
            "geometry_surface_override": "None; the writer copies unchanged angles/skin/near-surface from immutable pair case_00",
            "paired_thermal_only_simple_cloud_fraction": 0.0,
        },
        "observation_input": {
            "frame_result": str(FRAME_RESULT),
            "channels_selected_from_paired_receipt": list(CHANNELS),
            "observation_bt_K": ctx["y_bt"].tolist(),
            "observation_quality": ctx["y_rq"].tolist(),
            "observation_quality_all_good": bool(torch.equal(ctx["y_rq"], torch.zeros_like(ctx["y_rq"]))),
        },
        "expected_baseline_profile_sha256": ctx["profile_hashes"],
        "expected_baseline_native_suffix_sha256": ctx["native_hashes"],
        "saved_old_cost_baseline": {
            "Jo": ctx["old_cost_jo"],
            "BT_K": ctx["cost_scenarios"]["baseline"]["model_bt_K"],
            "rad_quality": ctx["cost_scenarios"]["baseline"]["rad_quality"],
            "valid_channel_count": ctx["cost_scenarios"]["baseline"]["valid_channel_count"],
        },
        "scope_limits": [
            "This is a diagnostic from a cached failed-host artifact, not a new valid native case or R2 observation match.",
            "No forecast/netCDF/NPZ beyond the 37 KB selected-column checkpoint was opened; the original 2.5 GB forecast was not read or hashed.",
            "No baseline RTTOV call has occurred in this preflight phase.",
        ],
    }
    return ctx, preflight


def _baseline_direct_h(ctx, run_root: Path, preflight: dict) -> dict:
    run_case = run_root / "baseline_h_case"
    if run_case.exists():
        raise FileExistsError(f"refusing to reuse baseline H case {run_case}")
    run_k = make_live_run_k(
        run_case, fixture_case_dir=PAIRED, ami_kma_bt=True,
        timeout=DEFAULT_RTTOV_TIMEOUT)
    obs_cfg = _make_obs_cfg(ctx, run_k)
    bt, quality, leaves = batched_allsky_bt(
        ctx["slot"], ctx["forcing"], obs_cfg, xland=ctx["xland"],
        ncmin_land=10.0, ncmin_sea=10.0)
    mask = _build_mask(ctx["obs"], quality)
    loss = compute_obs_loss(bt, ctx["obs"], mask, 1.0, delta=1.0)
    if not all(torch.isfinite(v).all() for v in (bt, quality, loss)):
        raise FloatingPointError("baseline H returned a non-finite BT, quality, or cost")

    atm = run_case / "in/profiles/001/atm"
    executed_profile = {
        name: np.loadtxt(atm / name, dtype=np.float64)
        for name in ("p.txt", "p_half.txt", "t.txt", "q.txt", "hydro.txt",
                     "hydro_deff.txt", "hydro_frac.txt", "o3.txt", "co2.txt")
    }
    # The writer round-trips these profiles through 17-digit ASCII. Compare the
    # critical T/Q/pressure arrays with the declared generated profile hashes.
    executed_profile_hashes = {
        name: array_sha(values) for name, values in executed_profile.items()
    }
    unchanged_fixture_files = (
        "in/profiles/001/atm/o3.txt", "in/profiles/001/atm/co2.txt",
        "in/profiles/001/angles.txt", "in/profiles/001/sfc/01/skin.txt",
        "in/profiles/001/sfc/01/near_surface.txt")
    fixture_copy_matches = {
        rel: sha(run_case / rel) == ctx["pair_sha256"][rel]
        for rel in unchanged_fixture_files
    }
    expected_cost = ctx["old_cost_jo"]
    actual_cost = float(loss.detach())
    diff_jo = actual_cost - expected_cost
    baseline_quality = quality.detach().cpu().numpy()[0].tolist()
    baseline_mask = mask.detach().cpu().numpy()[0].tolist()
    baseline_bt = bt.detach().cpu().numpy()[0].tolist()
    expected_channels = list(CHANNELS)
    emitted_channels = (run_case / "in/channels.txt").read_text().split()
    emitted_channels_match = emitted_channels == [str(c) for c in expected_channels]
    emitted_profile_match = all(
        executed_profile_hashes[file_name] == ctx["profile_hashes"][profile_name]
        for file_name, profile_name in (
            ("p.txt", "p_hPa"), ("p_half.txt", "p_half_hPa"),
            ("t.txt", "t_K_full_66"),
            ("q.txt", "q_ppmv_moist_full_66")))
    if int(mask.sum()) != 7:
        status = "BASELINE_H_FAILED_FIXED_SEVEN_CHANNEL_SUPPORT"
    elif not emitted_profile_match:
        status = "BASELINE_H_FAILED_EXECUTED_PROFILE_IDENTITY"
    elif not emitted_channels_match:
        status = "BASELINE_H_FAILED_EMITTED_CHANNEL_IDENTITY"
    elif not all(fixture_copy_matches.values()):
        status = "BASELINE_H_FAILED_PAIRED_FIXTURE_COPY_IDENTITY"
    elif max(abs(a-b) for a,b in zip(baseline_bt, ctx["cost_scenarios"]["baseline"]["model_bt_K"])) > 1.0e-9:
        status = "BASELINE_H_MISMATCH_SAVED_BT_MORE_THAN_1E-9K"
    elif abs(diff_jo) > 1.0e-9:
        status = "BASELINE_H_MISMATCH_SAVED_JO_MORE_THAN_1E-9"
    else:
        status = "BASELINE_H_READY_SEVEN_CHANNELS"
    return {
        "schema": "pr394_real_tq_baseline_h_v1",
        "status": status,
        "run_root": str(run_root),
        "baseline_case_path": str(run_case),
        "baseline_H_api": "batched_allsky_bt + caller-configured make_live_run_k/RTTOV KMA BT",
        "one_column_profile_count": 1,
        "BT_K": baseline_bt,
        "rad_quality": baseline_quality,
        "model_rad_quality_source": "RTTOV output from this direct all-sky baseline H call",
        "observation_dqf_source": "frame observation receipt; separate from model_rad_quality",
        "mask": baseline_mask,
        "n_valid": int(mask.sum()),
        "Jo_huber": actual_cost,
        "saved_old_baseline_Jo": expected_cost,
        "Jo_difference_vs_saved": diff_jo,
        "max_abs_BT_difference_K_vs_saved": max(
            abs(a-b) for a,b in zip(baseline_bt, ctx["cost_scenarios"]["baseline"]["model_bt_K"])),
        "all_seven_quality_flags_zero": bool(np.all(np.asarray(baseline_quality) == 0.0)),
        "declared_profile_hashes": ctx["profile_hashes"],
        "executed_profile_hashes": executed_profile_hashes,
        "executed_t_q_pressure_profiles_match_declared": emitted_profile_match,
        "emitted_channels_match_declared_10_through_16": emitted_channels_match,
        "unchanged_fixture_copy_matches": fixture_copy_matches,
        "case_h_resolution": {
            "run_script": str(run_case / "out/run.sh"),
            "run_script_sha256": sha(run_case / "out/run.sh"),
            "namelist": str(run_case / "out/rttov_test.txt"),
            "namelist_sha256": sha(run_case / "out/rttov_test.txt"),
            "channel_file": str(run_case / "in/channels.txt"),
            "channel_file_contents": (run_case / "in/channels.txt").read_text().split(),
            "executable": str(ctx["rttov_exe"]),
            "executable_sha256": sha(ctx["rttov_exe"]),
            "coefficient": str(ctx["coefficient"]),
            "coefficient_sha256": sha(ctx["coefficient"]),
        },
        "quality_and_cost_readiness_rule": {
            "fixed_channels_required": list(CHANNELS),
            "baseline_n_valid_must_equal": 7,
            "max_abs_BT_difference_tolerance_K": 1.0e-9,
            "abs_Jo_difference_tolerance": 1.0e-9,
            "executed_profile_arrays_must_match_exactly": True,
            "emitted_channel_file_must_equal_10_through_16": True,
            "raw_bitwise_cost_identity_claimed": False,
        },
        "call_count_scope": "one direct single-profile H API invocation; RTTOV process count is not independently instrumented",
        "source_sha256_before_h": ctx["source_sha256"],
        "source_sha256_after_h": source_snapshot(),
        "paired_case_sha256_before_h": ctx["pair_sha256"],
        "paired_case_sha256_after_h": pair_snapshot(),
        "checkpoint_sha256": ctx["input_sha256"]["checkpoint"],
        "frame_result_sha256": ctx["input_sha256"]["frame_observations"],
    }


def _record_one_phase(args) -> None:
    run_root = _new_run_root(args.run_root, "preflight")
    ctx, preflight = build_preflight(run_root)
    preflight_path = run_root / "preflight.json"
    _write_json(preflight_path, preflight)
    summary = {"status": preflight["status"], "preflight_receipt": str(preflight_path),
               "run_root": str(run_root), "no_RTTOV_call_yet": True}
    print(json.dumps(summary, indent=2))


def _baseline_phase(args) -> None:
    preflight_path = args.preflight_receipt
    if preflight_path is None or not preflight_path.is_file():
        raise FileNotFoundError("baseline phase requires a completed --preflight-receipt")
    preflight = json.loads(preflight_path.read_text())
    run_root = Path(preflight["run_root"]).resolve()
    if preflight_path.resolve() != (run_root / "preflight.json").resolve():
        raise ValueError("preflight receipt path is not rooted in its recorded unique run directory")
    if preflight.get("status") != "PREPARED_FOR_BASELINE_H_NOT_YET_RUN":
        raise ValueError("baseline phase requires a ready, not-yet-run preflight receipt")
    ctx, current = build_preflight(run_root)
    if (current["source_sha256_before_h"] != preflight["source_sha256_before_h"]
            or current["paired_case_sha256_before_h"] != preflight["paired_case_sha256_before_h"]
            or current["input_sha256"] != preflight["input_sha256"]):
        raise ValueError("inputs/sources changed since the saved preflight receipt")
    baseline_h = _baseline_direct_h(ctx, run_root, preflight)
    _write_json(run_root / "baseline_h.json", baseline_h)
    print(json.dumps({
        "status": baseline_h["status"],
        "baseline_receipt": str(run_root / "baseline_h.json"),
        "Jo": baseline_h["Jo_huber"], "n_valid": baseline_h["n_valid"],
        "BT_max_abs_difference_K": baseline_h["max_abs_BT_difference_K_vs_saved"],
        "run_root": str(run_root),
    }, indent=2))
    if baseline_h["status"] != "BASELINE_H_READY_SEVEN_CHANNELS":
        raise SystemExit(2)


def _capture_run_single_analysis(ctx, run_root: Path, max_iter: int) -> dict:
    import multiprocessing as mp
    import kdm6.da_fulldomain as fd

    analysis_root = run_root / f"analysis_obs_call_roots-{uuid.uuid4().hex[:12]}"
    if analysis_root.exists():
        raise FileExistsError(f"refusing to reuse analysis callback root {analysis_root}")
    analysis_root.mkdir(parents=True, exist_ok=False)
    _write_json(run_root / f"analysis_attempt-{analysis_root.name}.json",
                {"analysis_root": str(analysis_root), "status": "STARTED"})
    callback_trace = []
    original_sharded = fd.sharded_allsky

    def capture_sharded(*call_args, **call_kwargs):
        state, forcing, positions, target, mask, xland, cfg, case_root = call_args[:8]
        out = original_sharded(*call_args, **call_kwargs)
        adj_norms = {}
        if out.get("adj") is not None:
            for index, field in enumerate(State._fields):
                adj_norms[field] = float(np.linalg.norm(np.asarray(out["adj"][index])))
        callback_trace.append({
            "stage": Path(case_root).name,
            "case_root": str(case_root),
            "grad": bool(call_kwargs.get("grad", True)),
            "profile_positions": positions.tolist(),
            "input_state_sha256": state_hashes(state),
            "input_forcing_sha256": forcing_hashes(forcing),
            "xland": xland.detach().cpu().tolist(),
            "target_BT_K": target.detach().cpu().numpy()[0].tolist(),
            "fixed_mask": mask.detach().cpu().numpy()[0].tolist(),
            "BT_K": np.asarray(out["bt"], dtype=np.float64)[0].tolist(),
            "rad_quality": np.asarray(out["rq"], dtype=np.float64)[0].tolist(),
            "J_huber": float(out["j"]),
            "adjoint_field_norms": adj_norms,
            "channels": list(cfg["channels"]),
        })
        return out

    fd.sharded_allsky = capture_sharded
    pool = None
    try:
        context = mp.get_context("spawn")
        pool = context.Pool(1)
        result_package = run_single_column_analysis(
            ctx["xb"], [ctx["forcing"]], ctx["y_bt"], ctx["y_rq"], ctx["xland"],
            ctx["clear_cfg"], ctx["rttov_cfg"], str(analysis_root),
            window_config=ctx["window_config"], obs_time=1, pool=pool,
            n_workers=1, max_iter=max_iter, rttov_timeout=DEFAULT_RTTOV_TIMEOUT)
    finally:
        fd.sharded_allsky = original_sharded
        if pool is not None:
            pool.close()
            pool.join()
    return {"package": result_package, "callback_trace": callback_trace,
            "analysis_root": str(analysis_root)}


def _analysis_phase(args) -> None:
    if RESULT_PATH.exists():
        raise FileExistsError(f"refusing to overwrite existing diagnostic receipt {RESULT_PATH}")
    if args.max_iter != 1:
        raise ValueError("PR394 diagnostic phase is deliberately fixed at max_iter=1")
    preflight_path = args.preflight_receipt
    baseline_path = args.baseline_receipt
    if (preflight_path is None or baseline_path is None
            or not preflight_path.is_file() or not baseline_path.is_file()):
        raise FileNotFoundError("analysis phase requires both preflight and baseline-H receipts")
    preflight = json.loads(preflight_path.read_text())
    baseline_h = json.loads(baseline_path.read_text())
    run_root = Path(preflight["run_root"]).resolve()
    if baseline_h.get("status") != "BASELINE_H_READY_SEVEN_CHANNELS":
        raise ValueError("analysis requires an H baseline ready on all seven frozen channels")
    if Path(baseline_path).resolve() != (run_root / "baseline_h.json").resolve():
        raise ValueError("baseline H receipt is not in its recorded unique run root")
    if Path(preflight_path).resolve() != (run_root / "preflight.json").resolve():
        raise ValueError("preflight receipt is not in its recorded unique run root")

    ctx, current = build_preflight(run_root)
    if (current["input_sha256"] != preflight["input_sha256"]
            or current["source_sha256_before_h"] != baseline_h["source_sha256_after_h"]
            or current["paired_case_sha256_before_h"] != baseline_h["paired_case_sha256_after_h"]):
        raise ValueError("inputs/source/pair changed after baseline H preflight")
    source_before = source_snapshot()
    pair_before = pair_snapshot()
    status = "FAILED_NO_ACCEPTED_ANALYSIS"
    analysis_summary = None
    failure = None
    callback_trace = []
    model_metadata = None
    package = None
    try:
        captured = _capture_run_single_analysis(ctx, run_root, args.max_iter)
        package = captured["package"]
        callback_trace = captured["callback_trace"]
        model_metadata = package["metadata"]
        res = package["result"]
        j_final = (res.jb_final + res.jtheta_final + res.jobs_final)
        j_trace_total = res.j_trace[-1]["total"] if res.j_trace else None
        if model_metadata["n_valid_background"] != 7:
            raise RuntimeError("analysis returned without the required seven-channel background support")
        if j_trace_total is None or not np.isfinite(j_final):
            raise RuntimeError("analysis final J is missing or non-finite")
        if abs(j_trace_total - j_final) > 1.0e-10:
            raise RuntimeError("returned J components disagree with the final closure trace")
        analysis_summary = {
            "status": "ANALYSIS_RETURNED_DIAGNOSTIC_ONLY",
            "Jb_state": res.jb_final,
            "Jtheta": res.jtheta_final,
            "Jo": res.jobs_final,
            "Jtotal_components": j_final,
            "Jtotal_final_trace": j_trace_total,
            "n_valid_by_final_callback": res.j_trace[-1]["n_valid"],
            "callback_signature_by_final_time": res.j_trace[-1]["signature"],
            "theta_b": [float(v) for v in package["param_prior"].theta_b],
            "theta_analysis": [float(v) for v in res.theta_analysis],
            "sigma_log": [float(v) for v in package["param_prior"].sigma_log],
            "v_state_norm": float(res.v_state.norm()),
            "v_theta_norm": float(res.v_theta.norm()),
            "state_increment_norms": {
                f: float((getattr(res.x_analysis, f) - getattr(ctx["xb"], f)).norm())
                for f in State._fields
            },
            "n_window_evals": res.n_window_evals,
            "n_audit_evals": res.n_audit_evals,
            "callback_metadata": model_metadata,
            "callback_trace": callback_trace,
            "j_trace": res.j_trace,
            "accepted_state_published": True,
            "interpretation": "One-iteration actual RTTOV/T-Q integration diagnostic on the cached failed-artifact column; not an accepted physical analysis or valid new native case.",
        }
        status = "DIAGNOSTIC_ONLY_NOT_NEW_VALID_CASE"
    except BaseException as exc:
        failure = {"exception_type": type(exc).__name__, "message": str(exc),
                   "traceback": traceback.format_exc()}
        status = "FAILED_NO_ACCEPTED_ANALYSIS"
        analysis_summary = None
    finally:
        fd_source = source_snapshot()
        pair_after = pair_snapshot()

    result = {
        "study": "PR394 actual RTTOV one-column T/Q integration diagnostic",
        "status": status,
        "scope": "Actual single-profile RTTOV H and max_iter=1 existing dual minimizer over one normalized-dry 20 s KDM window; cached failed-run input only; diagnostic, not new valid native/science case.",
        "preflight_receipt": {"path": str(preflight_path), "status": preflight["status"]},
        "baseline_h_receipt": {"path": str(baseline_path),
                                "status": baseline_h["status"],
                                "Jo": baseline_h["Jo_huber"],
                                "n_valid": baseline_h["n_valid"]},
        "receipt_sha256": {
            "preflight": sha(preflight_path),
            "baseline_h": sha(baseline_path),
        },
        "diagnostic_driver_sha256": {
            "preflight_and_baseline_h": baseline_h.get(
                "diagnostic_driver_sha256_used_for_preflight_and_baseline_h"),
            "analysis": sha(Path(__file__).resolve()),
            "changed_after_baseline": baseline_h.get(
                "diagnostic_driver_sha256_used_for_preflight_and_baseline_h")
                != sha(Path(__file__).resolve()),
            "change_scope": (
                "After baseline H, the driver readiness/receipt checks were tightened, "
                "and a pre-callback adapter configuration error was corrected by passing "
                "params=None while retaining the pinned default prior. The baseline H "
                "input and call were unchanged."
            ),
        },
        "failed_setup_attempts": [
            {"path": str(path), "sha256": sha(path),
             "meaning": "setup failed before an accepted analysis; no state was accepted"}
            for path in sorted(EVIDENCE_DIR.glob("FAILED_ATTEMPT_*.json"))
        ],
        "fresh_run_root": str(run_root),
        "input_sha256": current["input_sha256"],
        "source_sha256_before_analysis": source_before,
        "source_sha256_after_analysis": fd_source,
        "paired_case_sha256_before_analysis": pair_before,
        "paired_case_sha256_after_analysis": pair_after,
        "source_and_pair_unchanged": source_before == fd_source and pair_before == pair_after,
        "failed_analysis": failure,
        "analysis": analysis_summary,
        "scope_limits": [
            "Input is the small selected-column checkpoint from the failed 358-minute host run, not a newly valid target-time native frame.",
            "No 2.5 GB forecast was opened or hashed, and no WRF host/native case was launched.",
            "Actual profile RTTOV H runs use a fresh copy of the immutable paired case_00; the original case is hashed before and after.",
            "The adapter captures logical all-sky callback outputs and paths; external child-process counts and every transient worker file are not independently persisted.",
            "No physical observation match, forecast score, accepted-science prior, parameter inference, or release/operational claim is made.",
        ],
    }
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _write_json(RESULT_PATH, result)
    print(json.dumps({"status": status, "result": str(RESULT_PATH),
                      "failure": failure,
                      "analysis": None if analysis_summary is None else {
                          k: analysis_summary[k] for k in ("Jb_state", "Jtheta", "Jo", "Jtotal_components", "n_window_evals", "n_audit_evals")}},
                     indent=2, allow_nan=False))
    if status == "FAILED_NO_ACCEPTED_ANALYSIS":
        raise SystemExit(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("preflight", "baseline", "analysis"), required=True)
    parser.add_argument("--run-root", type=Path,
                        help="fresh private graphify-out run root; must not already exist for preflight")
    parser.add_argument("--preflight-receipt", type=Path)
    parser.add_argument("--baseline-receipt", type=Path)
    parser.add_argument("--max-iter", type=int, default=1)
    args = parser.parse_args()
    os.environ.update(OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                      OMP_THREAD_LIMIT="1", VECLIB_MAXIMUM_THREADS="1")
    torch.set_num_threads(1)
    if args.phase == "preflight":
        run_root = _new_run_root(args.run_root, "preflight")
        try:
            ctx, record = build_preflight(run_root)
            record["status"] = "PREFLIGHT_READY_NOT_RUN"
        except BaseException as exc:
            record = {"schema": "pr394_real_tq_preflight_v1",
                      "status": "PREFLIGHT_FAILED_NO_RTTOV_RUN",
                      "run_root": str(run_root),
                      "failure": {"exception_type": type(exc).__name__, "message": str(exc)}}
        path = run_root / "preflight.json"
        _write_json(path, record)
        print(json.dumps({"status": record["status"], "run_root": str(run_root),
                          "preflight_receipt": str(path)}, indent=2))
        if record["status"] != "PREFLIGHT_READY_NOT_RUN":
            raise SystemExit(2)
    elif args.phase == "baseline":
        if args.preflight_receipt is None:
            raise SystemExit("--phase baseline requires --preflight-receipt")
        path = args.preflight_receipt.resolve()
        record = json.loads(path.read_text())
        run_root = Path(record["run_root"]).resolve()
        if path != (run_root / "preflight.json").resolve():
            raise SystemExit("preflight receipt/run-root identity mismatch")
        if record.get("status") != "PREFLIGHT_READY_NOT_RUN":
            raise SystemExit("baseline phase requires ready preflight")
        try:
            ctx = load_context()
            # Rebuild the one-step slot for this actual baseline-H invocation.
            current = build_preflight(run_root)[1]
            for field in ("input_sha256", "source_sha256_before_h", "paired_case_sha256_before_h"):
                if current[field] != record[field]:
                    raise ValueError(f"{field} changed after preflight")
            baseline = _baseline_direct_h(ctx, run_root, record)
        except BaseException as exc:
            baseline = {"schema": "pr394_real_tq_baseline_h_v1",
                        "status": "BASELINE_H_FAILED_NO_ANALYSIS",
                        "run_root": str(run_root),
                        "failure": {"exception_type": type(exc).__name__, "message": str(exc)}}
        baseline_path = run_root / "baseline_h.json"
        _write_json(baseline_path, baseline)
        print(json.dumps({"status": baseline["status"], "baseline_receipt": str(baseline_path),
                          "run_root": str(run_root), "Jo": baseline.get("Jo_huber"),
                          "n_valid": baseline.get("n_valid"),
                          "BT_max_abs_difference_K": baseline.get("max_abs_BT_difference_K_vs_saved")},
                         indent=2, allow_nan=False))
        if baseline["status"] != "BASELINE_H_READY_SEVEN_CHANNELS":
            raise SystemExit(2)
    else:
        if args.run_root is not None:
            raise SystemExit("analysis reuses only the unique run root bound by its preflight receipt")
        _analysis_phase(args)


if __name__ == "__main__":
    main()
