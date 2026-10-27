from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.analyze_qnc_representative_boundaries import analyze
from harness.native_qnc_representative_trace_records import read_representative_trace


ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "evidence/native_qnc_representative_boundaries_2026-10-28"
CONTROL = PACKET / "data/control/representative_moments.tsv"
ALPHA = PACKET / "data/alpha025/representative_moments.tsv"
CONTROL_WITNESS = ROOT / "evidence/native_qnc_control_witness_2026-10-28/control_witness_rows.json"
CANDIDATE = ROOT / "evidence/native_qnc_host_backoff_review_2026-10-28/residual_reason_rows.json"


def test_reader_rejects_missing_recorded_rk_value(tmp_path: Path):
    lines = CONTROL.read_text().splitlines(keepends=True)
    marker = "VAL\t3\t2\tRKSCALAR_AFTER\t113\t12\t70\tQNC\t"
    assert sum(line.startswith(marker) for line in lines) == 1
    changed = tmp_path / "missing.tsv"
    changed.write_text("".join(line for line in lines if not line.startswith(marker)))
    with pytest.raises(ValueError, match="field inventory differs"):
        read_representative_trace(changed)


def test_exact_saved_operand_sign_rejects_wrong_rk3_output(tmp_path: Path):
    lines = CONTROL.read_text().splitlines(keepends=True)
    marker = "VAL\t3\t3\tRKSCALAR_AFTER\t153\t4\t111\tQNC\tf32\t"
    assert sum(line.startswith(marker) for line in lines) == 1
    changed = tmp_path / "wrong_sign.tsv"
    changed.write_text("".join(
        marker + "BF000000\n" if line.startswith(marker) else line for line in lines))
    with pytest.raises(ValueError, match="saved-operand RK3 sign disagrees"):
        analyze(read_representative_trace(changed), read_representative_trace(ALPHA),
                json.loads(CONTROL_WITNESS.read_text()), json.loads(CANDIDATE.read_text()))


def test_checkpoint_join_rejects_wrong_same_level_word():
    control = json.loads(CONTROL_WITNESS.read_text())
    entry = next(row for row in control["rows"] if
                 (row["i_one_based"], row["j_one_based"]) == (153, 111))
    layer = next(layer for layer in entry["final_failed_levels"] if layer["native_k_one_based"] == 4)
    layer["control_f32_hex"]["QNCLOUD"] = "3F800000"
    with pytest.raises(ValueError, match="differs from checkpoint"):
        analyze(read_representative_trace(CONTROL), read_representative_trace(ALPHA),
                control, json.loads(CANDIDATE.read_text()))
