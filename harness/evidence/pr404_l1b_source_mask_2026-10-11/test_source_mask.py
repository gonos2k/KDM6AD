"""Actual netCDF4 regressions for raw/source-missing/padding/DQF separation."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import netCDF4
import numpy as np
import pytest

SCRIPT = Path(__file__).with_name("heldout_l1b_v2.py")
spec = importlib.util.spec_from_file_location("heldout_l1b_v2", SCRIPT)
writer = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(writer)


def write_image(path, words, *, missing=None, dtype="u2", scaled=False):
    with netCDF4.Dataset(path, "w") as ds:
        ds.createDimension("y", words.shape[0])
        ds.createDimension("x", words.shape[1])
        fill = np.uint16(65535) if dtype == "u2" else None
        var = ds.createVariable("image_pixel_values", dtype, ("y", "x"), fill_value=fill)
        var.setncattr("number_of_valid_bits_per_pixel", 13)
        if missing is not None:
            var.setncattr("missing_value", np.asarray(missing, dtype=np.uint16))
        if scaled:
            var.setncattr("scale_factor", 2.0)
            var.setncattr("add_offset", 10.0)
        var.set_auto_maskandscale(False)
        var[:] = words


@pytest.mark.parametrize("missing,expected", [
    (None, [[True, False, False, False, False]]),
    (444, [[True, False, False, True, False]]),
    ([444, 445], [[True, False, False, True, True]]),
])
def test_fill_and_missing_values_preserve_original_words(tmp_path, missing, expected):
    words = np.array([[65535, 0, 49155, 444, 445]], dtype=np.uint16)
    path = tmp_path / "raw.nc"
    write_image(path, words, missing=missing)
    with netCDF4.Dataset(path) as ds:
        var = ds.variables["image_pixel_values"]
        var.set_auto_maskandscale(False)
        # Reproduce the original sidecar defect using the actual library.
        assert not np.ma.getmaskarray(var[:]).any()
        raw, mask = writer.read_packed_source_patch(var, Ellipsis)
        np.testing.assert_array_equal(raw, words)
        assert raw.dtype == np.uint16
        assert mask.tolist() == expected
        np.testing.assert_array_equal(var[:], words)


def test_scale_disabled_for_both_raw_and_mask_reads(tmp_path):
    words = np.array([[65535, 444, 123]], dtype=np.uint16)
    path = tmp_path / "scaled.nc"
    write_image(path, words, missing=444, scaled=True)
    with netCDF4.Dataset(path) as ds:
        raw, mask = writer.read_packed_source_patch(ds.variables["image_pixel_values"], Ellipsis)
    np.testing.assert_array_equal(raw, words)
    assert mask.tolist() == [[True, True, False]]


def test_source_mask_includes_declared_validity_range(tmp_path):
    words = np.array([[0, 12, 65535, 444]], dtype=np.uint16)
    path = tmp_path / "range.nc"
    write_image(path, words)
    with netCDF4.Dataset(path, "a") as ds:
        ds.variables["image_pixel_values"].setncattr("valid_range", np.array([10, 200], dtype=np.uint16))
    with netCDF4.Dataset(path) as ds:
        raw, mask = writer.read_packed_source_patch(ds.variables["image_pixel_values"], Ellipsis)
    np.testing.assert_array_equal(raw, words)
    assert mask.tolist() == [[True, False, True, True]]


def test_source_missing_is_separate_from_dqf_and_production_quality(tmp_path):
    words = np.array([[0, 49155, 444]], dtype=np.uint16)
    path = tmp_path / "quality.nc"
    write_image(path, words, missing=444)
    from kdm6.obs.gk2a_l1b import _read_ami_bt

    with netCDF4.Dataset(path) as ds:
        var = ds.variables["image_pixel_values"]
        raw, missing = writer.read_packed_source_patch(var, Ellipsis)
        dn, dqf = writer.unpack_ami_word(raw, 13)
        assert missing.tolist() == [[False, False, True]]
        assert dqf.tolist() == [[0, 3, 0]]
        assert dn.tolist() == [[0, 3, 444]]
        var.set_auto_mask(True)
        _, quality = _read_ami_bt(var, writer.load_cal_table(writer.CALIBRATION)["channels"]["ir105"])
        assert quality.tolist() == [[0, 3, 1]]


def test_edge_padding_is_not_a_source_missing_value(tmp_path):
    words = np.array([[0, 65535], [49155, 444]], dtype=np.uint16)
    path = tmp_path / "edge.nc"
    write_image(path, words, missing=444)
    with netCDF4.Dataset(path) as ds:
        var = ds.variables["image_pixel_values"]
        raw, missing, padding = writer.source_patch_canvas(var, 0, 0)
        np.testing.assert_array_equal(raw[2:4, 2:4], words)
        assert padding.sum() == 21
        assert missing.sum() == 2
        assert not (missing & padding).any()
        assert raw[2, 2] == 0 and not missing[2, 2] and not padding[2, 2]
        assert raw[3, 2] == 49155 and not missing[3, 2] and not padding[3, 2]
        with pytest.raises(ValueError, match="outside source"):
            writer.source_patch_canvas(var, -1, 0)


@pytest.mark.parametrize("dtype", ["i2", "f4"])
def test_non_uint16_source_is_not_silently_coerced(tmp_path, dtype):
    path = tmp_path / "wrong.nc"
    write_image(path, np.array([[123]]), dtype=dtype)
    with netCDF4.Dataset(path) as ds:
        with pytest.raises(ValueError, match="must be uint16"):
            writer.read_packed_source_patch(ds.variables["image_pixel_values"], Ellipsis)
