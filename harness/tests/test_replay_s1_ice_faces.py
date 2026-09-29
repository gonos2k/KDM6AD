"""Replay the retained raw and normalized S1 face captures."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("case,caps", [("historical", 9), ("normalized", 0)])
def test_s1_ice_face_replay(case, caps):
    script = Path(__file__).resolve().parents[1] / "replay_s1_dry_ice_faces.py"
    result = subprocess.run([sys.executable, str(script), "--case", case],
                            capture_output=True, text=True, check=True)
    replay = json.loads(result.stdout)
    assert replay["selected_ice_blocks"] == 2
    assert replay["selected"][1]["positive_ice_faces"] == 14
    assert replay["selected"][1]["capped_n"] == caps
    assert not replay["s1_gate_closed"]


def test_first_ice_offer_changes_by_layer_thickness():
    from harness import replay_s1_dry_ice_faces as replay

    old = replay.parse_trace(replay.HERE / "s1_dry_ice_face_trace_2026-09-28.log")
    new = replay.parse_trace(
        replay.HERE / "s1_normalized_ice_face_2026-09-30.log",
        replay.NORMALIZED_TRACE_SHA,
    )
    for k in (15, 24):
        raw, normalized = old[1]["rows"][k], new[1]["rows"][k]
        assert raw["q_before"] == normalized["q_before"]
        assert abs(raw["falk_q"] / normalized["falk_q"] - normalized["dz_raw"]) \
            < 1e-4
