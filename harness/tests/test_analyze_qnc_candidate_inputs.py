"""Selected-donor candidate-input packet and shared-face regressions."""
from copy import deepcopy
from pathlib import Path

import pytest

from harness.analyze_qnc_candidate_inputs import analyze_case, read_faces, read_writer
from harness.native_qnc_candidate_face_overlay import receiver_union
from harness.native_qnc_domain_preflight_advect_overlay import failure_layer_coordinates


EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"
PACKET = EVIDENCE / "native_qnc_candidate_inputs_2026-10-28"
ROWS = (EVIDENCE / "native_qnc_host_backoff_review_2026-10-28"
        / "residual_reason_rows.json").read_bytes()
CAPTURE = receiver_union(ROWS)
DONORS = failure_layer_coordinates(ROWS)


def _case(case: str):
    root = PACKET / "data" / case
    return read_faces(root / "faces.tsv", CAPTURE), read_writer(root / "rk_writer.tsv")


def test_all_selected_shared_faces_and_seam_words_join():
    for case in ("control", "alpha025"):
        faces, writer = _case(case)
        result = analyze_case(faces, writer, DONORS)
        assert result["captured_cells"] == 382
        assert result["source_compatible_cells"] == {"axis_matched": 382, "rk_matched": 382}
        assert result["shared_face_checks"] == {
            "pre": 324, "post": 324, "low": 324, "applied_scale": 324,
            "target_outgoing": 318, "neighbor_outgoing": 6}
        assert len(result["seam_pairs"]) == 4
        assert any(item["pre_hex"] != "00000000" and item["post_hex"] != "00000000"
                   for item in result["seam_pairs"])


def test_header_field_shift_is_rejected(tmp_path: Path):
    raw = (PACKET / "data/alpha025/faces.tsv").read_text()
    changed = raw.replace("FX_PRE_WEST FX_PRE_EAST", "FX_PRE_EAST FX_PRE_WEST", 1)
    assert changed != raw
    path = tmp_path / "shifted_header.tsv"
    path.write_text(changed)
    with pytest.raises(ValueError, match="header/field order differs"):
        read_faces(path, CAPTURE)


def test_neighbor_face_mismatch_is_rejected():
    faces, writer = _case("alpha025")
    changed = deepcopy(faces)
    target = DONORS[0]
    neighbor = (target[0] - 1, target[1], target[2])
    word = changed["values"][neighbor]["FX_POST_EAST"]
    changed["values"][neighbor]["FX_POST_EAST"] = f"{int(word, 16) ^ 1:08X}"
    with pytest.raises(ValueError, match="shared POST face differs"):
        analyze_case(changed, writer, DONORS)


def test_writer_missing_row_is_rejected(tmp_path: Path):
    original = (PACKET / "data/control/rk_writer.tsv").read_text().splitlines()
    lines = [line for line in original if not (
        line.startswith("VAL") and line.split()[2:8] ==
        ["0", "POST_FINISH", "153", "4", "111", "QI"])]
    assert len(lines) == len(original) - 1
    path = tmp_path / "missing_writer.tsv"
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="record inventory differs"):
        read_writer(path)
