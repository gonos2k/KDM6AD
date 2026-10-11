#!/usr/bin/env python3
"""Read one explicitly named native case into a bounded, provenance-bound NPZ.

This consumer does not launch WRF, search run directories, retry, interpolate,
run KDM6/RTTOV, or create state frames absent from the archived forecast.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
PACKET = Path(__file__).resolve().parent
LEGACY_INTAKE_PATH = ROOT / "harness/evidence/pr395_native_tq_intake_2026-10-10/intake_native_tq.py"
LEGACY_CAPTURE_PATH = ROOT / "harness/evidence/pr395_tq_state_capture_2026-10-10/capture_tq_state.py"
CASE_SCHEMA = "kdm6ad_native_case_v3"
MANIFEST_SCHEMA = "kdm6ad_native_case_intake_v3"
STATE_TO_RAW = {
    "th": "THM", "qv": "QVAPOR", "qc": "QCLOUD", "qr": "QRAIN",
    "qi": "QICE", "qs": "QSNOW", "qg": "QGRAUP", "nccn": "QNCCN",
    "nc": "QNCLOUD", "ni": "QNICE", "nr": "QNRAIN", "bg": "QIB",
}
FORCING_TO_NATIVE = {"rho": "rho_m", "pii": "pii", "p": "p_pa", "delz": "delz"}
ANALYSIS_CHANNEL_NAMES = {
    10: "wv073", 11: "ir087", 12: "ir096", 13: "ir105",
    14: "ir112", 15: "ir123", 16: "ir133",
}
L1B_CHANNEL_ORDER = ("wv063", "wv069", "wv073", "ir087", "ir096", "ir105",
                     "ir112", "ir123", "ir133")
RECEIPT_FILES = ("exit_code", "experiment_valid.json", "run_identity.json", "namelist.input")
TIME_FORMAT = "%Y-%m-%d_%H:%M:%S"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def array_sha256(value: Any) -> str:
    array = np.ascontiguousarray(np.asarray(value))
    return hashlib.sha256(array.tobytes()).hexdigest()


def parse_time(value: str, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a YYYY-MM-DD_HH:MM:SS string")
    try:
        return datetime.strptime(value, TIME_FORMAT)
    except ValueError as exc:
        raise ValueError(f"{label} has invalid WRF time {value!r}") from exc


def validate_case(case_dict: dict) -> dict:
    """Validate and return a detached normalized case; no native files are opened."""
    if not isinstance(case_dict, dict) or case_dict.get("schema") != CASE_SCHEMA:
        raise ValueError(f"case schema must be {CASE_SCHEMA}")
    case = json.loads(json.dumps(case_dict))
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{3,100}", case_id):
        raise ValueError("case_id must be a stable 3–100 character identifier")
    observation = case.get("observation")
    native = case.get("native")
    analysis = case.get("analysis")
    output = case.get("output")
    if not all(isinstance(value, dict) for value in (observation, native, analysis, output)):
        raise ValueError("case must provide observation, native, analysis, and output objects")

    binding_keys = ("source_result_path", "source_result_sha256", "source_payload_path", "source_payload_sha256")
    has_l1b_binding = any(key in observation and observation[key] is not None for key in binding_keys)
    if has_l1b_binding:
        for key in binding_keys:
            if key.endswith("_path"):
                if not isinstance(observation.get(key), str) or not observation[key]:
                    raise ValueError(f"observation.{key} is required when L1B source binding is supplied")
            elif not isinstance(observation.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", observation[key]):
                raise ValueError(f"observation.{key} must be a lowercase SHA-256")
    metadata_fields = ("source_metadata_path", "source_metadata_sha256")
    has_metadata_binding = any(key in observation and observation[key] is not None for key in metadata_fields)
    if has_metadata_binding:
        if not has_l1b_binding:
            raise ValueError("reader metadata receipt requires the L1B result/payload binding")
        if not isinstance(observation.get("source_metadata_path"), str) or not observation["source_metadata_path"]:
            raise ValueError("observation.source_metadata_path is required with its hash")
        if (not isinstance(observation.get("source_metadata_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", observation["source_metadata_sha256"])):
            raise ValueError("observation.source_metadata_sha256 must be a lowercase SHA-256")
    scene_date = observation.get("scene_date")
    if not isinstance(scene_date, str) or not re.fullmatch(r"20\d{6}", scene_date):
        raise ValueError("observation.scene_date must use YYYYMMDD")
    nominal_slot = observation.get("nominal_slot_obt")
    if not isinstance(nominal_slot, str) or not re.fullmatch(r"20\d{10}", nominal_slot):
        raise ValueError("observation.nominal_slot_obt must use YYYYMMDDhhmm")
    if nominal_slot[:8] != scene_date:
        raise ValueError("nominal slot date differs from observation scene_date")
    nominal_time = parse_time(observation.get("nominal_obs_model_time"), "observation.nominal_obs_model_time")
    nominal_from_slot = datetime.strptime(nominal_slot, "%Y%m%d%H%M")
    if nominal_time != nominal_from_slot:
        raise ValueError("nominal model time must match the filename slot interpreted at minute precision")
    if (observation.get("time_assumption") != "NOMINAL_FILENAME_TIME_AS_MODEL_UTC_RESEARCH_MODE"
            or observation.get("observed_pixel_utc") is not None):
        raise ValueError("pixel UTC must remain uncertified under the declared nominal-time assumption")

    background_text = native.get("background_valid_time")
    background = parse_time(background_text, "native.background_valid_time")
    if nominal_time - background != timedelta(seconds=20):
        raise ValueError("the nominal observation model time must be exactly 20 seconds after background_valid_time")
    run_id, run_dir, initial_text = native.get("run_id"), native.get("run_dir"), native.get("initial_time")
    pending_fields = (run_id is None, run_dir is None, initial_text is None)
    if any(pending_fields) and not all(pending_fields):
        raise ValueError("pending native identity requires run_id, run_dir, and initial_time all null")
    if not all(pending_fields):
        if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{3,200}", run_id):
            raise ValueError("native.run_id must be a stable archive identifier")
        if not isinstance(run_dir, str) or not run_dir:
            raise ValueError("native.run_dir is required for a ready case")
        initial = parse_time(initial_text, "native.initial_time")
        if initial > background:
            raise ValueError("native initialization must be no later than background_valid_time")
        if (not isinstance(native.get("completion_receipt_path"), str)
                or not native["completion_receipt_path"]
                or not isinstance(native.get("completion_receipt_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", native["completion_receipt_sha256"])):
            raise ValueError("ready cases require an explicit hash-bound completion receipt naming the run archive")
    elif (native.get("completion_receipt_path") is not None
          or native.get("completion_receipt_sha256") is not None):
        raise ValueError("pending cases cannot bind a completion receipt without a selected native run")

    column = native.get("column")
    if not isinstance(column, dict):
        raise ValueError("native.column is required")
    for axis in ("j", "i"):
        if type(column.get(axis)) is not int or column[axis] < 0:
            raise ValueError(f"native.column.{axis} must be a nonnegative zero-based integer")
    for key in ("expected_latitude_deg", "expected_longitude_deg", "coordinate_tolerance_deg"):
        value = column.get(key)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(float(value)):
            raise ValueError(f"native.column.{key} must be finite")
    if not -90.0 <= float(column["expected_latitude_deg"]) <= 90.0:
        raise ValueError("native expected latitude is out of range")
    if not -180.0 <= float(column["expected_longitude_deg"]) <= 180.0:
        raise ValueError("native expected longitude is out of range")
    if not 0.0 < float(column["coordinate_tolerance_deg"]) <= 0.01:
        raise ValueError("native coordinate tolerance must be in (0,0.01] degrees")
    l1b_pixel = observation.get("nearest_pixel")
    if has_l1b_binding:
        if not isinstance(l1b_pixel, dict):
            raise ValueError("L1B source binding requires observation.nearest_pixel")
        if (type(l1b_pixel.get("row")) is not int or type(l1b_pixel.get("column")) is not int
                or l1b_pixel["row"] < 0 or l1b_pixel["column"] < 0):
            raise ValueError("observation nearest-pixel row/column must be nonnegative integers")
        for key in ("latitude_deg", "longitude_deg"):
            if (isinstance(l1b_pixel.get(key), bool) or not isinstance(l1b_pixel.get(key), (int, float))
                    or not math.isfinite(float(l1b_pixel[key]))):
                raise ValueError(f"observation.nearest_pixel.{key} must be finite")
    diagnostic_times = native.get("diagnostic_times", [])
    if not isinstance(diagnostic_times, list):
        raise ValueError("native.diagnostic_times must be a list")
    if len(set(diagnostic_times)) != len(diagnostic_times):
        raise ValueError("native.diagnostic_times cannot contain duplicates")
    parsed_diagnostics = [parse_time(value, f"native.diagnostic_times[{index}]")
                          for index, value in enumerate(diagnostic_times)]
    if parsed_diagnostics != sorted(parsed_diagnostics):
        raise ValueError("diagnostic_times must be strictly chronological")
    for value in parsed_diagnostics:
        if value <= background:
            raise ValueError("diagnostic times must be later than the core background")

    expected_analysis = {
        "dt_s": 20, "obs_time": 1, "nominal_obs_model_time": observation["nominal_obs_model_time"],
        "all_sky": True, "channel_ids_1based": list(range(10, 17)),
        "require_source_dqf_zero": True, "control_fields": ["th", "qv"],
        "ncmin_land": 10.0, "ncmin_sea": 10.0,
        "use_adaptive_time_step": False, "step_to_output_time": False,
    }
    if analysis != expected_analysis:
        raise ValueError(f"analysis configuration must equal the fixed one-step T/Q contract: {expected_analysis}")
    for key in ("manifest_path", "private_npz_path"):
        if not isinstance(output.get(key), str) or not output[key]:
            raise ValueError(f"output.{key} is required")
    manifest_path = Path(output["manifest_path"]).expanduser().resolve()
    npz_path = Path(output["private_npz_path"]).expanduser().resolve()
    if manifest_path == npz_path:
        raise ValueError("manifest and NPZ output paths must differ")
    case["_normalized_paths"] = {"manifest_path": str(manifest_path), "private_npz_path": str(npz_path)}
    return case


def _load_helper(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load preserved helper {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_legacy():
    intake = _load_helper(LEGACY_INTAKE_PATH, "pr406_preserved_pr395_native_tq_intake")
    capture = _load_helper(LEGACY_CAPTURE_PATH, "pr406_preserved_pr395_tq_capture")
    reader = intake.load_reader()
    return intake, capture, reader


def _read_namelist_value(text: str, name: str) -> str:
    matches = re.findall(rf"(?im)^\s*{re.escape(name)}\s*=\s*([^,!\s]+)", text)
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {name} assignment in archived namelist")
    return matches[0].strip().strip("\"'")


def _namelist_values(text: str, name: str) -> list[str] | None:
    """Read one single-line namelist assignment; reject duplicate/continued forms."""
    matches = []
    for line in text.splitlines():
        value = line.split("!", 1)[0]
        match = re.match(rf"(?i)^\s*{re.escape(name)}\s*=\s*(.*?)\s*$", value)
        if match:
            matches.append(match.group(1))
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(f"unsupported ambiguous archived namelist: multiple {name} assignments")
    values = [item.strip().strip("\"'") for item in matches[0].split(",") if item.strip()]
    return values


def _single_duration_component(text: str, name: str) -> int:
    values = _namelist_values(text, name)
    # WRF run_* values default to zero. They are single-entry parameters.
    if values is None:
        return 0
    if len(values) != 1 or not re.fullmatch(r"[+-]?\d+", values[0]):
        raise ValueError(f"unsupported ambiguous {name} duration assignment")
    value = int(values[0])
    if value < 0:
        raise ValueError(f"archived namelist {name} cannot be negative")
    return value


def _single_end_clock(text: str) -> tuple[datetime | None, str | None]:
    """Resolve a one-domain end_date or end_* tuple; ambiguous vectors fail closed."""
    date_values = _namelist_values(text, "end_date")
    date_value = None
    if date_values is not None:
        if len(date_values) != 1:
            raise ValueError("unsupported ambiguous multi-domain end_date assignment")
        date_value = parse_time(date_values[0], "namelist end_date")

    component_names = ("end_year", "end_month", "end_day", "end_hour")
    present = {name: _namelist_values(text, name) for name in component_names}
    minute_values = _namelist_values(text, "end_minute")
    second_values = _namelist_values(text, "end_second")
    has_components = any(values is not None for values in present.values()) or (
        minute_values is not None or second_values is not None)
    component_time = None
    if has_components:
        fields = {}
        for name, values in present.items():
            if values is None or len(values) != 1 or not re.fullmatch(r"\d+", values[0]):
                raise ValueError("unsupported ambiguous/incomplete end_year/month/day/hour assignment")
            fields[name] = int(values[0])
        for name, values in (("end_minute", minute_values), ("end_second", second_values)):
            if values is None:
                fields[name] = 0
            elif len(values) == 1 and re.fullmatch(r"\d+", values[0]):
                fields[name] = int(values[0])
            else:
                raise ValueError(f"unsupported ambiguous {name} assignment")
        try:
            component_time = datetime(fields["end_year"], fields["end_month"], fields["end_day"],
                                      fields["end_hour"], fields["end_minute"], fields["end_second"])
        except ValueError as exc:
            raise ValueError("archived end_* namelist fields are not a valid WRF time") from exc
    if date_value is not None and component_time is not None and date_value != component_time:
        raise ValueError("end_date conflicts with end_year/month/day/hour fields")
    if date_value is not None:
        return date_value, "end_date"
    if component_time is not None:
        return component_time, "end_year/month/day/hour fields"
    return None, None


def effective_production_window(namelist_text: str, initial_time: str) -> dict:
    """Resolve WRF's effective run stop from run_* duration or end-date fallback.

    WRF uses the additive run_days/run_hours/run_minutes/run_seconds duration
    when nonzero. If all four are zero, it uses the beginning/ending times.
    This case consumer supports one unambiguous domain time, not namelist
    vectors or continued assignments.
    """
    start = parse_time(initial_time, "native.initial_time")
    parts = {name: _single_duration_component(namelist_text, name) for name in
             ("run_days", "run_hours", "run_minutes", "run_seconds")}
    duration = (parts["run_days"] * 86400 + parts["run_hours"] * 3600
                + parts["run_minutes"] * 60 + parts["run_seconds"])
    if duration > 0:
        stop = start + timedelta(seconds=duration)
        basis = "wrf_run_duration_components"
    else:
        stop, basis = _single_end_clock(namelist_text)
        if stop is None:
            raise ValueError("all run_* durations are zero and no supported end_date/end_* is archived")
        duration = int((stop - start).total_seconds())
        if duration < 0:
            raise ValueError("effective archived run stop precedes its initialization time")
    return {"effective_start_time": start.strftime(TIME_FORMAT),
            "effective_stop_time": stop.strftime(TIME_FORMAT),
            "effective_duration_seconds": duration,
            "effective_stop_basis": basis,
            "run_duration_components": parts}


def assert_saved_times_within_production_window(times: list[str], start_time: str, stop_time: str) -> None:
    """Require every archived WRF saved time inside the inclusive production window."""
    start = parse_time(start_time, "effective production start")
    stop = parse_time(stop_time, "effective production stop")
    if stop < start:
        raise ValueError("effective production stop precedes start")
    if not times:
        raise ValueError("native forecast contains no saved Times")
    for index, value in enumerate(times):
        timestamp = parse_time(value, f"forecast Times[{index}]")
        if timestamp < start:
            raise ValueError("archived forecast Times precede effective production start")
        if timestamp > stop:
            raise ValueError("archived forecast Times exceed effective production stop")


def _namelist_control_record(run_dir: Path, identity: dict) -> dict:
    path = run_dir / "namelist.input"
    text = path.read_text()
    controls = identity.get("controls", {})
    namelist_no_grid_hash = hashlib.sha256("\n".join(
        line for line in text.splitlines() if "nproc_x" not in line and "nproc_y" not in line
    ).encode("utf-8")).hexdigest()
    declared_hash = controls.get("namelist_without_grid_sha256")
    if declared_hash != namelist_no_grid_hash:
        raise ValueError("run_identity namelist hash differs from archived effective namelist bytes")

    effective = {
        "mp_physics": _read_namelist_value(text, "mp_physics"),
        "time_step": int(_read_namelist_value(text, "time_step")),
        "history_interval": int(_read_namelist_value(text, "history_interval")),
        "history_interval_s": int(_read_namelist_value(text, "history_interval_s")),
        "use_adaptive_time_step": _read_namelist_value(text, "use_adaptive_time_step").lower(),
        "step_to_output_time": _read_namelist_value(text, "step_to_output_time").lower(),
        "ncmin_land": float(_read_namelist_value(text, "ncmin_land")),
        "ncmin_sea": float(_read_namelist_value(text, "ncmin_sea")),
    }
    fixed = {
        "mp_physics": "337", "time_step": 20,
        "use_adaptive_time_step": ".false.", "step_to_output_time": ".false.",
        "ncmin_land": 10.0, "ncmin_sea": 10.0,
    }
    for key, wanted in fixed.items():
        if effective[key] != wanted:
            raise ValueError(f"archived namelist {key}={effective[key]!r} violates required {wanted!r}")

    identity_map = {"history_interval": "history", "history_interval_s": "history_s"}
    if "time_step" in controls:
        identity_map["time_step"] = "time_step"
    for nml_key, identity_key in identity_map.items():
        if identity_key not in controls or int(controls[identity_key]) != effective[nml_key]:
            raise ValueError(f"run_identity.controls.{identity_key} differs from archived namelist {nml_key}")
    for nml_key, identity_key in (("run_minutes", "minutes"), ("run_seconds", "seconds")):
        try:
            nml_value = int(_read_namelist_value(text, nml_key))
        except ValueError:
            # Some effective namelists use run_hours instead of run_minutes.
            if nml_key == "run_minutes":
                hours = int(_read_namelist_value(text, "run_hours"))
                nml_value = 60 * hours
            else:
                nml_value = 0
        if identity_key in controls and int(controls[identity_key]) != nml_value:
            raise ValueError(f"run_identity.controls.{identity_key} differs from archived namelist {nml_key}")

    return {
        "namelist_path": str(path.resolve()), "namelist_sha256": sha256_file(path),
        "namelist_without_grid_sha256": namelist_no_grid_hash,
        "controls": effective,
        "case_details": {key: controls.get(key) for key in
                         ("label", "minutes", "seconds", "history", "history_s", "radt")},
        "run_identity_declared_controls": controls,
    }


def _archived_initial_time(run_dir: Path, identity: dict, valid: dict) -> str | None:
    """Read the run start from archived namelist or explicit runner metadata."""
    text = (run_dir / "namelist.input").read_text()
    try:
        value = _read_namelist_value(text, "start_date")
        parse_time(value, "namelist start_date")
        return value
    except ValueError:
        pass
    try:
        year = int(_read_namelist_value(text, "start_year"))
        month = int(_read_namelist_value(text, "start_month"))
        day = int(_read_namelist_value(text, "start_day"))
        hour = int(_read_namelist_value(text, "start_hour"))
        minute = int(_read_namelist_value(text, "start_minute")) if re.search(
            r"(?im)^\s*start_minute\s*=", text) else 0
        second = int(_read_namelist_value(text, "start_second")) if re.search(
            r"(?im)^\s*start_second\s*=", text) else 0
        value = datetime(year, month, day, hour, minute, second).strftime(TIME_FORMAT)
        return value
    except (ValueError, TypeError):
        pass
    for source in (identity, valid):
        for key in ("initial_time", "start_time", "start_date"):
            value = source.get(key)
            if isinstance(value, str):
                parse_time(value, f"archived {key}")
                return value
    return None


def _completion_gate(case: dict) -> dict:
    native = case["native"]
    run_dir = Path(native["run_dir"]).expanduser().resolve()
    run_id = native["run_id"]
    if run_dir.name != run_id:
        raise ValueError("run directory basename must equal the case's exact run_id")
    paths = {name: run_dir / name for name in RECEIPT_FILES}
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(f"required archived run evidence is missing: {path}")
    exit_text = paths["exit_code"].read_text().strip()
    valid = json.loads(paths["experiment_valid.json"].read_text())
    identity = json.loads(paths["run_identity.json"].read_text())
    if (exit_text != "0" or valid.get("exit_code") != 0
            or valid.get("experiment_valid") is not True
            or valid.get("model_completed") is not True
            or identity.get("exit_code") != 0
            or identity.get("experiment_valid") is not True):
        raise ValueError("archived runner identity/validity gate did not prove rc=0 and completed valid model run")
    identity_run_id = identity.get("run_id", identity.get("archive_run_id"))
    valid_run_id = valid.get("run_id", valid.get("archive_run_id"))
    for label, declared in (("run_identity", identity_run_id), ("experiment_valid", valid_run_id)):
        if declared is not None and declared != run_id:
            raise ValueError(f"{label} run ID differs from native.run_id")
    completion_path = Path(native["completion_receipt_path"]).expanduser().resolve()
    if not completion_path.is_file():
        raise FileNotFoundError(f"explicit run completion receipt is missing: {completion_path}")
    completion_sha = sha256_file(completion_path)
    if completion_sha != native["completion_receipt_sha256"]:
        raise ValueError("completion receipt SHA-256 differs from case declaration")
    completion = json.loads(completion_path.read_text())
    if completion.get("run_id") != run_id:
        raise ValueError("completion receipt run_id differs from the case's expected run ID")
    if Path(completion.get("run_dir", "")).resolve() != run_dir:
        raise ValueError("completion receipt run_dir differs from the explicit archived run directory")
    identity_sha = sha256_file(paths["run_identity.json"])
    valid_sha = sha256_file(paths["experiment_valid.json"])
    if (completion.get("run_identity_sha256") != identity_sha
            or completion.get("experiment_valid_sha256") != valid_sha
            or completion.get("launcher_exit_code_file") != 0):
        raise ValueError("completion receipt does not bind this archived identity/valid receipt and rc=0")
    completion_valid = completion.get("experiment_valid_receipt", {})
    if (completion_valid.get("exit_code") != 0
            or completion_valid.get("experiment_valid") is not True
            or completion_valid.get("model_completed") is not True
            or completion_valid.get("actual_proc_grid") != "1x1"):
        raise ValueError("completion receipt summary does not confirm valid completed 1x1 run")
    # The old producer's run_identity schema omits an embedded run ID. In that
    # explicit legacy case, the independent completion receipt above supplies
    # the missing link. If the producer declares an ID, require an exact match.
    identity_run_id = identity.get("run_id", identity.get("archive_run_id"))
    if identity_run_id is not None and identity_run_id != run_id:
        raise ValueError("run_identity declared run ID differs from the explicit case run ID")
    if str(identity.get("scheme")) != "337":
        raise ValueError("run_identity.scheme must be 337")
    actual_grid = identity.get("actual_proc_grid")
    if actual_grid != "1x1" or valid.get("actual_proc_grid") != "1x1":
        raise ValueError("runner identity and validity receipts must both report actual grid 1x1")
    controls = identity.get("controls", {})
    if int(controls.get("np", -1)) != 1:
        raise ValueError("run_identity.controls.np must be one rank")
    nml = _namelist_control_record(run_dir, identity)
    start_date = _archived_initial_time(run_dir, identity, valid)
    if start_date is not None and start_date != native["initial_time"]:
        raise ValueError("case initial_time differs from archived run initialization metadata")
    if start_date is None:
        raise ValueError("archived run evidence has no initial_time/start_date binding")
    time_window = effective_production_window((run_dir / "namelist.input").read_text(), start_date)
    return {
        "run_id": run_id, "run_dir": str(run_dir), "initial_time": native["initial_time"],
        **time_window,
        "completion_receipt_path": str(completion_path),
        "completion_receipt_sha256": completion_sha,
        "completion_receipt_identity_fallback": identity_run_id is None,
        "exit_code": 0, "experiment_valid": True, "model_completed": True,
        "experiment_valid_sha256": sha256_file(paths["experiment_valid.json"]),
        "run_identity_sha256": sha256_file(paths["run_identity.json"]),
        "exit_code_file_sha256": sha256_file(paths["exit_code"]),
        "runner_receipt_sha256": {name: sha256_file(path) for name, path in paths.items()},
        "actual_proc_grid": actual_grid, "scheme": str(identity["scheme"]),
        "runner_controls": controls, "namelist": nml,
        "receipt_paths": {key: str(value.resolve()) for key, value in paths.items()},
    }


def _read_wrf_times(ds) -> list[str]:
    if "Times" not in ds.variables:
        raise ValueError("native forecast has no Times coordinate")
    raw = ds["Times"][:]
    if np.ma.is_masked(raw):
        raise ValueError("native forecast Times contains masked entries")
    values = netCDF4.chartostring(np.asarray(raw)).reshape(-1).tolist()
    times = [str(value).rstrip("\x00 ") for value in values]
    parsed = [parse_time(value, f"Times[{index}]") for index, value in enumerate(times)]
    if parsed != sorted(parsed) or len(set(times)) != len(times):
        raise ValueError("native forecast Times must be unique and strictly increasing")
    return times


def _load_result_binding(case: dict) -> dict:
    observation = case["observation"]
    if observation.get("source_result_path") is None:
        return {"binding_status": "NATIVE_CORE_INTAKE_ONLY",
                "scene_date": observation["scene_date"],
                "nominal_slot_obt": observation["nominal_slot_obt"],
                "nominal_obs_model_time": observation["nominal_obs_model_time"],
                "time_assumption": observation["time_assumption"],
                "observed_pixel_utc": None,
                "result_path": None, "result_sha256": None, "payload_path": None,
                "payload_sha256": None, "metadata_path": None, "metadata_sha256": None,
                "reader_geos": None}
    result_path = Path(observation["source_result_path"]).expanduser().resolve()
    payload_path = Path(observation["source_payload_path"]).expanduser().resolve()
    metadata_path = (Path(observation["source_metadata_path"]).expanduser().resolve()
                     if observation.get("source_metadata_path") else None)
    if (not result_path.is_file() or not payload_path.is_file()
            or (metadata_path is not None and not metadata_path.is_file())):
        raise FileNotFoundError("case source result, original private payload, or reader metadata receipt is missing")
    result_bytes = result_path.read_bytes()
    result_sha = hashlib.sha256(result_bytes).hexdigest()
    payload_sha = sha256_file(payload_path)
    metadata_bytes = metadata_path.read_bytes() if metadata_path is not None else None
    metadata_sha = hashlib.sha256(metadata_bytes).hexdigest() if metadata_bytes is not None else None
    if result_sha != observation["source_result_sha256"]:
        raise ValueError("case source result SHA-256 differs from its declared binding")
    if payload_sha != observation["source_payload_sha256"]:
        raise ValueError("original L1B payload SHA-256 differs from its declared binding")
    if metadata_path is not None and metadata_sha != observation["source_metadata_sha256"]:
        raise ValueError("original L1B metadata receipt SHA-256 differs from its declared binding")
    result = json.loads(result_bytes)
    if result.get("schema") != "pr403_gk2a_l1b_heldout_result_v1":
        raise ValueError("observation result is not the admitted PR403 GK2A AMI L1B result")
    if result.get("status") != "DECODED_GK2A_L1B_SCENES_ONLY":
        raise ValueError("observation result does not record completed scene-only decode")
    if result.get("private_payload_sha256") != payload_sha:
        raise ValueError("result's private payload SHA does not match the provided payload")
    if Path(result.get("private_payload_path", "")).resolve() != payload_path:
        raise ValueError("case source result path differs from the declared private payload")
    if metadata_path is not None:
        if Path(result.get("private_decode_receipt_path", "")).resolve() != metadata_path:
            raise ValueError("case source metadata path differs from the result's decode-receipt path")
        decode_receipt = json.loads(metadata_bytes)
        if (Path(decode_receipt.get("private_npz_path", "")).resolve() != payload_path
                or decode_receipt.get("private_npz_sha256") != payload_sha):
            raise ValueError("private decode receipt does not bind the declared original payload")
    else:
        decode_receipt = None
    scene = next((row for row in result.get("scenes", [])
                  if row.get("date") == observation["scene_date"]), None)
    if scene is None or scene.get("selected_nominal_slot_obt") != observation["nominal_slot_obt"]:
        raise ValueError("case scene/date/nominal slot does not match the bound observation result")
    reader_geos = None
    if decode_receipt is not None:
        metadata_scene = next((row for row in decode_receipt.get("scenes", [])
                               if row.get("date") == observation["scene_date"]), None)
        if (metadata_scene is None
                or metadata_scene.get("selected_nominal_slot_obt") != observation["nominal_slot_obt"]
                or metadata_scene.get("nearest_pixel") != scene.get("nearest_pixel")):
            raise ValueError("public L1B result and original reader metadata receipt disagree on scene/nearest pixel")
        reader_metadata = metadata_scene.get("reader_metadata", {})
        if (reader_metadata.get("nominal_slot_obt") != observation["nominal_slot_obt"]
                or reader_metadata.get("pixel_utc_time_verified") is not False
                or reader_metadata.get("payload_valid_time_role") != "unset; filename label is OBT and no documented UTC conversion was applied"
                or reader_metadata.get("projection_type") != "GEOS"
                or not isinstance(reader_metadata.get("geos"), dict)
                or not isinstance(reader_metadata.get("geos_header_upper_left_rad"), dict)
                or reader_metadata.get("image_shape") != [500, 500]
                or reader_metadata.get("channels") != list(L1B_CHANNEL_ORDER)):
            raise ValueError("original reader metadata lacks the expected GEOS/nominal-time provenance")
        reader_geos = reader_metadata["geos"]
    if scene.get("status") != "POINT_WITHIN_RADIUS" or not scene.get("nearest_pixel_within_2p5km"):
        raise ValueError("L1B scene does not have the declared supported nearest pixel")
    dqf = scene.get("nearest_pixel", {}).get("reader_dqf_by_channel", {})
    expected_dqf_names = [ANALYSIS_CHANNEL_NAMES[channel] for channel in range(10, 17)]
    if any(dqf.get(channel) != 0 for channel in expected_dqf_names):
        raise ValueError("all seven admitted analysis-channel L1B DQFs must be zero")
    declared_pixel = observation["nearest_pixel"]
    result_pixel = scene["nearest_pixel"]
    for key in ("row", "column", "latitude_deg", "longitude_deg"):
        expected = declared_pixel[key]
        actual = result_pixel[key]
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            if not math.isclose(float(expected), float(actual), rel_tol=0.0, abs_tol=1e-9):
                raise ValueError(f"case L1B nearest pixel {key} differs from immutable result")
        elif expected != actual:
            raise ValueError(f"case L1B nearest pixel {key} differs from immutable result")
    if scene.get("time_interpretation") != (
            "Filename label and scene acquisition are OBT; mission_reference_time is planned UTC; "
            "payload valid_time_utc remains unset."):
        raise ValueError("observation result time provenance has changed")
    return {
        "binding_status": "BOUND_GK2A_L1B_SCENE",
        "scene_date": scene["date"], "nominal_slot_obt": scene["selected_nominal_slot_obt"],
        "nominal_obs_model_time": observation["nominal_obs_model_time"],
        "time_assumption": observation["time_assumption"],
        "result_path": str(result_path), "result_sha256": result_sha,
        "payload_path": str(payload_path), "payload_sha256": payload_sha,
        "metadata_path": str(metadata_path) if metadata_path is not None else None,
        "metadata_sha256": metadata_sha,
        "nearest_pixel": scene["nearest_pixel"],
        "nearest_pixel_within_2p5km": True,
        "analysis_channel_ids_1based": list(range(10, 17)),
        "analysis_channel_dqf": {name: dqf[name] for name in expected_dqf_names},
        "reader_geos": reader_geos,
        "reader_geos_header_upper_left_rad": (reader_metadata.get("geos_header_upper_left_rad")
                                               if metadata_path is not None else None),
        "reader_image_shape": (reader_metadata.get("image_shape") if metadata_path is not None else None),
        "reader_pixel_index_semantics": (reader_metadata.get("pixel_index_semantics")
                                         if metadata_path is not None else None),
        "reader_projection_type": (reader_metadata.get("projection_type") if metadata_path is not None else None),
        "reader_metadata_channels": (reader_metadata.get("channels") if metadata_path is not None else None),
        "observed_pixel_utc": None,
        "time_interpretation": scene["time_interpretation"],
    }


def _selected_frame(reader, ds, ti: int, j: int, i: int) -> dict:
    """Parameterised copy of PR395 reader arithmetic; reader module globals stay untouched."""
    if int(getattr(ds, "USE_THETA_M", 1)) != 1:
        raise ValueError("only USE_THETA_M=1 frame reconstruction is supported")
    arrays = {name: np.asarray(ds[name][ti, :, j, i], dtype=np.float64)
              for name in reader.STATE_VARS}
    p_pa = (np.asarray(ds["P"][ti, :, j, i], dtype=np.float64)
            + np.asarray(ds["PB"][ti, :, j, i], dtype=np.float64))
    qv = arrays["QVAPOR"]
    thm = arrays["THM"] + reader.T0
    pii = np.power(p_pa / reader.P0, reader.RCP)
    th = thm / (1.0 + (reader.R_V / reader.R_D) * qv)
    rho_d = p_pa / (reader.R_D * thm * pii)
    rho_m = rho_d * (1.0 + qv)
    ph64 = np.asarray(ds["PH"][ti, :, j, i], dtype=np.float64)
    phb64 = np.asarray(ds["PHB"][ti, :, j, i], dtype=np.float64)
    z_w = (ph64 + phb64) / float(reader.G)
    delz = z_w[1:] - z_w[:-1]
    xland = float(ds["XLAND"][ti, j, i])
    seaice = float(ds["SEAICE"][ti, j, i]) if "SEAICE" in ds.variables else None
    surface = {name: float(ds[name][ti, j, i]) for name in
               ("TSK", "T2", "Q2", "U10", "V10", "HGT")}
    mu = np.float32(ds["MU"][ti, j, i])
    mub = np.float32(ds["MUB"][ti, j, i])
    c1h = np.asarray(ds["C1H"][ti, :], dtype=np.float32)
    c2h = np.asarray(ds["C2H"][ti, :], dtype=np.float32)
    dnw = np.asarray(ds["DNW"][ti, :], dtype=np.float32)
    host_mass = (-(c1h * (mu + mub) + c2h) * dnw / np.float32(9.81)).astype(np.float32)
    p8w = reader.p8w_for_column(ds, ti, j, i)
    lat, lon = float(ds["XLAT"][ti, j, i]), float(ds["XLONG"][ti, j, i])
    numeric = (p_pa, rho_d, rho_m, pii, delz, host_mass, p8w, ph64, phb64)
    if (xland != 2.0 or (seaice is not None and seaice != 0.0)
            or not all(np.isfinite(value).all() for value in numeric)
            or not all(math.isfinite(value) for value in (*surface.values(), lat, lon))
            or np.any(host_mass <= 0.0) or np.any(delz <= 0.0)):
        raise ValueError(f"selected case column is nonfinite, land/ice, or has invalid layer metrics at Time={ti}")
    if len(p_pa) != 39 or len(p8w) != 40:
        raise ValueError("native selected column must contain 39 centers and 40 P8W interfaces")
    return {"state": arrays, "p_pa": p_pa, "th": th, "pii": pii, "rho_d": rho_d,
            "rho_m": rho_m, "delz": delz, "p8w_pa": p8w, "host_dry_mass_kg_m2": host_mass,
            "xland": xland, "seaice": seaice, "surface": surface,
            "lat": lat, "lon": lon, "time": ds["Times"][ti].tobytes().decode("ascii").strip()}


def _coordinates_and_reference(reader, native: dict) -> tuple[dict[str, np.ndarray], dict]:
    reader.validate_p8w_source()
    ref_files = {name: reader.REF_FIXTURE / "in/profiles/001/atm" / f"{name}.txt"
                 for name in ("p_half", "t", "q", "o3", "co2")}
    reference_bindings = {}
    expected_hashes = {
        "p_half": "4836e1a4726c4f5574fc77812bc2a6ddc2fe9bf74461c4d1fe6ddc641d8d263d",
        "t": "0777e1ae6390e4c21658e79cb62086d9b15387aca90a8ee90affcda9cfdaf4cd",
        "q": "d0ababfea9c62b2860d7e4abfd6f0f11a7b5e53fe23273221b6a3aeb94c85268",
        "o3": "9e34e3d23760e51c980f8a74b221ddfde829b2d6ea88f979e7fefa2895483ad7",
        "co2": "1f2fa0ab7945f5d642cbc3fa54c64c9b7af0867a55e3451555e3a972afece9df",
    }
    ref = reader.load_reference()
    for name, path in ref_files.items():
        digest = sha256_file(path)
        if digest != expected_hashes[name]:
            raise ValueError(f"pinned RTTOV upper-reference file changed: {path}")
        reference_bindings[name] = {"path": str(path.resolve()), "sha256": digest}
    p_lay, p_half, t, q, o3, co2 = reader.extend_above_native_top(native, ref)
    if len(p_lay) != 66 or len(p_half) != 67:
        raise ValueError("pinned reference extension must contain 27+39 layers and 27+40 interfaces")
    if (not np.array_equal(p_lay[-39:], native["p_pa"][::-1] / 100.0)
            or not np.array_equal(p_half[-40:], native["p8w_pa"][::-1].astype(np.float64) / 100.0)):
        raise ValueError("p_lay/p_half native suffixes differ from exact selected-column pressure")
    arrays = {
        "p_centers_native_bottomup_Pa": native["p_pa"].copy(),
        "p_half_native_bottomup_Pa": np.asarray(native["p8w_pa"], dtype=np.float32).copy(),
        "PH_raw_native_bottomup": np.asarray(native["PH_raw"], dtype=np.float64).copy(),
        "PHB_raw_native_bottomup": np.asarray(native["PHB_raw"], dtype=np.float64).copy(),
        "p_lay_rttov_topdown_hPa": np.asarray(p_lay, dtype=np.float64),
        "p_half_rttov_topdown_hPa": np.asarray(p_half, dtype=np.float64),
        "t_rttov_topdown_K": np.asarray(t, dtype=np.float64),
        "q_rttov_topdown_ppmv": np.asarray(q, dtype=np.float64),
        "o3_rttov_topdown_ppmv": np.asarray(o3, dtype=np.float64),
        "co2_rttov_topdown_ppmv": np.asarray(co2, dtype=np.float64),
    }
    return arrays, {"fixture_root": str(reader.REF_FIXTURE), "files": reference_bindings,
                    "upper_reference_layers": 27, "native_centers": 39, "native_interfaces": 40,
                    "total_layers": 66, "total_interfaces": 67,
                    "external_model_or_reanalysis_data_used": False,
                    "p8w_source_path": str(reader.WRF_P8W_SOURCE.resolve()),
                    "p8w_source_sha256": reader.validate_p8w_source(),
                    "p8w_method": "PR395 pinned Python REAL(4) calc_p8w transcription; distinct from raw PH/PHB"}


def _make_arrays(frames: list[dict], selected_times: list[str], background_time: str,
                 intake_module, capture_module, reader) -> tuple[dict[str, np.ndarray], dict]:
    if not frames or frames[0]["time"] != background_time:
        raise ValueError("the first selected native frame must be the required background")
    arrays: dict[str, np.ndarray] = {}
    for field in capture_module.STATE_FIELDS:
        raw_name = intake_module.STATE_TO_RAW[field]
        values = np.stack([np.asarray(frame["th"] if field == "th" else frame["state"][raw_name], dtype=np.float64)
                           for frame in frames])
        arrays[f"native_window_state__{field}"] = values
        arrays[f"background_initial_state__{field}"] = values[0:1].copy()
    for field in capture_module.FORCING_FIELDS:
        source = FORCING_TO_NATIVE[field]
        values = np.stack([np.asarray(frame[source], dtype=np.float64) for frame in frames])
        arrays[f"native_window_forcing__{field}"] = values
        arrays[f"forcing_window_0__{field}"] = values[0:1].copy()
    arrays["native_window_rho_d_kg_m3"] = np.stack([
        np.asarray(frame["rho_d"], dtype=np.float64) for frame in frames])
    arrays["rho_d_native_bottomup_kg_m3"] = arrays["native_window_rho_d_kg_m3"][0:1].copy()
    arrays["native_window_host_dry_mass_kg_m2"] = np.stack([
        np.asarray(frame["host_dry_mass_kg_m2"], dtype=np.float32) for frame in frames])
    arrays["host_dry_mass_background_kg_m2"] = arrays["native_window_host_dry_mass_kg_m2"][0].copy()
    for surface_key in ("TSK", "T2", "Q2", "U10", "V10", "HGT"):
        arrays[f"native_surface__{surface_key}"] = np.asarray(
            [frame["surface"][surface_key] for frame in frames], dtype=np.float64)
    for surface_key in ("xland", "latitude_deg", "longitude_deg"):
        source_key = {"latitude_deg": "lat", "longitude_deg": "lon"}.get(surface_key, surface_key)
        arrays[f"native_surface__{surface_key}"] = np.asarray(
            [frame[source_key] for frame in frames], dtype=np.float64)
    if all(frame["seaice"] is not None for frame in frames):
        arrays["native_surface__seaice"] = np.asarray([frame["seaice"] for frame in frames], dtype=np.float64)
    arrays["native_window_PH_raw_bottomup"] = np.stack([frame["PH_raw"] for frame in frames])
    arrays["native_window_PHB_raw_bottomup"] = np.stack([frame["PHB_raw"] for frame in frames])
    arrays["native_window_p_half_calc_p8w_bottomup_Pa"] = np.stack([
        np.asarray(frame["p8w_pa"], dtype=np.float32) for frame in frames])
    arrays["PH_raw_native_bottomup"] = frames[0]["PH_raw"].copy()
    arrays["PHB_raw_native_bottomup"] = frames[0]["PHB_raw"].copy()
    for raw_name in reader.STATE_VARS:
        arrays[f"wrf_raw__{raw_name}"] = np.stack([frame["state"][raw_name] for frame in frames])

    extra, ref_manifest = _coordinates_and_reference(reader, frames[0])
    arrays.update(extra)
    if not all(np.isfinite(value).all() for value in arrays.values()):
        raise FloatingPointError("selected native intake contains nonfinite arrays")
    mass = arrays["native_window_host_dry_mass_kg_m2"]
    if mass.dtype != np.float32 or mass.shape != (len(selected_times), 39) or np.any(mass <= 0.0):
        raise ValueError("host dry mass must remain positive float32 [Nselected,39]")
    if (arrays["p_centers_native_bottomup_Pa"].shape != (39,)
            or arrays["p_half_native_bottomup_Pa"].shape != (40,)):
        raise ValueError("native pressure coordinates must have exactly 39 centers and 40 interfaces")
    return arrays, ref_manifest


def _write_json_exclusive(path: Path, payload: dict) -> None:
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to replace case manifest {path}")
    temp_fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    linked = False
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, 0o644)
        os.link(temp, path)
        linked = True
        temp.unlink()
    except BaseException:
        temp.unlink(missing_ok=True)
        if linked:
            path.unlink(missing_ok=True)
        raise


def _array_inventory(arrays: dict[str, np.ndarray]) -> dict:
    return {name: {"shape": list(value.shape), "dtype": str(value.dtype),
                   "sha256": array_sha256(value)} for name, value in sorted(arrays.items())}


def _case_contract_snapshot(case: dict) -> dict:
    return {key: value for key, value in case.items() if not key.startswith("_")}


def _pending_manifest(case: dict, case_path: Path, case_sha: str, reason: str) -> dict:
    native = case["native"]
    return {
        "schema": MANIFEST_SCHEMA, "status": "PENDING_NATIVE_INPUT", "case_id": case["case_id"],
        "case_schema": CASE_SCHEMA,
        "manifest_path": case["_normalized_paths"]["manifest_path"],
        "private_npz_path": case["_normalized_paths"]["private_npz_path"],
        "case_json": {"path": str(case_path.resolve()), "sha256": case_sha},
        "case_contract": _case_contract_snapshot(case),
        "observation": case["observation"], "analysis": case["analysis"],
        "native_request": {"run_id": native["run_id"], "run_dir": native["run_dir"],
                           "initial_time": native["initial_time"],
                           "background_valid_time": native["background_valid_time"],
                           "nominal_obs_model_time": case["observation"]["nominal_obs_model_time"],
                           "column": native["column"], "diagnostic_times_requested": native["diagnostic_times"]},
        "pending_reason": reason,
        "npz": None,
        "analysis_executed": False,
    }


def _ready_manifest(case: dict, case_path: Path, case_sha: str, observation: dict,
                    run_binding: dict, forecast_path: Path, stat_before, stat_after,
                    selected_times: list[str], selected_indices: list[int], missing_diagnostics: list[str],
                    arrays: dict[str, np.ndarray], reference: dict, npz_path: Path) -> dict:
    capture_sha = sha256_file(LEGACY_CAPTURE_PATH)
    intake_sha = sha256_file(LEGACY_INTAKE_PATH)
    consumer_path = Path(__file__).resolve()
    reader_path = ROOT / "harness/evidence/native358_artifact_diag_2026-10-08/recipe/run_native_kma_bt_frames.py"
    return {
        "schema": MANIFEST_SCHEMA, "status": "READY_CORE_NATIVE_INTAKE", "case_id": case["case_id"],
        "case_schema": CASE_SCHEMA,
        "manifest_path": case["_normalized_paths"]["manifest_path"],
        "private_npz_path": str(npz_path.resolve()),
        "case_json": {"path": str(case_path.resolve()), "sha256": case_sha},
        "case_contract": _case_contract_snapshot(case),
        "observation": observation,
        "analysis_contract": case["analysis"],
        "native_run": {**run_binding,
            "forecast_path": str(forecast_path.resolve()),
            "forecast_stat_before": {"size_bytes": stat_before.st_size, "mtime_ns": stat_before.st_mtime_ns},
            "forecast_stat_after": {"size_bytes": stat_after.st_size, "mtime_ns": stat_after.st_mtime_ns},
            "forecast_size_mtime_stable_while_read": True,
            "initial_time": case["native"]["initial_time"],
            "background_valid_time": case["native"]["background_valid_time"],
            "nominal_obs_model_time": case["observation"]["nominal_obs_model_time"],
            "selected_times": selected_times, "selected_time_indices": selected_indices,
            "diagnostic_times_requested": case["native"]["diagnostic_times"],
            "diagnostic_times_omitted": missing_diagnostics,
            "native_observation_slot_required": False,
            "local_forcing_window_count": 1,
            "local_forcing_source_valid_time": case["native"]["background_valid_time"],
            "selected_column": {**case["native"]["column"], "levels": 39,
                                "actual_latitude_deg": float(arrays["native_surface__latitude_deg"][0]),
                                "actual_longitude_deg": float(arrays["native_surface__longitude_deg"][0])}},
        "source_bindings": {
            "observation_result_path": observation["result_path"],
            "observation_result_sha256": observation["result_sha256"],
            "original_observation_payload_path": observation["payload_path"],
            "original_observation_payload_sha256": observation["payload_sha256"],
            "observation_metadata_receipt_path": observation["metadata_path"],
            "observation_metadata_receipt_sha256": observation["metadata_sha256"],
            "pr395_intake_helper_path": str(LEGACY_INTAKE_PATH.resolve()),
            "pr395_intake_helper_sha256": intake_sha,
            "pr395_capture_helper_path": str(LEGACY_CAPTURE_PATH.resolve()),
            "pr395_capture_helper_sha256": capture_sha,
            "native_case_consumer_path": str(consumer_path),
            "native_case_consumer_sha256": sha256_file(consumer_path),
            "native_completion_receipt_path": run_binding["completion_receipt_path"],
            "native_completion_receipt_sha256": run_binding["completion_receipt_sha256"],
            "selected_column_reader_path": str(reader_path.resolve()),
            "selected_column_reader_sha256": sha256_file(reader_path),
            "p8w_reference_assets": reference,
        },
        "npz": {"path": str(npz_path.resolve()), "sha256": sha256_file(npz_path),
                "array_count": len(arrays), "arrays": _array_inventory(arrays),
                "host_dry_mass_key": "native_window_host_dry_mass_kg_m2",
                "host_dry_mass_dtype": "float32", "host_dry_mass_orientation": "bottom-up native levels"},
        "analysis_executed": False, "science_approved": False,
    }


def load_case(case_path: Path) -> dict:
    """Create a ready bounded intake, or return a pending manifest without opening a run."""
    case_path = Path(case_path).expanduser().resolve()
    raw_case = case_path.read_bytes()
    case_sha = hashlib.sha256(raw_case).hexdigest()
    case = validate_case(json.loads(raw_case))
    manifest_path = Path(case["_normalized_paths"]["manifest_path"])
    npz_path = Path(case["_normalized_paths"]["private_npz_path"])
    if manifest_path.exists() or npz_path.exists():
        raise FileExistsError("refusing to overwrite an existing intake manifest or NPZ")
    observation = _load_result_binding(case)
    if case["native"]["run_id"] is None:
        manifest = _pending_manifest(case, case_path, case_sha, "case has no selected native run ID/directory/initial time")
        _write_json_exclusive(manifest_path, manifest)
        return {"case": case, "manifest": manifest, "arrays": None}

    run_binding = _completion_gate(case)
    forecast_candidates = sorted(Path(case["native"]["run_dir"]).resolve().glob("klfs_lc05_fcst.*"))
    if len(forecast_candidates) != 1 or not forecast_candidates[0].is_file():
        raise ValueError("explicit run archive must contain exactly one klfs_lc05_fcst.* file")
    forecast = forecast_candidates[0]
    stat_before = forecast.stat()
    requested_diagnostics = list(case["native"]["diagnostic_times"])
    with netCDF4.Dataset(forecast, "r") as ds:
        if int(getattr(ds, "USE_THETA_M", 0)) != 1:
            raise ValueError("native forecast must declare USE_THETA_M=1")
        times = _read_wrf_times(ds)
        assert_saved_times_within_production_window(
            times, run_binding["effective_start_time"], run_binding["effective_stop_time"])
        time_to_index = {value: index for index, value in enumerate(times)}
        background_time = case["native"]["background_valid_time"]
        if parse_time(background_time, "native.background_valid_time") > parse_time(
                run_binding["effective_stop_time"], "effective production stop"):
            raise ValueError("required native background is after the effective archived production stop")
        if background_time not in time_to_index:
            stat_after = forecast.stat()
            if (stat_before.st_size, stat_before.st_mtime_ns) != (stat_after.st_size, stat_after.st_mtime_ns):
                raise RuntimeError("forecast changed while reading Times metadata")
            manifest = _pending_manifest(case, case_path, case_sha,
                f"required background valid time {background_time} is absent from archived Times")
            manifest["available_forecast_times_metadata"] = {"first": times[0], "last": times[-1], "count": len(times)}
            _write_json_exclusive(manifest_path, manifest)
            return {"case": case, "manifest": manifest, "arrays": None}
        missing_diagnostics = [value for value in requested_diagnostics if value not in time_to_index]
        selected_diagnostics = [value for value in requested_diagnostics if value in time_to_index]
        selected_times = [background_time] + selected_diagnostics
        selected_indices = [time_to_index[value] for value in selected_times]
        intake_helpers, capture_helpers, reader = _load_legacy()
        column = case["native"]["column"]
        selector = SimpleNamespace(J=column["j"], I=column["i"])
        frames = []
        for time_index in selected_indices:
            intake_helpers._validate_selected_frame_slices(ds, time_index, selector)
            native = _selected_frame(reader, ds, time_index, column["j"], column["i"])
            if native["time"] != times[time_index]:
                raise ValueError("selected-column reader timestamp differs from exact WRF Times metadata")
            lat_tol = float(column["coordinate_tolerance_deg"])
            if (abs(native["lat"] - float(column["expected_latitude_deg"])) > lat_tol
                    or abs(native["lon"] - float(column["expected_longitude_deg"])) > lat_tol):
                raise ValueError("actual XLAT/XLONG differs from case-declared native column coordinate")
            # Preserve selected raw heights separately from the P8W interface pressure.
            native["PH_raw"] = np.asarray(ds["PH"][time_index, :, column["j"], column["i"]]).copy()
            native["PHB_raw"] = np.asarray(ds["PHB"][time_index, :, column["j"], column["i"]]).copy()
            frames.append(native)
    stat_after = forecast.stat()
    if (stat_before.st_size, stat_before.st_mtime_ns) != (stat_after.st_size, stat_after.st_mtime_ns):
        raise RuntimeError("forecast size or modification time changed while selected hyperslabs were read")
    arrays, reference_manifest = _make_arrays(frames, selected_times,
        case["native"]["background_valid_time"], intake_helpers, capture_helpers, reader)
    # Atomic private no-clobber publication comes from the preserved PR395 intake helper.
    intake_helpers._atomic_npz(npz_path, arrays)
    try:
        manifest = _ready_manifest(case, case_path, case_sha, observation, run_binding,
            forecast, stat_before, stat_after, selected_times, selected_indices,
            missing_diagnostics, arrays, reference_manifest, npz_path)
        _write_json_exclusive(manifest_path, manifest)
    except BaseException:
        npz_path.unlink(missing_ok=True)
        raise
    return {"case": case, "manifest": manifest, "arrays": arrays}


def load_bound_intake(manifest_path: Path, npz_path: Path, *,
                      require_observation: bool = True) -> tuple[dict, dict[str, np.ndarray]]:
    """Reopen a completed intake; analysis callers require original L1B bindings by default."""
    manifest_path = Path(manifest_path).expanduser().resolve()
    npz_path = Path(npz_path).expanduser().resolve()
    manifest = json.loads(manifest_path.read_bytes())
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("status") != "READY_CORE_NATIVE_INTAKE":
        raise ValueError("analysis adapter requires READY_CORE_NATIVE_INTAKE")
    if Path(manifest.get("manifest_path", "")).resolve() != manifest_path:
        raise ValueError("manifest path differs from its recorded publication path")
    case_binding = manifest.get("case_json", {})
    case_path = Path(case_binding.get("path", "")).resolve()
    if not case_path.is_file() or sha256_file(case_path) != case_binding.get("sha256"):
        raise ValueError("case JSON changed after native intake")
    case = validate_case(json.loads(case_path.read_bytes()))
    if (manifest.get("case_id") != case["case_id"]
            or manifest.get("case_contract") != _case_contract_snapshot(case)):
        raise ValueError("manifest case contract differs from its exact bound case JSON")
    if (manifest.get("analysis_contract") != case["analysis"]
            or manifest.get("private_npz_path") != case["_normalized_paths"]["private_npz_path"]
            or npz_path != Path(case["_normalized_paths"]["private_npz_path"])):
        raise ValueError("manifest analysis/output contract differs from its bound case JSON")
    npz_binding = manifest.get("npz", {})
    if (Path(npz_binding.get("path", "")).resolve() != npz_path
            or not npz_path.is_file() or sha256_file(npz_path) != npz_binding.get("sha256")):
        raise ValueError("private NPZ path/SHA-256 differs from ready manifest")
    native_case = case["native"]
    native_manifest = manifest.get("native_run", {})
    gate = _completion_gate(case)
    for key in ("run_id", "run_dir", "initial_time", "scheme", "actual_proc_grid",
                "completion_receipt_path", "completion_receipt_sha256",
                "completion_receipt_identity_fallback", "runner_receipt_sha256", "receipt_paths", "namelist",
                "effective_start_time", "effective_stop_time", "effective_duration_seconds",
                "effective_stop_basis", "run_duration_components"):
        if native_manifest.get(key) != gate.get(key):
            raise ValueError(f"native manifest {key} differs from current archived run receipts")
    for key in ("run_id", "initial_time", "background_valid_time"):
        if native_manifest.get(key) != native_case.get(key):
            raise ValueError(f"manifest native_run.{key} differs from case JSON")
    if (Path(native_manifest.get("run_dir", "")).resolve() != Path(native_case["run_dir"]).resolve()
            or Path(native_manifest.get("completion_receipt_path", "")).resolve() !=
               Path(native_case["completion_receipt_path"]).resolve()
            or native_manifest.get("completion_receipt_sha256") != native_case["completion_receipt_sha256"]
            or native_manifest.get("nominal_obs_model_time") != case["observation"]["nominal_obs_model_time"]
            or native_manifest.get("selected_column", {}).get("j") != native_case["column"]["j"]
            or native_manifest.get("selected_column", {}).get("i") != native_case["column"]["i"]):
        raise ValueError("manifest run/target/column binding differs from case JSON")
    omitted = native_manifest.get("diagnostic_times_omitted", [])
    expected_selected = [native_case["background_valid_time"]] + [
        value for value in native_case["diagnostic_times"] if value not in omitted]
    if (native_manifest.get("selected_times") != expected_selected
            or len(native_manifest.get("selected_time_indices", [])) != len(expected_selected)):
        raise ValueError("manifest selected times do not match required background plus optional diagnostics")
    observation = manifest.get("observation", {})
    if require_observation and (observation.get("binding_status") != "BOUND_GK2A_L1B_SCENE"
                                or not observation.get("metadata_path")
                                or not observation.get("payload_path")
                                or not observation.get("result_path")
                                or not isinstance(observation.get("reader_geos"), dict)
                                or any(value != 0 for value in observation.get("analysis_channel_dqf", {}).values())
                                or set(observation.get("analysis_channel_dqf", {})) !=
                                {ANALYSIS_CHANNEL_NAMES[channel] for channel in range(10, 17)}):
        raise ValueError("analysis adapter requires bound PR403 scene/result/metadata/payload and seven DQF0 checks")
    current_observation = _load_result_binding(case)
    for key in ("binding_status", "scene_date", "nominal_slot_obt", "nominal_obs_model_time",
                "time_assumption", "observed_pixel_utc", "result_path", "result_sha256",
                "payload_path", "payload_sha256", "metadata_path", "metadata_sha256",
                "nearest_pixel", "nearest_pixel_within_2p5km", "analysis_channel_ids_1based",
                "analysis_channel_dqf", "reader_geos", "reader_geos_header_upper_left_rad",
                "reader_image_shape", "reader_pixel_index_semantics", "reader_projection_type",
                "reader_metadata_channels", "time_interpretation"):
        if observation.get(key) != current_observation.get(key):
            raise ValueError(f"manifest observation binding {key} differs from its case/source receipts")
    bindings = manifest.get("source_bindings", {})
    case_observation = case["observation"]
    if observation.get("scene_date") != case_observation["scene_date"] or (
            observation.get("nominal_slot_obt") != case_observation["nominal_slot_obt"]
            or observation.get("nominal_obs_model_time") != case_observation["nominal_obs_model_time"]
            or observation.get("time_assumption") != case_observation["time_assumption"]):
        raise ValueError("manifest observation-time contract differs from case JSON")
    if case_observation.get("source_result_path") is not None:
        expected_observation_bindings = (
            ("observation_result_path", "source_result_path"),
            ("observation_result_sha256", "source_result_sha256"),
            ("original_observation_payload_path", "source_payload_path"),
            ("original_observation_payload_sha256", "source_payload_sha256"),
            ("observation_metadata_receipt_path", "source_metadata_path"),
            ("observation_metadata_receipt_sha256", "source_metadata_sha256"),
        )
        for manifest_key, case_key in expected_observation_bindings:
            expected = case_observation.get(case_key)
            actual = bindings.get(manifest_key)
            if expected is not None and Path(str(actual)).resolve() != Path(str(expected)).resolve():
                raise ValueError(f"source binding {manifest_key} differs from case JSON")
            if case_key.endswith("sha256") and actual != expected:
                raise ValueError(f"source digest {manifest_key} differs from case JSON")
    for path_key, hash_key in (("pr395_intake_helper_path", "pr395_intake_helper_sha256"),
                               ("pr395_capture_helper_path", "pr395_capture_helper_sha256"),
                               ("selected_column_reader_path", "selected_column_reader_sha256"),
                               ("native_completion_receipt_path", "native_completion_receipt_sha256"),
                               ("native_case_consumer_path", "native_case_consumer_sha256")):
        path = Path(bindings[path_key]).resolve()
        if not path.is_file() or sha256_file(path) != bindings[hash_key]:
            raise ValueError(f"bound input/source changed after intake: {path}")
    if observation.get("binding_status") == "BOUND_GK2A_L1B_SCENE":
        for path_key, hash_key in (("observation_result_path", "observation_result_sha256"),
                                   ("original_observation_payload_path", "original_observation_payload_sha256"),
                                   ("observation_metadata_receipt_path", "observation_metadata_receipt_sha256")):
            if bindings.get(path_key) is None:
                if require_observation:
                    raise ValueError(f"analysis adapter requires {path_key}")
                continue
            path = Path(bindings[path_key]).resolve()
            if not path.is_file() or sha256_file(path) != bindings[hash_key]:
                raise ValueError(f"bound observation input changed after intake: {path}")
    elif require_observation:
        raise ValueError("native-only readiness intake cannot authorize an observation-linked analysis")
    for key, digest in manifest["native_run"]["runner_receipt_sha256"].items():
        path = Path(manifest["native_run"]["receipt_paths"][key]).resolve()
        if not path.is_file() or sha256_file(path) != digest:
            raise ValueError(f"archived runner receipt changed after native intake: {path}")
    reference = bindings.get("p8w_reference_assets", {})
    for record in [*reference.get("files", {}).values(),
                   {"path": reference.get("p8w_source_path"), "sha256": reference.get("p8w_source_sha256")}]:
        path = Path(record["path"]).resolve()
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise ValueError(f"pinned pressure/reference asset changed after native intake: {path}")
    forecast = manifest["native_run"]["forecast_path"]
    stat_record = manifest["native_run"]["forecast_stat_after"]
    forecast_path = Path(forecast).resolve()
    current_stat = forecast_path.stat()
    if (current_stat.st_size, current_stat.st_mtime_ns) != (
            stat_record["size_bytes"], stat_record["mtime_ns"]):
        raise ValueError("native forecast size/mtime changed after selected-column intake")
    with netCDF4.Dataset(forecast_path, "r") as ds:
        current_times = _read_wrf_times(ds)
    assert_saved_times_within_production_window(
        current_times, gate["effective_start_time"], gate["effective_stop_time"])
    indices = [native_manifest.get("selected_time_indices", [])[k]
               for k in range(len(native_manifest.get("selected_times", [])))]
    if (len(indices) != len(native_manifest.get("selected_times", []))
            or [current_times[index] for index in indices] != native_manifest.get("selected_times")):
        raise ValueError("native forecast Times no longer match the selected valid-time record")
    arrays = {}
    with np.load(npz_path, allow_pickle=False) as archive:
        arrays = {key: archive[key].copy() for key in archive.files}
    if set(arrays) != set(npz_binding["arrays"]):
        raise ValueError("private NPZ array key set differs from its manifest")
    for name, values in arrays.items():
        record = npz_binding["arrays"][name]
        if (list(values.shape) != record["shape"] or str(values.dtype) != record["dtype"]
                or array_sha256(values) != record["sha256"] or not np.isfinite(values).all()):
            raise ValueError(f"private NPZ array failed shape/dtype/hash/finiteness binding: {name}")
    selected_times = manifest["native_run"]["selected_times"]
    nselected = len(selected_times)
    if nselected < 1 or selected_times[0] != manifest["native_run"]["background_valid_time"]:
        raise ValueError("selected times must begin with exactly the required background")
    for field in STATE_TO_RAW:
        state = arrays[f"native_window_state__{field}"]
        background = arrays[f"background_initial_state__{field}"]
        if state.shape != (nselected, 39) or background.shape != (1, 39) or not np.array_equal(state[0:1], background):
            raise ValueError(f"background/native selected State aliases do not bind for {field}")
    for field in FORCING_TO_NATIVE:
        window = arrays[f"native_window_forcing__{field}"]
        initial = arrays[f"forcing_window_0__{field}"]
        if window.shape != (nselected, 39) or initial.shape != (1, 39) or not np.array_equal(window[0:1], initial):
            raise ValueError(f"background/native selected Forcing aliases do not bind for {field}")
    mass = arrays["native_window_host_dry_mass_kg_m2"]
    if (mass.shape != (nselected, 39) or mass.dtype != np.float32 or not np.isfinite(mass).all()
            or np.any(mass <= 0.0)
            or arrays["host_dry_mass_background_kg_m2"].shape != (39,)
            or not np.array_equal(mass[0], arrays["host_dry_mass_background_kg_m2"])):
        raise ValueError("host dry mass must remain float32 [Nselected,39] and bind background frame")
    if (arrays["native_window_rho_d_kg_m3"].shape != (nselected, 39)
            or arrays["rho_d_native_bottomup_kg_m3"].shape != (1, 39)
            or not np.array_equal(arrays["native_window_rho_d_kg_m3"][0:1],
                                  arrays["rho_d_native_bottomup_kg_m3"])):
        raise ValueError("dry-air density aliases do not bind to the selected background frame")
    if arrays["p_centers_native_bottomup_Pa"].shape != (39,) or arrays["p_half_native_bottomup_Pa"].shape != (40,):
        raise ValueError("native pressure coordinates must remain 39 centers and 40 interfaces")
    if arrays["native_window_p_half_calc_p8w_bottomup_Pa"].shape != (nselected, 40):
        raise ValueError("selected native P8W interfaces must be stored as [Nselected,40]")
    if (arrays["p_lay_rttov_topdown_hPa"].shape != (66,)
            or arrays["p_half_rttov_topdown_hPa"].shape != (67,)
            or not np.array_equal(arrays["p_lay_rttov_topdown_hPa"][-39:],
                                  arrays["p_centers_native_bottomup_Pa"][::-1] / 100.0)
            or not np.array_equal(arrays["p_half_rttov_topdown_hPa"][-40:],
                                  arrays["p_half_native_bottomup_Pa"][::-1].astype(np.float64) / 100.0)):
        raise ValueError("extended RTTOV pressures do not preserve exact 39/40 native suffixes")
    return manifest, arrays


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_json", type=Path)
    args = parser.parse_args()
    result = load_case(args.case_json)
    print(json.dumps({"case_id": result["manifest"]["case_id"],
                      "status": result["manifest"]["status"],
                      "manifest_path": result["manifest"]["manifest_path"]}, sort_keys=True))


if __name__ == "__main__":
    main()
