"""M4 gates for P4 pack_rttov_input (design 7, 14.3).

pack is the torch->numpy serialization boundary: it must (1) detach to numpy (no
grad leak — grad re-enters via K^T·λ_BT, not through this), (2) REQUIRE the four
forced RTTOV options (a wrong option silently changes what BT/K mean), (3) reject
non-finite profiles and a broken layer/level grid, (4) produce a deterministic
config-hash.
"""
from __future__ import annotations

import torch

import pytest

from kdm6.obs.model_profile_builder import RttovProfileTensors
from kdm6.obs.rttov_input_builder import (
    RttovInput,
    RttovInputConfig,
    pack_rttov_input,
)

F64 = torch.float64


def _profile(nlay=4, requires_grad=False):
    t = torch.linspace(250.0, 290.0, nlay, dtype=F64).requires_grad_(requires_grad)
    q = torch.linspace(10.0, 5000.0, nlay, dtype=F64).requires_grad_(requires_grad)
    p_lay = torch.linspace(200.0, 900.0, nlay, dtype=F64)
    p_half = torch.linspace(150.0, 1000.0, nlay + 1, dtype=F64)
    return RttovProfileTensors(t_lay=t, q_lay=q, p_lay=p_lay, p_half=p_half)


def _cfg(**kw):
    base = dict(coef_id="rtcoef_gkompsat2_1_ami_o3co2.dat", channels=tuple(range(1, 17)))
    base.update(kw)
    return RttovInputConfig(**base)


def test_pack_basic_shapes_and_numpy():
    rin = pack_rttov_input(_profile(nlay=4), _cfg())
    assert isinstance(rin, RttovInput)
    assert rin.nprofiles == 1 and rin.nlayers == 4
    assert rin.profile["T"].shape == (1, 4) and rin.profile["Q"].shape == (1, 4)
    assert rin.profile["P_HALF"].shape == (1, 5)
    # numpy boundary: not torch, no grad
    import numpy as np
    assert isinstance(rin.profile["T"], np.ndarray)
    assert len(rin.config_hash) == 16


def test_pack_detaches_no_grad_leak():
    rin = pack_rttov_input(_profile(nlay=4, requires_grad=True), _cfg())
    import numpy as np
    assert isinstance(rin.profile["T"], np.ndarray)  # detached to numpy, graph severed here


@pytest.mark.parametrize("bad", [
    dict(gas_units=1), dict(mmr_hydro=True), dict(adk_bt=False), dict(store_rad=False),
])
def test_forced_options_required(bad):
    with pytest.raises(ValueError, match="forced contract"):
        pack_rttov_input(_profile(), _cfg(**bad))


def test_empty_channels_rejected():
    with pytest.raises(ValueError, match="channels is empty"):
        pack_rttov_input(_profile(), _cfg(channels=()))


def test_empty_coef_rejected():
    with pytest.raises(ValueError, match="coef_id is required"):
        pack_rttov_input(_profile(), _cfg(coef_id=""))


def test_non_finite_profile_rejected():
    p = _profile(nlay=4)
    bad_t = p.t_lay.clone()
    bad_t[2] = float("nan")
    with pytest.raises(ValueError, match="non-finite"):
        pack_rttov_input(p._replace(t_lay=bad_t), _cfg())


def test_layer_level_mismatch_rejected():
    p = _profile(nlay=4)
    bad_half = torch.linspace(150.0, 1000.0, 4, dtype=F64)  # 4 levels, needs 5
    with pytest.raises(ValueError, match="Nlevels"):
        pack_rttov_input(p._replace(p_half=bad_half), _cfg())


def test_config_hash_deterministic_and_sensitive():
    h1 = pack_rttov_input(_profile(), _cfg()).config_hash
    h2 = pack_rttov_input(_profile(), _cfg()).config_hash
    h3 = pack_rttov_input(_profile(), _cfg(channels=(7, 8, 9))).config_hash
    assert h1 == h2          # deterministic
    assert h1 != h3          # sensitive to config (channels)


def test_t_q_shape_consistency():
    p = _profile(nlay=4)
    with pytest.raises(ValueError, match="same profile/layer grid"):
        pack_rttov_input(p._replace(q_lay=torch.linspace(1.0, 2.0, 3, dtype=F64)), _cfg())
