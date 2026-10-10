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
import inspect
import sys
import traceback
import uuid
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "oracle"))

from kdm6.da_dual import PNAMES, params_from_vtheta  # noqa: E402
from kdm6.da_cvt import cvt_apply  # noqa: E402
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
    host_mass_window = np.asarray(
        intake_arrays["native_window_host_dry_mass_kg_m2"])
    host_mass_background = np.asarray(
        intake_arrays["host_dry_mass_background_kg_m2"])
    host_mass_provenance = manifest.get("model_data_provenance", {}).get(
        "host_dry_mass", {})
    if (host_mass_window.dtype != np.float32 or host_mass_window.shape != (8, 39)
            or host_mass_background.dtype != np.float32 or host_mass_background.shape != (39,)
            or not np.isfinite(host_mass_window).all()
            or not np.isfinite(host_mass_background).all()
            or not np.all(host_mass_window > 0.0)
            or not np.all(host_mass_background > 0.0)
            or not np.array_equal(host_mass_window[0], host_mass_background)
            or host_mass_provenance.get("window_npz_key") != "native_window_host_dry_mass_kg_m2"
            or host_mass_provenance.get("background_npz_key") != "host_dry_mass_background_kg_m2"
            or host_mass_provenance.get("shape") != [8, 39]
            or host_mass_provenance.get("dtype") != "float32"
            or host_mass_provenance.get("units") != "kg dry air m-2 per native eta layer"
            or host_mass_provenance.get("orientation") != "bottom-up native levels"
            or not isinstance(host_mass_provenance.get("formula"), str)
            or not isinstance(host_mass_provenance.get("provenance"), str)):
        raise ValueError(
            "native intake host dry mass lacks matching finite float32 arrays and source-backed eta-layer metadata")
    host_mass_summary = {
        **host_mass_provenance,
        "source_key": "host_dry_mass_background_kg_m2",
        "shape": list(host_mass_background.shape),
        "dtype": str(host_mass_background.dtype),
        "sha256_raw_dtype_bytes": hashlib.sha256(
            np.ascontiguousarray(host_mass_background).tobytes()).hexdigest(),
        "window_source_key": "native_window_host_dry_mass_kg_m2",
        "window_shape": list(host_mass_window.shape),
        "window_dtype": str(host_mass_window.dtype),
        "background_matches_window_frame_0": True,
    }
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
            "PH_raw_native_bottomup", "m2 s-2", "bottom-up",
            "raw WRF geopotential PH; not pressure"),
        "PHB_raw_native_bottomup": (
            "PHB_raw_native_bottomup", "m2 s-2", "bottom-up",
            "raw WRF base-state geopotential PHB; not pressure"),
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
        "host_dry_mass_background": host_mass_summary,
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
    host_dry_mass_background_kg_m2: np.ndarray | None = None,
    extra_private_arrays: Mapping[str, np.ndarray] | None = None,
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
    if host_dry_mass_background_kg_m2 is not None:
        mass = np.asarray(host_dry_mass_background_kg_m2)
        if (mass.dtype != np.float32 or mass.shape != (xb.th.shape[-1],)
                or not np.isfinite(mass).all() or not np.all(mass > 0.0)):
            raise ValueError(
                "host eta-layer dry mass must preserve finite positive native float32 [K] intake values")
        payload["host_dry_mass_background_kg_m2"] = mass.copy()
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
    for name, values in (extra_private_arrays or {}).items():
        private_name = name if name.startswith("optimizer_state__") else f"control__{name}"
        payload[private_name] = _array(values).copy()
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
        # Hash before the no-clobber link so a post-publication read error can
        # never strand a checkpoint that the caller believes was not written.
        checkpoint_sha = sha256_file(temp)
        # A same-directory hard link is an atomic no-clobber publication.
        # os.replace would overwrite a file created after the early existence
        # check, which is unsafe for a checkpoint path intended to be fresh.
        os.link(temp, path)
        linked = True
        try:
            temp.unlink()
        except OSError:
            # The final name is already committed and private. A leftover
            # mode-0600 temporary hard link is harmless; do not report failure
            # after publication and leave an untracked checkpoint behind.
            pass
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            # As above, the linked checkpoint remains the committed result.
            pass
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
    return checkpoint_sha


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
        try:
            temp.unlink()
        except OSError:
            # The link is the commit point. Cleanup failure must not turn a
            # published success receipt into a reported failure whose outer
            # rollback deletes the referenced private checkpoint.
            pass
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


def _observe_existing_lbfgs(original_factory, observation: dict):
    """Return a temporary factory that observes the real PyTorch LBFGS instance.

    The original constructor, instance, and bound ``step`` implementation remain
    in use. This wrapper only records constructor/step outcomes; it does not wrap
    or re-evaluate the objective closure.
    """
    def factory(*args, **kwargs):
        observation["constructor_calls"] = observation.get("constructor_calls", 0) + 1
        optimizer = original_factory(*args, **kwargs)
        if observation["constructor_calls"] != 1:
            raise RuntimeError("fixed PR395 run constructed more than one LBFGS optimizer")
        observation["optimizer"] = optimizer
        observation["constructor_positional_arg_count"] = len(args)
        original_step = optimizer.step

        def observed_step(closure):
            observation["step_calls"] = observation.get("step_calls", 0) + 1
            returned_loss = original_step(closure)
            observation["step_returned"] = True
            observation["step_original_loss_returned"] = _jsonable(returned_loss)
            group = optimizer.param_groups[0]
            params = group["params"]
            state = optimizer.state.get(params[0], {}) if params else {}
            observation["step_state"] = {
                "n_iter": _jsonable(state.get("n_iter")),
                "func_evals": _jsonable(state.get("func_evals")),
                "step_t": _jsonable(state.get("t")),
                "prev_loss": _jsonable(state.get("prev_loss")),
                "group": {name: _jsonable(group.get(name)) for name in (
                    "lr", "max_iter", "max_eval", "history_size",
                    "tolerance_grad", "tolerance_change", "line_search_fn")},
            }
            state_arrays = {}
            state_structure = {}
            for state_name, state_value in state.items():
                if isinstance(state_value, torch.Tensor):
                    array_key = f"optimizer_state__{state_name}"
                    state_arrays[array_key] = _array(state_value).copy()
                    state_structure[state_name] = {"array_key": array_key}
                elif isinstance(state_value, (tuple, list)):
                    sequence = []
                    for index, item in enumerate(state_value):
                        if isinstance(item, torch.Tensor):
                            array_key = f"optimizer_state__{state_name}__{index}"
                            state_arrays[array_key] = _array(item).copy()
                            sequence.append({"array_key": array_key})
                        else:
                            sequence.append(_jsonable(item))
                    state_structure[state_name] = sequence
                else:
                    state_structure[state_name] = _jsonable(state_value)
            observation["optimizer_state_arrays"] = state_arrays
            observation["optimizer_state_structure"] = state_structure
            observation["optimizer_state_array_metadata"] = {
                name: {"shape": list(array.shape), "dtype": str(array.dtype),
                       "sha256_f64": array_sha256(array),
                       "private_npz_key": name}
                for name, array in state_arrays.items()
            }
            observation["torch_version"] = str(torch.__version__)
            try:
                source = inspect.getsource(original_step.__func__)
                observation["step_implementation_sha256"] = hashlib.sha256(
                    source.encode()).hexdigest()
            except (AttributeError, OSError, TypeError):
                observation["step_implementation_sha256"] = None
            # PyTorch exposes counters and the last step length but does not
            # return which stopping condition ended the loop.
            observation["termination_status"] = "UNKNOWN"
            observation["termination_reason"] = "NOT_EXPOSED_BY_PYTORCH_LBFGS"
            return returned_loss

        # An instance attribute is an ordinary callable. It delegates directly
        # to the original bound method above, preserving the algorithm object.
        optimizer.step = observed_step
        return optimizer

    return factory


def _final_control_snapshot(optimizer_observation: Mapping, result, package: Mapping,
                            window_config, xb: State) -> tuple[dict[str, np.ndarray], dict, dict]:
    """Read final accepted-control gradients left by the existing audit closure."""
    if (optimizer_observation.get("constructor_calls") != 1
            or optimizer_observation.get("step_calls") != 1
            or optimizer_observation.get("step_returned") is not True):
        raise RuntimeError("fixed PR395 run did not use exactly one observed, returned LBFGS step")
    optimizer = optimizer_observation.get("optimizer")
    if optimizer is None:
        raise RuntimeError("the original LBFGS instance was not retained")
    params = optimizer.param_groups[0]["params"]
    if len(params) != 2:
        raise RuntimeError("fixed PR395 T/Q control contract expects exactly state and parameter controls")
    v_state_param, v_theta_param = params
    if v_state_param.grad is None or v_theta_param.grad is None:
        raise RuntimeError("final accepted-state audit did not leave full control-space gradients")
    v_state = v_state_param.detach().clone()
    v_theta = v_theta_param.detach().clone()
    grad_state = v_state_param.grad.detach().clone()
    grad_theta = v_theta_param.grad.detach().clone()
    if not torch.equal(v_state, result.v_state) or not torch.equal(v_theta, result.v_theta):
        raise RuntimeError("original LBFGS controls differ from returned v_state/v_theta")
    if (not bool(torch.isfinite(grad_state).all())
            or not bool(torch.isfinite(grad_theta).all())):
        raise FloatingPointError("final full control-space gradient contains non-finite values")
    state_l2 = float(torch.linalg.vector_norm(grad_state).cpu())
    theta_l2 = float(torch.linalg.vector_norm(grad_theta).cpu())
    if (not math.isclose(state_l2, float(result.grad_norm_final), rel_tol=1e-12, abs_tol=1e-12)
            or not math.isclose(theta_l2, float(result.grad_theta_norm_final),
                                rel_tol=1e-12, abs_tol=1e-12)):
        raise RuntimeError("captured accepted-control gradients disagree with returned gradient norms")
    combined = torch.cat((grad_state.reshape(-1), grad_theta.reshape(-1)))
    b_sigma = package["b_sigma"]
    param_prior = package["param_prior"]
    rederived_state, _ = cvt_apply(xb, b_sigma, v_state, package["cvt"])
    if any(not torch.equal(getattr(rederived_state, field), getattr(result.x_analysis, field))
           for field in State._fields):
        raise RuntimeError("returned x_analysis differs from exact CVT reconstruction from v_state/b_sigma")
    rederived_theta = params_from_vtheta(param_prior, v_theta, live=False)
    if any(not torch.equal(getattr(rederived_theta, name), getattr(result.theta_analysis, name))
           for name in PNAMES):
        raise RuntimeError("returned theta_analysis differs from exact log-parameter reconstruction")
    theta_analysis = torch.stack([
        getattr(result.theta_analysis, name).detach().to(torch.float64)
        for name in result.theta_analysis._fields])
    eta = window_config.eta
    eta_pre = window_config.eta_pre
    private = {
        "optimizer_v_state_control": _array(v_state).copy(),
        "optimizer_v_theta_control": _array(v_theta).copy(),
        "optimizer_final_gradient_v_state": _array(grad_state).copy(),
        "optimizer_final_gradient_v_theta": _array(grad_theta).copy(),
        "optimizer_final_gradient_combined": _array(combined).copy(),
        "parameter_theta_background": _array(param_prior.theta_b).copy(),
        "parameter_sigma_log": _array(param_prior.sigma_log).copy(),
        "parameter_theta_analysis": _array(theta_analysis).copy(),
        "fixed_eta_present": np.asarray([eta is not None], dtype=np.bool_),
        "fixed_eta_pre_present": np.asarray([eta_pre is not None], dtype=np.bool_),
        "fixed_eta": np.empty(0, dtype=np.float64) if eta is None else _array(eta).copy(),
        "fixed_eta_pre": np.empty(0, dtype=np.float64) if eta_pre is None else _array(eta_pre).copy(),
    }
    _record_state(private, "b_sigma", b_sigma)
    private.update(optimizer_observation.get("optimizer_state_arrays", {}))
    vectors = {name: array for name, array in private.items()
               if name.startswith(("optimizer_v_", "optimizer_final_gradient_",
                                   "fixed_eta", "parameter_"))}
    hashes = {name: array_sha256(array) for name, array in vectors.items()}
    array_metadata = {
        name: {"shape": list(array.shape), "dtype": str(array.dtype),
               "sha256_f64": hashes[name],
               "private_npz_key": f"control__{name}"}
        for name, array in vectors.items()
    }
    step_state = optimizer_observation["step_state"]
    group = step_state["group"]
    public = {
        "optimizer": {
            "constructor_calls": optimizer_observation["constructor_calls"],
            "step_calls": optimizer_observation["step_calls"],
            "step_returned": optimizer_observation["step_returned"],
            "termination_status": optimizer_observation["termination_status"],
            "torch_version": optimizer_observation["torch_version"],
            "step_implementation_sha256": optimizer_observation["step_implementation_sha256"],
            "termination_reason": optimizer_observation["termination_reason"],
            "step_original_loss_returned": optimizer_observation["step_original_loss_returned"],
            "actual_n_iter": step_state["n_iter"],
            "actual_func_evals": step_state["func_evals"],
            "step_t": step_state["step_t"],
            "prev_loss_at_step_return": step_state["prev_loss"],
            "max_iter": group["max_iter"], "max_eval": group["max_eval"],
            "lr": group["lr"], "history_size": group["history_size"],
            "tolerance_grad": group["tolerance_grad"],
            "tolerance_change": group["tolerance_change"],
            "line_search_fn": group["line_search_fn"],
            "final_audit_gradient_absmax": float(combined.abs().max().cpu()),
            "final_audit_gradient_within_tolerance_grad": bool(
                float(combined.abs().max().cpu()) <= float(group["tolerance_grad"])),
            "state_snapshot_timing": "after original optimizer.step returned and before final accepted-state audit",
            "state_structure": optimizer_observation.get("optimizer_state_structure", {}),
            "state_arrays": optimizer_observation.get("optimizer_state_array_metadata", {}),
            "n_window_evals": int(result.n_window_evals),
            "n_audit_evals": int(result.n_audit_evals),
        },
        "final_control_gradient": {
            "contract": "total objective gradient in LBFGS control space after the existing final audit; includes control-prior and CVT/log-parameter chain terms, not an RTTOV H-adjoint norm",
            "v_state_order": list(State._fields),
            "v_state_shape": list(grad_state.shape),
            "v_theta_order": list(PNAMES),
            "v_theta_shape": list(grad_theta.shape),
            "state_l2_norm": state_l2,
            "state_linf_norm": float(grad_state.abs().max().cpu()),
            "theta_l2_norm": theta_l2,
            "theta_linf_norm": float(grad_theta.abs().max().cpu()),
            "combined_l2_norm": float(torch.linalg.vector_norm(combined).cpu()),
            "combined_linf_norm": float(combined.abs().max().cpu()),
            "block_norms_match_minimizer_return": True,
            "x_analysis_rederived_exactly_from_v_state_and_b_sigma": True,
            "theta_analysis_rederived_exactly_from_v_theta_and_prior": True,
            "array_sha256_f64": hashes,
            "arrays": array_metadata,
        },
        "control_background": {
            "b_sigma_by_state_field": {
                field: {"shape": list(_array(getattr(b_sigma, field)).shape),
                        "dtype": str(_array(getattr(b_sigma, field)).dtype),
                        "sha256_f64": array_sha256(getattr(b_sigma, field)),
                        "private_npz_key": f"control__b_sigma__{field}"}
                for field in State._fields},
            "parameter_theta_background_sha256_f64": array_sha256(param_prior.theta_b),
            "parameter_theta_background_private_npz_key": "control__parameter_theta_background",
            "parameter_sigma_log_sha256_f64": array_sha256(param_prior.sigma_log),
            "parameter_sigma_log_private_npz_key": "control__parameter_sigma_log",
            "parameter_theta_analysis_sha256_f64": array_sha256(theta_analysis),
            "parameter_theta_analysis_private_npz_key": "control__parameter_theta_analysis",
            "fixed_eta": {"present": eta is not None,
                          "shape": None if eta is None else list(_array(eta).shape),
                          "sha256_f64": None if eta is None else array_sha256(eta),
                          "private_npz_key": "control__fixed_eta"},
            "fixed_eta_pre": {"present": eta_pre is not None,
                              "shape": None if eta_pre is None else list(_array(eta_pre).shape),
                              "sha256_f64": None if eta_pre is None else array_sha256(eta_pre),
                              "private_npz_key": "control__fixed_eta_pre"},
        },
    }
    metadata = {
        "optimizer_capture": {key: value for key, value in optimizer_observation.items()
                              if key not in ("optimizer", "optimizer_state_arrays")},
        "control_capture": {
            "state_control_order": list(State._fields),
            "parameter_control_order": public["final_control_gradient"]["v_theta_order"],
            "fixed_eta_present": eta is not None,
            "fixed_eta_pre_present": eta_pre is not None,
        },
    }
    return private, public, metadata


def _classify_failure(exc: BaseException) -> str:
    message = str(exc).lower()
    if "rad_quality" in message or "frozen support" in message or "frozen-support" in message:
        return "FROZEN_QUALITY_OR_SUPPORT_ABORT"
    return "ANALYSIS_EXCEPTION"


def _public_optimizer_failure_summary(observation: Mapping) -> dict:
    """Keep failure diagnostics public while excluding optimizer objects/raw vectors."""
    return {key: value for key, value in observation.items()
            if key not in ("optimizer", "optimizer_state_arrays")}


def _numerical_return_failure_summary(analysis_runner_returned: bool,
                                      package) -> dict:
    has_result = isinstance(package, Mapping) and package.get("result") is not None
    if has_result:
        status = "RETURNED_BUT_CAPTURE_FAILED"
    elif analysis_runner_returned:
        status = "RUNNER_RETURNED_WITHOUT_MINIMIZER_RESULT"
    else:
        status = "FAILED_BEFORE_RETURN"
    return {"status": status,
            "analysis_runner_returned": analysis_runner_returned,
            "minimizer_returned_state": bool(has_result)}


def _final_audit_signature(result, *, obs_time: int, final_mask: torch.Tensor) -> dict:
    """Bind the accepted audit trace signature to its frozen seven-channel mask."""
    trace = getattr(result, "j_trace", None)
    if not isinstance(trace, list) or not trace:
        raise RuntimeError("minimizer return lacks a final objective trace for signature audit")
    signature = None
    for index, item in enumerate(trace):
        if not isinstance(item, Mapping):
            raise RuntimeError(f"objective trace entry {index} is not a mapping")
        signatures = item.get("signature")
        n_valid = item.get("n_valid")
        if not isinstance(signatures, Mapping) or not isinstance(n_valid, Mapping):
            raise RuntimeError(f"objective trace entry {index} lacks frozen signature/count maps")
        current_signature = signatures.get(obs_time, signatures.get(str(obs_time)))
        current_count = n_valid.get(obs_time, n_valid.get(str(obs_time)))
        if not isinstance(current_signature, str) or len(current_signature) != 64:
            raise RuntimeError(f"objective trace entry {index} lacks a SHA-256 observation signature")
        if any(character not in "0123456789abcdef" for character in current_signature):
            raise RuntimeError(f"objective trace entry {index} signature is not lowercase SHA-256 hex")
        if current_count != 7:
            raise RuntimeError(f"objective trace entry {index} does not retain the fixed seven-channel support")
        if signature is None:
            signature = current_signature
        elif current_signature != signature:
            raise RuntimeError("observation signature changed across the minimizer trace")
    mask_array = np.asarray(_array(final_mask), dtype=np.float64)
    return {
        "slot": obs_time,
        "sha256": signature,
        "trace_entry_count": len(trace),
        "final_trace_index": len(trace) - 1,
        "all_trace_signatures_match": True,
        "n_valid_each_trace_entry": 7,
        "final_frozen_mask": {
            "shape": list(mask_array.shape),
            "dtype": str(mask_array.dtype),
            "sha256_f64": array_sha256(mask_array),
        },
    }


def _initial_zero_control_closure(result, events: Sequence[Mapping], *, obs_time: int,
                                  final_audit_signature: Mapping,
                                  final_mask: torch.Tensor) -> dict:
    """Extract and validate the first existing optimizer closure at zero controls."""
    trace = getattr(result, "j_trace", None)
    if not isinstance(trace, list) or not trace:
        raise RuntimeError("minimizer return lacks the initial zero-control trace entry")
    initial = trace[0]
    if not isinstance(initial, Mapping):
        raise RuntimeError("initial zero-control trace entry is not a mapping")
    jb = float(initial["j_state"])
    jtheta = float(initial["j_theta"])
    jo = float(initial["j_obs"])
    total = float(initial["total"])
    if jb != 0.0 or jtheta != 0.0:
        raise RuntimeError("first optimizer closure is not at zero state/parameter controls")
    if not math.isclose(total, jb + jtheta + jo, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError("initial zero-control Jtotal differs from Jb + Jtheta + Jo")
    n_valid_map = initial.get("n_valid")
    signature_map = initial.get("signature")
    if not isinstance(n_valid_map, Mapping) or not isinstance(signature_map, Mapping):
        raise RuntimeError("initial zero-control trace lacks n_valid/signature maps")
    n_valid = n_valid_map.get(obs_time, n_valid_map.get(str(obs_time)))
    signature = signature_map.get(obs_time, signature_map.get(str(obs_time)))
    if n_valid != 7 or signature != final_audit_signature.get("sha256"):
        raise RuntimeError("initial zero-control trace support/signature differs from the accepted audit")
    first_grad_event = next((event for event in events if event.get("grad") is True), None)
    if first_grad_event is None or not first_grad_event.get("returned", False):
        raise RuntimeError("initial zero-control trace lacks its successful first grad=True H callback")
    if first_grad_event.get("frozen_mask") != first_grad_event.get("fixed_mask"):
        raise RuntimeError("initial zero-control H callback mutated its frozen mask")
    mask_array = np.asarray(first_grad_event["fixed_mask"], dtype=np.float64)
    if not np.array_equal(mask_array, _array(final_mask)):
        raise RuntimeError("initial zero-control H support differs from the accepted audit support")
    raw_h_cost = float(first_grad_event["J_huber"])
    if not math.isclose(jo, raw_h_cost, rel_tol=1e-12, abs_tol=1e-12):
        raise RuntimeError("initial zero-control trace Jo differs from its first H callback cost")
    return {
        "trace_index": 0,
        "control_semantics": "first existing optimizer closure before L-BFGS updates; v_state and v_theta start at zero",
        "Jb_state": jb,
        "Jtheta": jtheta,
        "Jo": jo,
        "Jtotal": total,
        "n_valid": int(n_valid),
        "operator_signature_sha256": signature,
        "signature_matches_final_accepted_audit": True,
        "first_grad_true_h_call_index": first_grad_event["call_index"],
        "first_h_J_huber_matches_Jo": True,
        "frozen_mask": {
            "shape": list(mask_array.shape),
            "dtype": str(mask_array.dtype),
            "values": mask_array.tolist(),
            "sha256_f64": array_sha256(mask_array),
        },
    }


def _background_quality_probe(events: Sequence[Mapping]) -> dict:
    """Keep the raw zero-mask QC-probe cost distinct from objective Jo at v=0."""
    probe = next((event for event in events if event.get("grad") is False), None)
    if probe is None or not probe.get("returned", False):
        raise RuntimeError("successful adapter return lacks its grad=False background quality probe")
    if probe.get("frozen_mask") != probe.get("fixed_mask"):
        raise RuntimeError("background quality probe mutated its zero loss mask")
    mask = np.asarray(probe["fixed_mask"], dtype=np.float64)
    if not np.isfinite(mask).all() or np.count_nonzero(mask) != 0:
        raise RuntimeError("background quality probe must retain its all-zero cost mask")
    raw_cost = float(probe["J_huber"])
    if raw_cost != 0.0:
        raise RuntimeError("all-zero background quality-probe mask must have zero Huber cost")
    return {
        "call_index": probe["call_index"],
        "raw_J_huber": raw_cost,
        "cost_semantics": "non-grad background quality probe with all-zero loss mask; not initial zero-control closure Jo",
        "target_BT_K": probe["target_BT_K"],
        "BT_K": probe["BT_K"],
        "rad_quality": probe["rad_quality"],
        "mask": {"shape": list(mask.shape), "dtype": str(mask.dtype),
                 "values": mask.tolist(), "sha256_f64": array_sha256(mask)},
        "mask_unchanged_across_h": True,
    }


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
            or getattr(window_config, "eta", None) is not None
            or getattr(window_config, "eta_pre", None) is not None
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
    optimizer_observation = {"constructor_calls": 0, "step_calls": 0,
                             "step_returned": False}
    package = None
    analysis_runner_returned = False
    final_audit_signature = None
    failure_stage = "PRE_ANALYSIS"
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
        failure_stage = "NATIVE_INPUT_VALIDATED"
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
        original_lbfgs_factory = torch.optim.LBFGS

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

        try:
            _fulldomain.sharded_allsky = capture_call
            torch.optim.LBFGS = _observe_existing_lbfgs(
                original_lbfgs_factory, optimizer_observation)
            runner_kwargs = {
                "window_config": window_config,
                "obs_time": obs_time,
                "pool": pool,
                "n_workers": n_workers,
                "max_iter": max_iter,
            }
            if rttov_timeout is not None:
                runner_kwargs["rttov_timeout"] = rttov_timeout
            failure_stage = "ANALYSIS_RUNNING"
            package = analysis_runner(
                xb, forcings, y_bt, y_rq, xland, clear_cfg, rttov_cfg,
                str(case_root),
                **runner_kwargs)
            analysis_runner_returned = True
            failure_stage = "ANALYSIS_RETURNED"
        finally:
            _fulldomain.sharded_allsky = original_sharded
            torch.optim.LBFGS = original_lbfgs_factory

        result = package["result"]
        if last_grad_call is not None:
            final_audit_signature = _final_audit_signature(
                result, obs_time=obs_time, final_mask=last_grad_call["mask"])
        failure_stage = "POST_RETURN_VALIDATION"
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
        background_mask = torch.as_tensor(
            actual_meta.get("background_mask"), dtype=final_mask.dtype,
            device=final_mask.device)
        if not torch.equal(final_mask, background_mask):
            raise RuntimeError("final all-sky callback mask differs from the frozen background support")
        final_event = events[last_grad_call["call_index"] - 1]
        if (final_event.get("frozen_mask") != final_event.get("fixed_mask")
                or not final_event.get("returned", False)):
            raise RuntimeError("final all-sky callback mutated its frozen mask or failed before return")
        if (final_audit_signature["final_frozen_mask"]["sha256_f64"]
                != array_sha256(final_mask)):
            raise RuntimeError("final callback mask digest changed after audit signature capture")
        initial_zero_control_closure = _initial_zero_control_closure(
            result, events, obs_time=obs_time,
            final_audit_signature=final_audit_signature, final_mask=final_mask)
        background_quality_probe = _background_quality_probe(events)

        control_private, control_public, control_metadata = _final_control_snapshot(
            optimizer_observation, result, package, window_config, xb)
        failure_stage = "CONTROL_CAPTURED"

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
                "operator_signature": final_audit_signature,
            },
            "initial_zero_control_closure": initial_zero_control_closure,
            "background_quality_probe": background_quality_probe,
            "background_slot_capture": {
                "semantics": "first successful grad=False background quality probe",
                "state_sha256": state_sha256(background_slot),
                "forcing_sha256": forcing_sha256(background_slot_forcing),
            },
            "control_and_optimizer_capture": control_metadata,
        }
        private_arrays = _private_payload(
            xb=xb, accepted_initial_state=accepted_state,
            background_slot_state=background_slot,
            final_slot_state=last_grad_call["state"], forcings=forcings,
            final_slot_forcing=last_grad_call["forcing"], rho_d=rho_d,
            y_bt=y_bt, y_rq=y_rq,
            rttov_cfg=rttov_cfg, native_coordinates=native_coordinates,
            slot_calls=events, receipt_metadata=config_metadata,
            host_dry_mass_background_kg_m2=intake_arrays[
                "host_dry_mass_background_kg_m2"],
            extra_private_arrays=control_private)
        failure_stage = "PRIVATE_CHECKPOINT_WRITE"
        private_sha = write_private_npz_atomic(private_checkpoint, private_arrays)
        checkpoint_written = True
        failure_stage = "PRIVATE_CHECKPOINT_WRITTEN"

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
            "optimization": control_public["optimizer"],
            "final_control_gradient": control_public["final_control_gradient"],
            "control_background": control_public["control_background"],
            "native_intake_context": intake_binding,
            "host_dry_mass_background": intake_binding["host_dry_mass_background"],
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
                "final_audit_signature": final_audit_signature,
                "initial_zero_control_closure": initial_zero_control_closure,
                "final_rad_quality": final_rq.tolist(),
                "n_window_evals": int(result.n_window_evals),
                "n_audit_evals": int(result.n_audit_evals),
            },
            "background_quality_probe": background_quality_probe,
            "logical_h_calls": events,
            "runtime_rttov_child_launches": None,
            "runtime_rttov_child_launch_note": "not instrumented; logical all-sky H callback outputs are recorded",
        }
        failure_stage = "PUBLIC_RECEIPT_WRITE"
        receipt_sha = _write_receipt_exclusive(public_receipt, receipt)
        failure_stage = "SUCCESS_RECEIPT_PUBLISHED"
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
            "numerical_return": _numerical_return_failure_summary(
                analysis_runner_returned, package),
            "physical_matchup_and_science_acceptance": {
                "status": "NOT_ASSESSED",
                "science_accepted": False,
            },
            "analysis_exception": {"type": type(exc).__name__, "message": str(exc),
                                   "traceback": traceback.format_exc()},
            "failure_stage": failure_stage,
            "final_audit_signature": final_audit_signature,
            "native_intake_context": intake_binding,
            "private_checkpoint": {"path": str(private_checkpoint), "published": False},
            "callback_attempt_metadata": events,
            "optimizer_observation": _public_optimizer_failure_summary(optimizer_observation),
            "production_source_sha256_before": source_before,
            "production_source_sha256_after": _source_snapshot(),
            "valid_native_analysis_published": False,
        }
        if not public_receipt.exists():
            _write_receipt_exclusive(public_receipt, failure)
        return failure
