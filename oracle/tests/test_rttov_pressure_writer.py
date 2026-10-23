"""Synthetic writer tests for the opt-in native pressure-grid contract."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from kdm6.obs.model_profile_builder import RttovProfileTensors
from kdm6.obs.rttov_case_writer import write_rttov_case
from kdm6.obs.rttov_input_builder import RttovInputConfig, pack_rttov_input


F64 = torch.float64


def _fixture(root: Path, *, duplicate_pressure_option: bool = False):
    atm = root / "in" / "profiles" / "001" / "atm"
    atm.mkdir(parents=True)
    (root / "out").mkdir(parents=True)
    (atm / "t.txt").write_text("280\n270\n260\n")
    (atm / "q.txt").write_text("100\n200\n300\n")
    (atm / "p_half.txt").write_text("100\n300\n600\n1000\n")
    (atm / "p.txt").write_text("200\n450\n800\n")
    nml = """&rttov_test_nml
defn%nprofiles = 1
defn%nchannels = 1
defn%nlevels = 4
defn%realprec = 10
defn%do_k = .TRUE.
defn%opts%config%adk_bt = .TRUE.
defn%run_gas_units = 2
"""
    if duplicate_pressure_option:
        nml += "defn%opts%interpolation%pressure_gradients = .FALSE.\n"
        nml += "defn%opts%interpolation%pressure_gradients = .FALSE.\n"
    nml += "/\n"
    (root / "out" / "rttov_test.txt").write_text(nml)
    (root / "out" / "run.sh").write_text("#!/bin/sh\nexit 0\n")
    return root


def _input(p_lay, p_half, *, pressure_gradients):
    profile = RttovProfileTensors(
        t_lay=torch.tensor([280.0, 270.0, 260.0], dtype=F64),
        q_lay=torch.tensor([100.0, 200.0, 300.0], dtype=F64),
        p_lay=torch.tensor(p_lay, dtype=F64),
        p_half=torch.tensor(p_half, dtype=F64),
    )
    config = RttovInputConfig(
        coef_id="synthetic-pressure-case", channels=(1,),
        pressure_gradients=pressure_gradients)
    return pack_rttov_input(profile, config)


def _pressure_bytes(root: Path):
    atm = root / "in" / "profiles" / "001" / "atm"
    return ((atm / "p.txt").read_bytes(), (atm / "p_half.txt").read_bytes(),
            (root / "out" / "rttov_test.txt").read_bytes())


def test_default_pressure_mode_still_rejects_off_fixture_grid(tmp_path):
    fixture = _fixture(tmp_path / "fixture")
    before = _pressure_bytes(fixture)
    off_grid = _input([180.0, 470.0, 820.0], [80.0, 320.0, 640.0, 1020.0],
                      pressure_gradients=False)
    out = tmp_path / "case"
    with pytest.raises(ValueError, match="does not match the fixture grid"):
        write_rttov_case(off_grid, out, fixture_case_dir=fixture)
    assert not out.exists()
    assert _pressure_bytes(fixture) == before


def test_opt_in_writes_each_native_pressure_trial_and_enables_k_on_copy(tmp_path):
    fixture = _fixture(tmp_path / "fixture")
    before = _pressure_bytes(fixture)
    out = tmp_path / "case"
    trials = (
        ([150.0, 430.0, 820.0], [50.0, 250.0, 650.0, 1000.0]),
        ([180.0, 510.0, 840.0], [80.0, 300.0, 700.0, 950.0]),
    )
    for index, (p_lay, p_half) in enumerate(trials):
        write_rttov_case(_input(p_lay, p_half, pressure_gradients=True), out,
                          fixture_case_dir=fixture, overwrite=(index > 0))
        atm = out / "in" / "profiles" / "001" / "atm"
        np.testing.assert_array_equal(np.loadtxt(atm / "p.txt"), p_lay)
        np.testing.assert_array_equal(np.loadtxt(atm / "p_half.txt"), p_half)
        text = (out / "out" / "rttov_test.txt").read_text()
        assert text.count("defn%opts%interpolation%pressure_gradients") == 1
        assert "defn%opts%interpolation%pressure_gradients = .TRUE." in text
        assert (fixture / "out" / "rttov_test.txt").read_bytes() == before[2]
    assert _pressure_bytes(fixture) == before


def test_opt_in_rejects_bad_native_center_interface_order_before_copy(tmp_path):
    fixture = _fixture(tmp_path / "fixture")
    before = _pressure_bytes(fixture)
    bad = _input([150.0, 700.0, 820.0], [50.0, 250.0, 650.0, 1000.0],
                 pressure_gradients=True)
    out = tmp_path / "case"
    with pytest.raises(ValueError, match="centres must lie strictly inside"):
        write_rttov_case(bad, out, fixture_case_dir=fixture)
    assert not out.exists()
    assert _pressure_bytes(fixture) == before


def test_opt_in_rejects_duplicate_namelist_pressure_option_without_mutating_fixture(tmp_path):
    fixture = _fixture(tmp_path / "fixture", duplicate_pressure_option=True)
    before = _pressure_bytes(fixture)
    valid = _input([150.0, 430.0, 820.0], [50.0, 250.0, 650.0, 1000.0],
                   pressure_gradients=True)
    out = tmp_path / "case"
    with pytest.raises(ValueError, match="duplicate RTTOV pressure_gradients"):
        write_rttov_case(valid, out, fixture_case_dir=fixture)
    assert not out.exists()
    assert _pressure_bytes(fixture) == before
