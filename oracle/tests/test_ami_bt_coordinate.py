"""Focused tests for the opt-in RTTOV-to-KMA BT/Jacobian conversion."""
from __future__ import annotations

import numpy as np
import pytest

from kdm6.obs.ami_bt_coordinate import (
    RTTOV_C1, RTTOV_C2, read_ami_filters, read_kma_calibration,
    transform_rttov_to_kma,
)


def _coef_file(path, *, instrument="gkompsat2-1   ami-vis"):
    rows = []
    vals = {
        8: (16176.09243, 1.672269316, .9964435886),
        13: (966.1533839, .1026489494, .9996594440),
        16: (752.7924878, .05177704020, .9997799864),
    }
    for channel in range(1, 17):
        nu, offset, slope = vals.get(channel, (20000.0-channel, 0.0, 1.0))
        rows.append(f"{channel} 1 {nu:.10g} {offset:.10g} {slope:.10g} 1.0")
    path.write_text(
        "IDENTIFICATION\n48 1 93 ! Platform sat_id instrument\n"
        f"{instrument}\nir\n13\nLINE-BY-LINE\nFILTER_FUNCTIONS\n"
        + "\n".join(rows) + "\nEND\n")
    return path


def _native_bt(radiance, filt):
    nu = filt["wavenumber_cm1"]
    return (RTTOV_C2 * nu / np.log(RTTOV_C1 * nu ** 3 / radiance + 1.0)
            - filt["offset_K"]) / filt["slope"]


def _kma_bt(radiance, cal):
    sigma = cal["bt_wavenumber_cm1"] * 100.0
    x = radiance * 1.0e-3 / 100.0
    a = cal["Plank_constant_h"] * cal["light_speed"] * sigma / cal["Boltzmann_constant_k"]
    b = 2.0 * cal["Plank_constant_h"] * cal["light_speed"]**2 * sigma**3
    teff = a / np.log(b / x + 1.0)
    return (cal["Teff_to_Tbb_c0"] + cal["Teff_to_Tbb_c1"] * teff
            + cal["Teff_to_Tbb_c2"] * teff**2)


def test_filter_reader_requires_the_consumed_gkompsat2_ami_identity(tmp_path):
    path = _coef_file(tmp_path / "coef.dat")
    filters = read_ami_filters(path)
    assert filters[13]["wavenumber_cm1"] == 966.1533839
    assert filters[13]["offset_K"] == .1026489494
    assert filters[13]["slope"] == .9996594440
    wrong = _coef_file(tmp_path / "wrong.dat", instrument="other-satellite other-sensor")
    with pytest.raises(ValueError, match="not RTTOV GKOMPSAT-2 AMI IR"):
        read_ami_filters(wrong)


def test_transform_maps_bt_and_every_k_field_and_preserves_vjp_duality(tmp_path):
    filters = read_ami_filters(_coef_file(tmp_path / "coef.dat"))
    calibration = read_kma_calibration()
    channels = (8, 13, 16)
    radiance = np.array([[50.0, 92.5, 113.0], [51.0, 92.8, 112.0]])
    bt_native = np.column_stack([
        _native_bt(radiance[:, j], filters[ch]) for j, ch in enumerate(channels)])
    k = {"T": np.arange(12, dtype=np.float64).reshape(2, 3, 2) + 1.0,
         "HYDRO6": np.arange(18, dtype=np.float64).reshape(2, 3, 3) - 2.0}
    bt_before, rad_before = bt_native.copy(), radiance.copy()
    k_before = {name: value.copy() for name, value in k.items()}

    bt_kma, k_kma, ratio = transform_rttov_to_kma(
        bt_native, radiance, k, channels, filters, calibration)

    expected_bt = np.column_stack([
        _kma_bt(radiance[:, j], calibration[{
            8: "wv063", 13: "ir105", 16: "ir133"}[ch]])
        for j, ch in enumerate(channels)])
    np.testing.assert_allclose(bt_kma, expected_bt, rtol=0.0, atol=1e-12)
    assert ratio.shape == bt_native.shape and np.isfinite(ratio).all()
    for name in k:
        np.testing.assert_allclose(k_kma[name], k_before[name] * ratio[:, :, None],
                                   rtol=0.0, atol=0.0)

    lam = np.array([[.3, -.8, 1.1], [-.4, .2, .7]])
    native_vjp = np.einsum("pcl,pc->pl", k_before["T"], lam * ratio)
    kma_vjp = np.einsum("pcl,pc->pl", k_kma["T"], lam)
    np.testing.assert_allclose(kma_vjp, native_vjp, rtol=0.0, atol=1e-14)
    np.testing.assert_array_equal(bt_native, bt_before)
    np.testing.assert_array_equal(radiance, rad_before)
    for name in k:
        np.testing.assert_array_equal(k[name], k_before[name])

    # Compare the ratio chain rule with independent plus/minus radiance values.
    ch = 13
    radiance = 92.5
    filt, cal = filters[ch], calibration["ir105"]
    eps = 1.0e-3
    native_fd = (_native_bt(radiance + eps, filt) - _native_bt(radiance - eps, filt)) / (2 * eps)
    kma_fd = (_kma_bt(radiance + eps, cal) - _kma_bt(radiance - eps, cal)) / (2 * eps)
    assert kma_fd == pytest.approx(ratio[0, 1] * native_fd, rel=1e-9, abs=1e-12)


@pytest.mark.parametrize("bad", [0.0, -1.0, np.nan, np.inf])
def test_transform_rejects_invalid_total_radiance(tmp_path, bad):
    filters = read_ami_filters(_coef_file(tmp_path / "coef.dat"))
    calibration = read_kma_calibration()
    channels = (13,)
    radiance = np.array([[92.5]])
    bt_native = np.array([[_native_bt(92.5, filters[13])]])
    radiance[0, 0] = bad
    with pytest.raises(ValueError, match="positive finite total radiance"):
        transform_rttov_to_kma(bt_native, radiance, {"T": np.ones((1, 1, 2))},
                               channels, filters, calibration)


def test_transform_rejects_a_mismatched_native_bt_and_unsupported_channel(tmp_path):
    filters = read_ami_filters(_coef_file(tmp_path / "coef.dat"))
    calibration = read_kma_calibration()
    rad = np.array([[92.5]])
    bt = np.array([[_native_bt(92.5, filters[13]) + 1.0e-4]])
    with pytest.raises(ValueError, match="BT replay exceeds"):
        transform_rttov_to_kma(bt, rad, {"T": np.ones((1, 1, 2))},
                               (13,), filters, calibration)
    with pytest.raises(ValueError, match="only thermal AMI channels 8..16"):
        transform_rttov_to_kma(np.zeros((1, 1)), rad, {"T": np.ones((1, 1, 2))},
                               (7,), filters, calibration)
