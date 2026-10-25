"""Non-square actual NetCDF layout binding; no native model execution."""
import copy

import numpy as np
import pytest

from harness.native_analysis_increment import bind_satellite_control
from harness.native_analysis_control import apply_pair
from harness.native_host_transition import NativeCheckpoint
from harness.native_live_stepper import checkpoint_geometry_id
from harness.native_satellite_objective import prepare_representable_control

nc = pytest.importorskip("netCDF4")

STAMP = "2025-07-19_00:00:40"


@pytest.fixture
def checkpoint(tmp_path):
    path = tmp_path / "restart.nc"
    with nc.Dataset(path, "w") as ds:
        for name, size in (("Time", 1), ("DateStrLen", 19), ("west_east", 3),
                           ("south_north", 2), ("bottom_top", 2)):
            ds.createDimension(name, size)
        ds.createVariable("Times", "S1", ("Time", "DateStrLen"))[:] = np.frombuffer(STAMP.encode(), "S1")[None]
        ds.createVariable("ITIMESTEP", "i4", ("Time",))[:] = [2]
        for name in ("H_DIABATIC", "QV_DIABATIC", "QC_DIABATIC", "QNCCN"):
            ds.createVariable(name, "f4", ("Time",))[:] = [0]
        order = ("Time", "bottom_top", "south_north", "west_east")
        # Independent file-order construction: sentinel = 100*k + 10*j + i.
        k, j, i = np.indices((2, 2, 3))
        ds.createVariable("THM_2", "f4", order)[:] = (100*k + 10*j + i + 20)[None]
        ds.createVariable("QVAPOR", "f4", order)[:] = ((k + j + i + 1)/1024)[None]
        ds.createVariable("MU_2", "f4", ("Time", "south_north", "west_east"))[:] = 90000
        for name, offset in (("XLAT", 35), ("XLONG", 125)):
            ds.createVariable(name, "f4", ("Time", "south_north", "west_east"))[:] = np.arange(6).reshape(1, 2, 3) + offset
    return NativeCheckpoint.capture(path, expected_time=STAMP, expected_itimestep=2)


def prepared(checkpoint):
    baseline = np.empty((2, 6, 2), np.float64)
    with nc.Dataset(checkpoint.file.path) as ds:
        # Explicit independent coordinates, not the implementation's transpose.
        for j in range(2):
            for i in range(3):
                for k in range(2):
                    baseline[:, j*3+i, k] = ds["THM_2"][0,k,j,i], ds["QVAPOR"][0,k,j,i]
    z = np.zeros_like(baseline)
    z[0, 4, 1] = 0.5  # flat4: native 1-based (i=2,k=2,j=2)
    z[1, 2, 0] = -0.5  # flat2: native 1-based (i=3,k=1,j=1)
    return baseline, prepare_representable_control(baseline, z, np.ones_like(z, bool), horizontal_shape=(2, 3),
                                                   background_checkpoint_id=checkpoint.file.sha256)


def test_bound_increment_lands_at_independent_non_square_sentinels(checkpoint):
    baseline, control = prepared(checkpoint)
    increment = bind_satellite_control(checkpoint, control, posterior_checkpoint_id="effective-analysis-v1")
    assert increment.delta_theta_m.shape == (3, 2, 2)
    assert np.argwhere(increment.delta_theta_m != 0).tolist() == [[1, 1, 1]]
    assert np.argwhere(increment.delta_qv != 0).tolist() == [[2, 0, 0]]
    with nc.Dataset(checkpoint.file.path) as ds:
        for i, k, j in np.argwhere(~increment.unchanged_mask):
            new_t, new_q = apply_pair(ds["THM_2"][0,k,j,i], ds["QVAPOR"][0,k,j,i],
                                      increment.delta_theta_m[i,k,j], increment.delta_qv[i,k,j])
            assert new_t == control["candidate"][0, j*3+i, k]
            assert new_q == control["candidate"][1, j*3+i, k]
    assert baseline[0, 4, 1] == 131  # explicit file-order sentinel
    assert increment.background_checkpoint_id == checkpoint.file.sha256
    assert increment.model_valid_time == STAMP
    assert increment.geometry_id == checkpoint_geometry_id(checkpoint)
    assert increment.posterior_checkpoint_id == "effective-analysis-v1"


@pytest.mark.parametrize("tamper", ["background", "candidate", "wire", "layout"])
def test_mismatched_preparation_is_rejected(checkpoint, tamper):
    _, control = prepared(checkpoint)
    bad = copy.deepcopy(control)
    if tamper == "background":
        bad["background_sha256"] = "0" * 64
    elif tamper == "candidate":
        bad["candidate"][0, 4, 1] += .01
    elif tamper == "wire":
        bad["wire_delta"][0, 4, 1] *= 2
    else:
        bad["horizontal_shape"] = (3, 2)
    with pytest.raises(ValueError):
        bind_satellite_control(checkpoint, bad, posterior_checkpoint_id="bad")


def test_identical_tq_and_geometry_cannot_rebind_to_changed_model_background(checkpoint):
    from pathlib import Path
    import shutil
    _, control = prepared(checkpoint)
    other_path = Path(checkpoint.file.path).with_name("changed_mu.nc")
    shutil.copy2(checkpoint.file.path, other_path)
    with nc.Dataset(other_path, "r+") as ds:
        ds["MU_2"][0, 0, 0] += np.float32(1.0)
    other = NativeCheckpoint.capture(other_path, expected_time=STAMP, expected_itimestep=2)
    assert checkpoint_geometry_id(other) == checkpoint_geometry_id(checkpoint)
    with nc.Dataset(checkpoint.file.path) as old, nc.Dataset(other.file.path) as new:
        for name in ("THM_2", "QVAPOR"):
            assert np.asarray(old[name][:]).tobytes() == np.asarray(new[name][:]).tobytes()
    with pytest.raises(ValueError, match="complete background checkpoint"):
        bind_satellite_control(other, control, posterior_checkpoint_id="must-not-rebind")
