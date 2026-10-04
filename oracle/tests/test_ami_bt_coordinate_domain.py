"""Fail-closed source checks for the offline AMI BT-coordinate replay."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


_ROOT = Path(__file__).resolve().parents[2]
_SOURCE = _ROOT / "harness/evidence/AMI_bt_coordinate_source_2026-10-04.py"
_OBS = _ROOT / "harness/evidence/AMI_local_support_result_2026-10-04.json"
_CAL = _ROOT / "harness/evidence/AMI_legacy_nominal_calibration_202507190000.json"
_SPEC = importlib.util.spec_from_file_location("ami_bt_coordinate_source", _SOURCE)
assert _SPEC is not None and _SPEC.loader is not None
_COORD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_COORD)


def _retained_positive_ir105_window() -> tuple[np.ndarray, np.ndarray]:
    report = json.loads(_OBS.read_text())
    entry = report["slots"][0]["channels"]["ir105"]
    return (np.asarray(entry["window_radiance"], dtype=np.float64),
            np.asarray(entry["window_bt_K"], dtype=np.float64))


def test_retained_positive_observation_window_passes_domain_guard():
    radiance, saved_bt = _retained_positive_ir105_window()
    assert radiance.shape == saved_bt.shape == (3, 3)
    assert np.isfinite(radiance).all() and (radiance > 0).all()
    _COORD.validate_radiance_window(radiance, saved_bt)


@pytest.mark.parametrize("bad", [-1.0, 0.0, np.nan, np.inf, -np.inf])
def test_nonpositive_or_nonfinite_radiance_fails_even_when_saved_bt_is_finite(bad):
    radiance, saved_bt = _retained_positive_ir105_window()
    radiance = radiance.copy()
    radiance[0, 0] = bad
    with pytest.raises(ValueError, match="radiance must be finite and positive"):
        _COORD.validate_radiance_window(radiance, saved_bt)


def test_negative_radiance_with_matching_clipped_legacy_bt_is_rejected():
    legacy = json.loads(_CAL.read_text())["channels"]["ir105"]
    radiance = np.full((3, 3), 84.10494944080688, dtype=np.float64)
    radiance[0, 0] = -1.0
    old_wavenumber = 10000.0 / float(legacy["channel_center_wavelength"])
    forged_saved_bt = np.asarray(_COORD.ami_phi(radiance, legacy, old_wavenumber))
    assert np.isfinite(forged_saved_bt).all()  # ami_phi clips this invalid input
    with pytest.raises(ValueError, match="radiance must be finite and positive"):
        _COORD.validate_radiance_window(radiance, forged_saved_bt)


@pytest.mark.parametrize("bad", [0.0, -1.0, np.nan, np.inf, -np.inf])
def test_nonpositive_or_nonfinite_saved_bt_fails(bad):
    radiance, saved_bt = _retained_positive_ir105_window()
    saved_bt = saved_bt.copy()
    saved_bt[0, 0] = bad
    with pytest.raises(ValueError, match="saved window BT must be finite and positive"):
        _COORD.validate_radiance_window(radiance, saved_bt)
