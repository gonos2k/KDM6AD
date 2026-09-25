"""Replay the public, bounded selected-window C2 trace artifact."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import s5_g4_selected_trace as replay  # noqa: E402


def test_public_c2_trace_recomputes_first_selected_difference():
    evidence = ROOT / "evidence" / "data"
    got = replay.replay(
        evidence / "S5_G4_C2_selected_trace_2026-09-25.json")

    first = got["first_selected_difference"]
    assert (first["stage"], first["group"], first["field"], first["i"]) == (
        2, 2, "ww", 117)
    assert first["different_words"] == 9890
    assert got["raw_words_compared"] == 4_007_610
    assert got["kdm_TH_selected_words"] == {
        "serial": 1_139_747_349,
        "x2": 1_139_747_350,
    }
    assert got["full_domain_reopened"] is False
