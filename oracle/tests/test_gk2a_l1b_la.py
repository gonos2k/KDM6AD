"""Focused synthetic contract tests for the isolated LA020GE reader."""
from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy

import numpy as np
import pytest
import torch

import kdm6.obs.gk2a_l1b_la as la_reader
from kdm6.obs.gk2a_l1b import CLEAN_IR_CHANNELS, dn_to_bt
from kdm6.obs.gk2a_l1b_la import read_la_slot
from kdm6.obs.obs_ingest import payload_to_column_obs

netCDF4 = pytest.importorskip("netCDF4")
F64 = {"dtype": torch.float64}
STAMP = "202507190534"
SCENE_TIME = "20250719_053442"
GEO = {
    "coff": 314.30357081070537,
    "loff": 2089.571379176208,
    "cfac": 20425338.903339352,
    "lfac": -20425338.903339356,
    "sub_longitude": 2.2375121010567303,
    "nominal_satellite_height": 42164000.0,
    "earth_equatorial_radius": 6378137.0,
    "earth_polar_radius": 6356752.3,
}
VALID_BITS = {ch: (12 if ch == "wv063" else 13) for ch in CLEAN_IR_CHANNELS}


def _calibration():
    path = (__import__("pathlib").Path(__file__).parents[1]
            / "kdm6/obs/data/gk2a_ami_cal_202507190000.json")
    return json.loads(path.read_text())


def _write_slot(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    table = _calibration()
    files = []
    raw_values = {}
    for index, channel in enumerate(CLEAN_IR_CHANNELS):
        path = tmp_path / f"gk2a_ami_le1b_{channel}_la020ge_{STAMP}.nc"
        ref = table["channels"][channel]
        with netCDF4.Dataset(path, "w") as ds:
            ds.createDimension("dim_image_y", 500)
            ds.createDimension("dim_image_x", 500)
            attrs = {
                "satellite_name": "GK-2A",
                "instrument_name": "AMI",
                "data_processing_center": "NMSC",
                "data_processing_mode": "operation",
                "observation_mode": "LA",
                "channel_spatial_resolution": "2.0",
                "channel_center_wavelength": str(ref["channel_center_wavelength"]),
                "scene_acquisition_time": SCENE_TIME,
                "mission_reference_time": "20250719_053000",
                "file_generation_time": "20250719_053600",
                "file_format_version": "1.0.0_20181120",
                "file_name": path.name,
                "geometric_correction_sw_version": "GK2_INRSM_V1.3",
                "calibration_table_version": "v.3.0_20190415",
                "projection_type": "GEOS",
                "number_of_columns": np.int32(500),
                "number_of_lines": np.int32(500),
                "number_of_total_swaths": np.int32(3),
                "resampling_kernel_type": "SINC",
                "image_upperleft_latitude": np.float64(0.7709971705416278),
                "image_upperleft_longitude": np.float64(2.0929034164225846),
                "observation_start_time": np.float64(806175282.4338461),
                "observation_end_time": np.float64(806175343.6724635),
                "time_synchro_utc": np.float64(806175282.4398186),
                "time_synchro_obt": np.float64(806175282.4338461),
                **GEO,
            }
            for key, value in attrs.items():
                ds.setncattr(key, value)
            for key in (
                    "DN_to_Radiance_Gain", "DN_to_Radiance_Offset",
                    "Teff_to_Tbb_c0", "Teff_to_Tbb_c1", "Teff_to_Tbb_c2",
                    "Plank_constant_h", "light_speed", "Boltzmann_constant_k",
                    "channel_center_wavelength"):
                ds.setncattr(key, ref[key])
            values = np.zeros((500, 500), dtype=np.uint16)
            values[0, 0] = np.uint16(100 + index)
            values[0, 1] = np.uint16(200 + index + (1 << 14))
            values[1, 0] = np.uint16(300 + index + (2 << 14))
            values[1, 1] = np.uint16(400 + index + (3 << 14))
            raw_values[channel] = values[:2, :2].copy()
            var = ds.createVariable(
                "image_pixel_values", "u2", ("dim_image_y", "dim_image_x"),
                zlib=True, complevel=1)
            var.setncattr("channel_name", channel.upper())
            var.setncattr("number_of_total_bits_per_pixel", np.int32(16))
            var.setncattr("number_of_valid_bits_per_pixel", np.int32(VALID_BITS[channel]))
            var.setncattr("number_of_data_quality_flag_bits_per_pixel", np.int32(2))
            var.setncattr(
                "data_quality_flag_meaning",
                "0:good_pixel, 1:conditionally_usable_pixel, 2:out_of_scan_area_pixel, 3:error_pixel")
            var[:] = values
        files.append(path)
    return files, table, raw_values


def _change_attr(path, name, value):
    with netCDF4.Dataset(path, "r+") as ds:
        ds.setncattr(name, value)


def _change_var_attr(path, variable, name, value):
    with netCDF4.Dataset(path, "r+") as ds:
        ds.variables[variable].setncattr(name, value)


def test_la_reader_preserves_slot_scene_raw_times_geometry_pixels_and_hashes(tmp_path):
    files, table, raw = _write_slot(tmp_path)
    result = read_la_slot(files, table, stride=1)
    payload = result.payload

    assert tuple(result.metadata["channels"]) == tuple(CLEAN_IR_CHANNELS)
    assert payload.valid_time_utc is None
    assert result.metadata["nominal_slot_obt"] == STAMP
    assert result.metadata["payload_valid_time_role"] == (
        "unset; filename label is OBT and no documented UTC conversion was applied")
    assert result.metadata["scene_acquisition_time_raw"] == SCENE_TIME
    assert result.metadata["scene_acquisition_time_parsed_obt"] == "2025-07-19T05:34:42"
    assert result.metadata["scene_acquisition_time_utc"] is None
    assert result.metadata["pixel_utc_time_verified"] is False
    assert result.metadata["mission_reference_time_raw"] == "20250719_053000"
    assert result.metadata["planned_utc_time"] == "2025-07-19T05:30:00Z"
    assert result.metadata["mission_reference_time_role"] == "planned UTC; not observed or pixel time"
    assert result.metadata["observation_start_time_raw"] == 806175282.4338461
    assert result.metadata["observation_end_time_raw"] == 806175343.6724635
    assert result.metadata["observation_time_units"] == "seconds"
    assert result.metadata["observation_time_epoch"] is None
    assert result.metadata["time_synchro_utc_raw"] == 806175282.4398186
    assert result.metadata["time_synchro_obt_raw"] == 806175282.4338461
    json.dumps(result.metadata, allow_nan=False)
    assert payload.bt.shape[1] == 9
    assert payload.obs_quality.shape == payload.bt.shape
    assert result.pixel_rows[0] == 0 and result.pixel_cols[0] == 0
    assert result.pixel_rows[1] == 0 and result.pixel_cols[1] == 1
    assert result.metadata["geos"] == GEO

    first_channel = CLEAN_IR_CHANNELS[0]
    expected_bt, expected_q = dn_to_bt(
        raw[first_channel], table["channels"][first_channel],
        valid_bits=VALID_BITS[first_channel])
    assert float(payload.bt[0, 0]) == float(expected_bt[0, 0])
    assert float(payload.obs_quality[0, 0]) == 0.0
    assert float(payload.obs_quality[1, 0]) == float(expected_q[0, 1]) == 1.0
    assert float(payload.obs_quality[500, 0]) == float(expected_q[1, 0]) == 2.0

    # Independent fixed NMSC header corner values, in degrees. The first
    # zero-based array pixel maps through one-based GEOS scan coordinate (1,1).
    assert result.metadata["geos_scan_coordinate_origin"].startswith("one-based")
    assert float(payload.lat[0]) == pytest.approx(44.174883888563436, abs=1e-9)
    assert float(payload.lon[0]) == pytest.approx(119.91453268952512, abs=1e-9)
    assert not math.isclose(float(payload.lat[0]), 44.20579104845654, abs_tol=1e-6)
    first_file = files[0]
    first_record = result.metadata["source_files"][0]
    assert first_record["source_id"] == first_file.name
    assert first_record["sha256"] == hashlib.sha256(first_file.read_bytes()).hexdigest()
    assert first_record["calibration_tuple_paired"] is True
    assert first_record["paired_bt_wavenumber_cm1"] == table["channels"][first_channel][
        "bt_wavenumber_cm1"]


def test_la_reader_is_input_order_independent_and_keeps_original_stride_indices(tmp_path):
    files, table, _ = _write_slot(tmp_path)
    forward = read_la_slot(files, table, stride=2)
    reversed_result = read_la_slot(list(reversed(files)), table, stride=2)

    assert torch.equal(forward.payload.bt, reversed_result.payload.bt)
    assert torch.equal(forward.payload.obs_quality, reversed_result.payload.obs_quality)
    assert torch.equal(forward.payload.lat, reversed_result.payload.lat)
    assert torch.equal(forward.payload.lon, reversed_result.payload.lon)
    assert np.array_equal(forward.pixel_rows, reversed_result.pixel_rows)
    assert np.array_equal(forward.pixel_cols, reversed_result.pixel_cols)
    assert forward.pixel_rows[0] == 1 and forward.pixel_cols[0] == 1
    assert forward.pixel_rows[1] == 1 and forward.pixel_cols[1] == 3
    assert forward.pixel_rows[250] == 3 and forward.pixel_cols[250] == 1


def test_la_reader_requires_complete_ordered_thermal_channel_set(tmp_path):
    files, table, _ = _write_slot(tmp_path)
    with pytest.raises(ValueError, match="missing required"):
        read_la_slot(files[:-1], table)
    with pytest.raises(ValueError, match="unsupported LA channel"):
        read_la_slot(
            files[:-1] + [tmp_path / f"gk2a_ami_le1b_sw038_la020ge_{STAMP}.nc"],
            table)


@pytest.mark.parametrize(
    "filename,attribute,value,match",
    [
        ("ir105", "coff", GEO["coff"] + 1.0, "GEOS upper-left coordinate"),
        ("ir105", "scene_acquisition_time", "20250719_053500", "does not match"),
        ("ir105", "mission_reference_time", "20250719_053100", "different LA scene family"),
        ("ir105", "observation_mode", "FD", "not a GK-2A AMI LA GEOS scene"),
        ("ir105", "DN_to_Radiance_Gain", 0.0, "does not exactly match"),
        ("ir105", "file_format_version", "1.0.0_bad", "unsupported LA file_format_version"),
    ])
def test_la_reader_rejects_mixed_scene_geometry_time_or_calibration(
        tmp_path, filename, attribute, value, match):
    files, table, _ = _write_slot(tmp_path)
    target = next(path for path in files if f"_{filename}_la020ge_" in path.name)
    _change_attr(target, attribute, value)
    with pytest.raises(ValueError, match=match):
        read_la_slot(files, table)


def test_la_reader_rejects_explicit_wavenumber_mismatch_and_mixed_slots(tmp_path):
    files, table, _ = _write_slot(tmp_path)
    with netCDF4.Dataset(files[-1], "r+") as ds:
        ds.setncattr("bt_wavenumber_cm1", table["channels"][CLEAN_IR_CHANNELS[-1]][
            "bt_wavenumber_cm1"] + 1.0)
    with pytest.raises(ValueError, match="BT wavenumber does not match"):
        read_la_slot(files, table)

    files, table, _ = _write_slot(tmp_path / "second")
    mismatched = tmp_path / "gk2a_ami_le1b_ir133_la020ge_202507190535.nc"
    files[-1].rename(mismatched)
    files[-1] = mismatched
    with pytest.raises(ValueError, match="mixed timestamps"):
        read_la_slot(files, table)


def test_la_reader_rejects_missing_packed_quality_metadata(tmp_path):
    files, table, _ = _write_slot(tmp_path)
    with netCDF4.Dataset(files[0], "r+") as ds:
        ds.variables["image_pixel_values"].delncattr(
            "number_of_data_quality_flag_bits_per_pixel")
    with pytest.raises(ValueError, match="missing attributes"):
        read_la_slot(files, table)


def test_la_reader_gates_total_bits_and_rejects_contradictory_dqf_meaning(tmp_path):
    files, table, _ = _write_slot(tmp_path)
    _change_var_attr(files[0], "image_pixel_values",
                     "number_of_total_bits_per_pixel", 15)
    with pytest.raises(ValueError, match="expected 16 total image bits"):
        read_la_slot(files, table)

    files, table, _ = _write_slot(tmp_path / "contradictory")
    _change_var_attr(
        files[0], "image_pixel_values", "data_quality_flag_meaning",
        "0:good_pixel, 0:error_pixel, 1:conditionally_usable_pixel, "
        "2:out_of_scan_area_pixel, 3:error_pixel")
    with pytest.raises(ValueError, match="unrecognized AMI data-quality flag meaning"):
        read_la_slot(files, table)


def test_la_reader_accepts_spacing_and_zero_planned_utc_sentinel(tmp_path):
    files, table, _ = _write_slot(tmp_path)
    _change_var_attr(
        files[0], "image_pixel_values", "data_quality_flag_meaning",
        "0 : good_pixel; 1:conditionally_usable_pixel 2 : out_of_scan_area_pixel, "
        "3:error_pixel")
    for path in files:
        _change_attr(path, "mission_reference_time", "00000000_000000")
    result = read_la_slot(files, table, stride=250)
    assert result.metadata["planned_utc_time"] is None
    assert result.payload.valid_time_utc is None
    assert result.payload.bt.shape == (4, 9)


def test_la_payload_does_not_autopropagate_obt_as_utc_to_column_consumer(tmp_path):
    files, table, _ = _write_slot(tmp_path)
    result = read_la_slot(files, table, stride=250)
    grid_lat = result.payload.lat[:2].clone()
    grid_lon = result.payload.lon[:2].clone()
    columns = payload_to_column_obs(
        result.payload, grid_lat, grid_lon, max_dist_km=100.0)
    assert result.metadata["scene_acquisition_time_utc"] is None
    assert result.payload.valid_time_utc is None
    assert columns.valid_time_utc is None


def test_la_reader_rejects_source_mutation_between_header_and_pixel_pass(
        monkeypatch, tmp_path):
    files, table, _ = _write_slot(tmp_path)
    changed_file = files[0]
    original_geos = la_reader.geos_latlon
    calls = {"count": 0}

    def mutate_after_header(lines, cols, geo):
        calls["count"] += 1
        result = original_geos(lines, cols, geo)
        # Nine one-based header-corner checks precede the full raster call.
        if calls["count"] == 10:
            raw = bytearray(changed_file.read_bytes())
            raw[-1] ^= 1
            changed_file.write_bytes(raw)
        return result

    monkeypatch.setattr(la_reader, "geos_latlon", mutate_after_header)
    with pytest.raises(ValueError, match="source file changed before pixel decoding"):
        read_la_slot(files, table)


def test_la_reader_snapshots_calibration_table_before_header_pass(
        monkeypatch, tmp_path):
    files, table, raw = _write_slot(tmp_path)
    original_table = deepcopy(table)
    original_geos = la_reader.geos_latlon
    calls = {"count": 0}

    def mutate_caller_table_after_headers(lines, cols, geo):
        calls["count"] += 1
        result = original_geos(lines, cols, geo)
        # This is the full-raster geolocation call after nine header checks.
        if calls["count"] == 10:
            table["channels"]["wv063"]["bt_wavenumber_cm1"] += 10.0
        return result

    monkeypatch.setattr(la_reader, "geos_latlon",
                        mutate_caller_table_after_headers)
    result = read_la_slot(files, table, stride=1)
    reference = original_table["channels"]["wv063"]
    expected_bt, _ = dn_to_bt(raw["wv063"], reference, valid_bits=VALID_BITS["wv063"])
    assert table["channels"]["wv063"]["bt_wavenumber_cm1"] != reference["bt_wavenumber_cm1"]
    assert result.metadata["source_files"][0]["paired_bt_wavenumber_cm1"] == reference[
        "bt_wavenumber_cm1"]
    assert float(result.payload.bt[0, 0]) == float(expected_bt[0, 0])
