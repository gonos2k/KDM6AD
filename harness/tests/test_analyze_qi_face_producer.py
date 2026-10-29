from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from harness.analyze_qi_face_producer import PACKET, analyze


def _mutated_packet(tmp_path, replacements: dict[str, str]):
    packet = tmp_path / "packet"
    shutil.copytree(PACKET, packet, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    trace = packet / "data/alpha025/qi_face.tsv"
    lines = trace.read_text().splitlines()
    for original, replacement in replacements.items():
        assert lines.count(original) == 1
        lines[lines.index(original)] = replacement
    trace.write_text("\n".join(lines) + "\n")
    receipt = packet / "execution_summary.json"
    content = json.loads(receipt.read_text())
    content["runs"]["alpha025"]["on"]["trace_sha256"]["qi_face"] = (
        hashlib.sha256(trace.read_bytes()).hexdigest())
    receipt.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n")
    return packet


def test_public_qi_face_analysis_reproduces_saved_result():
    assert analyze() == json.loads((PACKET / "analysis.json").read_text())


def test_applied_vertical_face_must_reproduce_recorded_tendency(tmp_path):
    packet = _mutated_packet(tmp_path, {
        "VAL 3 3 POST 2 33 168 FZ_BOTTOM f32 80000060":
            "VAL 3 3 POST 2 33 168 FZ_BOTTOM f32 80000000",
    })
    with pytest.raises(ValueError, match="applied QI face differs"):
        analyze(packet)


def test_lower_owner_branch_must_match_available_and_outflow(tmp_path):
    packet = _mutated_packet(tmp_path, {
        "VAL 3 3 OWNER 2 32 168 HIT bool 00000000":
            "VAL 3 3 OWNER 2 32 168 HIT bool 00000001",
    })
    with pytest.raises(ValueError, match="limiter branch disagrees"):
        analyze(packet)


def test_west_owner_nonexecution_requires_matching_limiter_bounds(tmp_path):
    packet = _mutated_packet(tmp_path, {
        "VAL 3 3 META 2 33 168 LIM_I_START i32 00000002":
            "VAL 3 3 META 2 33 168 LIM_I_START i32 00000001",
    })
    with pytest.raises(ValueError, match="QI limiter bounds"):
        analyze(packet)


def test_equal_but_impossible_post_face_changes_do_not_cancel_out(tmp_path):
    packet = _mutated_packet(tmp_path, {
        "VAL 3 3 POST 2 33 168 FX_WEST f32 00000000":
            "VAL 3 3 POST 2 33 168 FX_WEST f32 00000001",
        "VAL 3 3 POST 2 33 168 FX_EAST f32 00000000":
            "VAL 3 3 POST 2 33 168 FX_EAST f32 00000001",
    })
    with pytest.raises(ValueError, match="applied QI face differs"):
        analyze(packet)
