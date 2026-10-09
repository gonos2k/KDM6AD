#!/usr/bin/env python3
"""Extract one accepted native 8-frame selected-column T/Q intake.

This is intentionally a consumer, not a launcher: it refuses to open a forecast
unless the archived run has rc=0, experiment_valid=true, model_completed=true,
and the exact eight declared WRF ``Times``. It reads only the selected column
and writes one private NPZ plus a public provenance manifest. It performs no
KDM6 analysis, RTTOV call, retry, or forecast modification.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import re
import tempfile

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "oracle"))
READER = ROOT / "harness/evidence/native358_artifact_diag_2026-10-08/recipe/run_native_kma_bt_frames.py"
P8W_SOURCE = Path("/private/tmp/KDM6AD-viirs-native-run-20261007/isolated_project/host/KIM-meso_v1.0/share/wrf_timeseries.F")
WRAPPER_SOURCE = Path("/private/tmp/KDM6AD-viirs-native-run-20261007/isolated_project/host/KIM-meso_v1.0/phys/module_mp_kdm6ad_cons.F")
DEFAULT_MANIFEST = ROOT / "harness/evidence/pr395_native_tq_intake_2026-10-10/INTAKE.json"
DEFAULT_NPZ = ROOT / "graphify-out/pr395-native-tq-intake-2026-10-10/private/native_column_8frame.npz"
EXPECTED_RUN_ID = "mp337_viirs_norm2_dry1_055540_055800_358min_hist0_20261010_052612_p99148"
EXPECTED_TIMES = [f"2025-07-19_05:{m:02d}:{s:02d}" for m, s in
                  ((55, 40), (56, 0), (56, 20), (56, 40),
                   (57, 0), (57, 20), (57, 40), (58, 0))]
RAW_STATE_FIELDS = ("THM", "QVAPOR", "QCLOUD", "QRAIN", "QICE", "QSNOW",
                    "QGRAUP", "QNCCN", "QNCLOUD", "QNICE", "QNRAIN", "QIB")
STATE_TO_RAW = {"th": "THM", "qv": "QVAPOR", "qc": "QCLOUD", "qr": "QRAIN",
                "qi": "QICE", "qs": "QSNOW", "qg": "QGRAUP", "nccn": "QNCCN",
                "nc": "QNCLOUD", "ni": "QNICE", "nr": "QNRAIN", "bg": "QIB"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def array_sha256(value) -> str:
    a = np.ascontiguousarray(value)
    return hashlib.sha256(a.tobytes()).hexdigest()


def _check_selected_hyperslab(var, raw, *, expected_shape: tuple[int, ...], time_index: int,
                              j: int | None = None, i: int | None = None) -> np.ndarray:
    """Reject masked/fill/non-finite data before ndarray conversion loses masks.

    Only the caller's selected column or required one-dimensional coordinate
    vector is read. This follows frame_reader._flat's mask-before-array rule
    while keeping the native NetCDF access bounded to one (time,k,j,i) slice.
    """
    label = getattr(var, "name", "variable")
    location = f"Time={time_index}" + (f", j={j}, i={i}" if j is not None else "")
    if np.ma.is_masked(raw):
        raise ValueError(f"{label}: masked values in required selected hyperslab ({location})")
    values = np.asarray(raw)
    if values.shape != expected_shape:
        raise ValueError(
            f"{label}: selected hyperslab shape {values.shape} != {expected_shape} ({location})")
    if np.issubdtype(values.dtype, np.number):
        if not np.isfinite(values).all():
            raise ValueError(f"{label}: non-finite values in required selected hyperslab ({location})")
        for attribute in ("_FillValue", "missing_value"):
            if attribute in var.ncattrs():
                sentinel = np.asarray(var.getncattr(attribute))
                try:
                    found = np.isin(values, sentinel).any()
                except (TypeError, ValueError):
                    found = False
                if found:
                    raise ValueError(
                        f"{label}: {attribute} sentinel in required selected hyperslab ({location})")
    return values


def _validate_selected_frame_slices(ds, ti: int, reader) -> None:
    """Mask/shape/finite checks for only the selected column and needed vectors."""
    times_var = ds["Times"]
    if np.ma.is_masked(times_var[ti]):
        raise ValueError(f"Times: masked saved-time value at Time={ti}")
    selected_3d = RAW_STATE_FIELDS + ("P", "PB")
    for name in selected_3d:
        _check_selected_hyperslab(
            ds[name], ds[name][ti, :, reader.J, reader.I], expected_shape=(39,),
            time_index=ti, j=reader.J, i=reader.I)
    for name in ("PH", "PHB"):
        _check_selected_hyperslab(
            ds[name], ds[name][ti, :, reader.J, reader.I], expected_shape=(40,),
            time_index=ti, j=reader.J, i=reader.I)
    for name in ("FNM", "FNP", "C1H", "C2H", "DNW"):
        _check_selected_hyperslab(
            ds[name], ds[name][ti, :], expected_shape=(39,), time_index=ti)
    surface_names = ("XLAND", "TSK", "T2", "Q2", "U10", "V10", "HGT",
                     "MU", "MUB", "XLAT", "XLONG")
    if "SEAICE" in ds.variables:
        surface_names += ("SEAICE",)
    for name in surface_names:
        _check_selected_hyperslab(
            ds[name], ds[name][ti, reader.J, reader.I], expected_shape=(),
            time_index=ti, j=reader.J, i=reader.I)


def load_reader():
    spec = importlib.util.spec_from_file_location("pr395_native_column_reader", READER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load archived native reader: {READER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_completion_gate(run_dir: Path) -> tuple[dict, Path, dict, dict]:
    if run_dir.name != EXPECTED_RUN_ID:
        raise ValueError(f"expected the exact fresh PR395 native archive {EXPECTED_RUN_ID}, got {run_dir.name}")
    exit_path = run_dir / "exit_code"
    valid_path = run_dir / "experiment_valid.json"
    identity_path = run_dir / "run_identity.json"
    for path in (exit_path, valid_path, identity_path):
        if not path.is_file():
            raise RuntimeError(f"run completion evidence is missing: {path}")
    rc_text = exit_path.read_text().strip()
    valid = json.loads(valid_path.read_text())
    identity = json.loads(identity_path.read_text())
    if (rc_text != "0" or valid.get("exit_code") != 0
            or valid.get("experiment_valid") is not True
            or valid.get("model_completed") is not True
            or identity.get("exit_code") != 0
            or identity.get("experiment_valid") is not True):
        raise RuntimeError("native run gate failed: expected runner rc=0 and experiment_valid/model_completed=true")
    run_settings = _validate_run_identity_and_namelist(run_dir, identity, valid)
    forecasts = sorted(run_dir.glob("klfs_lc05_fcst.*"))
    if len(forecasts) != 1 or not forecasts[0].is_file():
        raise RuntimeError(f"expected exactly one archived forecast in {run_dir}; found {len(forecasts)}")
    return valid, forecasts[0], identity, run_settings


def _namelist_value(text: str, name: str) -> str:
    matches = re.findall(rf"(?im)^\s*{re.escape(name)}\s*=\s*([^,!\s]+)", text)
    if len(matches) != 1:
        raise ValueError(f"expected one {name} assignment in archived effective namelist")
    return matches[0].strip().strip("\"'")


def _validate_run_identity_and_namelist(run_archive: Path, identity: dict,
                                        valid_receipt: dict) -> dict:
    path = run_archive / "namelist.input"
    text = path.read_text()
    controls = identity.get("controls", {})
    expected_controls = {
        "label": "viirs_norm2_dry1_055540_055800", "minutes": 358,
        "seconds": 0, "history": 0, "history_s": 20, "np": 1,
        "radt": None,
    }
    if identity.get("scheme") != "337":
        raise ValueError(f"run_identity.scheme must be 337 for PR395, got {identity.get('scheme')!r}")
    for key, expected in expected_controls.items():
        if controls.get(key) != expected:
            raise ValueError(f"run_identity.controls.{key} must be {expected!r}, got {controls.get(key)!r}")
    if identity.get("actual_proc_grid") != "1x1" or valid_receipt.get("actual_proc_grid") != "1x1":
        raise ValueError("runner receipts must record the one-rank actual processor grid 1x1")

    # Match run_ss_case.campaign_identity's path-independent digest over the
    # executed archived namelist, excluding only the optional MPI grid lines.
    namelist_without_grid_sha256 = hashlib.sha256(
        "\n".join(line for line in text.splitlines()
                  if "nproc_x" not in line and "nproc_y" not in line).encode("utf-8")
    ).hexdigest()
    if controls.get("namelist_without_grid_sha256") != namelist_without_grid_sha256:
        raise ValueError("run_identity namelist hash differs from archived effective namelist bytes")

    namelist_controls = {
        "mp_physics": _namelist_value(text, "mp_physics"),
        "run_minutes": int(_namelist_value(text, "run_minutes")),
        "run_seconds": int(_namelist_value(text, "run_seconds")),
        "history_interval": int(_namelist_value(text, "history_interval")),
        "history_interval_s": int(_namelist_value(text, "history_interval_s")),
        "time_step": int(_namelist_value(text, "time_step")),
        "use_adaptive_time_step": _namelist_value(text, "use_adaptive_time_step").lower(),
        "step_to_output_time": _namelist_value(text, "step_to_output_time").lower(),
    }
    expected_namelist = {
        "mp_physics": "337", "run_minutes": 358, "run_seconds": 0,
        "history_interval": 0, "history_interval_s": 20, "time_step": 20,
        "use_adaptive_time_step": ".false.", "step_to_output_time": ".false.",
    }
    if namelist_controls != expected_namelist:
        raise ValueError(f"archived effective namelist differs from PR395 run controls: {namelist_controls}")

    ncmin_values = {}
    for name in ("ncmin_land", "ncmin_sea"):
        ncmin_values[name] = float(_namelist_value(text, name))
    if ncmin_values != {"ncmin_land": 10.0, "ncmin_sea": 10.0}:
        raise ValueError(f"archived run's ncmin values differ from predeclared 10/10: {ncmin_values}")
    wrapper = WRAPPER_SOURCE.read_text()
    forwarding = {
        "ncmin_land": "ARGS%ncmin_land = REAL(ncmin_land, c_double)",
        "ncmin_sea": "ARGS%ncmin_sea  = REAL(ncmin_sea, c_double)",
    }
    for name, line in forwarding.items():
        if wrapper.count(line) != 1:
            raise ValueError(f"expected one source forwarding statement for {name} in {WRAPPER_SOURCE}")
    return {
        "namelist": {"path": str(path), "sha256": sha256(path),
                     "controls": namelist_controls,
                     "identity_hash_matches_archived_bytes": True},
        "kdm6_moment_floor_inputs": {
            "path": str(path), "sha256": sha256(path), "values": ncmin_values,
            "interpretation": "archived effective namelist entries; checked against mp_kdm6ad_cons argument forwarding, not a claim that all wrapper defaults equal these settings"},
        "runner_identity": {"scheme": identity["scheme"], "controls": controls,
                            "actual_proc_grid": identity["actual_proc_grid"]},
    }


def _atomic_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    if path.parent.stat().st_mode & 0o077:
        raise PermissionError(f"private intake directory is accessible to group/other users: {path.parent}")
    if path.exists():
        raise FileExistsError(f"refusing to overwrite an existing private intake: {path}")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp.npz", dir=path.parent)
    os.close(fd)
    temp = Path(temp_name)
    linked = False
    try:
        np.savez_compressed(temp, **arrays)
        temp.chmod(0o600)
        os.link(temp, path)  # exclusive create: fail if another intake won the race
        linked = True
        temp.unlink()
    except BaseException:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        if linked:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def _write_json_exclusive(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    linked = False
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        temp.chmod(0o644)
        os.link(temp, path)
        linked = True
        temp.unlink()
    except BaseException:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        if linked:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def extract(run_dir: Path, manifest_path: Path, npz_path: Path) -> dict:
    run_dir = run_dir.resolve()
    if manifest_path.exists() or npz_path.exists():
        raise FileExistsError("refusing to replace an existing native-intake manifest or NPZ")
    valid_receipt, forecast, identity, run_settings = _read_completion_gate(run_dir)
    reader = load_reader()
    reader.validate_p8w_source()
    if reader.WRF_P8W_SOURCE.resolve() != P8W_SOURCE.resolve():
        raise RuntimeError("unrecognized P8W source selection")
    # This source identifies the Python REAL(4) transcription. It is not an
    # assertion that the host routine ran or that the current checkout was built.
    p8w_source_sha = sha256(P8W_SOURCE)
    if p8w_source_sha != reader.WRF_P8W_EXPECTED_SHA256[str(P8W_SOURCE)]:
        raise RuntimeError("calc_p8w source differs from the source pinned by the archived reader")
    ncmin_context = run_settings["kdm6_moment_floor_inputs"]
    wrapper_sha = sha256(WRAPPER_SOURCE)

    arrays: dict[str, np.ndarray] = {}
    frame_context = []
    forecast_stat_before = forecast.stat()
    with netCDF4.Dataset(forecast, "r") as ds:
        if int(getattr(ds, "USE_THETA_M", 0)) != 1:
            raise ValueError("native extraction requires USE_THETA_M=1")
        if not all(name in ds.variables for name in RAW_STATE_FIELDS +
                   ("P", "PB", "PH", "PHB", "FNM", "FNP", "XLAND", "TSK", "T2", "Q2", "U10", "V10", "HGT", "MU", "MUB", "C1H", "C2H", "DNW", "XLAT", "XLONG")):
            missing = [name for name in RAW_STATE_FIELDS +
                       ("P", "PB", "PH", "PHB", "FNM", "FNP", "XLAND", "TSK", "T2", "Q2", "U10", "V10", "HGT", "MU", "MUB", "C1H", "C2H", "DNW", "XLAT", "XLONG")
                       if name not in ds.variables]
            raise ValueError(f"native forecast is missing required selected-column fields: {missing}")
        actual_times = [ds["Times"][k].tobytes().decode("ascii").strip()
                        for k in range(len(ds.dimensions["Time"]))]
        if actual_times != EXPECTED_TIMES:
            raise ValueError(f"actual WRF Times differ from the exact eight required values: {actual_times}")
        native_frames = []
        for ti in range(8):
            _validate_selected_frame_slices(ds, ti, reader)
            native = reader.selected_frame(ds, ti)
            if len(native["p_pa"]) != 39 or len(native["p8w_pa"]) != 40:
                raise ValueError("selected native column must contain 39 centers and 40 calc_p8w interfaces")
            if native["time"] != EXPECTED_TIMES[ti]:
                raise ValueError("selected-column timestamp differs from the independently read WRF Times")
            native_frames.append(native)
            frame_context.append({
                "time": native["time"], "latitude_deg": native["lat"], "longitude_deg": native["lon"],
                "xland": native["xland"], "seaice": native["seaice"],
                "surface": native["surface"],
                "p_centers_native_bottomup_Pa_sha256": array_sha256(native["p_pa"]),
                "p_half_calc_p8w_native_bottomup_Pa_sha256": array_sha256(native["p8w_pa"]),
                "PH_raw_sha256": array_sha256(np.asarray(ds["PH"][ti, :, reader.J, reader.I])),
                "PHB_raw_sha256": array_sha256(np.asarray(ds["PHB"][ti, :, reader.J, reader.I])),
            })

    # State and forcing are from the exact first saved frame. The eight-frame
    # records remain available for downstream time-context and alternate slots.
    for state_field, wrf_name in STATE_TO_RAW.items():
        values = np.stack([np.asarray(n["th"] if state_field == "th" else n["state"][wrf_name], dtype=np.float64)
                           for n in native_frames])
        arrays[f"native_window_state__{state_field}"] = values
        arrays[f"background_initial_state__{state_field}"] = values[0:1].copy()
    forcing_sources = {"rho": "rho_m", "pii": "pii", "p": "p_pa", "delz": "delz"}
    for field, source in forcing_sources.items():
        values = np.stack([np.asarray(n[source], dtype=np.float64) for n in native_frames])
        arrays[f"native_window_forcing__{field}"] = values
        arrays[f"forcing_window_0__{field}"] = values[0:1].copy()
    for field in ("TSK", "T2", "Q2", "U10", "V10", "HGT"):
        arrays[f"native_surface__{field}"] = np.asarray(
            [n["surface"][field] for n in native_frames], dtype=np.float64)
    arrays["native_surface__xland"] = np.asarray([n["xland"] for n in native_frames], dtype=np.float64)
    if all(n["seaice"] is not None for n in native_frames):
        arrays["native_surface__seaice"] = np.asarray(
            [n["seaice"] for n in native_frames], dtype=np.float64)
    arrays["native_surface__latitude_deg"] = np.asarray([n["lat"] for n in native_frames], dtype=np.float64)
    arrays["native_surface__longitude_deg"] = np.asarray([n["lon"] for n in native_frames], dtype=np.float64)
    arrays["rho_d_native_bottomup_kg_m3"] = (
        arrays["forcing_window_0__rho"] / (1.0 + arrays["background_initial_state__qv"]))
    arrays["p_centers_native_bottomup_Pa"] = arrays["forcing_window_0__p"][0].copy()
    arrays["p_half_native_bottomup_Pa"] = np.asarray(native_frames[0]["p8w_pa"], dtype=np.float32).copy()
    with netCDF4.Dataset(forecast, "r") as ds:
        for raw_name in RAW_STATE_FIELDS:
            arrays[f"wrf_raw__{raw_name}"] = np.stack([
                np.asarray(ds[raw_name][ti, :, reader.J, reader.I], dtype=np.float64)
                for ti in range(8)])
        arrays["native_window_p_half_calc_p8w_bottomup_Pa"] = np.stack([
            np.asarray(n["p8w_pa"], dtype=np.float32) for n in native_frames])
        arrays["native_window_PH_raw_bottomup"] = np.stack([
            np.asarray(ds["PH"][ti, :, reader.J, reader.I]) for ti in range(8)])
        arrays["native_window_PHB_raw_bottomup"] = np.stack([
            np.asarray(ds["PHB"][ti, :, reader.J, reader.I]) for ti in range(8)])
        arrays["PH_raw_native_bottomup"] = np.asarray(ds["PH"][0, :, reader.J, reader.I]).copy()
        arrays["PHB_raw_native_bottomup"] = np.asarray(ds["PHB"][0, :, reader.J, reader.I]).copy()
    forecast_stat_after = forecast.stat()
    if ((forecast_stat_before.st_size, forecast_stat_before.st_mtime_ns)
            != (forecast_stat_after.st_size, forecast_stat_after.st_mtime_ns)):
        raise RuntimeError("native forecast size or modification time changed while selected hyperslabs were read")

    # Fixed upper reference atmosphere comes from the retained RTTOV cloud-test
    # profile fixture; current native T/Q/cloud/pressure always replace its model
    # column. Keep this assumption and the fixture hashes visible in the receipt.
    ref = reader.load_reference()
    extended = reader.extend_above_native_top(native_frames[0], ref)
    p_lay, p_half, t_profile, q_profile, o3_profile, co2_profile = extended
    upper_reference_layers = len(p_lay) - 39
    if upper_reference_layers != 27:
        raise ValueError(f"expected the retained 27-layer upper reference profile; got {upper_reference_layers}")
    arrays["p_lay_rttov_topdown_hPa"] = np.asarray(p_lay, dtype=np.float64)
    arrays["p_half_rttov_topdown_hPa"] = np.asarray(p_half, dtype=np.float64)
    arrays["t_rttov_topdown_K"] = np.asarray(t_profile, dtype=np.float64)
    arrays["q_rttov_topdown_ppmv"] = np.asarray(q_profile, dtype=np.float64)
    arrays["o3_rttov_topdown_ppmv"] = np.asarray(o3_profile, dtype=np.float64)
    arrays["co2_rttov_topdown_ppmv"] = np.asarray(co2_profile, dtype=np.float64)

    if len(p_lay) != len(p_half) - 1 or not np.array_equal(
            p_lay[-39:], native_frames[0]["p_pa"][::-1] / 100.0):
        raise ValueError("extended RTTOV grid did not preserve the 39 native centers exactly")
    if not np.array_equal(p_half[-40:], native_frames[0]["p8w_pa"][::-1].astype(np.float64) / 100.0):
        raise ValueError("extended RTTOV grid did not preserve the 40 native P8W interfaces exactly")
    if not all(np.isfinite(a).all() for a in arrays.values()):
        raise FloatingPointError("native intake contains non-finite values")

    # Source hash and method are recorded independently from the current model
    # binary/library identity in run_identity.json.
    helper_path = READER
    launch_evidence = ROOT / "graphify-out/pr395-native-progress"
    loaded_libraries_path = launch_evidence / "LOADED_LIBRARIES.json"
    loaded_libraries = (json.loads(loaded_libraries_path.read_text())
                        if loaded_libraries_path.is_file() else None)
    manifest = {
        "schema": "pr395_native_tq_intake_v1",
        "status": "READY_VALID_NATIVE_INTAKE",
        "native_run": {
            "run_id": EXPECTED_RUN_ID,
            "run_directory": str(run_dir), "forecast_path": str(forecast),
            "runner_exit_code_file": str(run_dir / "exit_code"), "exit_code": 0,
            "experiment_valid": True, "model_completed_flag": True,
            "runner_experiment_valid_sha256": sha256(run_dir / "experiment_valid.json"),
            "runner_identity_sha256": sha256(run_dir / "run_identity.json"),
            "run_identity": identity,
            "validated_run_settings": run_settings,
            "actual_saved_times": actual_times, "expected_saved_times": EXPECTED_TIMES,
            "background_time": EXPECTED_TIMES[0], "forecast_bytes": forecast_stat_after.st_size,
            "forecast_mtime_ns": forecast_stat_after.st_mtime_ns,
            "forecast_size_mtime_stable_while_read": True,
            "forecast_stat_before": {"size_bytes": forecast_stat_before.st_size,
                                     "mtime_ns": forecast_stat_before.st_mtime_ns},
            "forecast_stat_after": {"size_bytes": forecast_stat_after.st_size,
                                    "mtime_ns": forecast_stat_after.st_mtime_ns},
            "forecast_sha256": None,
            "forecast_hash_policy": "not re-read as a multi-GB stream; source is tied to archived completion evidence, file size/mtime, and selected-array hashes",
            "runner_valid_receipt": valid_receipt,
        },
        "selected_column": {"j": reader.J, "i": reader.I, "levels": 39},
        "selected_column_orientation": "zero-based WRF (j,i), vertical bottom-up",
        "clock": {"scenario": "A_nominal_centers_only", "pixel_time_verified": False,
                  "obs_time": 1, "dt_s": 20, "nominal_slot_utc": "2025-07-19_05:56:00",
                  "interpretation": "slot index 1 is the second exact native saved frame; center-sample nominal alignment only"},
        "science_approved": False, "analysis_executed": False,
        "model_data_provenance": {
            "source": "fresh accepted WRF forecast archive selected by this run's completion evidence",
            "reader_path": str(helper_path), "reader_sha256": sha256(helper_path),
            "selected_column_reader": "selected_frame reads one time index and only (j=86,i=48) hyperslabs for state/thermo/surface/coordinates",
            "center_pressure": "float64-first P + PB from stored REAL(4) fields",
            "temperature": "THM plus 300 K, divided by Exner and with Rv/Rd moisture correction as archived selected_frame; State.th carries dry potential temperature",
            "water_vapor": "native QVAPOR retained as kg kg-1 dry-air mixing ratio",
            "cloud_fields": "native WRF Q fields copied by selected_frame, then packed in public KDM6 State field order",
            "native_interface_pressure": {"stored_key": "p_half_native_bottomup_Pa", "dtype": "float32", "method": "Python REAL(4) transcription of calc_p8w; not an executed host output", "source_path": str(P8W_SOURCE), "source_sha256": p8w_source_sha, "precision_note": "P+PB REAL(4), WRF REAL(4) operations; distinct from raw PH/PHB"},
            "raw_height_interfaces": "PH and PHB retained separately from derived calc_p8w interfaces",
            "frames": frame_context,
            "kdm6_moment_floor_inputs": ncmin_context,
            "host_wrapper_forwarding_source": {"path": str(WRAPPER_SOURCE),
                                                "sha256": wrapper_sha,
                                                "source_lines": "ncmin_land and ncmin_sea are copied to C ABI arguments as REAL(c_double)"},
            "frame_array_sha256": {k: array_sha256(v) for k, v in sorted(arrays.items())},
        },
        "upper_reference_assumption": {
            "kind": "fixed_upper_reference_atmosphere_from_retained_RTTOV_test_fixture",
            "fixture_root": str(reader.REF_FIXTURE),
            "files": {name: {"path": str(reader.REF_FIXTURE / "in/profiles/001/atm" / f"{name}.txt"),
                             "sha256": sha256(reader.REF_FIXTURE / "in/profiles/001/atm" / f"{name}.txt")}
                      for name in ("p_half", "t", "q", "o3", "co2")},
            "method": "retain reference levels above native top using archived extend_above_native_top; replace entire 39-layer model segment with each fresh native model input; native p-centers and REAL(4)-transcribed calc_p8w interfaces form exact suffix",
            "grid": {"native_centers": 39, "native_interfaces": 40,
                     "upper_reference_layers": upper_reference_layers,
                     "total_rttov_layers": int(len(p_lay)), "total_rttov_interfaces": int(len(p_half)),
                     "orientation": "RTTOV top-down; native arrays remain bottom-up"},
            "external_model_or_reanalysis_data_used": False,
            "gas_fields": "O3/CO2 from the same fixed reference fixture; interpolation follows archived helper; endpoint behavior is described by that helper",
        },
        "npz": {"path": str(npz_path.resolve()), "sha256": None,
                "keys": sorted(arrays), "array_count": len(arrays)},
        "provenance_scope": {
            "source_snapshot_head": "30931e52f99e38f9abcd6e7e3b8cd055227a5c23",
            "current_worktree_head": "8e5aab06fac08d35efc67374adb1928404103dbb",
            "current_head_build_claimed": False,
            "live_launch_evidence_directory": str(launch_evidence),
            "loaded_libraries_observation": loaded_libraries,
            "loaded_libraries_observation_sha256": (sha256(loaded_libraries_path)
                                                    if loaded_libraries_path.is_file() else None),
            "executable_and_loaded_library": "the live loaded-library observation and run_identity attribute the prepared executable/library; no current-head build claim",
            "notes": "The run's loaded binary/library are attributed by the run identity and separate launch evidence; this intake does not claim that current source was compiled into them.",
        },
    }
    _atomic_npz(npz_path, arrays)
    manifest["npz"]["sha256"] = sha256(npz_path)
    try:
        _write_json_exclusive(manifest_path, manifest)
    except BaseException:
        npz_path.unlink(missing_ok=True)
        raise
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True,
                        help="one completed run_ss_case archive directory")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--npz", type=Path, default=DEFAULT_NPZ)
    args = parser.parse_args()
    result = extract(args.run_dir, args.manifest, args.npz)
    print(json.dumps({"status": result["status"], "manifest": str(args.manifest),
                      "npz": result["npz"], "times": result["native_run"]["actual_saved_times"]}, indent=2))


if __name__ == "__main__":
    main()
