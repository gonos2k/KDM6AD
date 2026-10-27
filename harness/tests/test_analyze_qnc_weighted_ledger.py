from __future__ import annotations

from pathlib import Path

import pytest

from harness.analyze_qnc_shared_face_trace import read_shared_trace
from harness.analyze_qnc_weighted_ledger import analyze_weighted_ledger


DATA = Path(__file__).resolve().parents[1] / "evidence/native_qnc_shared_face_2026-10-27/data"


@pytest.mark.parametrize(
    ("case", "face_total", "recorded_total", "residual"),
    (
        ("control", -27767629636.38332, -27767630848.107536, -1211.7242138368),
        ("alpha025", -27767544586.44994, -27767543347.630615, 1238.8193226734645),
    ),
)
def test_saved_seven_cell_ledger_has_exact_internal_cancellation(case, face_total, recorded_total, residual):
    result = analyze_weighted_ledger(
        read_shared_trace(DATA / case / "qnc_shared.tsv"), run_id=case)
    assert len(result["internal_face_component_pairs"]) == 12
    assert all(row["same_face_bits"] and row["exact_coefficient_cancellation"]
               for row in result["internal_face_component_pairs"].values())
    assert result["internal_correction_exact"]["exact"] == "0"
    assert result["internal_low_order_exact"]["exact"] == "0"
    assert result["perimeter_face_incidences"] == 30
    assert result["perimeter_total"]["exact"] == result["exact_face_total"]["exact"]
    assert result["exact_face_total"]["approximately"] == pytest.approx(face_total, abs=1e-5)
    assert result["recorded_weighted_tendency_total"]["approximately"] == pytest.approx(recorded_total, abs=1e-5)
    assert result["recorded_minus_exact_face"]["approximately"] == pytest.approx(residual, abs=1e-9)
    assert result["limits"]["whole_domain_conservation_certified"] is False


@pytest.mark.parametrize(
    ("old", "new"),
    (
        ("VAL 1 RK3_POST 220 6 63 FX_EAST f32 D6E7601F",
         "VAL 1 RK3_POST 220 6 63 FX_EAST f32 D6E7601E"),
        ("VAL 1 RK3_POST 220 6 63 RDZW f32 C252DDF8",
         "VAL 1 RK3_POST 220 6 63 RDZW f32 C252DDF7"),
    ),
)
def test_internal_face_or_metric_mutation_breaks_exact_cancellation(tmp_path, old, new):
    text = (DATA / "control/qnc_shared.tsv").read_text()
    assert text.count(old) == 1
    path = tmp_path / "different.tsv"
    path.write_text(text.replace(old, new, 1))
    with pytest.raises(ValueError, match="internal face failed exact cancellation"):
        analyze_weighted_ledger(read_shared_trace(path), run_id="mutated")
