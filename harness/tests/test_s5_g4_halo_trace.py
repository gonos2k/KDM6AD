"""Replay the bounded exact-build S5 caller/halo/output trace artifact."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import s5_g4_halo_trace as replay  # noqa: E402


def test_exact2_trace_recomputes_inputs_halos_and_first_output_difference():
    manifest = (ROOT / "evidence" / "data"
                / "S5_G4_exact2_halo_stencil_trace_2026-09-25.json")
    got = replay.replay(manifest)

    assert got["caller_input_words_compared"] == 297_924
    assert got["caller_input_word_differences"] == 0
    assert got["x2_seam_owner_halo_differences"] == 0
    first = got["first_selected_output_difference"]
    assert (first["stage"], first["group"], first["field"], first["i"]) == (
        2, 2, "ww", 117)
    assert first["different_words"] == 9_890
    ww_counts = {
        row["i"]: row["different_words"]
        for row in got["selected_output_records_with_differences"]
        if row["stage"] == 2 and row["group"] == 2 and row["field"] == "ww"
    }
    assert ww_counts == {117: 9_890, 234: 9_970}
    assert got["full_domain_reopened"] is False
