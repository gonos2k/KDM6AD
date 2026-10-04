"""Focused wiring tests for the opt-in live RTTOV-to-KMA BT factory path."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from kdm6.obs import ami_bt_coordinate as btcoord
from kdm6.obs import rttov_case_writer as case_writer
from kdm6.obs.rttov_runner import RttovKOutput


CHANNELS = (13, 8, 16)  # Deliberately not ascending AMI/RTTOV order.
TOTAL = np.array([[92.5, 50.0, 113.0], [92.8, 51.0, 112.0]], dtype=np.float64)


def _filters_text(path: Path) -> Path:
    values = {
        8: (1617.609243, 1.672269316, 0.9964435886),
        13: (966.1533839, 0.1026489494, 0.9996594440),
        16: (752.7924878, 0.0517770402, 0.9997799864),
    }
    rows = []
    for channel in range(1, 17):
        nu, offset, slope = values.get(channel, (20000.0 - channel, 0.0, 1.0))
        rows.append(f"{channel} 1 {nu:.10g} {offset:.10g} {slope:.10g} 1.0")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "IDENTIFICATION\n48 1 93 ! Platform satellite instrument\n"
        "gkompsat2-1 ami-vis\nir\n13\nLINE-BY-LINE\nFILTER_FUNCTIONS\n"
        + "\n".join(rows) + "\nEND\n")
    return path


def _native_bt(radiance: np.ndarray, filt: dict) -> np.ndarray:
    nu = filt["wavenumber_cm1"]
    planck = btcoord.RTTOV_C2 * nu / np.log(
        btcoord.RTTOV_C1 * nu ** 3 / radiance + 1.0)
    return (planck - filt["offset_K"]) / filt["slope"]


def _write_fake_case(root: Path, channels, total: np.ndarray, bt: np.ndarray,
                     quality: np.ndarray) -> tuple[Path, Path]:
    case_out = root / "out"
    (case_out / "k").mkdir(parents=True)
    (case_out / "direct").mkdir()
    (root / "in").mkdir()
    (case_out / "run.sh").write_text("#!/bin/sh\nexit 0\n")
    # coef_id in RttovInput is intentionally unrelated; the fixture namelist wins.
    (case_out / "rttov_test.txt").write_text("defn%coef_prefix = 'coeffs'\n")
    (root / "in" / "coef.txt").write_text("defn%f_coef = 'ami.dat'\n")
    coef_path = _filters_text(case_out / "coeffs" / "ami.dat")
    def block(name: str, values: np.ndarray) -> str:
        flat = " ".join(f"{float(v):.17g}" for v in values.reshape(-1))
        return f"RADIANCE%{name} = (\n{flat}\n)\n"
    (case_out / "k" / "radiance.txt").write_text(
        block("TOTAL", total) + block("BT", bt) + block("QUALITY", quality))
    # A conflicting direct-run radiance ensures the opt-in reads the same K-run file.
    (case_out / "direct" / "radiance.txt").write_text(block("TOTAL", np.ones_like(total)))
    return case_out, coef_path


def _k_fields(nchannels: int) -> dict[str, np.ndarray]:
    return {
        "T": np.arange(2 * nchannels * 2, dtype=np.float64).reshape(2, nchannels, 2) + 1.0,
        "Q": np.arange(2 * nchannels * 3, dtype=np.float64).reshape(2, nchannels, 3) + 2.0,
        "P_HALF": np.arange(2 * nchannels * 4, dtype=np.float64).reshape(2, nchannels, 4) + 3.0,
        "HYDRO": np.arange(2 * nchannels * 8 * 2, dtype=np.float64).reshape(2, nchannels, 16) + 4.0,
        "HYDRO_DEFF": np.arange(2 * nchannels * 7 * 2, dtype=np.float64).reshape(2, nchannels, 14) + 5.0,
    }


def _mock_factory_run(monkeypatch, tmp_path, *, channels=CHANNELS, total=TOTAL,
                      quality=None, refl=None):
    filters_path = tmp_path / "consumed_coef_file.txt"
    filters = btcoord.read_ami_filters(_filters_text(filters_path))
    native_bt = np.zeros_like(total, dtype=np.float64)
    for j, channel in enumerate(channels):
        usable = np.isfinite(total[:, j]) & (total[:, j] > 0.0)
        native_bt[usable, j] = _native_bt(total[usable, j], filters[channel])
    if quality is None:
        quality = np.zeros_like(total)
    k = _k_fields(len(channels))
    output = RttovKOutput(native_bt, quality, k, 2, len(channels), refl=refl)
    root = tmp_path / "case"
    captured = {"written": 0, "ran": 0, "filter_path": None, "calibration_reads": 0}

    def write_case(rttov_input, out_case_dir, **kwargs):
        captured["written"] += 1
        case_out, consumed_path = _write_fake_case(root, channels, total, native_bt, quality)
        captured["filter_path"] = consumed_path
        return case_out

    def run_case(script, **kwargs):
        captured["ran"] += 1
        return output

    original_filters = btcoord.read_ami_filters

    def read_filters(path):
        captured["filter_path"] = Path(path).resolve()
        return original_filters(path)

    original_calibration = btcoord.read_kma_calibration

    def read_calibration():
        captured["calibration_reads"] += 1
        return original_calibration()

    monkeypatch.setattr(case_writer, "write_rttov_case", write_case)
    monkeypatch.setattr(case_writer, "_run_rttov_k_unlocked", run_case)
    monkeypatch.setattr(btcoord, "read_ami_filters", read_filters)
    monkeypatch.setattr(btcoord, "read_kma_calibration", read_calibration)
    cfg = SimpleNamespace(channels=tuple(channels), coef_id="not-the-consumed-coef-path")
    rttov_input = SimpleNamespace(config=cfg, nprofiles=2)
    return root, rttov_input, output, captured


def test_optin_uses_locked_case_total_consumed_coeff_and_scales_every_k_row(
        monkeypatch, tmp_path):
    root, rttov_input, native, captured = _mock_factory_run(monkeypatch, tmp_path)
    k_before = {name: value.copy() for name, value in native.k.items()}
    filters = btcoord.read_ami_filters(_filters_text(tmp_path / "expected_coef.dat"))
    calibration = btcoord.read_kma_calibration()
    expected_input_k = {name: value.copy() for name, value in k_before.items()}
    case_writer.add_cloud_k_slots(expected_input_k, nlay=2)
    expected_bt, expected_k, expected_ratio = btcoord.transform_rttov_to_kma(
        native.bt, TOTAL, expected_input_k, CHANNELS, filters, calibration)

    captured["calibration_reads"] = 0  # Count only the factory snapshot.
    run_k = case_writer.make_live_run_k(root, ami_kma_bt=True)
    observable, kma_k, quality = run_k(rttov_input)

    np.testing.assert_allclose(observable, expected_bt, rtol=0.0, atol=0.0)
    np.testing.assert_array_equal(quality, native.rad_quality)
    assert set(kma_k) == set(k_before) | {"HYDRO6", "HYDRO7", "HYDRO_DEFF6", "HYDRO_DEFF7"}
    for name, expected in expected_k.items():
        np.testing.assert_array_equal(kma_k[name], expected)
    for name, original in k_before.items():
        np.testing.assert_array_equal(native.k[name], original)
    assert expected_ratio.shape == native.bt.shape
    assert captured["written"] == captured["ran"] == 1
    assert captured["calibration_reads"] == 1  # factory snapshot; no per-call reload
    assert captured["filter_path"] == (root / "out" / "coeffs" / "ami.dat").resolve()
    assert "not-the-consumed-coef-path" not in str(captured["filter_path"])


def test_native_default_and_solar_path_are_unchanged(monkeypatch, tmp_path):
    root, rttov_input, native, captured = _mock_factory_run(monkeypatch, tmp_path,
                                                            channels=(1,),
                                                            total=np.array([[50.0], [51.0]]),
                                                            refl=np.full((2, 1), 0.25))
    native.bt[:] = 0.0
    run_k = case_writer.make_live_run_k(root, solar_channels=(1,))
    observable, k, quality = run_k(rttov_input)
    np.testing.assert_array_equal(observable, native.refl)
    assert k is native.k
    assert quality is native.rad_quality
    assert captured["calibration_reads"] == 0


def test_optin_rejects_solar_and_unknown_channels_before_writer_or_runner(
        monkeypatch, tmp_path):
    root, rttov_input, _, captured = _mock_factory_run(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="thermal AMI channels only"):
        case_writer.make_live_run_k(root, solar_channels=(1,), ami_kma_bt=True)
    assert captured["written"] == captured["ran"] == 0

    unsupported = SimpleNamespace(config=SimpleNamespace(channels=(7,)), nprofiles=2)
    run_k = case_writer.make_live_run_k(root, ami_kma_bt=True)
    with pytest.raises(ValueError, match="channels 8..16"):
        run_k(unsupported)
    assert captured["written"] == captured["ran"] == 0


def test_optin_refuses_zero_total_even_when_quality_marks_the_channel_bad(
        monkeypatch, tmp_path):
    total = TOTAL.copy()
    total[0, 1] = 0.0
    quality = np.zeros_like(total)
    quality[0, 1] = 2.0
    root, rttov_input, _, captured = _mock_factory_run(
        monkeypatch, tmp_path, total=total, quality=quality)
    run_k = case_writer.make_live_run_k(root, ami_kma_bt=True)
    with pytest.raises(ValueError, match="positive finite total radiance"):
        run_k(rttov_input)
    assert captured["written"] == captured["ran"] == 1
