"""AMI format witnesses use literal packed words independently of the decoder."""
from pathlib import Path

import numpy as np
import pytest
import torch

from kdm6.obs.gk2a_l1b import (
    AMI_CHANNELS, dn_to_bt, load_cal_table, read_ko_slot, unpack_ami_word,
)
from kdm6.obs.gk2a_l1b_fd import read_fd_slot
from kdm6.obs.obs_ingest import payload_to_column_obs
from kdm6.obs.obs_loss import compute_obs_loss
from kdm6.obs.rttov_obs_operator import _build_mask

CAL = load_cal_table(Path(__file__).resolve().parents[1] /
                     "kdm6/obs/data/gk2a_ami_cal_202507190000.json")["channels"]


def test_literal_dqf_words_preserve_all_four_quality_values():
    raw = np.array([0x0BB8, 0x4BB8, 0x8BB8, 0xCBB8], dtype=np.uint16)
    dn, quality = unpack_ami_word(raw, 13)
    np.testing.assert_array_equal(dn, [3000, 3000, 3000, 3000])
    np.testing.assert_array_equal(quality, [0, 1, 2, 3])
    bt, quality = dn_to_bt(raw, CAL["ir105"], valid_bits=13)
    assert np.isfinite(bt).all()
    np.testing.assert_array_equal(bt, np.repeat(bt[0], 4))
    assert quality[2] == 2  # A plausible BT never promotes DQF=2 to usable.


@pytest.mark.parametrize("dtype", ["<u2", ">u2"])
def test_word_byte_order_does_not_change_dn_or_quality(dtype):
    dn, q = unpack_ami_word(np.array([0x3E80, 0xBE80], dtype=dtype), 14)
    np.testing.assert_array_equal(dn, [16000, 16000])
    np.testing.assert_array_equal(q, [0, 2])


@pytest.mark.parametrize("bits,words,maximum", [
    (11, [0x07FF, 0x47FF, 0x87FF, 0xC7FF], 2047),
    (12, [0x0FFF, 0x4FFF, 0x8FFF, 0xCFFF], 4095),
    (13, [0x1FFF, 0x5FFF, 0x9FFF, 0xDFFF], 8191),
    (14, [0x3FFF, 0x7FFF, 0xBFFF, 0xFFFF], 16383),
])
def test_channel_width_maxima_do_not_overlap_dqf(bits, words, maximum):
    dn, quality = unpack_ami_word(np.array(words, dtype=np.uint16), np.uint8(bits))
    np.testing.assert_array_equal(dn, [maximum] * 4)
    np.testing.assert_array_equal(quality, [0, 1, 2, 3])


def test_sw038_14_bit_witness_and_unused_dn_bits():
    raw = np.array([0x3E80], dtype=np.uint16)
    dn, q = unpack_ami_word(raw, 14)
    assert dn[0] == 16000 and q[0] == 0
    bt, _ = dn_to_bt(raw, CAL["sw038"], valid_bits=14)
    assert bt[0] == pytest.approx(284.944, abs=0.001)
    dn12, q12 = unpack_ami_word(raw, 12)
    assert dn12[0] == 3712 and q12[0] == 0


@pytest.mark.parametrize("channel,bits,words", [
    ("ir105", 13, [0x1FFF, 0x5FFF, 0x9FFF, 0xDFFF]),
    ("sw038", 14, [0x3FFF, 0x7FFF, 0xBFFF, 0xFFFF]),
])
def test_negative_radiance_is_unusable_and_keeps_existing_dqf(channel, bits, words):
    bt, quality = dn_to_bt(np.array(words, dtype=np.uint16), CAL[channel], valid_bits=bits)
    np.testing.assert_array_equal(quality, [3, 1, 2, 3])
    np.testing.assert_array_equal(bt, np.zeros(4))  # Finite non-observation placeholder.


@pytest.mark.parametrize("offset,gain,words", [
    (0.0, 1.0, [0x0000, 0x4000, 0x8000, 0xC000]),  # Exact zero radiance.
    (0.0, 1e308, [0x0002, 0x4002, 0x8002, 0xC002]),  # Finite coefficients, overflow.
])
def test_zero_or_nonfinite_pixel_radiance_is_not_a_calibration_repair(offset, gain, words):
    cal = dict(CAL["ir105"], DN_to_Radiance_Offset=offset, DN_to_Radiance_Gain=gain)
    with np.errstate(all="raise"):
        bt, quality = dn_to_bt(np.array(words, dtype=np.uint16), cal, valid_bits=13)
    np.testing.assert_array_equal(quality, [3, 1, 2, 3])
    assert np.isfinite(bt).all()


@pytest.mark.parametrize("name,value", [
    ("DN_to_Radiance_Gain", np.nan), ("DN_to_Radiance_Offset", np.inf),
    ("Teff_to_Tbb_c0", -np.inf), ("Teff_to_Tbb_c1", None),
    ("Teff_to_Tbb_c2", [0.0]), ("channel_center_wavelength", 0.0),
    ("channel_center_wavelength", 1e-300), ("Plank_constant_h", -1.0),
    ("light_speed", True), ("Boltzmann_constant_k", 0.0),
])
def test_malformed_calibration_is_refused_separately_from_pixel_qc(name, value):
    with pytest.raises(ValueError, match="AMI calibration"):
        dn_to_bt(np.array([0x0BB8], dtype=np.uint16),
                 dict(CAL["ir105"], **{name: value}), valid_bits=13)


def test_nonfinite_temperature_from_calibration_is_refused():
    with pytest.raises(ValueError, match="calibration.*non-finite brightness temperature"):
        dn_to_bt(np.array([0x0BB8], dtype=np.uint16),
                 dict(CAL["ir105"], Teff_to_Tbb_c2=1e308), valid_bits=13)


@pytest.mark.parametrize("bits", [None, 10, 15, 16, 13.0, "13", True, np.bool_(True)])
def test_invalid_valid_bit_metadata_is_not_guessed(bits):
    with pytest.raises(ValueError, match="bit count"):
        unpack_ami_word(np.array([3000], dtype=np.uint16), bits)


@pytest.mark.parametrize("dtype", [np.int16, np.int64, np.uint32, np.float64])
def test_raw_word_dtype_cannot_be_silently_cast(dtype):
    with pytest.raises(ValueError, match="uint16"):
        unpack_ami_word(np.array([3000], dtype=dtype), 13)


def test_mask_requires_explicit_netcdf_handling():
    with pytest.raises(ValueError, match="mask"):
        unpack_ami_word(np.ma.array([3000], dtype=np.uint16, mask=[True]), 13)


def _slot(tmp_path, product, *, bits=14, masked=False, endian="little"):
    nc4 = pytest.importorskip("netCDF4")
    path = tmp_path / f"gk2a_ami_le1b_sw038_{product}_202507190000.nc"
    with nc4.Dataset(path, "w") as ds:
        ds.createDimension("dim_image_y", 2)
        ds.createDimension("dim_image_x", 2)
        dtype = np.dtype("<u2" if endian == "little" else ">u2")
        var = ds.createVariable("image_pixel_values", dtype,
                                ("dim_image_y", "dim_image_x"), fill_value=65535,
                                endian=endian)
        if bits is not None:
            var.number_of_valid_bits_per_pixel = bits
        var[:] = np.ma.array([[0x3E80, 0x7E80], [0xBE80, 0xFE80]],
                              dtype=np.uint16, mask=[[masked, False], [False, False]])
        attrs = dict(standard_parallel1=30., standard_parallel2=60.,
                     origin_latitude=38., central_meridian=126., pixel_size=2000.,
                     upper_left_easting=0., upper_left_northing=0.,
                     image_width=2, image_height=2,
                     coff=0.5, loff=0.5, cfac=20425338.903339352,
                     lfac=-20425338.903339352, sub_longitude=2.2375121010567303,
                     nominal_satellite_height=42164000.,
                     earth_equatorial_radius=6378137., earth_polar_radius=6356752.3)
        for name, value in attrs.items():
            ds.setncattr(name, value)
        for name, value in CAL["sw038"].items():
            if value is not None:
                ds.setncattr(name, value)
        # A misleading global attribute/cal-table entry must not replace the
        # image variable's authoritative word width.
        ds.setncattr("number_of_valid_bits_per_pixel", 13)
    return path


def _read(path, product):
    if product == "ko020lc":
        cal = {"channels": {"sw038": dict(CAL["sw038"], number_of_valid_bits_per_pixel=13)}}
        return read_ko_slot([path], cal, stride=1)
    return read_fd_slot([path], bbox=(-90., 90., -180., 180.), stride=1)


@pytest.mark.parametrize("product", ["ko020lc", "fd020ge"])
@pytest.mark.parametrize("masked", [False, True])
@pytest.mark.parametrize("endian", ["little", "big"])
def test_netcdf_variable_width_dqf_and_mask_reach_payload(tmp_path, product, masked, endian):
    payload = _read(_slot(tmp_path, product, bits=np.uint8(14), masked=masked,
                          endian=endian), product)
    j = AMI_CHANNELS.index("sw038")
    np.testing.assert_array_equal(payload.obs_quality[:, j], [int(masked), 1, 2, 3])
    assert float(payload.bt[-1, j]) == pytest.approx(284.944, abs=0.001)
    if not masked:
        np.testing.assert_allclose(payload.bt[:, j], 284.944, atol=.001, rtol=0)


@pytest.mark.parametrize("product", ["ko020lc", "fd020ge"])
def test_netcdf_invalid_radiance_cannot_reach_observation_loss(tmp_path, product):
    nc4 = pytest.importorskip("netCDF4")
    path = _slot(tmp_path, product)
    with nc4.Dataset(path, "a") as ds:
        # Invalid Q0, invalid Q2, valid but NetCDF-masked, genuinely valid Q0.
        ds["image_pixel_values"][:] = np.ma.array(
            [[0x3FFF, 0xBFFF], [0x3E80, 0x3E80]], dtype=np.uint16,
            mask=[[False, False], [True, False]])
    payload = _read(path, product)
    j = AMI_CHANNELS.index("sw038")
    np.testing.assert_array_equal(payload.obs_quality[:, j], [3, 2, 1, 0])
    columns = payload_to_column_obs(payload, payload.lat, payload.lon, max_dist_km=0.0)
    assert columns.n_assigned == 4
    obs = {"bt": columns.bt[:, j:j+1], "obs_quality": columns.obs_quality[:, j:j+1]}
    mask = _build_mask(obs, torch.zeros_like(obs["bt"]))
    torch.testing.assert_close(mask[:, 0], torch.tensor([0., 0., 0., 1.], dtype=torch.float64))
    predicted = torch.full_like(obs["bt"], 290., requires_grad=True)
    loss = compute_obs_loss(predicted, obs, mask, 2.)
    grad, = torch.autograd.grad(loss, predicted)
    torch.testing.assert_close(grad[:, 0], torch.tensor([0., 0., 0., 0.5], dtype=torch.float64))
    assert loss.item() > 0.0  # The usable neighbour remains in the loss.


@pytest.mark.parametrize("product", ["ko020lc", "fd020ge"])
def test_missing_variable_width_is_refused_even_with_global_fallback(tmp_path, product):
    with pytest.raises(ValueError, match="missing number_of_valid_bits_per_pixel"):
        _read(_slot(tmp_path, product, bits=None), product)


@pytest.mark.parametrize("product", ["ko020lc", "fd020ge"])
def test_empty_or_duplicate_channel_slots_fail_before_opening(tmp_path, product):
    reader = (lambda files: read_ko_slot(files, {"channels": CAL})) if product == "ko020lc" else read_fd_slot
    with pytest.raises(ValueError, match="at least one"):
        reader([])
    path = tmp_path / f"gk2a_ami_le1b_sw038_{product}_202507190000.nc"
    with pytest.raises(ValueError, match="duplicate AMI channel"):
        reader([path, path])


@pytest.mark.parametrize("product", ["ko020lc", "fd020ge"])
@pytest.mark.parametrize("stride", [0, -1, 1.5, True])
def test_invalid_stride_is_rejected_before_file_access(product, stride):
    reader = (lambda files: read_ko_slot(files, {"channels": CAL}, stride=stride)) if product == "ko020lc" else (lambda files: read_fd_slot(files, stride=stride))
    with pytest.raises(ValueError, match="stride"):
        reader([])


@pytest.mark.parametrize("product", ["ko020lc", "fd020ge"])
def test_same_shape_channels_must_share_geolocation(tmp_path, product):
    import shutil
    nc4 = pytest.importorskip("netCDF4")
    first = _slot(tmp_path, product)
    second = first.with_name(first.name.replace("sw038", "ir105"))
    shutil.copyfile(first, second)
    with nc4.Dataset(second, "a") as ds:
        key = "central_meridian" if product == "ko020lc" else "sub_longitude"
        ds.setncattr(key, float(ds.getncattr(key)) + 0.01)
    with pytest.raises(ValueError, match="channel geometry"):
        if product == "ko020lc":
            read_ko_slot([first, second], {"channels": CAL}, stride=1)
        else:
            read_fd_slot([first, second], bbox=(-90., 90., -180., 180.), stride=1)


@pytest.mark.parametrize("product", ["ko020lc", "fd020ge"])
def test_resolver_rejects_ambiguous_channel_files(tmp_path, product):
    from kdm6.obs.gk2a_l1b import slot_files
    from kdm6.obs.gk2a_l1b_fd import fd_slot_files
    for folder in (tmp_path / "a", tmp_path / "b"):
        folder.mkdir()
        (folder / f"gk2a_ami_le1b_sw038_{product}_202507190000.nc").touch()
    resolver = slot_files if product == "ko020lc" else fd_slot_files
    with pytest.raises(ValueError, match="ambiguous AMI channel"):
        resolver(tmp_path, "202507190000", channels=["sw038"])
