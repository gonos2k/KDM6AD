"""Algebraic diagnostics, not an executed host or KDM experiment."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "saved_diag", Path(__file__).with_name("diagnose_saved_state.py"))
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


def fixture():
    native, capture = {}, {}
    for field in diag.STATE_FIELDS:
        native[f"native_window_state__{field}"] = np.full((8, 39), 0.0)
        for prefix in ("background_initial_state", "returned_analysis_initial_state",
                       "background_slot_state", "final_slot_state"):
            capture[f"{prefix}__{field}"] = np.zeros((1, 39))
    native["native_window_forcing__pii"] = np.full((8, 39), 0.9)
    native["native_window_host_dry_mass_kg_m2"] = np.tile(
        np.arange(1, 40, dtype=np.float32), (8, 1))
    return native, capture


def test_temperature_pressure_effect_survives_equal_theta():
    native, capture = fixture()
    native["native_window_state__th"][:] = 300
    capture["background_slot_state__th"][:] = 300
    native["native_window_forcing__pii"][1] = 0.91
    arrays, summary = diag.diagnose(native, capture)
    np.testing.assert_allclose(arrays["temperature_difference_K"], 3.0)
    np.testing.assert_array_equal(arrays["temperature_theta_term_K"], np.zeros(39))
    np.testing.assert_allclose(arrays["temperature_exner_term_K"], 3.0)
    assert summary["temperature_identity_max_abs_residual_K"] < 1e-12


def test_weighted_analysis_and_model_increments_are_distinct():
    native, capture = fixture()
    capture["background_initial_state__qv"][:] = 0.01
    capture["returned_analysis_initial_state__qv"][:] = 0.012
    capture["background_slot_state__qv"][:] = 0.009
    capture["background_slot_state__qc"][:] = 0.001
    capture["final_slot_state__qv"][:] = 0.011
    capture["final_slot_state__qc"][:] = 0.0005
    _, summary = diag.diagnose(native, capture)
    values = summary["water_increments_kg_m2"]
    assert values["analysis"] == pytest.approx(1.56)
    assert values["model_analysis"] == pytest.approx(-0.39)
    assert values["model_background"] == pytest.approx(0.0)
    assert values["slot_analysis_minus_background"] == pytest.approx(1.17)
    assert abs(values["decomposition_identity_residual"]) < 1e-14


def test_original_native_mass_dtype_is_required():
    native, capture = fixture()
    native["native_window_host_dry_mass_kg_m2"] = native[
        "native_window_host_dry_mass_kg_m2"].astype(np.float64)
    with pytest.raises(ValueError, match="float32"):
        diag.diagnose(native, capture)
