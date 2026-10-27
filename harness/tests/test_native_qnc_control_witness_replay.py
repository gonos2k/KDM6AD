from __future__ import annotations

import json
from pathlib import Path
import runpy
import shutil

import pytest


REPO = Path(__file__).resolve().parents[2]
PACKET = REPO / "harness/evidence/native_qnc_control_witness_2026-10-28"


def test_same_level_control_witness_counts_and_scope():
    replay = runpy.run_path(str(PACKET / "replay.py"))
    result = replay["build_analysis"]()
    summary = result["summary"]
    assert summary["profile_count"] == 54
    assert summary["candidate_liquid_failure_layer_count"] == 54
    assert summary["candidate_ice_failure_layer_count"] == 1
    assert summary["control_repair_layer_counts"] == {"positive_NC_with_positive_QC": 54,
                                                       "QI_zero": 1}
    assert summary["new_liquid_failure_origin_counts"] == {"ready_positive_NC": 27,
                                                            "ready_QC_NC_zero": 2}
    assert summary["ready_final_layer_overlap"] == {
        "same_layer_both": 20, "ready_only": 8, "final_only": 35,
        "disjoint_ready_final_profiles": 5}
    assert summary["liquid_final_layers_by_native_k"]["4"] == 21
    assert summary["new_liquid_final_layers_by_native_k"]["4"] == 15
    assert result["ice_subnormal_witness"] == {
        "flat_index_zero_based": 39078, "native_ijk_one_based": [1, 168, 33],
        "ready_QI_hex": "00000007", "final_alpha_QI_hex": "00000002",
        "control_QI_hex": "00000000", "NI_hex_all_boundaries": "00000000"}
    assert result["limits"]["named_process_cause_identified"] is False
    assert result["offline_model_calls"] == {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0}


def test_control_witness_replay_rejects_zero_control_nc_at_liquid_failure(tmp_path, monkeypatch):
    copied = tmp_path / "packet"
    shutil.copytree(PACKET, copied)
    path = copied / "control_witness_rows.json"
    data = json.loads(path.read_text())
    first = data["rows"][0]["final_failed_levels"][0]
    assert first["final_reason"] == "liquid"
    first["control_f32_hex"]["QNCLOUD"] = "00000000"
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    replay = runpy.run_path(str(PACKET / "replay.py"))
    monkeypatch.setitem(replay["build_analysis"].__globals__, "PACKET", copied)
    with pytest.raises(ValueError, match="control witness still has a hard moment failure"):
        replay["build_analysis"]()


def test_control_witness_current_producer_source_is_pinned(tmp_path, monkeypatch):
    manifest = json.loads((PACKET / "manifest.json").read_text())
    copied_repo = tmp_path / "repository"
    for name in manifest["external_source_pins"]:
        target = copied_repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, target)
    producer = copied_repo / "harness/native_qnc_control_witness_producer.py"
    producer.write_text(producer.read_text() + "\n# source drift\n")
    replay = runpy.run_path(str(PACKET / "replay.py"))
    monkeypatch.setitem(replay["main"].__globals__, "REPO", copied_repo)
    with pytest.raises(ValueError, match="control-witness current source differs"):
        replay["main"]()
