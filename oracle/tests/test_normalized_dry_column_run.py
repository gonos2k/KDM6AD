import ctypes
import importlib.util
from pathlib import Path

import numpy as np
import pytest


SCRIPT = Path(__file__).parents[1] / "scripts/run_normalized_dry_column.py"
SPEC = importlib.util.spec_from_file_location("column_run", SCRIPT)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def case():
    state = np.array([[v, v] for v in
                      (280., 0.01, 0., 1e-4, 1e-4, 0., 1e-5, 1e9, 0., 1e5, 1e4, 2.5e-8)])
    forcing = np.array([[v, v] for v in (1., 0.9, 7e4, 500.)])
    return state, forcing


class LinearABI:
    """Analytic y=2*x ABI double to test wiring and failure cleanup."""
    def __init__(self, jvp_error=0):
        self.jvp_error = jvp_error
        self.calls, self.closed = [], 0

    def kdm6_step_ad_number_c(self, x, f, im, k, jm, dt, value, out, handle, land,
                              nc_land, nc_sea, variant, dry):
        self.size = 12 * k
        self.calls.append((dt, variant, dry, value, nc_land, nc_sea))
        np.ctypeslib.as_array(out, shape=(self.size,))[:] = 2 * np.ctypeslib.as_array(x, shape=(self.size,))
        ctypes.cast(handle, ctypes.POINTER(ctypes.c_void_p))[0] = None if value else 1
        return 0

    def kdm6_handle_jvp_c(self, handle, direction, out):
        if self.jvp_error:
            return self.jvp_error
        np.ctypeslib.as_array(out, shape=(self.size,))[:] = 2 * np.ctypeslib.as_array(direction, shape=(self.size,))
        return 0

    kdm6_handle_vjp_c = kdm6_handle_jvp_c

    def kdm6_handle_closep_c(self, handle):
        self.closed += 1
        ctypes.cast(handle, ctypes.POINTER(ctypes.c_void_p))[0] = None
        return 0


def test_all_forward_and_ad_calls_use_one_configuration():
    lib = LinearABI()
    arrays, checks = runner.run_column(lib, *case(), 1.)
    assert checks["numerical_checks_passed"]
    assert checks["numerical_input_checks_passed"]
    assert checks["strict_pair_state_admitted"]
    assert checks["observational_admission"] is False
    assert checks["operator_executed"] and checks["operator_outputs_finite"]
    assert len(lib.calls) == 4
    assert all(call[:3] == (20., 2, 1) and call[4:] == (10., 10.) for call in lib.calls)
    assert [call[3] for call in lib.calls] == [0, 1, 1, 1]
    np.testing.assert_allclose(arrays["jvp"], arrays["finite_difference"], rtol=1e-8, atol=1e-10)
    np.testing.assert_array_equal(arrays["state_out"], arrays["value_only_output"])
    np.testing.assert_array_equal(arrays["finite_difference"],
                                  (arrays["plus_output"] - arrays["minus_output"]) / (2e-4))
    assert float(arrays["xland"]) == 1.0
    assert lib.closed == 1


def test_failed_jvp_closes_handle():
    lib = LinearABI(jvp_error=7)
    with pytest.raises(RuntimeError, match="JVP failed"):
        runner.run_column(lib, *case(), 1.)
    assert lib.closed == 1


def test_matching_jvp_vjp_does_not_hide_wrong_finite_difference():
    class WrongDerivativeABI(LinearABI):
        def kdm6_handle_jvp_c(self, handle, direction, out):
            code = super().kdm6_handle_jvp_c(handle, direction, out)
            np.ctypeslib.as_array(out, shape=(self.size,))[:] *= 1.5
            return code

        kdm6_handle_vjp_c = kdm6_handle_jvp_c

    _, checks = runner.run_column(WrongDerivativeABI(), *case(), 1.)
    assert checks["duality_relative"] < 1e-12
    assert not checks["finite_difference_passed"]
    assert not checks["numerical_checks_passed"]


def test_invalid_state_is_rejected_before_native_call():
    negative_pair, _ = case()
    negative_pair[runner.PROG_FIELDS.index("qc"), 0] = -1e-3
    negative_pair[runner.PROG_FIELDS.index("nc"), 0] = -1.0
    assert not runner.classify_state(negative_pair)["strict_pair_state_admitted"]

    state, forcing = case()
    state[1, 0] = -1.
    lib = LinearABI()
    with pytest.raises(ValueError, match="nonnegative state"):
        runner.run_column(lib, state, forcing, 1.)
    assert not lib.calls


def test_finite_unpaired_state_passes_numerical_inputs_but_fails_pair_admission():
    state, _ = case()
    state[runner.PROG_FIELDS.index("qc"), 0] = 1e-3
    result = runner.classify_state(state, "finite unpaired sample")
    assert result == dict(
        state_label="finite unpaired sample",
        numerical_input_checks_passed=True,
        strict_pair_state_admitted=False,
        observational_admission=False,
    )
    lib = LinearABI()
    with pytest.raises(ValueError, match="unsupported qc/nc moment pair"):
        runner.run_column(lib, state, case()[1], 1.)
    assert not lib.calls


def test_nonfinite_state_fails_numerical_input_checks_before_native_call():
    state, forcing = case()
    state[0, 0] = np.nan
    result = runner.classify_state(state, "nonfinite sample")
    assert result["numerical_input_checks_passed"] is False
    assert result["strict_pair_state_admitted"] is False
    assert result["observational_admission"] is False
    lib = LinearABI()
    with pytest.raises(ValueError, match="finite positive temperature"):
        runner.run_column(lib, state, forcing, 1.)
    assert not lib.calls


def test_existing_output_is_rejected_before_reading_inputs(tmp_path):
    with pytest.raises(ValueError, match="already exists"):
        runner.main(["--input", "missing.nc", "--library", "missing.so", "--i", "0",
                     "--j", "0", "--output", str(tmp_path)])


@pytest.mark.parametrize("wrong_derivative", [False, True])
def test_main_saves_numerical_failure_and_returns_nonzero(tmp_path, monkeypatch, wrong_derivative):
    """Persist a failed FD check even when the ABI double passes duality."""
    import json
    from types import SimpleNamespace

    import netCDF4
    import torch

    state, forcing = case()
    input_path, library_path = tmp_path / "input.nc", tmp_path / "analytic-abi.so"
    with netCDF4.Dataset(input_path, "w") as ds:
        ds.DX = ds.DY = 5000.0
        for name, size in (("Time", 1), ("west_east", 1), ("south_north", 1)):
            ds.createDimension(name, size)
    library_path.write_bytes(b"analytic test double, not a native library")
    frame = SimpleNamespace(state=[torch.from_numpy(v[None, :]) for v in state],
                            forcing=[torch.from_numpy(v[None, :]) for v in forcing],
                            xland=torch.tensor([1.0]), meta={"valid_time_utc": "synthetic"})
    monkeypatch.setattr(runner, "read_wrfout_frame", lambda *a, **kw: frame)

    class DerivativeABI(LinearABI):
        def kdm6_handle_jvp_c(self, handle, direction, out):
            code = super().kdm6_handle_jvp_c(handle, direction, out)
            if wrong_derivative:
                np.ctypeslib.as_array(out, shape=(self.size,))[:] *= 1.5
            return code

        kdm6_handle_vjp_c = kdm6_handle_jvp_c

    monkeypatch.setattr(runner, "load_library", lambda path: DerivativeABI())
    output = tmp_path / "result"
    code = runner.main(["--input", str(input_path), "--library", str(library_path),
                        "--i", "0", "--j", "0", "--output", str(output)])
    saved = json.loads((output / "result.json").read_text())
    assert code == int(wrong_derivative)
    assert saved["status"] == ("NUMERICAL_CHECK_FAILED" if wrong_derivative else "NUMERICAL_PASS")
    assert saved["checks"]["duality_relative"] < 1e-12
    assert saved["checks"]["finite_difference_passed"] is (not wrong_derivative)
    assert saved["accepted_observation_cost"] is False
    with np.load(output / "arrays.npz", allow_pickle=False) as arrays:
        np.testing.assert_array_equal(arrays["state_in"], state)
        np.testing.assert_array_equal(arrays["finite_difference"],
                                      (arrays["plus_output"] - arrays["minus_output"]) / (2e-4))
