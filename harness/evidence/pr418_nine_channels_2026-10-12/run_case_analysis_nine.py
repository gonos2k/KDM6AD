#!/usr/bin/env python3
"""Consume a ready case core with the unchanged one-column T/Q analysis.

No native launcher, archive search, retry or external-observation fallback.
The core is one saved native background and one frozen 20-second forcing.
"""
from __future__ import annotations

import argparse
import json
import importlib.util
import math
import multiprocessing as mp
import os
from pathlib import Path
import sys

import numpy as np
import torch

PACKET = Path(__file__).resolve().parent
ROOT = PACKET.parents[2]
sys.path.insert(0, str(ROOT / "oracle"))
PR407_PACKET = ROOT / "harness/evidence/pr407_native_saved_time_bound_2026-10-11"
sys.path.insert(0, str(PR407_PACKET))


def _load_explicit_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import explicit helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Use a private module name and an explicit path. Another evidence packet may
# already have cached `case_capture_adapter` with a different intake version.
_capture_adapter = _load_explicit_module(
    PR407_PACKET / "case_capture_adapter.py", "pr418_pr407_case_capture_adapter")
load_module = _capture_adapter.load_module
_prepare_capture_module = _capture_adapter.prepare_capture_module
sha = _capture_adapter.sha
from kdm6.da_single_column import _selected_channels  # noqa: E402
from kdm6.obs.obs_loss import compute_obs_loss  # noqa: E402

LEGACY_DRIVER = ROOT / "harness/evidence/pr395_native_tq_intake_2026-10-10/run_analysis.py"
INTAKE_SOURCE = PR407_PACKET / "intake_native_case_v4.py"
CHANNELS = tuple(range(10, 17))
CHANNELS_9 = tuple(range(8, 17))
CHANNEL_NAMES = {
    8: "wv063", 9: "wv069", 10: "wv073", 11: "ir087", 12: "ir096",
    13: "ir105", 14: "ir112", 15: "ir123", 16: "ir133",
}
L1B_CHANNEL_ORDER = tuple(CHANNEL_NAMES[channel] for channel in CHANNELS_9)
F64 = {"dtype": torch.float64}


def prepare_capture_module():
    """Bind the opt-in driver itself into capture's before/after source snapshot."""
    capture = _prepare_capture_module()
    driver_path = Path(__file__).resolve()
    driver_sha = sha(driver_path)
    base_snapshot = capture._source_snapshot

    def source_snapshot():
        if sha(driver_path) != driver_sha:
            raise ValueError("nine-channel driver source changed during capture")
        return {**base_snapshot(), str(driver_path): driver_sha}

    capture._source_snapshot = source_snapshot
    return capture


def _audit_initial_objectives_selected(capture_result, y_bt, *, expected_channels: int):
    """Cross-check the zero-mask probe against the initial closure at channel N.

    This mirrors the bounded arithmetic audit in the legacy PR395 driver while
    making the support count explicit. It reads only saved receipt fields and
    performs no H, M, or optimizer work.
    """
    calls = capture_result.get("logical_h_calls", [])
    probe_event = next((call for call in calls if call.get("grad") is False), None)
    first_grad_event = next((call for call in calls if call.get("grad") is True), None)
    objective = capture_result.get("objective", {})
    zero = objective.get("initial_zero_control_closure")
    probe = capture_result.get("background_quality_probe")
    unavailable = {
        "status": "NOT_AVAILABLE",
        "initial_zero_control_objective": None,
        "background_quality_probe": None,
        "crosscheck_valid": False,
        "h_or_m_re_evaluations_for_crosscheck": 0,
    }
    if (not isinstance(zero, dict) or not isinstance(probe, dict)
            or probe_event is None or first_grad_event is None):
        return unavailable

    zero_mask = np.asarray(zero.get("frozen_mask", {}).get("values"), dtype=np.float64)
    probe_bt = np.asarray(probe.get("BT_K"), dtype=np.float64)
    probe_target = np.asarray(probe.get("target_BT_K"), dtype=np.float64)
    probe_cost_mask = np.asarray(probe.get("mask", {}).get("values"), dtype=np.float64)
    first_grad_bt = np.asarray(first_grad_event.get("BT_K"), dtype=np.float64)
    first_grad_mask = np.asarray(first_grad_event.get("fixed_mask"), dtype=np.float64)
    expected_shape = tuple(y_bt.shape)
    if (expected_shape != (1, expected_channels)
            or any(a.shape != expected_shape for a in
                   (zero_mask, probe_bt, probe_target, probe_cost_mask,
                    first_grad_bt, first_grad_mask))):
        return {**unavailable, "status": "INVALID_SHAPE"}
    if not (np.isfinite(zero_mask).all() and np.isfinite(probe_bt).all()
            and np.isfinite(probe_target).all() and np.isfinite(probe_cost_mask).all()
            and np.isfinite(first_grad_bt).all() and np.isfinite(first_grad_mask).all()):
        return {**unavailable, "status": "NONFINITE_CAPTURE"}

    zero_jo = float(zero["Jo"])
    zero_jb = float(zero["Jb_state"])
    zero_jtheta = float(zero["Jtheta"])
    zero_total = float(zero["Jtotal"])
    raw_probe_masked_cost = float(probe["raw_J_huber"])
    probe_zero_mask_cost = float(compute_obs_loss(
        torch.as_tensor(probe_bt, **F64), {"bt": y_bt, "bias": 0.0},
        torch.as_tensor(probe_cost_mask, **F64), 1.0, delta=1.0))
    probe_bt_under_frozen_mask = float(compute_obs_loss(
        torch.as_tensor(probe_bt, **F64), {"bt": y_bt, "bias": 0.0},
        torch.as_tensor(zero_mask, **F64), 1.0, delta=1.0))
    mask_matches_first_closure = np.array_equal(zero_mask, first_grad_mask)
    probe_state_matches_first_closure = (
        probe_event.get("state_sha256") == first_grad_event.get("state_sha256"))
    probe_bt_matches_first_closure = np.array_equal(probe_bt, first_grad_bt)
    probe_target_matches_input = np.array_equal(probe_target, y_bt.detach().cpu().numpy())
    zero_objective_matches_components = math.isclose(
        zero_total, zero_jb + zero_jtheta + zero_jo, rel_tol=0.0, abs_tol=1e-12)
    raw_probe_cost_matches_zero_mask = math.isclose(
        raw_probe_masked_cost, probe_zero_mask_cost, rel_tol=0.0, abs_tol=1e-12)
    probe_under_frozen_matches_zero_jo = math.isclose(
        probe_bt_under_frozen_mask, zero_jo, rel_tol=1e-12, abs_tol=1e-12)
    crosscheck_valid = bool(
        zero.get("trace_index") == 0
        and zero.get("n_valid") == expected_channels
        and zero_jb == 0.0 and zero_jtheta == 0.0
        and zero_objective_matches_components
        and int(np.count_nonzero(zero_mask)) == expected_channels
        and not np.any(probe_cost_mask)
        and mask_matches_first_closure
        and probe_state_matches_first_closure
        and probe_bt_matches_first_closure
        and probe_target_matches_input
        and raw_probe_cost_matches_zero_mask
        and probe_under_frozen_matches_zero_jo)
    return {
        "status": "CROSSCHECKED" if crosscheck_valid else "MISMATCH",
        "expected_channel_count": expected_channels,
        "initial_zero_control_objective": {
            "Jo0_huber": zero_jo, "Jb_state": zero_jb,
            "Jtheta": zero_jtheta, "Jtotal": zero_total,
            "trace_index": int(zero["trace_index"]),
            "n_valid": int(zero["n_valid"]),
            "operator_signature_sha256": zero["operator_signature_sha256"],
            "frozen_mask": zero["frozen_mask"],
        },
        "background_quality_probe": {
            "probe_masked_cost": raw_probe_masked_cost,
            "cost_semantics": probe.get("cost_semantics"),
            "zero_mask": probe.get("mask"),
            "zero_mask_cost_recomputed": probe_zero_mask_cost,
            "probe_BT_cost_recomputed_with_frozen_mask": probe_bt_under_frozen_mask,
            "probe_BT_K": probe_bt.tolist(),
            "rad_quality": probe.get("rad_quality"),
        },
        "crosschecks": {
            "first_zero_control_closure_components_sum": zero_objective_matches_components,
            "probe_cost_matches_zero_mask_recomputation": raw_probe_cost_matches_zero_mask,
            "probe_and_initial_closure_states_match": probe_state_matches_first_closure,
            "probe_BT_matches_first_zero_control_H_BT": probe_bt_matches_first_closure,
            "probe_target_matches_validated_observation": probe_target_matches_input,
            "frozen_mask_matches_first_zero_control_H": mask_matches_first_closure,
            "probe_BT_under_frozen_mask_matches_initial_zero_control_Jo": probe_under_frozen_matches_zero_jo,
            "h_or_m_re_evaluations_for_crosscheck": 0,
        },
    }


def observation_values(manifest, channels: tuple[int, ...] | None = None):
    """Read already-decoded L1B point values; do not reacquire/decode a scene."""
    selected_channels = _selected_channels(channels)
    obs = manifest["observation"]
    if obs["binding_status"] != "BOUND_GK2A_L1B_SCENE":
        raise ValueError("a native-only intake cannot authorize an observation-linked analysis")
    point = obs["nearest_pixel"]
    date = obs["scene_date"]
    payload_path = Path(obs["payload_path"])
    if selected_channels == CHANNELS_9:
        if obs.get("reader_metadata_channels") != list(L1B_CHANNEL_ORDER):
            raise ValueError("nine-channel binding requires the exact L1B payload channel order")
        if sha(payload_path) != obs.get("payload_sha256"):
            raise ValueError("nine-channel payload SHA differs from its bound observation receipt")
    with np.load(obs["payload_path"], allow_pickle=False) as payload:
        bt_all = payload[date + "_patch_bt_K"][2, 2].copy()
        dqf_all = payload[date + "_patch_reader_dqf"][2, 2].copy()
        lat = float(payload[date + "_patch_latitude_deg"][2, 2])
        lon = float(payload[date + "_patch_longitude_deg"][2, 2])
    names = tuple(CHANNEL_NAMES[channel] for channel in selected_channels)
    indices = tuple(L1B_CHANNEL_ORDER.index(name) for name in names)
    if bt_all.shape != (len(L1B_CHANNEL_ORDER),) or dqf_all.shape != bt_all.shape:
        raise ValueError("original decoded payload must retain the exact nine-channel L1B row")
    bt, dqf = bt_all[list(indices)], dqf_all[list(indices)]
    expected_bt = np.array([point["bt_K_by_channel"][n] for n in names])
    expected_q = np.array([point["reader_dqf_by_channel"][n] for n in names])
    if (bt.shape != (len(selected_channels),) or not np.isfinite(bt).all()
            or not np.array_equal(bt, expected_bt)
            or not np.array_equal(dqf, expected_q) or np.any(dqf != 0)
            or lat != point["latitude_deg"] or lon != point["longitude_deg"]):
        raise ValueError("original decoded payload differs from the bound selected-channel point")
    return bt, dqf


def build_inputs(manifest, arrays, fixture_copy, template_fixture, legacy,
                 channels: tuple[int, ...] | None = None):
    """Value-only configuration; production M/H/minimizer remain unchanged."""
    from kdm6.state import State, Forcing

    selected_channels = _selected_channels(channels)
    bt, dqf = observation_values(manifest, selected_channels)
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
    input_cfg = legacy.RttovInputConfig("paired-case_00-GK2A-AMI", selected_channels, surface=surface, geometry=geometry)
    profile_cfg = legacy.RttovProfileConfig(gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=torch.as_tensor(p_lay, **F64), rttov_level_pressure=torch.as_tensor(p_half, **F64),
        cloud=False, dry_number=True)
    clear_cfg = legacy.OsseObsConfig(run_k=None, profile_cfg=profile_cfg, input_cfg=input_cfg,
        obs_sigma=1.0, t_ref=torch.as_tensor(arrays["t_rttov_topdown_K"], **F64),
        q_ref=torch.as_tensor(arrays["q_rttov_topdown_ppmv"], **F64), t_blend_octaves=0.0, q_blend_octaves=0.0)
    rttov_cfg = {"channels": selected_channels, "coef_id": "paired-case_00-GK2A-AMI", "fixture_case_dir": str(fixture_copy),
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
        "native_producer_effective_start": manifest["native_run"]["effective_start_time"],
        "native_producer_effective_stop": manifest["native_run"]["effective_stop_time"],
        "nominal_observation_slot": manifest["native_run"]["nominal_obs_model_time"],
        "observation_slot_pixel_time_verified": False, "observation_sigma_bias_prior_assumptions": "unchanged exploration contract",
        "forcing_hypothesis": "one saved BG forcing held for a local20s KDM step, not a full host integration",
        "geometry_derivation": geometry_context, "native_L1B_distance_m": distance,
        "host_slot_comparison": "optional diagnostics only; no saved host slot required"}
    channel_binding = None
    if selected_channels == CHANNELS_9:
        channel_binding = {
            "validation": "supplemental_nine_channel_payload_binding",
            "payload_sha256": obs["payload_sha256"],
            "payload_channel_order": list(L1B_CHANNEL_ORDER),
            "selected_ami_physical_ids": list(selected_channels),
            "selected_channel_names": [CHANNEL_NAMES[channel] for channel in selected_channels],
            "selected_bt_exactly_matches_bound_point": True,
            "all_selected_source_dqf_zero": True,
        }
        run_manifest["observation_channel_binding"] = channel_binding
    n_channels = len(selected_channels)
    return {"xb": xb, "forcing": forcing, "y_bt": torch.as_tensor(bt, **F64).reshape(1, n_channels),
            "y_rq": torch.as_tensor(dqf, **F64).reshape(1, n_channels), "xland": xland,
            "clear_cfg": clear_cfg, "rttov_cfg": rttov_cfg, "window_config": window, "run_manifest": run_manifest}


def execute(manifest_path, npz_path, output_root, template_fixture, channels=None):
    selected_channels = _selected_channels(channels)
    legacy = load_module(LEGACY_DRIVER, "case_analysis_pr395_primitives")
    if Path(template_fixture).resolve() != legacy.TEMPLATE_FIXTURE.resolve():
        raise ValueError("this bounded consumer requires the declared GK2A-AMI template fixture")
    intake = load_module(INTAKE_SOURCE, "case_analysis_intake")
    manifest, arrays = intake.load_bound_intake(manifest_path, npz_path)
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise FileExistsError("case analysis output root must be fresh; no retry/overwrite")
    source_paths = [Path(__file__), INTAKE_SOURCE, PR407_PACKET / "case_capture_adapter.py",
                    LEGACY_DRIVER, legacy.CAPTURE_HELPER]
    pinned = {str(p): sha(p) for p in source_paths}
    output_root.mkdir(parents=True, mode=0o700)
    output_root.chmod(0o700)
    fixture_copy = output_root / "rttov_fixture"
    fixture = legacy._prepare_fixture_copy(Path(template_fixture), fixture_copy, arrays)
    ctx = build_inputs(manifest, arrays, fixture_copy, Path(template_fixture), legacy,
                       selected_channels)
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
        capture_kwargs = {}
        if selected_channels == CHANNELS_9:
            capture_kwargs["channels"] = selected_channels
        result = capture.run_capture(xb=ctx["xb"], forcings=(ctx["forcing"],), y_bt=ctx["y_bt"], y_rq=ctx["y_rq"],
            xland=ctx["xland"], clear_cfg=ctx["clear_cfg"], rttov_cfg=ctx["rttov_cfg"],
            window_config=ctx["window_config"], obs_time=1, pool=pool, max_iter=3, n_workers=1,
            private_checkpoint=output_root / "private/accepted_state.npz", public_receipt=output_root / "CAPTURE.json",
            case_root=output_root / "h_cases", native_intake_context_path=manifest_path,
            native_intake_context_sha256=preflight["intake_manifest_sha256"], native_intake_npz_path=npz_path,
            native_intake_npz_sha256=preflight["intake_npz_sha256"], run_manifest=ctx["run_manifest"],
            **capture_kwargs)
    asset_after = {str(p): sha(p) for p in fixture_paths}
    audit = _audit_initial_objectives_selected(
        result, ctx["y_bt"], expected_channels=len(selected_channels))
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
    parser.add_argument("--nine-channels", action="store_true",
                        help="opt in to all AMI physical channels 8..16 (WV063/WV069 plus 10..16)")
    args = parser.parse_args()
    os.environ.update(OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OMP_THREAD_LIMIT="1", VECLIB_MAXIMUM_THREADS="1")
    torch.set_num_threads(1)
    selected_channels = CHANNELS_9 if args.nine_channels else None
    result = execute(args.intake_manifest, args.intake_npz, args.output_root,
                     args.template_fixture, channels=selected_channels)
    print(json.dumps({"case_id": result["case_id"], "status": result["status"]}))
    return 0 if result["status"] == "RETURNED_CASE_DIAGNOSTIC" else 1


if __name__ == "__main__":
    raise SystemExit(main())
