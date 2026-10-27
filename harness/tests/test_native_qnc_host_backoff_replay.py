from __future__ import annotations

from pathlib import Path
import hashlib
import json
import runpy
import shutil

import numpy as np
import pytest


PACKET = Path(__file__).resolve().parents[1] / "evidence/native_qnc_host_backoff_2026-10-27"


def test_host_backoff_saved_replay_keeps_global_and_block_gates_distinct():
    replay = runpy.run_path(str(PACKET / "replay.py"))
    result = replay["build_analysis"]()
    assert result["host_execution_from_receipts"]["host_steps"] == 4
    assert result["host_execution_from_receipts"]["RTTOV_direct_calls"] == 2
    assert result["support"]["historical_alpha"]["invalid_m0_profiles"] == 55
    assert result["support"]["alpha025"]["invalid_m0_profiles"] == 54
    assert result["support"]["alpha025"]["lost_m0_channel_cells"] == 378
    assert result["support"]["recovered_flat_index"] == 14728
    assert result["cases"]["control"]["target_moments"]["host_moments_post_nc_raw"] == 277381.21875
    assert result["cases"]["alpha025"]["target_moments"]["host_moments_post_nc_raw"] == pytest.approx(1.991152167)
    assert result["cases"]["control"]["target_rttov_layer61"]["hydro_deff"][5] == 52.0
    assert result["cases"]["alpha025"]["target_rttov_layer61"]["hydro_deff"][5] == pytest.approx(5.02)
    assert result["block28_direct"]["control"]["M0_loss"] == 0
    assert result["block28_direct"]["alpha025"]["M0_loss"] == 0
    assert result["block28_direct"]["alpha025"]["target_full_block_row_zero_based"] == 392
    assert result["block28_direct"]["alpha025"]["target_compact_profile_row_zero_based"] == 390
    assert result["block28_direct"]["alpha025"]["target_rttov_profile_directory_one_based"] == 391
    assert result["target_abs_residual_candidate_minus_control_K"][3] == pytest.approx(-0.32598548670910077)
    assert result["full_fixed_support_candidate_cost_defined"] is False
    assert result["offline_replay_model_calls"] == {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0}


def test_host_backoff_replay_rejects_recovered_target_still_invalid(tmp_path, monkeypatch):
    copied = tmp_path / "packet"
    shutil.copytree(PACKET, copied)
    path = copied / "support_masks.npz"
    with np.load(path, allow_pickle=False) as z:
        arrays = {name: np.asarray(z[name]).copy() for name in z.files}
    arrays["alpha025_hard_invalid"][14728] = True
    with path.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
    replay = runpy.run_path(str(PACKET / "replay.py"))
    monkeypatch.setitem(replay["build_analysis"].__globals__, "PACKET", copied)
    with pytest.raises(ValueError, match="hard-admission difference"):
        replay["build_analysis"]()


def test_host_backoff_replay_rejects_wrong_live_density_conversion(tmp_path, monkeypatch):
    copied = tmp_path / "packet"
    shutil.copytree(PACKET, copied)
    path = copied / "target_state.json"
    target = json.loads(path.read_text())
    target["cases"]["alpha025"]["optical_number_conversion"]["rho_d_from_f32_AL_ALB_kg_dry_m3"] = 2.0
    path.write_text(json.dumps(target, indent=2, sort_keys=True) + "\n")
    replay = runpy.run_path(str(PACKET / "replay.py"))
    monkeypatch.setitem(replay["build_analysis"].__globals__, "PACKET", copied)
    with pytest.raises(ValueError, match="dry-number optical gate conversion differs"):
        replay["build_analysis"]()


def test_host_backoff_packet_rejects_generated_bytecode_inventory(tmp_path):
    replay = runpy.run_path(str(PACKET / "replay.py"))
    generated = tmp_path / "__pycache__"
    generated.mkdir()
    bytecode = generated / "replay.cpython-310.pyc"
    bytecode.write_bytes(b"generated")
    with pytest.raises(ValueError, match="unsafe/repeated evidence path"):
        replay["_files"](tmp_path, {"files": [{"path": "__pycache__/replay.cpython-310.pyc",
                                                 "bytes": 9, "sha256": "unused"}]})


def test_host_backoff_replay_rejects_wrong_rttov_profile_count(tmp_path, monkeypatch):
    copied = tmp_path / "packet"
    shutil.copytree(PACKET, copied)
    capture = copied / "data/control/block28_direct.npz"
    with np.load(capture, allow_pickle=False) as z:
        arrays = {name: np.asarray(z[name]).copy() for name in z.files}
    arrays["profile_valid"][0] = False
    with capture.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
    summary_path = copied / "execution_summary.json"
    summary = json.loads(summary_path.read_text())
    summary["block28_direct"]["control"]["capture_sha256"] = hashlib.sha256(capture.read_bytes()).hexdigest()
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    replay = runpy.run_path(str(PACKET / "replay.py"))
    monkeypatch.setitem(replay["build_analysis"].__globals__, "PACKET", copied)
    with pytest.raises(ValueError, match="block28 direct call or fixed support differs"):
        replay["build_analysis"]()


def test_host_backoff_replay_rejects_unbound_hard_mask_producer(tmp_path, monkeypatch):
    copied = tmp_path / "packet"
    shutil.copytree(PACKET, copied)
    receipt_path = copied / "support_mask_producer_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["input_checkpoint_sha256"]["alpha025"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    replay = runpy.run_path(str(PACKET / "replay.py"))
    monkeypatch.setitem(replay["build_analysis"].__globals__, "PACKET", copied)
    with pytest.raises(ValueError, match="hard-mask producer receipt differs"):
        replay["build_analysis"]()
