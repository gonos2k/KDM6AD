#!/usr/bin/env python3
"""Capture accepted-state and observation-slot state for one bounded T/Q run.

This wrapper calls the existing ``run_single_column_analysis`` once after the
caller has passed the new-native validity gate. It does not create RTTOV inputs,
read a forecast, create a process pool, retry, or change the solver. A successful
return is required before a private checkpoint is atomically published. The
returned initial analysis state and final slot state are deliberately stored as
different records.

The caller must provide a unique private NPZ path, a public receipt path, the
native-intake context receipt and its expected SHA, native-coordinate source
arrays with units/orientation, and the already-validated model/H configuration.
The intended fixed local checkpoint for the prepared PR395 case is
``graphify-out/pr395-tq-state-capture-2026-10-10/private/accepted-final-state.npz``.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import traceback
import uuid
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT / "oracle"))

from kdm6.da_dual import default_param_prior  # noqa: E402
from kdm6.da_fulldomain import _freeze_h_value  # noqa: E402
import kdm6.da_fulldomain as _fulldomain  # noqa: E402
from kdm6.da_single_column import run_single_column_analysis  # noqa: E402
from kdm6.rttov_bridge import freeze_dry_air_density  # noqa: E402
from kdm6.state import Forcing, State  # noqa: E402
from kdm6.thermo import (  # noqa: E402
    compute_qs_ice, compute_qs_water, compute_rh, default_thermo_params,
)

CHANNELS = tuple(range(10, 17))
EXPECTED_NATIVE_SAVED_TIMES = tuple(
    f"2025-07-19_05:{minute:02d}:{second:02d}"
    for minute, second in ((55, 40), (56, 0), (56, 20), (56, 40),
                           (57, 0), (57, 20), (57, 40), (58, 0)))
DEFAULT_PRIVATE_CHECKPOINT = ROOT / (
    "graphify-out/pr395-tq-state-capture-2026-10-10/private/accepted-final-state.npz")
DEFAULT_PUBLIC_RECEIPT = ROOT / (
    "harness/evidence/pr395_tq_state_capture_2026-10-10/RESULT.json")
STATE_FIELDS = tuple(State._fields)
FORCING_FIELDS = tuple(Forcing._fields)
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _array(value) -> np.ndarray:
    if isinstance(value, torch.Tensor):
        value = value.detach().cpu().numpy()
    return np.ascontiguousarray(np.asarray(value))


def array_sha256(value) -> str:
    array = np.ascontiguousarray(_array(value), dtype=np.float64)
    return hashlib.sha256(array.tobytes()).hexdigest()


def state_sha256(state: State) -> dict[str, str]:
    return {field: array_sha256(getattr(state, field)) for field in STATE_FIELDS}


def forcing_sha256(forcing: Forcing) -> dict[str, str]:
    return {field: array_sha256(getattr(forcing, field)) for field in FORCING_FIELDS}


def _record_state(payload: dict[str, np.ndarray], prefix: str, state: State) -> None:
    for field in STATE_FIELDS:
        payload[f"{prefix}__{field}"] = _array(getattr(state, field)).copy()


def _record_forcing(payload: dict[str, np.ndarray], prefix: str, forcing: Forcing) -> None:
    for field in FORCING_FIELDS:
        payload[f"{prefix}__{field}"] = _array(getattr(forcing, field)).copy()


def _finite_range(values) -> dict:
    array = np.asarray(_array(values), dtype=np.float64)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return {"count_finite": 0, "min": None, "max": None, "mean": None}
    return {"count_finite": int(finite.size), "min": float(finite.min()),
            "max": float(finite.max()), "mean": float(finite.mean())}


def _relative_percent(reference: torch.Tensor, candidate: torch.Tensor) -> dict:
    ref = _array(reference).astype(np.float64, copy=False)
    value = _array(candidate).astype(np.float64, copy=False)
    finite_pair = np.isfinite(ref) & np.isfinite(value)
    valid = finite_pair & (ref > 0.0)
    relative = (value[valid] / ref[valid] - 1.0) * 100.0
    return {
        "units": "percent",
        "valid_positive_reference_count": int(relative.size),
        "nonfinite_pair_count": int((~finite_pair).sum()),
        "zero_or_nonpositive_reference_count": int((finite_pair & (ref <= 0.0)).sum()),
        "min": None if relative.size == 0 else float(relative.min()),
        "max": None if relative.size == 0 else float(relative.max()),
        "mean": None if relative.size == 0 else float(relative.mean()),
    }


def _thermo_saturation_ratios(state: State, forcing: Forcing) -> tuple[torch.Tensor, torch.Tensor]:
    """Return phase-aware and liquid-water qs ratios on the native grid."""
    thermo = default_thermo_params()
    temperature = state.th * forcing.pii
    pressure = forcing.p
    qsat_w = compute_qs_water(temperature, pressure, params=thermo)
    qsat_i = compute_qs_ice(temperature, pressure, params=thermo)
    qsat = torch.where(temperature < thermo.ttp, qsat_i, qsat_w)
    phase_aware = compute_rh(state.qv, qsat, params=thermo)
    liquid_only = compute_rh(state.qv, qsat_w, params=thermo)
    return phase_aware, liquid_only


def _require_finite_state(state: State, *, label: str) -> None:
    for field in STATE_FIELDS:
        if not bool(torch.isfinite(getattr(state, field)).all()):
            raise FloatingPointError(f"{label}.{field} contains non-finite native values")


def _require_finite_forcing(forcing: Forcing, *, label: str) -> None:
    for field in FORCING_FIELDS:
        if not bool(torch.isfinite(getattr(forcing, field)).all()):
            raise FloatingPointError(f"{label}.{field} contains non-finite native values")


def _state_metrics(before: State, after: State, forcing: Forcing) -> dict:
    _require_finite_state(before, label="metrics_before")
    _require_finite_state(after, label="metrics_after")
    _require_finite_forcing(forcing, label="metrics_forcing")
    before_t = before.th * forcing.pii
    after_t = after.th * forcing.pii
    delta_t = after_t - before_t
    rh_before, liq_before = _thermo_saturation_ratios(before, forcing)
    rh_after, liq_after = _thermo_saturation_ratios(after, forcing)
    rh_before = rh_before * 100.0
    rh_after = rh_after * 100.0
    liq_before = liq_before * 100.0
    liq_after = liq_after * 100.0
    delta_rh = rh_after - rh_before
    delta_liq = liq_after - liq_before
    return {
        "physical_temperature_K": {
            "before": _finite_range(before_t),
            "after": _finite_range(after_t),
            "delta": _finite_range(delta_t),
            "delta_l2_norm": float(torch.linalg.vector_norm(delta_t).detach().cpu()),
            "formula": "T = th * pii with the same recorded forcing for both states",
        },
        "qv_dry_mixing_ratio_kg_kg": {
            "before": _finite_range(before.qv),
            "after": _finite_range(after.qv),
            "absolute_delta": _finite_range(after.qv - before.qv),
            "absolute_delta_l2_norm": float(torch.linalg.vector_norm(
                after.qv - before.qv).detach().cpu()),
            "relative_delta": _relative_percent(before.qv, after.qv),
        },
        "relative_humidity_percent": {
            "before": _finite_range(rh_before),
            "after": _finite_range(rh_after),
            "delta": _finite_range(delta_rh),
            "spatial_summary": "grid-point ratio mean/range over the full native column",
            "formula": "100 * KDM6 thermo.compute_rh(qv, phase-aware qs(T,p)); qmin lower floor only, no 100% cap",
            "interpretation_limit": "model q/qs ratio; not rigorously identical to observed vapor-pressure e/es RH",
        },
        "liquid_water_saturation_ratio_percent": {
            "before": _finite_range(liq_before),
            "after": _finite_range(liq_after),
            "delta": _finite_range(delta_liq),
            "spatial_summary": "grid-point qv/qs_water ratio mean/range over the full native column",
            "formula": "100 * KDM6 thermo.compute_rh(qv, qs_water(T,p)); not clipped at 100%",
            "interpretation_limit": "separate from phase-aware RH; a column mean is not a ratio of column sums",
        },
    }


def _field_status(state: State, field: str) -> dict:
    value = _array(getattr(state, field)).astype(np.float64, copy=False)
    if not np.all(np.isfinite(value)):
        raise FloatingPointError(f"state.{field} contains non-finite values")
    return {
        "units": ("kg kg-1 dry air" if field == "qc" else
                  "number per kg dry air" if field == "nc" else "KDM6 state units"),
        "range": _finite_range(value),
        "positive_count": int(np.count_nonzero(value > 0.0)),
        "unweighted_vertical_level_sum": float(value.sum()),
        "sum_definition": "unweighted sum over native vertical levels, not an area/mass-integrated column budget",
    }


def _jsonable(value):
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().tolist()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: _jsonable(getattr(value, field.name))
                for field in dataclasses.fields(value)}
    if hasattr(value, "_fields") and isinstance(value, tuple):
        return {name: _jsonable(getattr(value, name)) for name in value._fields}
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def _source_snapshot() -> dict:
    return {name: sha256_file(ROOT / name) for name in SOURCE_FILES}


def _validate_intake_binding(
    xb: State,
    forcings: Sequence[Forcing],
    native_intake_context_path: Path,
    native_intake_context_sha256: str,
    native_intake_npz_path: Path,
    native_intake_npz_sha256: str,
) -> tuple[dict, dict, dict, dict]:
    path = Path(native_intake_context_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"native intake context is missing: {path}")
    actual_context_sha = sha256_file(path)
    if actual_context_sha != native_intake_context_sha256:
        raise ValueError("native intake context SHA does not match the caller-declared identity")
    manifest = json.loads(path.read_text())
    if manifest.get("schema") != "pr395_native_tq_intake_v1":
        raise ValueError("native intake manifest schema is not the approved PR395 contract")
    if manifest.get("status") != "READY_VALID_NATIVE_INTAKE":
        raise ValueError("native intake has not passed the valid-native gate")
    native_run = manifest.get("native_run", {})
    if (native_run.get("exit_code") != 0
            or native_run.get("experiment_valid") is not True
            or native_run.get("model_completed_flag") is not True
            or native_run.get("actual_saved_times") != native_run.get("expected_saved_times")
            or native_run.get("actual_saved_times") != list(EXPECTED_NATIVE_SAVED_TIMES)
            or native_run.get("background_time") != "2025-07-19_05:55:40"):
        raise ValueError("native run receipt does not prove rc=0, valid completion, and all eight exact saved times")
    selected_column = manifest.get("selected_column", {})
    if {key: selected_column.get(key) for key in ("j", "i", "levels")} != {
            "j": 86, "i": 48, "levels": 39}:
        raise ValueError("native intake column identity differs from predeclared PR395 selection")
    clock = manifest.get("clock", {})
    if (clock.get("scenario") != "A_nominal_centers_only"
            or clock.get("pixel_time_verified") is not False
            or clock.get("obs_time") != 1
            or clock.get("dt_s") != 20
            or clock.get("nominal_slot_utc") != "2025-07-19_05:56:00"):
        raise ValueError("native intake clock fields differ from the predeclared one-step slot")
    saved_times = native_run.get("actual_saved_times")
    if (not isinstance(saved_times, list) or len(saved_times) != 8
            or saved_times[0] != native_run.get("background_time")
            or saved_times[1] != clock.get("nominal_slot_utc")):
        raise ValueError("saved WRF Times do not map state index 0/1 to background/nominal slot")
    if manifest.get("science_approved") is not False or manifest.get("analysis_executed") is not False:
        raise ValueError("intake must remain pre-analysis and not science-approved")

    npz_path = Path(native_intake_npz_path).resolve()
    if not npz_path.is_file():
        raise FileNotFoundError(f"native intake NPZ is missing: {npz_path}")
    actual_npz_sha = sha256_file(npz_path)
    if actual_npz_sha != native_intake_npz_sha256:
        raise ValueError("native intake NPZ SHA does not match the caller-declared identity")
    # Only the validated compact intake NPZ and its manifest are opened here.
    # The native forecast/source files are never opened by this capture wrapper.
    with np.load(npz_path, allow_pickle=False) as archive:
        intake_arrays = {key: archive[key].copy() for key in archive.files}
    current_state_sha = state_sha256(xb)
    _require_finite_state(xb, label="native_intake_background_initial")
    expected_state_sha = {
        field: array_sha256(intake_arrays[f"background_initial_state__{field}"])
        for field in STATE_FIELDS
    }
    if expected_state_sha != current_state_sha:
        raise ValueError("initial State arrays differ from exact validated intake arrays")
    if len(forcings) != 1:
        raise ValueError("PR395 native intake currently fixes a one-entry 20 s forcing window")
    _require_finite_forcing(forcings[0], label="native_intake_forcing_0")
    expected_forcing_sha = {
        field: array_sha256(intake_arrays[f"forcing_window_0__{field}"])
        for field in FORCING_FIELDS
    }
    if expected_forcing_sha != forcing_sha256(forcings[0]):
        raise ValueError("forcing window differs from exact validated intake arrays")
    coordinates = {}
    definitions = {
        "native_p_centers_bottomup": (
            "p_centers_native_bottomup_Pa", "Pa", "bottom-up",
            "float64-first P+PB center pressure"),
        "native_p_half_calc_p8w_bottomup_real4": (
            "p_half_native_bottomup_Pa", "Pa", "bottom-up",
            "REAL(4)-transcribed calc_p8w; distinct from raw PH/PHB"),
        "PH_raw_native_bottomup": (
            "PH_raw_native_bottomup", "Pa", "bottom-up", "raw native PH"),
        "PHB_raw_native_bottomup": (
            "PHB_raw_native_bottomup", "Pa", "bottom-up", "raw native PHB"),
        "p_lay_rttov_topdown": (
            "p_lay_rttov_topdown_hPa", "hPa", "top-down", "RTTOV layer grid"),
        "p_half_rttov_topdown": (
            "p_half_rttov_topdown_hPa", "hPa", "top-down", "RTTOV interface grid"),
    }
    for output_name, (intake_name, units, orientation, source) in definitions.items():
        values = _array(intake_arrays[intake_name])
        if not np.all(np.isfinite(values)):
            raise ValueError(f"native coordinate {intake_name} contains non-finite values")
        coordinates[output_name] = {
            "units": units, "orientation": orientation, "source": source,
            "shape": list(values.shape), "dtype": str(values.dtype),
            "sha256": hashlib.sha256(values.tobytes()).hexdigest(),
            "values": values,
        }
    native_centers = torch.as_tensor(
        coordinates["native_p_centers_bottomup"]["values"], dtype=torch.float64).reshape(-1)
    forcing_centers = forcings[0].p.reshape(-1)
    if not torch.equal(native_centers, forcing_centers):
        raise ValueError("native P+PB centers differ from the exact input Forcing.p array")
    return ({
        "path": str(path), "sha256": actual_context_sha,
        "initial_state_sha256": current_state_sha,
        "npz_path": str(npz_path), "npz_sha256": actual_npz_sha,
        "forcing_window_0_sha256": forcing_sha256(forcings[0]),
        "manifest_schema": manifest["schema"], "manifest_status": manifest["status"],
        "background_time": native_run["background_time"],
        "expected_saved_times": native_run["expected_saved_times"],
        "actual_saved_times": native_run["actual_saved_times"],
        "selected_column": manifest["selected_column"], "clock": clock,
        "state_time_index_to_wrf_times": {
            "0": saved_times[0], "1": saved_times[1],
            "mapping_basis": "first two exact actual_saved_times entries; slot nominal, pixel time unverified",
        },
        "pressure_sources": manifest.get("pressure_sources", manifest.get("pressure_provenance")),
        "science_approved": manifest["science_approved"],
        "analysis_executed_at_intake": manifest["analysis_executed"],
    }, coordinates, intake_arrays, manifest)


def _private_payload(
    *,
    xb: State,
    accepted_initial_state: State,
    background_slot_state: State,
    final_slot_state: State,
    forcings: Sequence[Forcing],
    final_slot_forcing: Forcing,
    rho_d: torch.Tensor,
    y_bt,
    y_rq,
    rttov_cfg: Mapping,
    native_coordinates: Mapping[str, Mapping],
    slot_calls: Sequence[Mapping],
    receipt_metadata: Mapping,
) -> dict[str, np.ndarray]:
    payload: dict[str, np.ndarray] = {}
    _record_state(payload, "background_initial_state", xb)
    _record_state(payload, "returned_analysis_initial_state", accepted_initial_state)
    _record_state(payload, "background_slot_state", background_slot_state)
    _record_state(payload, "final_slot_state", final_slot_state)
    for i, forcing in enumerate(forcings):
        _record_forcing(payload, f"forcing_window_{i}", forcing)
    _record_forcing(payload, "final_slot_forcing", final_slot_forcing)
    payload["rho_d_native_bottomup_kg_m3"] = _array(rho_d).copy()
    payload["observation_y_bt_K"] = _array(y_bt).copy()
    payload["observation_y_dqf"] = _array(y_rq).copy()
    payload["p_centers_native_bottomup_Pa"] = _array(final_slot_forcing.p).copy()
    payload["exner_final_slot_native_bottomup"] = _array(final_slot_forcing.pii).copy()
    for name, value in native_coordinates.items():
        payload[f"native_coordinate__{name}"] = _array(value["values"]).copy()
    for name in ("p_lay", "p_half", "t_ref", "q_ref"):
        if name in rttov_cfg:
            payload[f"rttov_config__{name}"] = _array(rttov_cfg[name]).copy()
    if slot_calls:
        final_call = slot_calls[-1]
        if final_call.get("mask") is not None:
            payload["final_slot_frozen_mask"] = _array(final_call["mask"]).copy()
        if final_call.get("rad_quality") is not None:
            payload["final_slot_rad_quality"] = _array(final_call["rad_quality"]).copy()
        if final_call.get("bt") is not None:
            payload["final_slot_bt_K"] = _array(final_call["bt"]).copy()
    meta = json.dumps(_jsonable(receipt_metadata), sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()
    payload["capture_metadata_json_utf8"] = np.frombuffer(meta, dtype=np.uint8).copy()
    return payload


def write_private_npz_atomic(path: Path, payload: Mapping[str, np.ndarray]) -> str:
    """Write a unique private NPZ atomically; refuse to replace any existing file."""
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    if (path.parent.stat().st_mode & 0o077) != 0:
        raise PermissionError(f"private checkpoint directory is accessible to group/other: {path.parent}")
    if path.exists():
        raise FileExistsError(f"refusing to overwrite private checkpoint: {path}")
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    linked = False
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            np.savez_compressed(stream, **payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, 0o600)
        # A same-directory hard link is an atomic no-clobber publication.
        # os.replace would overwrite a file created after the early existence
        # check, which is unsafe for a checkpoint path intended to be fresh.
        os.link(temp, path)
        linked = True
        temp.unlink()
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        if linked:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise
    return sha256_file(path)


def _write_receipt_exclusive(path: Path, receipt: Mapping) -> str:
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(_jsonable(receipt), indent=2, allow_nan=False).encode() + b"\n"
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # link() atomically refuses an existing destination; then remove temp.
        os.link(temp, path)
        temp.unlink()
    except BaseException:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise
    return hashlib.sha256(data).hexdigest()


def _public_h_config_summary(config: Mapping) -> dict:
    arrays = {"p_lay", "p_half", "t_ref", "q_ref", "rho_d"}
    summary = {}
    for name, value in config.items():
        if name in arrays:
            if value is None:
                summary[name] = None
            else:
                array = _array(value)
                summary[name] = {"shape": list(array.shape), "dtype": str(array.dtype),
                                 "sha256_f64": array_sha256(array)}
        else:
            summary[name] = _jsonable(value)
    return summary


def _classify_failure(exc: BaseException) -> str:
    message = str(exc).lower()
    if "rad_quality" in message or "frozen support" in message or "frozen-support" in message:
        return "FROZEN_QUALITY_OR_SUPPORT_ABORT"
    return "ANALYSIS_EXCEPTION"


def _validate_predeclared_run(window_config, manifest: Mapping, *, obs_time: int,
                              max_iter: int, forcings: Sequence[Forcing]) -> None:
    expected = {
        "obs_time": 1,
        "dt_s": 20,
        "max_iter": 3,
        "observation_sigma_K": 1.0,
        "observation_bias_K": 0.0,
        "huber_delta_K": 1.0,
        "th_sigma_K": 0.8,
        "qv_sigma_log": 0.08,
        "qv_levels_from_bottom": 12,
        "non_tq_state_sigmas_zero": True,
        "parameter_prior_active": [],
        "partition_control": False,
        "pseudo_rh": False,
        "warm_start": False,
        "automatic_retry": False,
        "ncmin_land": 10.0,
        "ncmin_sea": 10.0,
    }
    missing = [name for name in expected if name not in manifest]
    if missing:
        raise ValueError(f"run_manifest must freeze every PR395 parameter; missing {missing}")
    for name, value in expected.items():
        if manifest[name] != value:
            raise ValueError(f"run_manifest.{name}={manifest[name]!r} violates fixed PR395 value {value!r}")
    if (obs_time != 1 or max_iter != 3 or len(forcings) != 1
            or float(getattr(window_config, "dt", math.nan)) != 20.0
            or getattr(window_config, "normalized_dry", False) is not True
            or float(getattr(window_config, "ncmin_land", math.nan)) != 10.0
            or float(getattr(window_config, "ncmin_sea", math.nan)) != 10.0):
        raise ValueError("helper arguments differ from the fixed PR395 obs_time/dt/window contract")


def run_capture(
    *,
    xb: State,
    forcings: Sequence[Forcing],
    y_bt,
    y_rq,
    xland,
    clear_cfg,
    rttov_cfg: dict,
    window_config,
    obs_time: int,
    pool,
    private_checkpoint: Path,
    public_receipt: Path,
    case_root: Path,
    native_intake_context_path: Path,
    native_intake_context_sha256: str,
    native_intake_npz_path: Path,
    native_intake_npz_sha256: str,
    run_manifest: Mapping,
    max_iter: int = 3,
    n_workers: int = 1,
    rttov_timeout: float | None = None,
    analysis_runner=run_single_column_analysis,
) -> dict:
    """Execute existing adapter once and publish state only after successful return.

    No module or optimizer change is made here. The last successful grad=True
    all-sky callback is the final audit slot state; its forcing comes directly
    from that callback's actual H invocation. The non-grad background probe is
    retained separately as ``background_slot_state``.
    """
    private_checkpoint = Path(private_checkpoint).resolve()
    public_receipt = Path(public_receipt).resolve()
    case_root = Path(case_root).resolve()
    if private_checkpoint.parent.name != "private":
        raise ValueError("private_checkpoint must be stored in an explicitly named private directory")
    if private_checkpoint.exists() or public_receipt.exists() or case_root.exists():
        raise FileExistsError("checkpoint, receipt, and H case root must all be fresh paths")
    intake_binding = None
    native_coordinates = {}
    intake_arrays = {}
    intake_manifest = {}
    events = []
    source_before = _source_snapshot()
    checkpoint_written = False
    try:
        forcings = tuple(forcings)
        if not forcings:
            raise ValueError("forcings must contain the full ordered model window")
        _validate_predeclared_run(
            window_config, run_manifest, obs_time=obs_time,
            max_iter=max_iter, forcings=forcings)
        if tuple(rttov_cfg.get("channels", ())) != CHANNELS:
            raise ValueError("rttov_cfg must use fixed AMI physical channels 10..16")
        if (float(rttov_cfg.get("ncmin_land", math.nan)) != 10.0
                or float(rttov_cfg.get("ncmin_sea", math.nan)) != 10.0):
            raise ValueError("fixed PR395 caller H configuration requires ncmin_land=ncmin_sea=10")
        intake_binding, native_coordinates, intake_arrays, intake_manifest = _validate_intake_binding(
            xb, forcings, native_intake_context_path,
            native_intake_context_sha256, native_intake_npz_path,
            native_intake_npz_sha256)
        # Fixed-forcing PR395 uses the same forcing at the only initial and
        # observation slot. Record the exact source index used for frozen rho_d.
        rho_d_formula = freeze_dry_air_density(xb, forcings[0])
        rho_d = torch.as_tensor(
            intake_arrays["rho_d_native_bottomup_kg_m3"],
            dtype=xb.th.dtype, device=xb.th.device).clone()
        if not torch.equal(rho_d, rho_d_formula):
            raise ValueError("intake frozen rho_d differs from initial State/forcing[0] formula")
        if "rho_d" in rttov_cfg and not torch.equal(
                torch.as_tensor(rttov_cfg["rho_d"], dtype=xb.th.dtype), rho_d):
            raise ValueError("caller rho_d differs from the frozen initial-state/forcing density")
        h_forcing = forcings[0]
        p_lay = torch.as_tensor(rttov_cfg.get("p_lay"), dtype=torch.float64)
        p_half = torch.as_tensor(rttov_cfg.get("p_half"), dtype=torch.float64)
        nlev = xb.th.shape[-1]
        if not torch.equal(p_lay, torch.as_tensor(
                intake_arrays["p_lay_rttov_topdown_hPa"], dtype=torch.float64)):
            raise ValueError("RTTOV layer grid differs from the validated intake grid")
        if not torch.equal(p_half, torch.as_tensor(
                intake_arrays["p_half_rttov_topdown_hPa"], dtype=torch.float64)):
            raise ValueError("RTTOV interface grid differs from the validated intake grid")
        if p_lay.ndim != 1 or p_lay.numel() < nlev or not torch.equal(
                h_forcing.p.flip(-1) / 100.0, p_lay[-nlev:].expand_as(h_forcing.p)):
            raise ValueError("RTTOV center grid does not exactly retain native P+PB forcing centers")
        if p_half.ndim != 1 or p_half.numel() != p_lay.numel() + 1:
            raise ValueError("RTTOV p-half grid must contain one more interface than p-lay")
        p_half_calc_p8w = np.asarray(
            intake_arrays["p_half_native_bottomup_Pa"])
        if p_half_calc_p8w.dtype != np.float32 or p_half_calc_p8w.shape != (nlev + 1,):
            raise ValueError("native calc_p8w half pressure must be float32 with K+1 bottom-up interfaces")
        expected_p8w = (p_half[-(nlev + 1):].flip(-1).detach().cpu().numpy() * 100.0).astype(np.float32)
        if not np.array_equal(p_half_calc_p8w, expected_p8w):
            raise ValueError("REAL(4) calc_p8w native p-half differs from supplied RTTOV interface suffix")

        call_number = 0
        background_slot = None
        background_slot_forcing = None
        last_grad_call = None
        original_sharded = _fulldomain.sharded_allsky

        def capture_call(*call_args, **call_kwargs):
            nonlocal call_number, background_slot, background_slot_forcing, last_grad_call
            state, forcing, positions, target, mask, xland_value, cfg, case_root = call_args[:8]
            grad = bool(call_kwargs.get("grad", True))
            call_number += 1
            input_state = State(*(getattr(state, f).detach().clone() for f in STATE_FIELDS))
            input_forcing = Forcing(*(getattr(forcing, f).detach().clone() for f in FORCING_FIELDS))
            event = {
                "call_index": call_number,
                "stage": Path(case_root).name,
                "grad": grad,
                "profile_positions": _array(positions).tolist(),
                "state_sha256": state_sha256(input_state),
                "forcing_sha256": forcing_sha256(input_forcing),
                "channels": list(cfg["channels"]),
                "target_BT_K": _array(target).tolist(),
                "frozen_mask": _array(mask).tolist(),
            }
            events.append(event)
            if not grad and background_slot is None:
                background_slot = input_state
                background_slot_forcing = input_forcing
            out = original_sharded(*call_args, **call_kwargs)
            event.update({
                "returned": True,
                "BT_K": _array(out["bt"]).tolist(),
                "rad_quality": _array(out["rq"]).tolist(),
                "fixed_mask": _array(mask).tolist(),
                "J_huber": float(out["j"]),
            })
            if grad:
                last_grad_call = {
                    "state": input_state,
                    "forcing": input_forcing,
                    "mask": torch.as_tensor(mask, dtype=torch.float64).detach().clone(),
                    "bt": torch.as_tensor(out["bt"], dtype=torch.float64).detach().clone(),
                    "rad_quality": torch.as_tensor(out["rq"], dtype=torch.float64).detach().clone(),
                    "j": float(out["j"]),
                    "call_index": call_number,
                }
            return out

        _fulldomain.sharded_allsky = capture_call
        try:
            runner_kwargs = {
                "window_config": window_config,
                "obs_time": obs_time,
                "pool": pool,
                "n_workers": n_workers,
                "max_iter": max_iter,
            }
            if rttov_timeout is not None:
                runner_kwargs["rttov_timeout"] = rttov_timeout
            package = analysis_runner(
                xb, forcings, y_bt, y_rq, xland, clear_cfg, rttov_cfg,
                str(case_root),
                **runner_kwargs)
        finally:
            _fulldomain.sharded_allsky = original_sharded

        result = package["result"]
        actual_meta = package["metadata"]
        if (actual_meta.get("normalized_dry") is not True
                or actual_meta.get("require_frozen_quality") is not True
                or actual_meta.get("n_valid_background") != 7
                or actual_meta.get("channels_ami_physical_ids") != list(CHANNELS)
                or actual_meta.get("huber_delta_K") != 1.0
                or actual_meta.get("observation_sigma_K") != 1.0
                or actual_meta.get("observation_bias_K") != 0.0
                or actual_meta.get("partition_control") is not False
                or actual_meta.get("pseudo_rh") is not False):
            raise RuntimeError("returned adapter metadata differs from the fixed seven-channel T/Q contract")
        state_prior = actual_meta.get("state_prior", {})
        if (state_prior.get("th_sigma_K") != 0.8
                or state_prior.get("qv_sigma_log") != 0.08
                or state_prior.get("qv_levels_from_bottom") != 12
                or any(count != 0 for name, count in
                       state_prior.get("active_counts_from_built_sigma", {}).items()
                       if name not in ("th", "qv"))):
            raise RuntimeError("returned state prior differs from the fixed PR395 T/Q control contract")
        param_prior = actual_meta.get("parameter_prior", {})
        if (param_prior.get("active") != []
                or param_prior.get("sigma_log") != [0.0, 0.0, 0.0, 0.0]):
            raise RuntimeError("returned parameter prior is not pinned inactive")
        if background_slot is None or background_slot_forcing is None:
            raise RuntimeError("successful adapter return lacked a background slot H probe")
        if last_grad_call is None:
            raise RuntimeError("successful adapter return lacked a final grad=True audit H callback")
        if int(result.n_audit_evals) != 1:
            raise RuntimeError(
                "this fixed one-run PR395 contract requires exactly one final accepted-state audit")
        if tuple(last_grad_call["state"].th.shape) != tuple(result.x_analysis.th.shape):
            raise RuntimeError("final slot and returned initial analysis have incompatible native shapes")
        if not math.isclose(last_grad_call["j"], float(result.jobs_final), rel_tol=0.0, abs_tol=1e-10):
            raise RuntimeError("last captured final-slot H cost differs from returned final Jo")
        final_mask = last_grad_call["mask"]
        final_rq = last_grad_call["rad_quality"]
        if tuple(final_mask.shape) != (1, len(CHANNELS)) or tuple(final_rq.shape) != (1, len(CHANNELS)):
            raise RuntimeError("final callback did not return exact [1,7] support/quality arrays")
        if bool(((final_mask > 0) & (final_rq != 0)).any()):
            raise RuntimeError("final callback quality invalidated frozen support")
        if int(final_mask.sum()) != 7:
            raise RuntimeError("final accepted-state callback does not retain all seven frozen channels")
        if not torch.equal(final_rq[final_mask > 0], torch.zeros_like(final_rq[final_mask > 0])):
            raise RuntimeError("final accepted-state quality flags are nonzero on frozen support")

        accepted_state = State(*(getattr(result.x_analysis, f).detach().clone()
                                 for f in STATE_FIELDS))
        for i, forcing in enumerate(forcings):
            if tuple(forcing.p.shape) != tuple(xb.th.shape):
                raise ValueError(f"forcing_window[{i}] does not match native [1,K] state shape")
        metrics = {
            "initial_time_state": _state_metrics(xb, accepted_state, forcings[0]),
            "observation_slot_state": _state_metrics(
                background_slot, last_grad_call["state"], last_grad_call["forcing"]),
            "background_slot_qc": _field_status(background_slot, "qc"),
            "background_slot_nc": _field_status(background_slot, "nc"),
            "final_slot_qc": _field_status(last_grad_call["state"], "qc"),
            "final_slot_nc": _field_status(last_grad_call["state"], "nc"),
        }
        _require_finite_state(accepted_state, label="returned_analysis_initial_state")
        _require_finite_state(last_grad_call["state"], label="final_slot_state")
        _require_finite_forcing(last_grad_call["forcing"], label="final_slot_forcing")
        source_after = _source_snapshot()
        if source_after != source_before:
            raise RuntimeError("tracked KDM/RTTOV sources changed during analysis; refusing checkpoint")
        if not public_receipt.parent.exists():
            public_receipt.parent.mkdir(parents=True, exist_ok=True)
        if public_receipt.exists() or private_checkpoint.exists():
            raise FileExistsError("output path appeared during run; refusing publication")

        config_metadata = {
            "run_manifest": _jsonable(run_manifest),
            "window_config": _jsonable(window_config),
            "obs_time": obs_time,
            "h_forcing_index": min(obs_time, len(forcings) - 1),
            "n_forcings": len(forcings),
            "max_iter": max_iter,
            "n_workers": n_workers,
            "normalized_dry": True,
            "channels_ami_physical_ids": list(CHANNELS),
            "final_slot_capture": {
                "semantics": "last successful grad=True all-sky callback; existing minimizer performs its final accepted-state audit after optimizer step",
                "call_index": last_grad_call["call_index"],
                "state_sha256": state_sha256(last_grad_call["state"]),
                "forcing_sha256": forcing_sha256(last_grad_call["forcing"]),
            },
            "background_slot_capture": {
                "semantics": "first successful grad=False background quality probe",
                "state_sha256": state_sha256(background_slot),
                "forcing_sha256": forcing_sha256(background_slot_forcing),
            },
        }
        private_arrays = _private_payload(
            xb=xb, accepted_initial_state=accepted_state,
            background_slot_state=background_slot,
            final_slot_state=last_grad_call["state"], forcings=forcings,
            final_slot_forcing=last_grad_call["forcing"], rho_d=rho_d,
            y_bt=y_bt, y_rq=y_rq,
            rttov_cfg=rttov_cfg, native_coordinates=native_coordinates,
            slot_calls=events, receipt_metadata=config_metadata)
        private_sha = write_private_npz_atomic(private_checkpoint, private_arrays)
        checkpoint_written = True

        metadata = package["metadata"]
        receipt = {
            "schema": "pr395_tq_state_capture_v1",
            "status": "RETURNED_DIAGNOSTIC_ONLY",
            "input_validity": {
                "status": "VALIDATED_NATIVE_INPUT",
                "manifest_sha256": intake_binding["sha256"],
                "native_npz_sha256": intake_binding["npz_sha256"],
                "native_run_exit_code": 0,
                "actual_saved_times": intake_binding["actual_saved_times"],
            },
            "numerical_return": {
                "status": "RETURNED",
                "minimizer_returned_state": True,
                "final_accepted_state_audit_callback": True,
            },
            "physical_matchup_and_science_acceptance": {
                "status": "NOT_ASSESSED",
                "pixel_time_verified": False,
                "science_accepted": False,
                "note": "nominal model slot evaluation does not certify pixel-time matchup or scientific acceptance",
            },
            "minimizer_returned_state": True,
            "valid_native_analysis_published": False,
            "native_intake_context": intake_binding,
            "private_checkpoint": {
                "path": str(private_checkpoint),
                "sha256": private_sha,
                "array_keys": sorted(private_arrays),
                "contains_full_state_arrays": True,
                "public_receipt_contains_full_state_arrays": False,
            },
            "production_source_sha256_before_after": {
                "before": source_before, "after": source_after,
                "unchanged": source_before == source_after,
            },
            "state_array_sha256": {
                "background_initial": state_sha256(xb),
                "returned_analysis_initial": state_sha256(accepted_state),
                "background_slot": state_sha256(background_slot),
                "final_slot": state_sha256(last_grad_call["state"]),
            },
            "forcing_array_sha256": {
                "forcing_window": [forcing_sha256(f) for f in forcings],
                "background_slot": forcing_sha256(background_slot_forcing),
                "final_slot": forcing_sha256(last_grad_call["forcing"]),
            },
            "native_coordinate_arrays": {
                name: {k: v for k, v in item.items() if k != "values"}
                for name, item in native_coordinates.items()
            },
            "actual_h_configuration": _public_h_config_summary(rttov_cfg),
            "effective_h_configuration": _public_h_config_summary(
                {**rttov_cfg, "rho_d": rho_d}),
            "frozen_optical_rho_d": {
                "shape": list(rho_d.shape),
                "units": "kg m-3 dry-air density",
                "orientation": "native bottom-up KDM grid",
                "sha256_f64": array_sha256(rho_d),
                "formula": "freeze_dry_air_density(background_initial_state, forcing_window_0)",
                "forcing_index": 0,
                "intake_array_sha256_f64": array_sha256(
                    intake_arrays["rho_d_native_bottomup_kg_m3"]),
            },
            "adapter_metadata": _jsonable(metadata),
            "observations": {
                "channels_ami_physical_ids": list(CHANNELS),
                "y_bt_K": _jsonable(y_bt),
                "observation_dqf": _jsonable(y_rq),
                "model_rad_quality_is_separate_from_observation_dqf": True,
            },
            "metrics": metrics,
            "objective": {
                "Jb_state": float(result.jb_final),
                "Jtheta": float(result.jtheta_final),
                "Jo": float(result.jobs_final),
                "Jtotal": float(result.jb_final + result.jtheta_final + result.jobs_final),
                "Jtotal_final_trace": (None if not result.j_trace else
                                       float(result.j_trace[-1]["total"])),
                "n_valid": int(final_mask.sum()),
                "frozen_support": final_mask.tolist(),
                "final_rad_quality": final_rq.tolist(),
                "n_window_evals": int(result.n_window_evals),
                "n_audit_evals": int(result.n_audit_evals),
            },
            "logical_h_calls": events,
            "runtime_rttov_child_launches": None,
            "runtime_rttov_child_launch_note": "not instrumented; logical all-sky H callback outputs are recorded",
        }
        receipt_sha = _write_receipt_exclusive(public_receipt, receipt)
        receipt["public_receipt_sha256"] = receipt_sha
        return receipt
    except BaseException as exc:
        if checkpoint_written:
            try:
                private_checkpoint.unlink()
            except FileNotFoundError:
                pass
        failure = {
            "schema": "pr395_tq_state_capture_v1",
            "status": _classify_failure(exc),
            "input_validity": {
                "status": ("VALIDATED_NATIVE_INPUT" if intake_binding is not None
                           else "NOT_VALIDATED"),
                "manifest_sha256": None if intake_binding is None else intake_binding["sha256"],
                "native_npz_sha256": None if intake_binding is None else intake_binding["npz_sha256"],
            },
            "numerical_return": {
                "status": "FAILED_BEFORE_RETURN",
                "minimizer_returned_state": False,
            },
            "physical_matchup_and_science_acceptance": {
                "status": "NOT_ASSESSED",
                "science_accepted": False,
            },
            "analysis_exception": {"type": type(exc).__name__, "message": str(exc),
                                   "traceback": traceback.format_exc()},
            "native_intake_context": intake_binding,
            "private_checkpoint": {"path": str(private_checkpoint), "published": False},
            "callback_attempt_metadata": events,
            "production_source_sha256_before": source_before,
            "production_source_sha256_after": _source_snapshot(),
            "valid_native_analysis_published": False,
        }
        if not public_receipt.exists():
            _write_receipt_exclusive(public_receipt, failure)
        return failure
