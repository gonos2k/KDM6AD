"""Finite-step normalization and duplicate-launch protection; no RTTOV calls."""

import json

import numpy as np
import pytest

import execute_finite_response as driver


def test_half_kelvin_step_preserves_derivative_and_quadratic_remainder():
    b = np.full(7, 280.0)
    kd = np.arange(1.0, 8.0)
    h = 0.5
    curvature = np.arange(7.0) * 0.01
    minus = b - h * kd + h**2 * curvature
    plus = b + h * kd + h**2 * curvature
    r = driver.compare_pair(minus, plus, b, kd, h, -h * kd, h * kd)
    np.testing.assert_allclose(r["D_FD_K_per_unit_direction"], kd, atol=1e-12)
    np.testing.assert_allclose(r["E_minus_ideal_K"], h**2 * curvature, atol=1e-12)
    np.testing.assert_allclose(r["E_plus_serialized_K"], h**2 * curvature, atol=1e-12)


def test_small_response_keeps_absolute_error_without_relative_ratio():
    b = np.zeros(7)
    kd = np.full(7, 1e-9)
    r = driver.compare_pair(-kd, kd * 2, b, kd, 1, -kd, kd)
    assert r["relative_error"] == [None] * 7
    np.testing.assert_allclose(r["derivative_error_K_per_unit_direction"], 0.5e-9)
    with pytest.raises(ValueError, match="positive"):
        driver.compare_pair(-kd, kd, b, kd, 0, -kd, kd)


def test_guard_refuses_second_execution_before_launch(tmp_path, monkeypatch):
    plan = {
        "execution_guard": {
            "guard_path": str(tmp_path / "guard.json"),
            "lock_path": str(tmp_path / "lock"),
        }
    }
    monkeypatch.setattr(driver, "validate", lambda *args: plan)
    launches = []
    monkeypatch.setattr(driver, "run_trials", lambda *args: launches.append(1))
    driver.execute(tmp_path / "plan.json", "fixedhash", "testexec001")
    with pytest.raises(FileExistsError):
        driver.execute(tmp_path / "plan.json", "fixedhash", "testexec002")
    assert launches == [1]
    assert (
        json.loads((tmp_path / "guard.json").read_text())["execution_id"]
        == "testexec001"
    )
