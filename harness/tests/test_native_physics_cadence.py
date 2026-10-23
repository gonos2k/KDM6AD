"""Restart-seed STEPRA cadence preparation tests; no model execution."""
from __future__ import annotations

import json
from pathlib import Path
import shutil

import netCDF4 as nc
import numpy as np
import pytest

import harness.native_physics_cadence as cadence
from harness.native_host_transition import NativeCheckpoint, file_sha256
from harness.native_physics_cadence import prepare_radiation_step_restart
from harness.native_replay_compare import compare_frames


TIME = "2025-07-19_00:02:00"


def _restart(path, *, stepra=15, stepra_dtype="i4", stepra_dims=("Time",),
             stepra_values=None, include_stepra=True):
    if stepra_values is None:
        stepra_values = (stepra,)
    with nc.Dataset(path, "w") as ds:
        ds.createDimension("Time", 1)
        ds.createDimension("DateStrLen", 19)
        ds.createDimension("bottom_top", 2)
        ds.createDimension("CharLen", 4)
        ds.createVariable("Times", "S1", ("Time", "DateStrLen"))[:] = np.frombuffer(
            TIME.encode("ascii"), dtype="S1")[None, :]
        ds.createVariable("ITIMESTEP", "i4", ("Time",))[:] = [6]
        ds.createVariable("H_DIABATIC", "f4", ("Time", "bottom_top"))[:] = [[0.0, 0.1]]
        ds.createVariable("QV_DIABATIC", "f4", ("Time", "bottom_top"))[:] = [[0.0, 0.0]]
        ds.createVariable("QC_DIABATIC", "f4", ("Time", "bottom_top"))[:] = [[0.0, 0.0]]
        ds.createVariable("QNCCN", "f4", ("Time", "bottom_top"))[:] = [[1.0, 2.0]]
        ds.createVariable("T", "f4", ("Time", "bottom_top"))[:] = [[280.0, 275.0]]
        ds.createVariable("TAG", "S1", ("CharLen",))[:] = np.frombuffer(b"seed", dtype="S1")
        if include_stepra:
            variable = ds.createVariable("STEPRA", stepra_dtype, stepra_dims)
            variable[:] = np.asarray(stepra_values, dtype=stepra_dtype)
            variable.setncattr("meaning", "radiation interval in model steps")
        ds.setncattr("PHYSICS_CONTEXT", "fixed native seed")


def _state(path):
    return NativeCheckpoint.capture(path, expected_time=TIME, expected_itimestep=6)


def test_prepare_radiation_step_checkpoint_changes_only_stepra_and_records_provenance(tmp_path):
    source_path = tmp_path / "source.nc"
    target_path = tmp_path / "prepared.nc"
    receipt_path = tmp_path / "prepared.json"
    _restart(source_path, stepra=15)
    state = _state(source_path)
    source_hash = file_sha256(source_path)

    prepared = prepare_radiation_step_restart(state, target_path, receipt_path)

    assert file_sha256(source_path) == source_hash == state.file.sha256
    assert target_path.is_file() and receipt_path.is_file()
    assert target_path.resolve() != source_path.resolve()
    assert prepared.time == state.time and prepared.itimestep == state.itimestep
    assert prepared.schema == state.schema
    with nc.Dataset(source_path) as before, nc.Dataset(target_path) as after:
        before.set_auto_maskandscale(False)
        after.set_auto_maskandscale(False)
        assert int(before["STEPRA"][0]) == 15
        assert int(after["STEPRA"][0]) == 1
        comparison = compare_frames(before, after, 0, 0, TIME)
    assert comparison["missing_variables"] == []
    assert comparison["extra_variables"] == []
    assert comparison["numeric_element_mismatches"] == 1
    assert comparison["variables"]["STEPRA"]["mismatch_count"] == 1
    assert all(report["raw_bitwise_equal"] for name, report in comparison["variables"].items()
               if name != "STEPRA")

    record = json.loads(receipt_path.read_text())
    assert record["scope"] == "restart seed only; STEPRA cadence field change, no model execution"
    assert record["source_sha256"] == source_hash
    assert record["target_sha256"] == prepared.file.sha256 == file_sha256(target_path)
    assert record["source_stepra"] == 15 and record["target_stepra"] == 1
    assert record["changed_variables"] == record["expected_changed_variables"] == ["STEPRA"]
    assert record["metadata"]["passed"]
    assert record["metadata"]["differences"] == []
    assert record["metadata"]["output_ringing_normalizations"] == []


def test_stepra_one_still_creates_distinct_valid_seed_without_variable_changes(tmp_path):
    source = tmp_path / "source.nc"
    target = tmp_path / "prepared.nc"
    receipt = tmp_path / "prepared.json"
    _restart(source, stepra=1)
    state = _state(source)
    source_sha = file_sha256(source)

    prepared = prepare_radiation_step_restart(state, target, receipt)

    assert source_sha == file_sha256(source)
    assert prepared.file.sha256 == file_sha256(target)
    assert target.resolve() != source.resolve()
    record = json.loads(receipt.read_text())
    assert record["source_stepra"] == record["target_stepra"] == 1
    assert record["changed_variables"] == record["expected_changed_variables"] == []
    assert record["comparison"]["raw_bitwise_equal"] is True
    assert record["metadata"]["passed"]


@pytest.mark.parametrize("kwargs,match", [
    ({"include_stepra": False}, "missing STEPRA"),
    ({"stepra_dtype": "i8"}, "int32"),
    ({"stepra_dims": ("Time", "bottom_top"), "stepra_values": ((15, 15),)}, "scalar"),
    ({"stepra_values": (0,)}, "positive"),
    ({"stepra_values": (-1,)}, "positive"),
])
def test_prepare_refuses_missing_or_malformed_stepra(tmp_path, kwargs, match):
    source = tmp_path / "source.nc"
    _restart(source, **kwargs)
    state = _state(source)
    target, receipt = tmp_path / "prepared.nc", tmp_path / "prepared.json"

    with pytest.raises(ValueError, match=match):
        prepare_radiation_step_restart(state, target, receipt)

    assert not target.exists()
    assert not receipt.exists()


@pytest.mark.parametrize("existing", ["target", "receipt"])
def test_prepare_never_overwrites_existing_destination(tmp_path, existing):
    source = tmp_path / "source.nc"
    target, receipt = tmp_path / "prepared.nc", tmp_path / "prepared.json"
    _restart(source)
    state = _state(source)
    occupied = target if existing == "target" else receipt
    occupied.write_bytes(b"caller-owned")

    with pytest.raises(FileExistsError):
        prepare_radiation_step_restart(state, target, receipt)

    assert occupied.read_bytes() == b"caller-owned"
    assert not (receipt if existing == "target" else target).exists()


def test_receipt_publish_failure_rolls_back_target_and_preserves_source(tmp_path, monkeypatch):
    source = tmp_path / "source.nc"
    target, receipt = tmp_path / "prepared.nc", tmp_path / "prepared.json"
    _restart(source)
    state = _state(source)
    source_hash = file_sha256(source)
    real_link = cadence.os.link
    calls = 0

    def fail_second_link(src, dst, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected receipt publication failure")
        return real_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(cadence.os, "link", fail_second_link)
    with pytest.raises(OSError, match="injected"):
        prepare_radiation_step_restart(state, target, receipt)

    assert calls == 2
    assert not target.exists()
    assert not receipt.exists()
    assert file_sha256(source) == source_hash


def test_prepare_refuses_checkpoint_bytes_changed_after_capture(tmp_path):
    source = tmp_path / "source.nc"
    target, receipt = tmp_path / "prepared.nc", tmp_path / "prepared.json"
    _restart(source)
    state = _state(source)
    with nc.Dataset(source, "r+") as ds:
        ds["STEPRA"][0] = 16

    with pytest.raises(RuntimeError, match="pinned file changed"):
        prepare_radiation_step_restart(state, target, receipt)

    assert not target.exists()
    assert not receipt.exists()
