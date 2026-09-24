import math
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from moment_representation_probe import derivative_check, historical_rows, run_case  # noqa:E402
from kdm6 import fconst as fc  # noqa:E402
from kdm6.cloud_dsd import default_cloud_dsd_params, diag_cloud_slope_torch  # noqa:E402


@pytest.mark.parametrize("mode", ["small", "large"])
@pytest.mark.parametrize("rho", [0.25, 0.88, 1.4])
def test_newly_generated_rates_match_across_representations(mode, rho):
    result = run_case(mode=mode, capped=False, density=rho)
    assert result["mode_actual"] == mode and result["rain_active"]
    assert (
        result["volume_production_mass_rate"] > 0 and result["volume_number_rate"] > 0
    )
    assert (
        max(result["relative_errors"].values()) < 128 * torch.finfo(torch.float64).eps
    )
    assert math.isclose(
        result["volume_number_rate"] / rho,
        result["number_rate_converted_back_to_dry"],
        rel_tol=8 * torch.finfo(torch.float64).eps,
    )


@pytest.mark.parametrize("mode", ["small", "large"])
def test_actual_caps_and_closed_gate_are_separate(mode):
    cap = run_case(mode=mode, capped=True)
    off = run_case(mode=mode, capped=True, gate_active=False)
    assert cap["mass_cap_active"] and cap["number_cap_active"]
    assert cap["volume_production_mass_rate"] > 0
    assert not off["rain_active"]
    assert off["volume_production_mass_rate"] == off["volume_number_rate"] == 0


@pytest.mark.parametrize("mode", ["small", "large"])
def test_density_direction_passes_independent_finite_difference(mode):
    result = derivative_check(mode)
    assert result["density_direction"] != 0
    assert result["mass_rate_jvp"] != 0 and result["number_rate_jvp"] != 0
    assert result["max_relative_jvp_fd_error"] < 2e-6


def test_raw_mass_number_copy_changes_actual_recomputed_cloud_slope():
    q = torch.tensor([[2e-4]], dtype=torch.float64)
    nd = torch.tensor([[1.2e9]], dtype=torch.float64)
    rho = torch.full_like(q, 0.25)
    p = default_cloud_dsd_params()
    correct = diag_cloud_slope_torch(q, rho * nd, rho, params=p)
    unconverted = diag_cloud_slope_torch(q, nd, rho, params=p)
    exponent = fc._f32(1.0 / fc._f32(p.dmc))
    torch.testing.assert_close(
        unconverted / correct, rho**exponent, rtol=32 * torch.finfo(q.dtype).eps, atol=0
    )
    assert float((unconverted / correct).item()) < 0.7


def test_retained_rows_are_conditional_recalculations_not_native_approval():
    rows = historical_rows()
    assert len(rows) == 6
    assert {r["native_layer"] for r in rows} == {11, 12, 14}
    assert all(
        r["conditional"] and not r["physical_number_basis_resolved"] for r in rows
    )
    assert (
        max(v for r in rows for v in r["relative_error"].values())
        < 128 * torch.finfo(torch.float64).eps
    )


@pytest.mark.parametrize("rho", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_density_rejected(rho):
    with pytest.raises(ValueError):
        run_case(mode="small", capped=False, density=rho)
