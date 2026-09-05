"""Focused regressions for the observation/DA boundary audit findings.

These tests use the injected runK seam and synthetic coordinates, so the
boundary contracts remain executable without a local RTTOV binary or host
wrfout asset.
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from kdm6.da_driver import OsseObsConfig, batched_allsky_bt
from kdm6.io.frame_reader import derive_delz, derive_p_pii, derive_rho, derive_th
from kdm6.obs._rttov_reference.rttov_ascii import parse_rttov_ascii_blocks
from kdm6.obs.model_profile_builder import RttovProfileConfig, model_to_rttov_tensors
from kdm6.obs.obs_ingest import ObsPayload, collocate, payload_to_column_obs
from kdm6.obs.rttov_input_builder import RttovInputConfig
from kdm6.rttov_bridge import freeze_dry_air_density
from kdm6.state import Forcing, State


F64 = torch.float64


def _cloud_state() -> State:
    def row(values):
        return torch.tensor(values, dtype=F64).unsqueeze(0)

    z = row([0.0, 0.0])
    return State(
        th=row([296.0, 285.0]), qv=row([0.02, 0.02]),
        qc=row([1.0e-3, 1.0e-3]), qr=row([1.0e-4, 8.0e-5]),
        qi=row([2.0e-4, 1.0e-4]), qs=row([1.0e-4, 5.0e-5]),
        qg=z, nccn=row([1.0e9, 1.0e9]), nc=row([1.0e8, 1.0e8]),
        ni=row([1.0e7, 1.0e7]), nr=row([1.0e4, 1.0e4]), bg=z)


def _cloud_forcing() -> Forcing:
    def row(values):
        return torch.tensor(values, dtype=F64).unsqueeze(0)

    return Forcing(rho=row([1.02, 0.95]), pii=row([0.97, 0.94]),
                   p=row([9.0e4, 7.0e4]), delz=row([500.0, 600.0]))


def _cloud_cfg(rho_d):
    return RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry", cloud=True,
        rttov_layer_pressure=torch.tensor([700.0, 900.0], dtype=F64),
        rttov_level_pressure=torch.tensor([600.0, 800.0, 1000.0], dtype=F64),
        rho_d=rho_d)


def test_allsky_run_k_receives_layer_pressure_witness():
    """The all-sky DA call must carry profile P through pack/runK."""
    state = _cloud_state()
    forcing = _cloud_forcing()
    seen = []

    def run_k(rin):
        seen.append(rin.profile)
        n, nch, nlay = rin.nprofiles, 2, rin.nlayers
        zeros = np.zeros((n, nch, nlay), dtype=np.float64)
        k = {name: zeros.copy() for name in
             ("T", "Q", "HYDRO6", "HYDRO7", "HYDRO_DEFF6", "HYDRO_DEFF7")}
        return np.zeros((n, nch)), k, np.zeros((n, nch))

    cfg = OsseObsConfig(
        run_k=run_k,
        profile_cfg=_cloud_cfg(freeze_dry_air_density(state, forcing)),
        input_cfg=RttovInputConfig(coef_id="audit-p", channels=(1, 2)),
    )
    batched_allsky_bt(state, forcing, cfg)

    assert len(seen) == 1
    assert "P" in seen[0]
    assert np.array_equal(seen[0]["P"], np.array([[700.0, 900.0]]))


def test_empty_collocation_validates_grid_then_returns_empty():
    obs_lat = torch.empty(0, dtype=F64)
    obs_lon = torch.empty(0, dtype=F64)
    grid_lat = torch.tensor([35.0, 35.5], dtype=F64)
    grid_lon = torch.tensor([125.0, 125.5], dtype=F64)

    idx, dist = collocate(obs_lat, obs_lon, grid_lat, grid_lon)
    assert idx.dtype == torch.int64 and idx.numel() == 0
    assert dist.dtype == F64 and dist.numel() == 0

    payload = ObsPayload(
        bt=torch.empty((0, 2), dtype=F64),
        obs_quality=torch.empty((0, 2), dtype=F64),
        lat=obs_lat, lon=obs_lon)
    out = payload_to_column_obs(payload, grid_lat, grid_lon, max_dist_km=10.0)
    assert out.n_assigned == 0 and out.col_of_obs.numel() == 0
    assert torch.equal(out.obs_quality, torch.ones((2, 2), dtype=F64))

    with pytest.raises(ValueError, match="degenerate grid"):
        collocate(obs_lat, obs_lon, torch.zeros(2, dtype=F64),
                  torch.zeros(2, dtype=F64))


def _clear_state_and_forcing():
    z = torch.zeros(3, dtype=F64)
    state = State(th=torch.full((3,), 300.0, dtype=F64),
                  qv=torch.full((3,), 0.01, dtype=F64),
                  qc=z, qr=z, qi=z, qs=z, qg=z, nccn=z, nc=z, ni=z, nr=z, bg=z)
    forcing = Forcing(rho=torch.ones(3, dtype=F64),
                      pii=torch.full((3,), 0.95, dtype=F64),
                      p=torch.tensor([100.0, 300.0, 500.0], dtype=F64),
                      delz=torch.ones(3, dtype=F64))
    cfg = RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=torch.tensor([200.0, 400.0], dtype=F64),
        rttov_level_pressure=torch.tensor([150.0, 250.0, 350.0], dtype=F64))
    return state, forcing, cfg


@pytest.mark.parametrize("field, values, match", [
    ("p", torch.tensor([-1.0, 300.0, 500.0], dtype=F64), "model pressure"),
    ("pii", torch.tensor([0.95, 0.0, 0.95], dtype=F64), "Exner forcing"),
    ("rho", torch.tensor([1.0, -1.0, 1.0], dtype=F64), "air density"),
    ("delz", torch.tensor([1.0, 0.0, 1.0], dtype=F64), "layer height"),
])
def test_profile_rejects_invalid_derived_forcing_domain(field, values, match):
    state, forcing, cfg = _clear_state_and_forcing()
    with pytest.raises(ValueError, match=match):
        model_to_rttov_tensors(state, forcing._replace(**{field: values}), cfg)


def test_profile_rejects_nonpositive_target_and_half_pressure():
    state, forcing, cfg = _clear_state_and_forcing()
    with pytest.raises(ValueError, match="RTTOV layer pressure"):
        model_to_rttov_tensors(
            state, forcing,
            cfg._replace(rttov_layer_pressure=torch.tensor([-1.0, 400.0], dtype=F64)))
    with pytest.raises(ValueError, match="half-level pressure"):
        model_to_rttov_tensors(
            state, forcing,
            cfg._replace(rttov_level_pressure=torch.tensor([-1.0, 250.0, 350.0], dtype=F64)))


def test_frame_derivations_reject_invalid_physical_domains():
    with pytest.raises(ValueError, match="derived pressure"):
        derive_p_pii(torch.tensor([[-2.0]], dtype=F64),
                     torch.tensor([[1.0]], dtype=F64))
    with pytest.raises(ValueError, match="temperature denominator"):
        derive_th(torch.tensor([[0.0]], dtype=F64),
                  torch.tensor([[-2.0]], dtype=F64))
    with pytest.raises(ValueError, match="pressure for density"):
        derive_rho(torch.tensor([[-1.0]], dtype=F64),
                   torch.tensor([[0.0]], dtype=F64),
                   torch.tensor([[0.95]], dtype=F64),
                   torch.tensor([[0.01]], dtype=F64))
    with pytest.raises(ValueError, match="layer thickness"):
        derive_delz(torch.zeros((1, 3), dtype=F64),
                    torch.tensor([[0.0, 1.0, 1.0]], dtype=F64))


def test_rttov_ascii_rejects_malformed_token_instead_of_dropping_it(tmp_path):
    path = tmp_path / "radiance.txt"
    path.write_text("RADIANCE%BT = (\n 1.0 2.0 BAD 4.0\n)\n")
    with pytest.raises(ValueError, match="invalid numeric token.*BAD"):
        parse_rttov_ascii_blocks(path)
