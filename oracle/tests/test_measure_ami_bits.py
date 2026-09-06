"""Independent AMI measurement expectations track the production QC boundary."""
from pathlib import Path

import numpy as np
import pytest

from kdm6.obs.gk2a_l1b import load_cal_table, read_ko_slot
from scripts.measure_ami_bits import (
    independent_bt, independent_radiance_ok, independent_words,
    sample_source, selection,
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
