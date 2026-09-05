"""Focused regressions for PR208 shard validation."""
import pytest
import torch

from kdm6.da_parallel import ShardSpec, build_shard_specs, run_sharded_sensitivity
from kdm6.state import Forcing, State


def _state(B=2, K=1):
    return State(*(torch.ones((B, K), dtype=torch.float64)
                   for _ in State._fields))


def _forcing(B=2, K=1):
    return Forcing(*(torch.ones((B, K), dtype=torch.float64)
                     for _ in Forcing._fields))


def test_review208_direct_shard_duplicate_is_rejected_before_worker(monkeypatch):
    x = _state()
    f = _forcing()
    spec = ShardSpec(
        shard_id=0, b_total=2, col_idx=torch.tensor([0, 0, 1]),
        x_truth=x, x_background=x, forcing=f, n_steps=1, dt=20.0,
        obs_times=(), case_root="unused", profile_kwargs={}, input_kwargs={},
        obs_sigma=1.0, t_ref=None, q_ref=None, q_blend_octaves=4.0)

    def fail_if_called(_):
        raise AssertionError("duplicate validation must precede worker execution")
    monkeypatch.setattr("kdm6.da_parallel._shard_worker", fail_if_called)
    with pytest.raises(RuntimeError, match="duplicates"):
        run_sharded_sensitivity([spec], n_workers=1, parallel=False)


def test_review208_shard_builder_rejects_fractional_observation_time(tmp_path):
    x = _state()
    with pytest.raises(ValueError, match="finite and exactly integral"):
        build_shard_specs(
            x, x, _forcing(), [torch.tensor([0, 1])], n_steps=2, dt=20.0,
            obs_times=[1.5], case_root=str(tmp_path), profile_kwargs={},
            input_kwargs={})


def test_review208_shard_builder_rejects_unpaired_profile_refs(tmp_path):
    x = _state()
    for t_ref, q_ref in ((torch.ones(1), None), (None, torch.ones(1))):
        with pytest.raises(ValueError, match="t_ref and q_ref"):
            build_shard_specs(
                x, x, _forcing(), [torch.tensor([0, 1])], n_steps=1, dt=20.0,
                obs_times=[], case_root=str(tmp_path), profile_kwargs={},
                input_kwargs={}, t_ref=t_ref, q_ref=q_ref)


def test_review208_direct_shard_spec_rejects_unpaired_profile_refs():
    x = _state()
    f = _forcing()
    with pytest.raises(ValueError, match="t_ref and q_ref"):
        ShardSpec(
            shard_id=0, b_total=2, col_idx=torch.tensor([0, 1]),
            x_truth=x, x_background=x, forcing=f, n_steps=1, dt=20.0,
            obs_times=(), case_root="unused", profile_kwargs={}, input_kwargs={},
            obs_sigma=1.0, t_ref=torch.ones(1), q_ref=None,
            q_blend_octaves=4.0)


def test_review208_sharded_run_rechecks_mutated_ref_pair_before_worker(monkeypatch):
    x = _state()
    f = _forcing()
    spec = ShardSpec(
        shard_id=0, b_total=2, col_idx=torch.tensor([0, 1]),
        x_truth=x, x_background=x, forcing=f, n_steps=1, dt=20.0,
        obs_times=(), case_root="unused", profile_kwargs={}, input_kwargs={},
        obs_sigma=1.0, t_ref=None, q_ref=None, q_blend_octaves=4.0)
    spec.t_ref = torch.ones(1)

    def fail_if_called(_):
        raise AssertionError("ref-pair validation must precede worker execution")
    monkeypatch.setattr("kdm6.da_parallel._shard_worker", fail_if_called)
    with pytest.raises(ValueError, match="t_ref and q_ref"):
        run_sharded_sensitivity([spec], n_workers=1, parallel=False)
