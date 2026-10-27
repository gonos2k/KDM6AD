from __future__ import annotations

import json
from pathlib import Path
import runpy
import shutil

import pytest


REPO = Path(__file__).resolve().parents[2]
PACKET = REPO / "harness/evidence/native_qnc_host_backoff_review_2026-10-28"


def test_current_source_replay_separates_three_observation_baselines():
    replay = runpy.run_path(str(PACKET / "replay.py"))
    result = replay["build_analysis"]()
    rows = result["comparisons"]
    assert result["block"]["M0_profiles"] == 287
    assert result["block"]["M0_channel_cells"] == 2009
    assert rows["original_control"]["target_BT_K"][3] == pytest.approx(285.8225734260864)
    assert rows["variant_control"]["target_BT_K"][3] == pytest.approx(286.1484689544752)
    assert rows["variant_alpha025"]["target_BT_K"][3] == pytest.approx(285.8224834677661)
    assert rows["variant_control"]["M0_changed_profile_count_vs_original"] == 1
    assert rows["variant_alpha025"]["M0_changed_profile_count_vs_original"] == 284
    assert result["target_ir105_bt_difference_K"]["variant_alpha_minus_original"] == pytest.approx(-8.995832030223028e-5)
    assert result["target_ir105_bt_difference_K"]["variant_alpha_minus_variant_control"] == pytest.approx(-0.32598548670910077)
    remaining = result["remaining_full_M0_hard_failures"]
    assert remaining["profile_count"] == 54
    assert remaining["channel_cell_count"] == 378
    assert remaining["reason_profile_counts"] == {
        "liquid_QC_positive_NC_nonpositive": 53,
        "ice_QI_positive_NI_nonpositive": 1,
        "negative_NC": 0,
        "negative_NI": 0,
    }
    assert remaining["already_invalid_at_pre_command_READY40"] == 25
    assert remaining["new_since_pre_command_READY40"] == 29
    assert result["full_fixed_support_candidate_cost_defined"] is False


@pytest.mark.parametrize("source", ("harness/analyze_saved_qnc_scale_backoff.py",
                                    "harness/analyze_native_qnc_saved_state_budget.py",
                                    "harness/native_qnc_residual_reason_producer.py"))
def test_current_replay_rejects_changed_or_legacy_calculator(tmp_path, monkeypatch, source):
    manifest = json.loads((PACKET / "manifest.json").read_text())
    copied_repo = tmp_path / "repository"
    for name in manifest["external_source_pins"]:
        target = copied_repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, target)
    target = copied_repo / source
    if source.endswith("analyze_native_qnc_saved_state_budget.py"):
        archived = (REPO / "harness/evidence/native_qnc_coeff_rounding_2026-10-27/"
                    "source_snapshots/pr462_saved_state_budget.py.txt")
        shutil.copyfile(archived, target)
    else:
        target.write_text(target.read_text() + "\n# comment-only source drift\n")
    replay = runpy.run_path(str(PACKET / "replay.py"))
    monkeypatch.setitem(replay["main"].__globals__, "REPO", copied_repo)
    with pytest.raises(ValueError, match="current host-backoff source changed"):
        replay["main"]()


def test_residual_reason_replay_rejects_inconsistent_raw_words(tmp_path, monkeypatch):
    copied = tmp_path / "packet"
    shutil.copytree(PACKET, copied)
    path = copied / "residual_reason_rows.json"
    data = json.loads(path.read_text())
    data["rows"][0]["failing_level_words"][0]["final_f32_hex"]["QNCLOUD"] = "3F800000"
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    replay = runpy.run_path(str(PACKET / "replay.py"))
    monkeypatch.setitem(replay["build_analysis"].__globals__, "PACKET", copied)
    with pytest.raises(ValueError, match="bitwords/reason stages differ"):
        replay["build_analysis"]()


def test_residual_replay_rejects_post_command_ready_claim(tmp_path, monkeypatch):
    copied = tmp_path / "packet"
    shutil.copytree(PACKET, copied)
    path = copied / "ready_boundary_receipt.json"
    receipt = json.loads(path.read_text())
    receipt["post_command_READY40_checkpoint_observed"] = True
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    replay = runpy.run_path(str(PACKET / "replay.py"))
    monkeypatch.setitem(replay["build_analysis"].__globals__, "PACKET", copied)
    with pytest.raises(ValueError, match="pre-command READY40/analysis TQ boundary receipt differs"):
        replay["build_analysis"]()
