"""Focused PR208 regressions for WRF and RTTOV observation boundaries."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from kdm6.io import read_wrfout_frame
from kdm6.obs.model_profile_builder import RttovProfileTensors
from kdm6.obs.obs_ingest import ObsPayload, payload_to_column_obs
from kdm6.obs.rttov_case_writer import write_rttov_case
from kdm6.obs.rttov_input_builder import (
    RttovInput,
    RttovInputConfig,
    pack_rttov_input,
)


F64 = torch.float64


def _cfg(**changes):
    values = dict(coef_id="audit", channels=(1,))
    values.update(changes)
    return RttovInputConfig(**values)


def _profile(nprofiles=2, nlayers=4, *, p_half=None, p_lay=None):
    t = torch.full((nprofiles, nlayers), 280.0, dtype=F64)
    q = torch.full((nprofiles, nlayers), 100.0, dtype=F64)
    if p_half is None:
        p_half = torch.linspace(100.0, 1000.0, nlayers + 1, dtype=F64)
    if p_lay is None:
        p_lay = torch.linspace(200.0, 900.0, nlayers, dtype=F64)
    return RttovProfileTensors(
        t_lay=t, q_lay=q,
        p_half=torch.as_tensor(p_half, dtype=F64),
        p_lay=torch.as_tensor(p_lay, dtype=F64),
    )


@pytest.mark.parametrize("nprofiles,nlayers,match", [
    (0, 4, "at least one profile"),
    (1, 0, "at least one layer"),
])
def test_review208_pack_rejects_typed_empty_profile_axes(nprofiles, nlayers, match):
    profile = _profile(
        nprofiles=nprofiles,
        nlayers=nlayers,
        p_half=torch.empty((nprofiles, nlayers + 1), dtype=F64),
        p_lay=torch.empty((nprofiles, nlayers), dtype=F64),
    )
    with pytest.raises(ValueError, match=match):
        pack_rttov_input(profile, _cfg())


def test_review208_pack_accepts_one_shared_pressure_row():
    profile = _profile(
        p_half=torch.linspace(100.0, 1000.0, 5, dtype=F64).unsqueeze(0),
        p_lay=torch.linspace(200.0, 900.0, 4, dtype=F64).unsqueeze(0),
    )
    packed = pack_rttov_input(profile, _cfg())
    assert packed.nprofiles == 2
    assert packed.profile["P_HALF"].shape == (1, 5)
    assert packed.profile["P"].shape == (1, 4)


@pytest.mark.parametrize("field", ["p_half", "p_lay"])
def test_review208_pack_rejects_unpaired_pressure_rows(field):
    kwargs = {
        "p_half": torch.linspace(100.0, 1000.0, 5, dtype=F64),
        "p_lay": torch.linspace(200.0, 900.0, 4, dtype=F64),
    }
    kwargs[field] = kwargs[field].repeat(3, 1)
    with pytest.raises(ValueError, match=r"provide one shared row or exactly 2 rows"):
        pack_rttov_input(_profile(**kwargs), _cfg())


def test_review208_pack_rejects_pressure_layer_axis_mismatch():
    profile = _profile(p_lay=torch.linspace(200.0, 900.0, 3, dtype=F64))
    with pytest.raises(ValueError, match="layer pressure must ride the T/Q grid"):
        pack_rttov_input(profile, _cfg())


def test_review208_writer_rejects_manual_zero_profile_before_fixture_copy(tmp_path):
    rin = RttovInput(
        profile={"T": np.empty((0, 4)), "Q": np.empty((0, 4))},
        config=_cfg(), config_hash="audit", nprofiles=0, nlayers=4,
    )
    with pytest.raises(ValueError, match="requires at least one profile"):
        write_rttov_case(rin, tmp_path / "case")
    assert not (tmp_path / "case").exists()


def test_review208_writer_rejects_manual_zero_channels_before_fixture_copy(tmp_path):
    rin = RttovInput(
        profile={"T": np.ones((1, 4)), "Q": np.ones((1, 4))},
        config=_cfg(channels=()), config_hash="audit", nprofiles=1, nlayers=4,
    )
    with pytest.raises(ValueError, match="at least one channel"):
        write_rttov_case(rin, tmp_path / "case")
    assert not (tmp_path / "case").exists()


class _Variable:
    def __init__(self, name, data):
        self.name, self.data = name, data

    def __getitem__(self, key):
        return self.data[key]


@pytest.fixture()
def synthetic_frame(monkeypatch):
    names = ("QVAPOR THM P PB QNCCN QCLOUD QRAIN QICE QSNOW QGRAUP "
             "QNCLOUD QNICE QNRAIN QIB").split()
    variables = {
        name: _Variable(name, np.zeros((1, 2, 1, 2), dtype=np.float64))
        for name in names
    }
    variables["PB"].data.fill(90000.0)
    heights = np.array([0.0, 500.0, 1200.0]).reshape(1, 3, 1, 1)
    variables["PHB"] = _Variable(
        "PHB", np.broadcast_to(heights * 9.81, (1, 3, 1, 2)).copy())
    variables["PH"] = _Variable("PH", np.zeros((1, 3, 1, 2)))
    variables["XLAND"] = _Variable(
        "XLAND", np.array([1.0, 2.0]).reshape(1, 1, 2))
    closed = []
    dataset = SimpleNamespace(
        variables=variables,
        USE_THETA_M=1,
        dimensions={name: SimpleNamespace(size=size) for name, size in
                    (("west_east", 2), ("south_north", 1), ("bottom_top", 2))},
        close=lambda: closed.append(True),
    )
    monkeypatch.setitem(sys.modules, "netCDF4",
                        SimpleNamespace(Dataset=lambda path: dataset))
    return variables, closed


@pytest.mark.parametrize("bad", [0.0, 1.5, -999.0])
def test_review208_frame_rejects_invalid_xland_before_ccn_fallback(synthetic_frame, bad):
    variables, closed = synthetic_frame
    variables["XLAND"].data[0, 0, 0] = bad
    with pytest.raises(ValueError, match="XLAND.*categorical"):
        read_wrfout_frame("synthetic", nccn_policy="init_profile")
    assert closed == [True]


def test_review208_distance_first_can_assign_unusable_nearest_observation():
    """Record the retained distance-first owner policy at its boundary."""
    payload = ObsPayload(
        bt=torch.tensor([[250.0], [260.0]], dtype=F64),
        obs_quality=torch.tensor([[1.0], [0.0]], dtype=F64),
        lat=torch.tensor([35.0, 35.01], dtype=F64),
        lon=torch.tensor([125.0, 125.0], dtype=F64),
    )
    # The flagged row is exactly on the first grid point; the usable row is
    # farther away and collides with that same point.  Ownership is assigned
    # by distance before the quality mask is propagated to the payload.
    result = payload_to_column_obs(
        payload,
        torch.tensor([35.0, 35.1], dtype=F64),
        torch.tensor([125.0, 126.0], dtype=F64),
        max_dist_km=20.0,
    )
    assert result.col_of_obs.tolist() == [0, -1]
    assert float(result.obs_quality[0, 0]) == 1.0
