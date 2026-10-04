"""Independent AMI measurement expectations track the production QC boundary."""
from pathlib import Path

import numpy as np
import pytest

from kdm6.obs.gk2a_l1b import load_cal_table, read_ko_slot
from kdm6.obs.gk2a_l1b_fd import geos_latlon, read_fd_slot
from scripts.measure_ami_bits import (
    independent_bt, independent_radiance_ok, independent_words,
    resolve_fd_calibration, sample_source, selection,
)


_CAL = load_cal_table(Path(__file__).resolve().parents[1] /
                      "kdm6/obs/data/gk2a_ami_cal_202507190000.json")


def _ko_fixture(tmp_path):
    nc4 = pytest.importorskip("netCDF4")
    path = tmp_path / "gk2a_ami_le1b_ir105_ko020lc_202507190000.nc"
    with nc4.Dataset(path, "w") as ds:
        ds.createDimension("dim_image_y", 2)
        ds.createDimension("dim_image_x", 2)
        var = ds.createVariable("image_pixel_values", "u2",
                                ("dim_image_y", "dim_image_x"), fill_value=65535)
        var.number_of_valid_bits_per_pixel = 13
        # One Q0 word has nonpositive calibrated radiance; three Q0 words are valid.
        var[:] = np.array([[0x1FFF, 0x0BB8],
                           [0x0BB8, 0x0BB8]], dtype=np.uint16)
        attrs = {
            "standard_parallel1": 30.0,
            "standard_parallel2": 60.0,
            "origin_latitude": 38.0,
            "central_meridian": 126.0,
            "pixel_size": 2000.0,
            "upper_left_easting": 0.0,
            "upper_left_northing": 0.0,
            "image_width": 2,
            "image_height": 2,
        }
        for name, value in attrs.items():
            ds.setncattr(name, value)
    return path


def _fd_fixture(tmp_path, *, explicit_wavenumber, c0_delta=0.0):
    nc4 = pytest.importorskip("netCDF4")
    path = tmp_path / "gk2a_ami_le1b_ir105_fd020ge_202507190100.nc"
    cal = dict(_CAL["channels"]["ir105"])
    cal["Teff_to_Tbb_c0"] += c0_delta
    geo = {
        "coff": 0.5, "loff": 0.5, "cfac": 20425338.903339352,
        "lfac": -20425338.903339352, "sub_longitude": 2.2375121010567303,
        "nominal_satellite_height": 42164000.0, "earth_equatorial_radius": 6378137.0,
        "earth_polar_radius": 6356752.3,
    }
    with nc4.Dataset(path, "w") as ds:
        ds.createDimension("dim_image_y", 2)
        ds.createDimension("dim_image_x", 2)
        var = ds.createVariable("image_pixel_values", "u2",
                                ("dim_image_y", "dim_image_x"))
        var.number_of_valid_bits_per_pixel = np.uint8(13)
        var[:] = np.array([[3909, 0x4000 | 3909],
                           [0x8000 | 3909, 0xC000 | 3909]], dtype=np.uint16)
        for name, value in geo.items():
            ds.setncattr(name, value)
        for name in ("DN_to_Radiance_Gain", "DN_to_Radiance_Offset",
                     "Teff_to_Tbb_c0", "Teff_to_Tbb_c1", "Teff_to_Tbb_c2",
                     "Plank_constant_h", "light_speed", "Boltzmann_constant_k",
                     "channel_center_wavelength"):
            ds.setncattr(name, cal[name])
        if explicit_wavenumber:
            ds.setncattr("bt_wavenumber_cm1", 1000.0)
    return path, geo


def _sample_fd(path, geo, reference):
    payload = read_fd_slot([path], bbox=(-90.0, 90.0, -180.0, 180.0), stride=1)
    rows = np.arange(2, dtype=np.int64)
    lines, columns = np.meshgrid(rows.astype(float), rows.astype(float), indexing="ij")
    lat, lon = geos_latlon(lines, columns, geo)
    selection_doc = {"rows": rows, "cols": rows,
                     "keep": np.ones(4, dtype=bool),
                     "coordinates": (lat.reshape(-1), lon.reshape(-1)),
                     "domain": {"kind": "minimal synthetic 2x2 FD"}}
    return sample_source("FD", [path], "202507190100",
                         {"channels": {"ir105": reference}}, payload,
                         selection_doc, chunk_rows=1)


def test_historical_counterfactual_keeps_clipped_invalid_bt_separate():
    raw = np.array([0x1FFF], dtype=np.uint16)
    dn_old, q_old, dn_new, q_new = independent_words(
        raw, 13, np.zeros(1, dtype=bool))
    cal = _CAL["channels"]["ir105"]
    assert q_old.tolist() == [0.0]  # old >> 13 classified this word as usable
    assert independent_radiance_ok(dn_new, cal).tolist() == [False]
    assert independent_bt(dn_old, cal, historical=True).tolist() == [
        pytest.approx(20.381922391051123)]
    assert independent_bt(dn_new, cal).tolist() == [0.0]


def test_sample_source_independent_expectation_includes_radiance_qc(tmp_path):
    path = _ko_fixture(tmp_path)
    files = [path]
    payload = read_ko_slot(files, _CAL, stride=1)
    observed, _ = sample_source(
        "KO", files, "202507190000", _CAL, payload,
        selection("KO", files, 1), chunk_rows=1)
    row = observed["channels"]["ir105"]

    assert row["old_usable_finite"] == 4
    assert row["correct_usable_finite"] == 3
    check = row["production_vs_independent_correct"]
    assert check["q_exact"] is True
    assert check["bt_exact_count"] == 4
    assert check["bt_max_abs_error_K"] == 0.0
    assert check["bt_max_ulp"] == 0


def test_sample_source_keeps_embedded_dqf_and_netcdf_mask(tmp_path):
    nc4 = pytest.importorskip("netCDF4")
    path = _ko_fixture(tmp_path)
    with nc4.Dataset(path, "a") as ds:
        ds["image_pixel_values"][:] = np.ma.array(
            [[0x1FFF, 0x9FFF], [0x0BB8, 0x0BB8]], dtype=np.uint16,
            mask=[[False, False], [True, False]])
    files = [path]
    payload = read_ko_slot(files, _CAL, stride=1)
    observed, _ = sample_source(
        "KO", files, "202507190000", _CAL, payload,
        selection("KO", files, 1), chunk_rows=1)
    row = observed["channels"]["ir105"]
    assert row["correct_dqf_counts_finite"] == [1, 1, 1, 1]
    assert row["correct_usable_finite"] == 1
    assert row["production_vs_independent_correct"]["q_exact"] is True
    assert row["production_vs_independent_correct"]["bt_exact_count"] == 4


@pytest.mark.parametrize("c0_delta", [0.0, 0.1])
def test_fd_sample_uses_explicit_file_calibration_and_wavenumber(tmp_path, c0_delta):
    path, geo = _fd_fixture(tmp_path, explicit_wavenumber=True, c0_delta=c0_delta)
    reference = dict(_CAL["channels"]["ir105"])
    saved_reference = dict(reference)
    observed, file_records = _sample_fd(path, geo, reference)
    row = observed["channels"]["ir105"]
    assert file_records[0]["bt_wavenumber_source"] == "explicit_file_attribute"
    assert file_records[0]["effective_wavenumber_cm1"] == 1000.0
    assert file_records[0]["embedded_calibration_matches_external"] is False
    assert row["production_vs_independent_correct"]["q_exact"] is True
    assert row["production_vs_independent_correct"]["bt_exact_count"] == 4
    assert row["production_vs_independent_correct"]["bt_max_abs_error_K"] == 0.0
    assert row["correct_dqf_counts_finite"] == [1, 1, 1, 1]
    assert reference == saved_reference


@pytest.mark.parametrize("reference_wavenumber_delta", [0.0, 0.01])
def test_fd_sample_binds_missing_wavenumber_to_published_tuple(tmp_path, reference_wavenumber_delta):
    path, geo = _fd_fixture(tmp_path, explicit_wavenumber=False)
    reference = dict(_CAL["channels"]["ir105"])
    reference["bt_wavenumber_cm1"] += reference_wavenumber_delta
    saved_reference = dict(reference)
    observed, file_records = _sample_fd(path, geo, reference)
    row = observed["channels"]["ir105"]
    assert file_records[0]["bt_wavenumber_source"] == "audited_published_package_tuple_fallback"
    assert file_records[0]["effective_wavenumber_cm1"] == _CAL["channels"]["ir105"]["bt_wavenumber_cm1"]
    assert file_records[0]["embedded_calibration_matches_external"] is (reference_wavenumber_delta == 0.0)
    assert row["production_vs_independent_correct"]["q_exact"] is True
    assert row["production_vs_independent_correct"]["bt_exact_count"] == 4
    assert row["production_vs_independent_correct"]["bt_max_abs_error_K"] == 0.0
    assert row["correct_dqf_counts_finite"] == [1, 1, 1, 1]
    assert reference == saved_reference


def test_fd_independent_fallback_refuses_an_unknown_tuple(tmp_path):
    path, _ = _fd_fixture(tmp_path, explicit_wavenumber=False, c0_delta=0.1)
    with pytest.raises(ValueError, match="does not exactly match the independent published package tuple"):
        resolve_fd_calibration(path, "ir105")
