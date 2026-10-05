"""The frozen dual identity must retain the run_k BT coordinate tag."""
from types import SimpleNamespace

from kdm6 import da_dual


def _callback():
    def run_k(value):
        return ("unchanged", value)

    run_k.solar_channels = ()
    return run_k


def test_frozen_run_k_bt_coordinate_changes_fingerprint_and_is_snapshotted():
    native = _callback()
    native.bt_coordinate = "rttov_native"
    kma = _callback()
    kma.bt_coordinate = "kma_v3_0"

    native_cfg = da_dual._freeze_obs_cfg(SimpleNamespace(run_k=native))
    kma_cfg = da_dual._freeze_obs_cfg(SimpleNamespace(run_k=kma))
    native_before = da_dual._obs_cfg_fingerprint(native_cfg)
    kma_before = da_dual._obs_cfg_fingerprint(kma_cfg)

    assert native_before != kma_before
    assert native_cfg.run_k.bt_coordinate == "rttov_native"
    assert kma_cfg.run_k.bt_coordinate == "kma_v3_0"
    assert native_cfg.run_k.solar_channels == kma_cfg.run_k.solar_channels == ()
    assert native_cfg.run_k("input") == kma_cfg.run_k("input") == ("unchanged", "input")

    # The callback's executable is still the same callable, while the identity
    # tag is frozen independently of later mutation on the original function.
    kma.bt_coordinate = "changed_after_freeze"
    assert kma_cfg.run_k.bt_coordinate == "kma_v3_0"
    assert da_dual._obs_cfg_fingerprint(kma_cfg) == kma_before


def test_missing_bt_coordinate_keeps_solar_and_legacy_fingerprint_stable():
    callback = _callback()
    callback.solar_channels = (1, 2)
    frozen = da_dual._freeze_obs_cfg(SimpleNamespace(run_k=callback))
    fingerprint = da_dual._obs_cfg_fingerprint(frozen)

    assert frozen.run_k.bt_coordinate is None
    assert frozen.run_k.solar_channels == (1, 2)
    assert frozen.run_k("value") == ("unchanged", "value")
    assert da_dual._obs_cfg_fingerprint(frozen) == fingerprint
