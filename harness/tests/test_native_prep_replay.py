"""Synthetic input/time/schema refusal tests for the saved-prep loader.

These tiny fixtures exercise loader guards only; they are not host data or
native-model evidence.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np
import pytest

import harness.native_prep_replay as replay


def _namelist(*, hypsometric_opt=2, non_hydrostatic=".true.", time_step=20,
              time_step_fract_num=0, time_step_fract_den=1, e_vert=40):
    return (
        "&time_control\n"
        " start_date='2025-07-19_00:00:00',\n"
        f" time_step={time_step},\n"
        f" time_step_fract_num={time_step_fract_num},\n"
        f" time_step_fract_den={time_step_fract_den},\n/\n"
        "&domains\n e_we=235,\n e_sn=283,\n"
        f" e_vert={e_vert},\n non_hydrostatic={non_hydrostatic},\n/\n"
        "&physics\n mp_physics=137,\n use_theta_m=1,\n no_mp_heating=0,\n"
        " use_q_diabatic=0,\n mp_zero_out=2,\n mp_zero_out_all=0,\n"
        f" mp_zero_out_thresh=9.99999994e-9,\n hypsometric_opt={hypsometric_opt},\n/\n"
    )


class _Record:
    def __init__(self, **values):
        self.values = values

    def value(self, name):
        return self.values[name]


def _install_pre_checkpoint_fakes(monkeypatch):
    # The tests below fail before any geometry variables are loaded. Keep the
    # selected trace records minimal and make accidental later access obvious.
    row = _Record(T_NEW_PRE=np.float32(280.), Q=np.float32(.01))
    monkeypatch.setattr(replay, "load_case", lambda *a, **k: SimpleNamespace(config={"dt": 20.}))
    rows = {}
    for k in range(1, 40):
        rows[("FINISH_PRE", 2, 3, k, 4)] = row
        rows[("MP_INPUT", 2, 3, k, 4)] = row
    monkeypatch.setattr(replay, "read_native_trace", lambda path: rows)


class _TimesVariable:
    dimensions = ("Time", "DateStrLen")
    dtype = np.dtype("S1")

    def __init__(self, value):
        self.value = value
        self.array = np.asarray([list(value)], dtype="S1")

    def __getitem__(self, index):
        return self.array[index]


class _CheckpointVariable:
    def __init__(self, dimensions, dtype=np.float32):
        self.dimensions = dimensions
        self.dtype = np.dtype(dtype)

    def ncattrs(self):
        return []

    def __getitem__(self, index):
        raise AssertionError("checkpoint field should not be read before its dtype guard")


class _Dataset:
    def __init__(self, *, time, interface_count=40, mass_count=39):
        self.dimensions = {
            "west_east": range(234),
            "south_north": range(282),
            "bottom_top": range(mass_count),
            "bottom_top_stag": range(interface_count),
        }
        variables = {"Times": _TimesVariable(time)}
        for name in ('PH_2', 'PHB'):
            variables[name] = _CheckpointVariable(
                ('Time', 'bottom_top_stag', 'south_north', 'west_east'))
        for name in ('ALB', 'PB', 'AL', 'P', 'QVAPOR', 'THM_2'):
            variables[name] = _CheckpointVariable(
                ('Time', 'bottom_top', 'south_north', 'west_east'))
        for name in ('MU_2', 'MU_1', 'MUB', 'XLAND'):
            variables[name] = _CheckpointVariable(('Time', 'south_north', 'west_east'))
        for name in ('C3F', 'C4F'):
            variables[name] = _CheckpointVariable(('Time', 'bottom_top_stag'))
        for name in ('C3H', 'C4H'):
            variables[name] = _CheckpointVariable(('Time', 'bottom_top'))
        variables['P_TOP'] = _CheckpointVariable(('Time',))
        self.variables = variables

    def set_auto_maskandscale(self, value):
        assert value is False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _run_loader(monkeypatch, tmp_path, *, nml_text=None, checkpoint_time="2025-07-19_00:00:40",
                interface_count=40, mass_count=39):
    nml = tmp_path/"namelist.input"
    nml.write_text(_namelist() if nml_text is None else nml_text, encoding="ascii")
    _install_pre_checkpoint_fakes(monkeypatch)
    fake_netcdf = SimpleNamespace(Dataset=lambda path: _Dataset(
        time=checkpoint_time, interface_count=interface_count, mass_count=mass_count))
    monkeypatch.setitem(sys.modules, "netCDF4", fake_netcdf)
    return replay.load_native_prep_case("trace", nml, "checkpoint", 2, 3, 4, 39)


def test_expected_checkpoint_time_includes_fractional_timestep():
    assignments = replay._namelist_assignments(_namelist(
        time_step=20, time_step_fract_num=1, time_step_fract_den=2
    ))
    assert replay._expected_checkpoint_time(assignments, 2, 20.5) == "2025-07-19_00:00:41"


def test_expected_checkpoint_time_handles_exact_rational_fraction_only():
    assignments = replay._namelist_assignments(_namelist(
        time_step=20, time_step_fract_num=1, time_step_fract_den=3
    ))
    assert replay._expected_checkpoint_time(assignments, 3, 20 + 1/3) == "2025-07-19_00:01:01"
    with pytest.raises(ValueError, match="fractional-second endpoints"):
        replay._expected_checkpoint_time(assignments, 1, 20 + 1/3)


def test_loader_refuses_wrong_numeric_checkpoint_time(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match=r"Times=.*expected 2025-07-19_00:00:40"):
        _run_loader(monkeypatch, tmp_path, checkpoint_time="2025-07-19_00:00:20")


@pytest.mark.parametrize("option, expected", [
    ("hypsometric_opt=2", "hypsometric_opt=1"),
    ("non_hydrostatic=.true.", "non_hydrostatic=.false."),
])
def test_loader_refuses_unsupported_prep_option_before_trace_load(monkeypatch, tmp_path, option, expected):
    nml = tmp_path/"namelist.input"
    nml.write_text(_namelist().replace(option, expected), encoding="ascii")

    def unexpected(*args, **kwargs):
        raise AssertionError("unsupported option should be rejected before trace/checkpoint load")

    monkeypatch.setattr(replay, "load_case", unexpected)
    monkeypatch.setattr(replay, "read_native_trace", unexpected)
    with pytest.raises(ValueError, match="hypsometric_opt|non_hydrostatic=true"):
        replay.load_native_prep_case("trace", nml, "checkpoint", 2, 3, 4, 39)


def test_loader_refuses_incomplete_native_interface_shape(monkeypatch, tmp_path):
    nml = tmp_path/"namelist.input"
    nml.write_text(_namelist(), encoding="ascii")
    _install_pre_checkpoint_fakes(monkeypatch)
    fake_netcdf = SimpleNamespace(Dataset=lambda path: _Dataset(
        time="2025-07-19_00:00:40", interface_count=39, mass_count=39))
    monkeypatch.setitem(sys.modules, "netCDF4", fake_netcdf)
    with pytest.raises(ValueError, match="interface count differs"):
        replay.load_native_prep_case("trace", nml, "checkpoint", 2, 3, 4, 39)


def test_loader_refuses_truncated_native_mass_column_before_checkpoint(monkeypatch, tmp_path):
    nml = tmp_path/"namelist.input"
    nml.write_text(_namelist(e_vert=41), encoding="ascii")

    def unexpected(*args, **kwargs):
        raise AssertionError("truncated column should be rejected before trace/checkpoint load")

    monkeypatch.setattr(replay, "load_case", unexpected)
    monkeypatch.setattr(replay, "read_native_trace", unexpected)
    with pytest.raises(ValueError, match="full native mass column requires 40"):
        replay.load_native_prep_case("trace", nml, "checkpoint", 2, 3, 4, 39)


def test_loader_uses_explicit_input_namelist_not_valid_sibling_output(monkeypatch, tmp_path):
    input_nml = tmp_path/"namelist.input"
    output_nml = tmp_path/"namelist.output"
    input_nml.write_text(_namelist(hypsometric_opt=1), encoding="ascii")
    output_nml.write_text(_namelist(hypsometric_opt=2), encoding="ascii")

    def unexpected(*args, **kwargs):
        raise AssertionError("the invalid explicitly supplied namelist must be refused first")

    monkeypatch.setattr(replay, "load_case", unexpected)
    monkeypatch.setattr(replay, "read_native_trace", unexpected)
    with pytest.raises(ValueError, match="hypsometric_opt"):
        replay.load_native_prep_case("trace", input_nml, "checkpoint", 2, 3, 4, 39)


def test_loader_refuses_float64_checkpoint_field_without_casting(monkeypatch, tmp_path):
    nml = tmp_path/"namelist.input"
    nml.write_text(_namelist(), encoding="ascii")
    _install_pre_checkpoint_fakes(monkeypatch)

    class Float64PH2Dataset(_Dataset):
        def __init__(self):
            super().__init__(time="2025-07-19_00:00:40")
            self.variables['PH_2'].dtype = np.dtype(np.float64)

    fake_netcdf = SimpleNamespace(Dataset=lambda path: Float64PH2Dataset())
    monkeypatch.setitem(sys.modules, "netCDF4", fake_netcdf)
    with pytest.raises(ValueError, match="PH_2 must be stored as native binary32"):
        replay.load_native_prep_case("trace", nml, "checkpoint", 2, 3, 4, 39)
