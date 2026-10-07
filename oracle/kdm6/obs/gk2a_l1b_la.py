"""Header-preserving reader for GK-2A AMI LA (la020ge) thermal channels.

This is separate from the KO and FD adapters. It reuses their packed-word
decoder and GEOS inverse projection, while keeping LA slot and scene metadata
distinct in a small sidecar.
"""
from __future__ import annotations

import copy
import hashlib
import math
import numbers
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np
import torch

from .gk2a_l1b import CLEAN_IR_CHANNELS, _positive_stride, _read_ami_bt
from .gk2a_l1b_fd import _GEO_ATTRS, geos_latlon
from .obs_ingest import ObsPayload

_F64 = {"dtype": torch.float64}
_LA_RE = re.compile(r"gk2a_ami_le1b_([a-z0-9]+)_la020ge_(\d{12})\.nc$")
_CAL_ATTRS = (
    "DN_to_Radiance_Gain", "DN_to_Radiance_Offset",
    "Teff_to_Tbb_c0", "Teff_to_Tbb_c1", "Teff_to_Tbb_c2",
    "Plank_constant_h", "light_speed", "Boltzmann_constant_k",
    "channel_center_wavelength",
)
_SCENE_ATTRS = (
    "satellite_name", "instrument_name", "data_processing_center",
    "data_processing_mode", "observation_mode", "projection_type",
    "channel_spatial_resolution", "scene_acquisition_time",
    "mission_reference_time", "file_generation_time", "file_format_version",
    "geometric_correction_sw_version", "calibration_table_version",
    "number_of_total_swaths", "resampling_kernel_type",
    "image_upperleft_latitude", "image_upperleft_longitude",
)
_NUMERIC_TIME_ATTRS = (
    "observation_start_time", "observation_end_time",
    "time_synchro_utc", "time_synchro_obt",
)


@dataclass(frozen=True)
class LAReadResult:
    """Existing ObsPayload plus the sidecar needed to interpret an LA read.

    payload.valid_time_utc stays unset: the filename and scene acquisition
    timestamp are OBT, not UTC. Planned mission UTC and raw numeric time fields
    stay in metadata without inferring an OBT/UTC offset.
    pixel_rows/pixel_cols map each payload row back to its original LA raster
    location after stride sampling and GEOS-disk filtering.
    """

    payload: ObsPayload
    metadata: dict
    pixel_rows: np.ndarray
    pixel_cols: np.ndarray


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _plain_scalar(value):
    return value.item() if isinstance(value, np.generic) else value


def _real_scalar(value, label: str, *, allow_numeric_string: bool = False) -> float:
    if (isinstance(value, (bool, np.bool_)) or np.iscomplexobj(value)
            or np.ndim(value) != 0):
        raise ValueError(f"{label} must be a finite real scalar")
    if not allow_numeric_string and not isinstance(value, numbers.Real):
        raise ValueError(f"{label} must be a finite real scalar")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite real scalar") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite real scalar")
    return result


def _paired_calibration(ds, channel: str, calibration_table: dict) -> dict:
    """Require exact file/table coefficient pairing and an audited BT center."""
    reference = calibration_table.get("channels", {}).get(channel)
    if not isinstance(reference, dict):
        raise ValueError(f"{channel}: paired AMI calibration table entry is missing")
    for name in _CAL_ATTRS:
        try:
            raw = ds.getncattr(name)
        except AttributeError as exc:
            raise ValueError(f"{ds.filepath()}: missing calibration attribute {name}") from exc
        if isinstance(raw, np.generic):
            raw = raw.item()
        actual = _real_scalar(raw, f"{channel} file {name}",
                              allow_numeric_string=(name == "channel_center_wavelength"))
        expected = _real_scalar(reference.get(name), f"{channel} table {name}",
                                allow_numeric_string=(name == "channel_center_wavelength"))
        if actual != expected:
            raise ValueError(
                f"{channel}: file {name} does not exactly match the paired calibration table")
    if "bt_wavenumber_cm1" not in reference:
        raise ValueError(f"{channel}: paired table lacks bt_wavenumber_cm1")
    wn = _real_scalar(reference["bt_wavenumber_cm1"],
                      f"{channel} paired BT wavenumber")
    if wn <= 0.0:
        raise ValueError(f"{channel}: paired BT wavenumber must be positive")
    if "bt_wavenumber_cm1" in ds.ncattrs():
        file_wn = _real_scalar(ds.getncattr("bt_wavenumber_cm1"),
                               f"{channel} file BT wavenumber")
        if file_wn != wn:
            raise ValueError(f"{channel}: file BT wavenumber does not match the paired table")
    return dict(reference)


def _parse_scene_obt(raw: str, nominal_stamp: str) -> str:
    """Parse the packet/first-swath OBT string without assigning a timezone."""
    if not isinstance(raw, str):
        raise ValueError("scene_acquisition_time must be the original timestamp string")
    try:
        scene = datetime.strptime(raw, "%Y%m%d_%H%M%S")
        nominal = datetime.strptime(nominal_stamp, "%Y%m%d%H%M")
    except ValueError as exc:
        raise ValueError("LA timestamps must use YYYYMMDD_HHMMSS / YYYYMMDDHHMM") from exc
    if scene.strftime("%Y%m%d%H%M") != nominal.strftime("%Y%m%d%H%M"):
        raise ValueError(
            f"scene acquisition minute {scene:%Y%m%d%H%M} does not match "
            f"the nominal filename OBT slot {nominal_stamp}")
    return scene.isoformat()


def _parse_planned_utc(raw: str) -> str | None:
    """Parse mission_reference_time as planned UTC, not observed pixel time."""
    if not isinstance(raw, str):
        raise ValueError("mission_reference_time must be a string")
    if raw == "00000000_000000":
        return None
    try:
        value = datetime.strptime(raw, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError("mission_reference_time must use YYYYMMDD_HHMMSS or the zero sentinel") from exc
    return value.isoformat().replace("+00:00", "Z")


def _validate_quality_meaning(variable, path: Path) -> None:
    required = (
        "channel_name", "number_of_total_bits_per_pixel",
        "number_of_valid_bits_per_pixel",
        "number_of_data_quality_flag_bits_per_pixel",
        "data_quality_flag_meaning",
    )
    missing = [name for name in required if name not in variable.ncattrs()]
    if missing:
        raise ValueError(f"{path.name}: image_pixel_values is missing attributes {missing}")
    total_bits = _real_scalar(
        variable.getncattr("number_of_total_bits_per_pixel"),
        f"{path.name} number_of_total_bits_per_pixel")
    if total_bits != 16.0:
        raise ValueError(f"{path.name}: expected 16 total image bits")
    dqf_bits = _real_scalar(
        variable.getncattr("number_of_data_quality_flag_bits_per_pixel"),
        f"{path.name} number_of_data_quality_flag_bits_per_pixel")
    if dqf_bits != 2.0:
        raise ValueError(f"{path.name}: expected the two-bit AMI quality field")
    meaning = variable.getncattr("data_quality_flag_meaning")
    if isinstance(meaning, bytes):
        meaning = meaning.decode("ascii", errors="strict")
    if not isinstance(meaning, str):
        raise ValueError(f"{path.name}: data_quality_flag_meaning must be text")
    text = " ".join(meaning.casefold().replace(";", ",").split())
    pairs = re.findall(r"(\d+)\s*:\s*([a-z0-9_]+)", text)
    expected = {
        "0": "good_pixel",
        "1": "conditionally_usable_pixel",
        "2": "out_of_scan_area_pixel",
        "3": "error_pixel",
    }
    if len(pairs) != len(expected) or dict(pairs) != expected:
        raise ValueError(f"{path.name}: unrecognized AMI data-quality flag meaning")


def read_la_slot(files: Sequence[str | Path], calibration_table: dict,
                 *, stride: int = 1) -> LAReadResult:
    """Read a complete LA020GE AMI 8–16 slot into an ObsPayload and sidecar.

    All nine channels must share the same nominal slot, scene family, 500×500
    GEOS geometry, raw time headers and exactly paired calibration tuple. The
    filename minute remains the payload slot label; this routine does not
    validate pixel scan time or authorize an observation/DA match.
    """
    stride = _positive_stride(stride)
    if not files:
        raise ValueError("LA slot must contain all nine thermal channel files")
    if not isinstance(calibration_table, dict) or not isinstance(
            calibration_table.get("channels"), dict):
        raise ValueError("LA reader requires the paired AMI calibration table")
    # Calibration values are static I/O inputs. Snapshot before opening any
    # file so caller mutation cannot change the BT center between header and
    # pixel passes.
    calibration_table = copy.deepcopy(calibration_table)

    by_channel: dict[str, Path] = {}
    nominal_stamp = None
    for item in files:
        path = Path(item)
        match = _LA_RE.fullmatch(path.name)
        if match is None:
            raise ValueError(f"not an LA020GE L1B filename: {path}")
        channel, stamp = match.groups()
        if channel not in CLEAN_IR_CHANNELS:
            raise ValueError(f"unsupported LA channel {channel}; expected AMI 8–16")
        if channel in by_channel:
            raise ValueError(f"duplicate LA channel {channel}")
        if nominal_stamp is None:
            nominal_stamp = stamp
        elif stamp != nominal_stamp:
            raise ValueError(f"mixed timestamps in LA slot: {nominal_stamp} vs {stamp}")
        by_channel[channel] = path
    missing = [channel for channel in CLEAN_IR_CHANNELS if channel not in by_channel]
    if missing:
        raise ValueError(f"LA slot is missing required AMI 8–16 channels: {missing}")

    import netCDF4

    common_scene_fields = tuple(
        name for name in _SCENE_ATTRS if name != "scene_acquisition_time")
    slot_family = None
    slot_geometry = None
    slot_raw_times = None
    slot_scene_raw = None
    slot_scene_obt = None
    slot_planned_utc = None
    files_metadata = {}
    expected_hashes = {}

    # Header-only pass: reject malformed/mixed scenes before decoding any
    # image_pixel_values array.
    for channel in CLEAN_IR_CHANNELS:
        path = by_channel[channel]
        expected_hash = _sha256(path)
        with netCDF4.Dataset(str(path)) as ds:
            required = (
                *_SCENE_ATTRS, "file_name", "number_of_columns", "number_of_lines",
                *_GEO_ATTRS, *_NUMERIC_TIME_ATTRS,
            )
            missing_attrs = [name for name in required if name not in ds.ncattrs()]
            if missing_attrs:
                raise ValueError(f"{path.name}: missing LA header attributes {missing_attrs}")
            if ds.getncattr("file_name") != path.name:
                raise ValueError(f"{path.name}: file_name attribute does not match the original filename")
            if (ds.getncattr("satellite_name") != "GK-2A"
                    or ds.getncattr("instrument_name") != "AMI"
                    or ds.getncattr("observation_mode") != "LA"
                    or ds.getncattr("projection_type") != "GEOS"):
                raise ValueError(f"{path.name}: not a GK-2A AMI LA GEOS scene")
            if ds.getncattr("file_format_version") != "1.0.0_20181120":
                raise ValueError(
                    f"{path.name}: unsupported LA file_format_version "
                    f"{ds.getncattr('file_format_version')!r}")
            if _real_scalar(ds.getncattr("channel_spatial_resolution"),
                            f"{path.name} channel_spatial_resolution",
                            allow_numeric_string=True) != 2.0:
                raise ValueError(f"{path.name}: LA020GE channel resolution must be 2 km")
            if (_real_scalar(ds.getncattr("number_of_columns"),
                             f"{path.name} number_of_columns") != 500.0
                    or _real_scalar(ds.getncattr("number_of_lines"),
                                    f"{path.name} number_of_lines") != 500.0):
                raise ValueError(f"{path.name}: LA020GE must be the original 500×500 image")
            if ("dim_image_y" not in ds.dimensions or "dim_image_x" not in ds.dimensions
                    or len(ds.dimensions["dim_image_y"]) != 500
                    or len(ds.dimensions["dim_image_x"]) != 500):
                raise ValueError(f"{path.name}: LA dimensions must be 500×500")
            variable = ds.variables.get("image_pixel_values")
            if (variable is None or variable.shape != (500, 500)
                    or variable.dimensions != ("dim_image_y", "dim_image_x")
                    or variable.dtype != np.dtype("uint16")):
                raise ValueError(f"{path.name}: image_pixel_values must be 500×500 uint16")
            variable_attrs = (
                "channel_name", "number_of_valid_bits_per_pixel",
                "number_of_data_quality_flag_bits_per_pixel",
            )
            missing_variable_attrs = [
                name for name in variable_attrs if name not in variable.ncattrs()]
            if missing_variable_attrs:
                raise ValueError(
                    f"{path.name}: image_pixel_values is missing attributes "
                    f"{missing_variable_attrs}")
            if variable.getncattr("channel_name") != channel.upper():
                raise ValueError(f"{path.name}: variable channel_name does not match filename channel")
            valid_bits = _real_scalar(
                variable.getncattr("number_of_valid_bits_per_pixel"),
                f"{path.name} number_of_valid_bits_per_pixel")
            if valid_bits not in (11.0, 12.0, 13.0, 14.0):
                raise ValueError(f"{path.name}: unsupported valid-bit count {valid_bits}")
            _validate_quality_meaning(variable, path)

            scene_raw = ds.getncattr("scene_acquisition_time")
            scene_obt = _parse_scene_obt(scene_raw, nominal_stamp)
            mission_raw = ds.getncattr("mission_reference_time")
            planned_utc = _parse_planned_utc(mission_raw)
            scene_family = tuple(_plain_scalar(ds.getncattr(name))
                                 for name in common_scene_fields)
            geometry = {
                name: _real_scalar(ds.getncattr(name), f"{path.name} {name}")
                for name in _GEO_ATTRS
            }
            header_anchor_rad = {
                name: _real_scalar(ds.getncattr(name), f"{path.name} {name}")
                for name in ("image_upperleft_latitude", "image_upperleft_longitude")
            }
            if (geometry["cfac"] == 0.0 or geometry["lfac"] == 0.0
                    or geometry["earth_equatorial_radius"] <= 0.0
                    or geometry["earth_polar_radius"] <= 0.0
                    or geometry["nominal_satellite_height"]
                    <= geometry["earth_equatorial_radius"]):
                raise ValueError(f"{path.name}: invalid LA GEOS parameters")
            # NMSC's LA GEOS scan coordinates are one-based even though the
            # NetCDF image array indices (and this sidecar's pixel IDs) are 0-based.
            anchor_lat, anchor_lon = geos_latlon(
                np.array([1.0]), np.array([1.0]), geometry)
            if (not math.isclose(float(anchor_lat[0]),
                                 math.degrees(header_anchor_rad["image_upperleft_latitude"]),
                                 rel_tol=0.0, abs_tol=1e-9)
                    or not math.isclose(float(anchor_lon[0]),
                                        math.degrees(header_anchor_rad["image_upperleft_longitude"]),
                                        rel_tol=0.0, abs_tol=1e-9)):
                raise ValueError(
                    f"{path.name}: one-based GEOS upper-left coordinate does not match header")
            raw_times = {
                name: _real_scalar(ds.getncattr(name), f"{path.name} {name}")
                for name in _NUMERIC_TIME_ATTRS
            }
            if slot_family is None:
                slot_family = scene_family
                slot_geometry = geometry
                slot_anchor_rad = header_anchor_rad
                slot_raw_times = raw_times
                slot_scene_raw = scene_raw
                slot_scene_obt = scene_obt
                slot_planned_utc = planned_utc
            else:
                if (scene_family != slot_family or scene_raw != slot_scene_raw
                        or planned_utc != slot_planned_utc):
                    raise ValueError(f"{path.name}: channel belongs to a different LA scene family")
                if geometry != slot_geometry:
                    raise ValueError(f"{path.name}: channel geometry differs within slot")
                if header_anchor_rad != slot_anchor_rad:
                    raise ValueError(f"{path.name}: GEOS image corner differs within slot")
                if raw_times != slot_raw_times:
                    raise ValueError(f"{path.name}: raw time headers differ within slot")

            paired = _paired_calibration(ds, channel, calibration_table)
            files_metadata[channel] = {
                "source_id": path.name,
                "source_path": str(path),
                "sha256": expected_hash,
                "calibration_tuple_paired": True,
                "paired_calibration_values": {
                    **{name: paired[name] for name in _CAL_ATTRS},
                    "bt_wavenumber_cm1": paired["bt_wavenumber_cm1"],
                },
                "paired_bt_wavenumber_cm1": paired["bt_wavenumber_cm1"],
                "number_of_valid_bits_per_pixel": int(valid_bits),
            }
        if _sha256(path) != expected_hash:
            raise ValueError(
                f"{path.name}: source file changed during header validation")
        expected_hashes[channel] = expected_hash

    # Pixel dimensions originate in the original LA raster. Stride follows the
    # existing center-offset sampling convention and GEOS-disk NaNs are omitted.
    row0 = stride // 2
    rows = np.arange(row0, 500, stride, dtype=np.float64)
    cols = np.arange(row0, 500, stride, dtype=np.float64)
    row_grid, col_grid = np.meshgrid(rows, cols, indexing="ij")
    lat_grid, lon_grid = geos_latlon(row_grid + 1.0, col_grid + 1.0, slot_geometry)
    keep = np.isfinite(lat_grid) & np.isfinite(lon_grid)
    pixel_rows = row_grid.astype(np.int64).reshape(-1)[keep.reshape(-1)]
    pixel_cols = col_grid.astype(np.int64).reshape(-1)[keep.reshape(-1)]
    if pixel_rows.size == 0:
        raise ValueError("LA GEOS image has no finite geolocated pixels")

    bt_columns, quality_columns = [], []
    pixel_slices = (slice(row0, 500, stride), slice(row0, 500, stride))
    for channel in CLEAN_IR_CHANNELS:
        path = by_channel[channel]
        expected_hash = expected_hashes[channel]
        if _sha256(path) != expected_hash:
            raise ValueError(f"{path.name}: source file changed before pixel decoding")
        with netCDF4.Dataset(str(path)) as ds:
            calibration = _paired_calibration(ds, channel, calibration_table)
            bt, quality = _read_ami_bt(
                ds.variables["image_pixel_values"], calibration, pixel_slices)
        if _sha256(path) != expected_hash:
            raise ValueError(
                f"{path.name}: source file changed during pixel decoding")
        bt_columns.append(bt.reshape(-1)[keep.reshape(-1)])
        quality_columns.append(quality.reshape(-1)[keep.reshape(-1)])

    # The first channel may have changed after its individual decode while a
    # later channel was being read; guard the complete assembled slot too.
    for channel in CLEAN_IR_CHANNELS:
        path = by_channel[channel]
        if _sha256(path) != expected_hashes[channel]:
            raise ValueError(f"{path.name}: source file changed before payload return")

    pixel_keep = keep.reshape(-1)
    payload = ObsPayload(
        bt=torch.as_tensor(np.stack(bt_columns, axis=1), **_F64),
        obs_quality=torch.as_tensor(np.stack(quality_columns, axis=1), **_F64),
        lat=torch.as_tensor(np.ascontiguousarray(lat_grid.reshape(-1)[pixel_keep]), **_F64),
        lon=torch.as_tensor(np.ascontiguousarray(lon_grid.reshape(-1)[pixel_keep]), **_F64),
        valid_time_utc=None)
    scene_header = dict(zip(common_scene_fields, slot_family))
    metadata = {
        "source_product": "GK-2A AMI L1B LA020GE",
        "channels": list(CLEAN_IR_CHANNELS),
        "nominal_slot_obt": nominal_stamp,
        "payload_valid_time_role": "unset; filename label is OBT and no documented UTC conversion was applied",
        "scene_acquisition_time_raw": slot_scene_raw,
        "scene_acquisition_time_parsed_obt": slot_scene_obt,
        "scene_acquisition_time_utc": None,
        "pixel_utc_time_verified": False,
        "mission_reference_time_raw": scene_header["mission_reference_time"],
        "mission_reference_time_role": "planned UTC; not observed or pixel time",
        "planned_utc_time": slot_planned_utc,
        "observation_start_time_raw": slot_raw_times["observation_start_time"],
        "observation_end_time_raw": slot_raw_times["observation_end_time"],
        "observation_time_units": "seconds",
        "observation_time_epoch": None,
        "time_synchro_utc_raw": slot_raw_times["time_synchro_utc"],
        "time_synchro_obt_raw": slot_raw_times["time_synchro_obt"],
        "numeric_time_interpretation": (
            "observation start/end are documented seconds with no epoch resolved here; "
            "synchro UTC/OBT fields remain raw and no offset conversion was inferred"),
        "time_semantics_source_url": (
            "https://datasvc.nmsc.kma.go.kr/resources/common/pdf/"
            "%EC%B2%9C%EB%A6%AC%EC%95%88%EC%9C%84%EC%84%B1%202A%ED%98%B8%20"
            "%20%EC%9E%90%EB%A3%8C%ED%99%9C%EC%9A%A9%20QA.pdf"),
        "image_shape": [500, 500],
        "image_dimensions": ["dim_image_y", "dim_image_x"],
        "channel_spatial_resolution_km": 2.0,
        "projection_type": "GEOS",
        "scene_family": scene_header,
        "geos": dict(slot_geometry),
        "geos_scan_coordinate_origin": "one-based GEOS counts; returned pixel IDs are zero-based array indices",
        "geos_header_upper_left_rad": dict(slot_anchor_rad),
        "source_files": [files_metadata[channel] for channel in CLEAN_IR_CHANNELS],
        "pixel_index_semantics": (
            "pixel_rows/pixel_cols align with payload rows and give original "
            "LA image indices after stride sampling and finite-GEOS-footprint filtering"),
        "stride": stride,
    }
    return LAReadResult(payload=payload, metadata=metadata,
                        pixel_rows=pixel_rows, pixel_cols=pixel_cols)
