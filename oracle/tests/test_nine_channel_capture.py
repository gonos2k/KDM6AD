"""Portable nine-channel capture audit using a synthetic H and provenance gate."""
from __future__ import annotations

import copy
import dataclasses
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
import torch

ROOT = Path(__file__).resolve().parents[2]
CHANNELS_9 = tuple(range(8, 17))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


da_fixture = _load("portable_nine_channel_da_fixture",
                   ROOT / "oracle/tests/test_da_single_column.py")
driver = _load(
    "portable_nine_channel_driver",
    ROOT / "harness/evidence/pr418_nine_channels_2026-10-12/run_case_analysis_nine.py")


def _synthetic_capture(tmp_path, monkeypatch, *, background_quality_flag=False,
                       source_reader_change=None):
    xb, forcing_window, y_bt, y_rq, xland, clear_cfg, rttov_cfg, window = (
        da_fixture._inputs(k=39, channels=CHANNELS_9))
    forcing = forcing_window[0]
    window = dataclasses.replace(
        window, ncmin_land=10.0, ncmin_sea=10.0, active_fields=("th", "qv"))
    rttov_cfg = dict(rttov_cfg, ncmin_land=10.0, ncmin_sea=10.0)
    mass = np.ones((8, 39), dtype=np.float32)
    arrays = {
        "rho_d_native_bottomup_kg_m3": rttov_cfg["rho_d"].detach().cpu().numpy().copy(),
        "p_lay_rttov_topdown_hPa": rttov_cfg["p_lay"].detach().cpu().numpy().copy(),
        "p_half_rttov_topdown_hPa": rttov_cfg["p_half"].detach().cpu().numpy().copy(),
        "p_half_native_bottomup_Pa": (
            rttov_cfg["p_half"].flip(-1).detach().cpu().numpy() * 100.0).astype(np.float32),
        "native_window_host_dry_mass_kg_m2": mass.copy(),
        "host_dry_mass_background_kg_m2": mass[0].copy(),
    }
    intake_binding = {
        "path": "synthetic-test-only://manifest",
        "sha256": "0" * 64,
        "npz_path": "synthetic-test-only://arrays",
        "npz_sha256": "1" * 64,
        "actual_saved_times": ["synthetic-bg", "synthetic-slot"],
        "host_dry_mass_background": {
            "source_key": "synthetic-test-only",
            "units": "synthetic test fixture; no native host input",
        },
    }
    run_manifest = {
        "case_id": "SYNTHETIC_NINE_CHANNEL_CAPTURE",
        "obs_time": 1, "dt_s": 20, "max_iter": 3,
        "observation_sigma_K": 1.0, "observation_bias_K": 0.0,
        "huber_delta_K": 1.0, "th_sigma_K": 0.8,
        "qv_sigma_log": 0.08, "qv_levels_from_bottom": 12,
        "non_tq_state_sigmas_zero": True,
        "parameter_prior_active": [], "partition_control": False,
        "pseudo_rh": False, "warm_start": False, "automatic_retry": False,
        "ncmin_land": 10.0, "ncmin_sea": 10.0,
        "observation_channel_binding": {
            "validation": "synthetic-test-only",
            "selected_ami_physical_ids": list(CHANNELS_9),
        },
    }
    staged_reader = None
    if source_reader_change is not None:
        legacy = driver.load_module(driver.LEGACY_DRIVER, "source_mutation_test_primitives")
        original_reader = Path(legacy.NATIVE_READER).resolve()
        staged_reader = tmp_path / "staged_geometry_reader.py"
        staged_reader.write_bytes(original_reader.read_bytes())
        original_path_builder = driver._analysis_source_paths

        def paths_with_staged_reader(module):
            return tuple(
                staged_reader if Path(path).resolve() == Path(module.NATIVE_READER).resolve()
                else path
                for path in original_path_builder(module))

        monkeypatch.setattr(driver, "_analysis_source_paths", paths_with_staged_reader)
    capture = driver.prepare_capture_module()

    def synthetic_provenance(_xb, _forcings, *_args):
        assert tuple(_xb.th.shape) == (1, 39)
        return intake_binding, {}, arrays, {"synthetic_only": True}

    monkeypatch.setattr(capture, "_validate_intake_binding", synthetic_provenance)
    h_calls = da_fixture._install_synthetic_allsky(
        monkeypatch, background_qc_flag=background_quality_flag,
        bad_channel=0, inputs=(xb, (forcing,), y_bt, y_rq, xland, clear_cfg,
                                rttov_cfg, window))
    if staged_reader is not None:
        synthetic_h = da_fixture.fd.sharded_allsky
        mutated = {"done": False}

        def mutate_reader_after_synthetic_h(*args, **kwargs):
            output = synthetic_h(*args, **kwargs)
            if not mutated["done"]:
                if source_reader_change == "remove":
                    staged_reader.unlink()
                else:
                    staged_reader.write_bytes(
                        staged_reader.read_bytes() + b"\n# synthetic mutation\n")
                mutated["done"] = True
            return output

        monkeypatch.setattr(da_fixture.fd, "sharded_allsky", mutate_reader_after_synthetic_h)
    checkpoint = tmp_path / "private" / "accepted.npz"
    receipt_path = tmp_path / "capture.json"
    result = capture.run_capture(
        xb=xb, forcings=(forcing,), y_bt=y_bt, y_rq=y_rq, xland=xland,
        clear_cfg=clear_cfg, rttov_cfg=rttov_cfg, window_config=window,
        obs_time=1, pool=da_fixture.InlinePool(), max_iter=3, channels=CHANNELS_9,
        private_checkpoint=checkpoint, public_receipt=receipt_path,
        case_root=tmp_path / "synthetic-H", native_intake_context_path=tmp_path / "unused.json",
        native_intake_context_sha256="synthetic-test-only",
        native_intake_npz_path=tmp_path / "unused.npz",
        native_intake_npz_sha256="synthetic-test-only", run_manifest=run_manifest)
    return result, checkpoint, receipt_path, h_calls, y_bt, staged_reader


def test_nine_channel_capture_roundtrip_and_selected_count_audit(tmp_path, monkeypatch):
    result, checkpoint, receipt_path, h_calls, y_bt, _ = _synthetic_capture(
        tmp_path, monkeypatch)
    assert result["status"] == "RETURNED_DIAGNOSTIC_ONLY"
    assert result["objective"]["n_valid"] == 9
    assert result["adapter_metadata"]["channels_ami_physical_ids"] == list(CHANNELS_9)
    assert result["objective"]["initial_zero_control_closure"]["n_valid"] == 9
    assert result["objective"]["final_audit_signature"]["n_valid_each_trace_entry"] == 9
    assert len(result["logical_h_calls"]) == len(h_calls) >= 3
    assert all(call["channels"] == list(CHANNELS_9) for call in result["logical_h_calls"])
    assert all(np.asarray(call["rad_quality"]).shape == (1, 9)
               and np.all(np.asarray(call["rad_quality"]) == 0)
               for call in result["logical_h_calls"])

    audit = driver._audit_initial_objectives_selected(
        result, y_bt, expected_channels=9)
    assert audit["status"] == "CROSSCHECKED"
    assert audit["expected_channel_count"] == 9
    wrong_count = copy.deepcopy(result)
    wrong_count["objective"]["initial_zero_control_closure"]["n_valid"] = 8
    assert driver._audit_initial_objectives_selected(
        wrong_count, y_bt, expected_channels=9)["status"] == "MISMATCH"

    with np.load(checkpoint, allow_pickle=False) as saved:
        assert saved["observation_y_bt_K"].shape == (1, 9)
        assert saved["observation_y_dqf"].shape == (1, 9)
        assert saved["final_slot_bt_K"].shape == (1, 9)
        assert saved["final_slot_rad_quality"].shape == (1, 9)
        assert saved["final_slot_frozen_mask"].shape == (1, 9)
        np.testing.assert_array_equal(saved["observation_y_bt_K"], y_bt.numpy())
        metadata = json.loads(saved["capture_metadata_json_utf8"].tobytes().decode())
    assert metadata["channels_ami_physical_ids"] == list(CHANNELS_9)
    assert json.loads(receipt_path.read_text())["observations"][
        "channels_ami_physical_ids"] == list(CHANNELS_9)


def test_background_model_quality_32768_aborts_before_optimizer_or_checkpoint(
        tmp_path, monkeypatch):
    result, checkpoint, _, _, _, _ = _synthetic_capture(
        tmp_path, monkeypatch, background_quality_flag=True)
    assert result["status"] == "ANALYSIS_EXCEPTION"
    assert "n_valid=8, required=9" in json.dumps(result)
    assert result["callback_attempt_metadata"][0]["rad_quality"][0][0] == 32768.0
    assert result["optimizer_observation"]["constructor_calls"] == 0
    assert result["optimizer_observation"]["step_calls"] == 0
    assert not checkpoint.exists()


@pytest.mark.parametrize("source_reader_change", ["modify", "remove"])
def test_geometry_reader_source_change_is_saved_in_failure_receipt(
        tmp_path, monkeypatch, source_reader_change):
    result, checkpoint, receipt_path, _, _, staged_reader = _synthetic_capture(
        tmp_path, monkeypatch, source_reader_change=source_reader_change)
    assert result["status"] == "ANALYSIS_EXCEPTION"
    assert "tracked KDM/RTTOV sources changed" in result["analysis_exception"]["message"]
    assert result["numerical_return"] == {
        "status": "RETURNED_BUT_CAPTURE_FAILED",
        "analysis_runner_returned": True,
        "minimizer_returned_state": True,
    }
    key = str(staged_reader.resolve())
    before = result["production_source_sha256_before"]
    after = result["production_source_sha256_after"]
    assert key in before and key in after
    assert before[key] != after[key]
    if source_reader_change == "remove":
        assert after[key] is None
    assert json.loads(receipt_path.read_text()) == result
    assert not checkpoint.exists()
