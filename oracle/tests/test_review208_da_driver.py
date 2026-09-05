"""Focused regressions for PR208 DA-driver input contracts."""
from types import SimpleNamespace

import numpy as np
import pytest

from kdm6.da_driver import (OsseObsConfig, WindowConfig,
                            _normalize_obs_times, run_osse_sensitivity)


def test_review208_fractional_osse_time_is_rejected_before_truth_run():
    cfg = SimpleNamespace(run_k=None, profile_cfg=SimpleNamespace(cloud=False),
                           input_cfg=None)
    with pytest.raises(ValueError, match="finite and exactly integral"):
        run_osse_sensitivity(None, None, [], [1.9], WindowConfig(dt=20.0), cfg)


def test_review208_direct_osse_rejects_mixed_scalar_before_truth_h(monkeypatch):
    def run_k(_):
        raise AssertionError("mixed sigma validation must precede the truth H")
    run_k.solar_channels = (1,)
    cfg = OsseObsConfig(
        run_k=run_k, profile_cfg=SimpleNamespace(cloud=False),
        input_cfg=SimpleNamespace(channels=(7, 1)), obs_sigma=1.0)
    # The public OSSE entry point validates the tagged mixed-unit contract
    # before it can invoke the truth-side H or touch the state arguments.
    with pytest.raises(ValueError, match="per-channel"):
        run_osse_sensitivity(None, None, [], [0], WindowConfig(dt=20.0), cfg)


def test_review208_integral_numpy_time_is_normalized_and_bool_is_rejected():
    assert _normalize_obs_times([np.float64(1.0), np.int64(0), "2"], 2) == (1, 0, 2)
    with pytest.raises(TypeError, match="non-bool"):
        _normalize_obs_times([True], 2)


def test_review208_top_profile_references_are_paired():
    with pytest.raises(ValueError, match="t_ref and q_ref"):
        OsseObsConfig(
            run_k=None, profile_cfg=SimpleNamespace(cloud=False),
            input_cfg=None, t_ref=np.array([250.0]))

    cfg = OsseObsConfig(
        run_k=None, profile_cfg=SimpleNamespace(cloud=False), input_cfg=None,
        t_ref=np.array([250.0]), q_ref=np.array([10.0]))
    cfg.q_ref = None
    from kdm6.da_driver import _validate_top_profile_refs
    with pytest.raises(ValueError, match="t_ref and q_ref"):
        _validate_top_profile_refs(cfg)
