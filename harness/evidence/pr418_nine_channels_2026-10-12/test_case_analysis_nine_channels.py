"""Focused synthetic coverage for the explicit nine-channel case route."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

import numpy as np
import pytest

PACKET = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
PR407 = ROOT / "harness/evidence/pr407_native_saved_time_bound_2026-10-11"
CHANNELS_7 = tuple(range(10, 17))
CHANNELS_9 = tuple(range(8, 17))


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# Reuse the existing bound-payload fixture and synthetic H callback. The bound
# PR407 source files stay unchanged and the callback never launches RTTOV.
adapter_tests = _module(
    "pr418_bound_case_fixture", PR407 / "test_case_analysis_adapter.py")
driver = _module("pr418_nine_channel_driver", PACKET / "run_case_analysis_nine.py")
da_fixture = _module("pr418_existing_da_fixture", ROOT / "oracle/tests/test_da_single_column.py")


def _ready_case(tmp_path: Path):
    scratch = tmp_path / "case-fixture"
    scratch.mkdir()
    return adapter_tests.bound_ready_case(scratch)


def _nine_context(tmp_path: Path, ready_data):
    legacy = driver.load_module(driver.LEGACY_DRIVER, "pr418_nine_channel_primitives")
    template = tmp_path / "case-fixture" / "template"
    return driver.build_inputs(ready_data["manifest"], ready_data["arrays"],
        tmp_path / "fixture-copy", template, legacy, channels=CHANNELS_9)


def test_driver_loads_pr407_capture_adapter_by_explicit_path(monkeypatch):
    sentinel = SimpleNamespace(
        load_module=lambda *args, **kwargs: pytest.fail("cached adapter was reused"))
    monkeypatch.setitem(sys.modules, "case_capture_adapter", sentinel)
    reloaded = _module("pr418_nine_driver_import_guard", PACKET / "run_case_analysis_nine.py")
    loaded_path = Path(reloaded._capture_adapter.__file__).resolve()
    assert loaded_path == (PR407 / "case_capture_adapter.py").resolve()


@pytest.mark.parametrize("channels, expected", [
    (CHANNELS_7, np.arange(282.0, 289.0)),
    (CHANNELS_9, np.arange(280.0, 289.0)),
])
def test_observation_values_preserve_selected_physical_channel_order(
        tmp_path, channels, expected):
    _, _, _, ready, _ = _ready_case(tmp_path)
    bt, dqf = driver.observation_values(ready["manifest"], channels)
    np.testing.assert_array_equal(bt, expected)
    np.testing.assert_array_equal(dqf, np.zeros(len(channels)))


def test_nine_channel_inputs_record_exact_payload_binding(tmp_path):
    ready = _ready_case(tmp_path)
    _, _, _, ready_data, _ = ready
    ctx = _nine_context(tmp_path, ready_data)
    manifest = ready_data["manifest"]
    binding = ctx["run_manifest"]["observation_channel_binding"]
    assert tuple(ctx["rttov_cfg"]["channels"]) == CHANNELS_9
    assert tuple(ctx["clear_cfg"].input_cfg.channels) == CHANNELS_9
    assert tuple(ctx["y_bt"].shape) == tuple(ctx["y_rq"].shape) == (1, 9)
    assert binding["payload_sha256"] == manifest["observation"]["payload_sha256"]
    assert binding["payload_channel_order"] == list(driver.L1B_CHANNEL_ORDER)
    assert binding["selected_ami_physical_ids"] == list(CHANNELS_9)
    assert binding["selected_channel_names"] == list(driver.L1B_CHANNEL_ORDER)
    assert binding["selected_bt_exactly_matches_bound_point"] is True
    assert binding["all_selected_source_dqf_zero"] is True


def test_nine_channel_observation_rejects_order_hash_and_flag_mismatches(tmp_path):
    _, _, _, ready, _ = _ready_case(tmp_path)
    manifest = copy.deepcopy(ready["manifest"])
    manifest["observation"]["reader_metadata_channels"] = list(
        reversed(driver.L1B_CHANNEL_ORDER))
    with pytest.raises(ValueError, match="exact L1B payload channel order"):
        driver.observation_values(manifest, CHANNELS_9)

    manifest = copy.deepcopy(ready["manifest"])
    manifest["observation"]["payload_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="payload SHA"):
        driver.observation_values(manifest, CHANNELS_9)

    source = ready["manifest"]["observation"]["payload_path"]
    changed_payload = tmp_path / "flagged-wv063.npz"
    with np.load(source, allow_pickle=False) as archive:
        arrays = {key: archive[key].copy() for key in archive.files}
    arrays["20250720_patch_reader_dqf"][2, 2, 0] = 1.0
    np.savez(changed_payload, **arrays)
    manifest = copy.deepcopy(ready["manifest"])
    obs = manifest["observation"]
    obs["payload_path"] = str(changed_payload)
    obs["payload_sha256"] = driver.sha(changed_payload)
    obs["nearest_pixel"]["reader_dqf_by_channel"]["wv063"] = 1.0
    with pytest.raises(ValueError, match="selected-channel point"):
        driver.observation_values(manifest, CHANNELS_9)


def _run_capture(tmp_path: Path, monkeypatch, *, background_qc_flag=False):
    _, manifest_path, npz_path, ready, _ = _ready_case(tmp_path)
    ctx = _nine_context(tmp_path, ready)
    synthetic_inputs = (
        ctx["xb"], (ctx["forcing"],), ctx["y_bt"], ctx["y_rq"], ctx["xland"],
        ctx["clear_cfg"], ctx["rttov_cfg"], ctx["window_config"])
    observed_h_calls = da_fixture._install_synthetic_allsky(
        monkeypatch, background_qc_flag=background_qc_flag,
        bad_channel=0, inputs=synthetic_inputs)
    capture = driver.prepare_capture_module()
    checkpoint = tmp_path / "capture" / "private" / "accepted.npz"
    receipt_path = tmp_path / "capture" / "CAPTURE.json"
    result = capture.run_capture(
        xb=ctx["xb"], forcings=(ctx["forcing"],), y_bt=ctx["y_bt"], y_rq=ctx["y_rq"],
        xland=ctx["xland"], clear_cfg=ctx["clear_cfg"], rttov_cfg=ctx["rttov_cfg"],
        window_config=ctx["window_config"], obs_time=1,
        pool=da_fixture.InlinePool(), max_iter=3, channels=CHANNELS_9,
        private_checkpoint=checkpoint, public_receipt=receipt_path,
        case_root=tmp_path / "capture" / "h_cases",
        native_intake_context_path=manifest_path,
        native_intake_context_sha256=driver.sha(manifest_path),
        native_intake_npz_path=npz_path,
        native_intake_npz_sha256=driver.sha(npz_path),
        run_manifest=ctx["run_manifest"])
    return result, checkpoint, receipt_path, observed_h_calls, ctx


def test_nine_channel_capture_audit_and_private_public_roundtrip(tmp_path, monkeypatch):
    result, checkpoint, receipt_path, calls, ctx = _run_capture(tmp_path, monkeypatch)
    assert result["status"] == "RETURNED_DIAGNOSTIC_ONLY"
    assert result["objective"]["n_valid"] == 9
    assert result["adapter_metadata"]["channels_ami_physical_ids"] == list(CHANNELS_9)
    assert result["adapter_metadata"]["n_valid_background"] == 9
    assert result["objective"]["initial_zero_control_closure"]["n_valid"] == 9
    assert result["objective"]["final_audit_signature"]["n_valid_each_trace_entry"] == 9
    assert len(result["logical_h_calls"]) == len(calls) >= 3
    assert all(np.asarray(call["target_BT_K"]).shape == (1, 9)
               for call in result["logical_h_calls"])
    assert all(np.asarray(call["rad_quality"]).shape == (1, 9)
               and np.all(np.asarray(call["rad_quality"]) == 0)
               for call in result["logical_h_calls"])
    assert stat.S_IMODE(checkpoint.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(checkpoint.stat().st_mode) == 0o600
    with np.load(checkpoint, allow_pickle=False) as archive:
        np.testing.assert_array_equal(
            archive["observation_y_bt_K"], ctx["y_bt"].detach().cpu().numpy())
        assert archive["observation_y_bt_K"].shape == (1, 9)
        assert archive["final_slot_bt_K"].shape == (1, 9)
        assert archive["final_slot_rad_quality"].shape == (1, 9)
        assert archive["final_slot_frozen_mask"].shape == (1, 9)
        metadata = json.loads(archive["capture_metadata_json_utf8"].tobytes().decode())
    assert metadata["channels_ami_physical_ids"] == list(CHANNELS_9)
    assert metadata["run_manifest"]["observation_channel_binding"]["payload_sha256"] == ctx[
        "run_manifest"]["observation_channel_binding"]["payload_sha256"]
    saved_receipt = json.loads(receipt_path.read_text())
    assert saved_receipt["observations"]["channels_ami_physical_ids"] == list(CHANNELS_9)
    assert saved_receipt["observations"]["channel_binding"]["validation"] == (
        "supplemental_nine_channel_payload_binding")
    assert saved_receipt["objective"]["n_valid"] == 9

    audit = driver._audit_initial_objectives_selected(
        result, ctx["y_bt"], expected_channels=9)
    assert audit["status"] == "CROSSCHECKED"
    assert audit["expected_channel_count"] == 9
    assert audit["crosschecks"]["probe_target_matches_validated_observation"] is True

    bad_count = copy.deepcopy(result)
    bad_count["objective"]["initial_zero_control_closure"]["n_valid"] = 8
    assert driver._audit_initial_objectives_selected(
        bad_count, ctx["y_bt"], expected_channels=9)["status"] == "MISMATCH"

    lost_support = copy.deepcopy(result)
    lost_support["objective"]["initial_zero_control_closure"]["frozen_mask"][
        "values"][0][0] = 0.0
    first_grad = next(call for call in lost_support["logical_h_calls"]
                      if call.get("grad") is True)
    first_grad["fixed_mask"][0][0] = 0.0
    assert driver._audit_initial_objectives_selected(
        lost_support, ctx["y_bt"], expected_channels=9)["status"] == "MISMATCH"

    lost_zero_probe = copy.deepcopy(result)
    lost_zero_probe["background_quality_probe"]["mask"]["values"][0][0] = 1.0
    assert driver._audit_initial_objectives_selected(
        lost_zero_probe, ctx["y_bt"], expected_channels=9)["status"] == "MISMATCH"


def test_nine_channel_background_model_quality_32768_aborts_before_checkpoint(
        tmp_path, monkeypatch):
    result, checkpoint, _, calls, _ = _run_capture(
        tmp_path, monkeypatch, background_qc_flag=True)
    assert result["status"] == "ANALYSIS_EXCEPTION"
    assert "n_valid=8, required=9" in json.dumps(result)
    assert result["callback_attempt_metadata"]
    assert result["callback_attempt_metadata"][0]["rad_quality"][0][0] == 32768.0
    assert result["optimizer_observation"]["constructor_calls"] == 0
    assert result["optimizer_observation"]["step_calls"] == 0
    assert not checkpoint.exists()
