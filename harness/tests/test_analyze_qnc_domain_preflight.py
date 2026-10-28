"""Regression on the executed 54-layer QNC preflight and its joins."""
import json
from pathlib import Path

import pytest

from harness.analyze_qnc_domain_preflight import analyze, read_advect, read_writer
from harness.native_qnc_domain_preflight_advect_overlay import failure_layer_coordinates


EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"
PACKET = EVIDENCE / "native_qnc_domain_preflight_2026-10-28"
ROWS = (EVIDENCE / "native_qnc_host_backoff_review_2026-10-28"
        / "residual_reason_rows.json").read_bytes()
TARGETS = failure_layer_coordinates(ROWS)


def _case(case: str):
    root = PACKET / "data" / case
    return read_advect(root / "advect.tsv", TARGETS), read_writer(root / "rk_writer.tsv")


def test_selected_layer_divergence_and_prior_target_join():
    control, control_writer = _case("control")
    alpha, alpha_writer = _case("alpha025")
    result = analyze(control, control_writer, alpha, alpha_writer, ROWS)
    assert result["control"]["category_counts"] == {
        "applied_correction_exceeds_available": 7, "rk3_positive": 47}
    assert result["alpha025"]["category_counts"] == {
        "applied_correction_exceeds_available": 48,
        "exact_positive_but_stored_nonpositive": 6}
    assert result["paired_category_counts"] == {
        "applied_correction_exceeds_available__to__applied_correction_exceeds_available": 7,
        "rk3_positive__to__applied_correction_exceeds_available": 41,
        "rk3_positive__to__exact_positive_but_stored_nonpositive": 6,
    }
    previous = json.loads((EVIDENCE / "native_qnc_saved_face_probe_2026-10-28"
                           / "analysis.json").read_text())
    for case in ("control", "alpha025"):
        assert (result[case]["cells"]["i113_j70_k12"]["applied_face_residual_exact"]["exact"]
                == previous[case]["original_exact_saved_face"]["residual"]["exact"])


def test_missing_or_changed_face_row_is_rejected(tmp_path: Path):
    original = (PACKET / "data/alpha025/advect.tsv").read_text()
    lines = original.splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("VAL "))
    missing = tmp_path / "missing.tsv"
    missing.write_text("\n".join(lines[:first] + lines[first + 1:]) + "\n")
    with pytest.raises(ValueError, match="missing a tile or liquid target"):
        read_advect(missing, TARGETS)

    words = lines[first].split()
    words[-1] = "7F800000"
    lines[first] = " ".join(words)
    nonfinite = tmp_path / "nonfinite.tsv"
    nonfinite.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="nonfinite f32 word"):
        read_advect(nonfinite, TARGETS)


def test_writer_old_buffer_or_qnc_tamper_breaks_join():
    control, writer = _case("control")
    alpha, alpha_writer = _case("alpha025")
    key = (3, "RKSCALAR_BEFORE", 113, 12, 70, "SCALAR_OLD")
    original = writer["values"][key]
    writer["values"][key] = ("f32", f"{int(original[1], 16) + 1:08X}")
    with pytest.raises(ValueError, match="PD-prepared old buffer/live QNC handoff differs"):
        analyze(control, writer, alpha, alpha_writer, ROWS)


def test_writer_rejects_wrong_boolean_dtype(tmp_path: Path):
    raw = (PACKET / "data/alpha025/rk_writer.tsv").read_text()
    changed = raw.replace("TENDEC\tbool\t00", "TENDEC\tf32\t00000000", 1)
    assert changed != raw
    path = tmp_path / "wrong_dtype.tsv"
    path.write_text(changed)
    with pytest.raises(ValueError, match="step/dtype differs"):
        read_writer(path)


def test_writer_rejects_unknown_field(tmp_path: Path):
    raw = (PACKET / "data/alpha025/rk_writer.tsv").read_text()
    extra = "VAL\t3\t3\tRKSCALAR_AFTER\t113\t12\t70\tEXTRA\tf32\t00000000\n"
    path = tmp_path / "extra.tsv"
    path.write_text(raw + extra)
    with pytest.raises(ValueError, match="step/dtype differs"):
        read_writer(path)


def test_writer_rejects_missing_allowed_row(tmp_path: Path):
    original = (PACKET / "data/control/rk_writer.tsv").read_text().splitlines()
    lines = [line for line in original if not (
        line.startswith("VAL") and line.split()[2:8] ==
        ["0", "POST_FINISH", "153", "4", "111", "QI"])]
    assert len(lines) == len(original) - 1
    path = tmp_path / "missing_row.tsv"
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="record inventory differs"):
        read_writer(path)


def test_advect_rejects_nonowner_coordinate(tmp_path: Path):
    lines = (PACKET / "data/alpha025/advect.tsv").read_text().splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith("VAL "))
    words = lines[index].split()
    words[5] = "0"  # i is outside the recorded tile and native domain.
    lines[index] = " ".join(words)
    path = tmp_path / "nonowner.tsv"
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="not owned by recorded tile"):
        read_advect(path, TARGETS)


def test_advect_rejects_overlapping_tile_interiors(tmp_path: Path):
    lines = (PACKET / "data/alpha025/advect.tsv").read_text().splitlines()
    changed = []
    for line in lines:
        if line.startswith("CALL 1 "):
            words = line.split()
            words[16] = "283"  # JTE for the first tile; now overlaps tile 2.
            line = " ".join(words)
        elif line.startswith("VAL 1 "):
            words = line.split()
            words[19] = "283"  # Matching JTE in every first-tile value row.
            line = " ".join(words)
        changed.append(line)
    path = tmp_path / "overlap.tsv"
    path.write_text("\n".join(changed) + "\n")
    with pytest.raises(ValueError, match="tile interiors overlap"):
        read_advect(path, TARGETS)
