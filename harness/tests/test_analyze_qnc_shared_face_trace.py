from __future__ import annotations

from pathlib import Path

import pytest

from harness.analyze_qnc_shared_face_trace import analyze_shared_trace, read_shared_trace


DATA = Path(__file__).resolve().parents[1] / "evidence/native_qnc_shared_face_2026-10-27/data"


@pytest.mark.parametrize("case", ("control", "alpha025"))
def test_actual_full_domain_shared_face_capture(case):
    source = DATA / case
    shared = read_shared_trace(source / "qnc_shared.tsv")
    analysis = analyze_shared_trace(
        shared, flux_path=source / "qnc_flux.tsv", upstream_path=source / "upstream_nc.tsv",
        run_id=f"{case}_shared_v1_on",
    )
    assert len(shared["calls"]) == 2
    assert shared["row_count"] == 147
    assert sum(row["owns_star"] for row in shared["calls"].values()) == 1
    assert len(analysis["six_internal_faces"]) == 6
    assert len(analysis["seven_cell_directional_tendency"]) == 7
    assert sum(len(items) for items in analysis["seven_cell_directional_tendency"].values()) == 21
    assert analysis["all_captured_checks_pass"]
    assert analysis["target_final_rk3_qnc"]["bits_hex"] == (
        "405C5296" if case == "control" else "C0741F1E"
    )
    assert not analysis["limits"]["domain_number_conservation_certified"]


@pytest.mark.parametrize(
    ("old", "new", "message"),
    (
        ("CALL 1 3 20 20 41A00000 1", "CALL 1 3 3 20 41A00000 1", "20-second"),
        ("META 1 JTE 142", "META 1 JTE 61", "ownership"),
        ("VAL 1 RK3_POST 221 6 63 FX_WEST f32 D6E7601F",
         "VAL 1 RK3_POST 221 6 63 FX_WEST f32 7FC00000", "nonfinite"),
    ),
)
def test_shared_parser_rejects_wrong_time_owner_and_nonfinite(tmp_path, old, new, message):
    raw = (DATA / "control/qnc_shared.tsv").read_text()
    assert raw.count(old) == 1
    path = tmp_path / "wrong.tsv"
    path.write_text(raw.replace(old, new, 1))
    with pytest.raises(ValueError, match=message):
        read_shared_trace(path)


def test_shared_parser_rejects_missing_or_duplicate_face(tmp_path):
    raw = (DATA / "control/qnc_shared.tsv").read_text()
    row = "VAL 1 RK3_POST 221 6 63 FX_WEST f32 D6E7601F\n"
    assert raw.count(row) == 1
    for name, mutated in (("missing", raw.replace(row, "", 1)),
                          ("duplicate", raw + row)):
        path = tmp_path / f"{name}.tsv"
        path.write_text(mutated)
        with pytest.raises(ValueError):
            read_shared_trace(path)


def test_shared_analysis_detects_broken_neighbor_face(tmp_path):
    raw = (DATA / "control/qnc_shared.tsv").read_text()
    row = "VAL 1 RK3_POST 220 6 63 FX_EAST f32 D6E7601F"
    assert raw.count(row) == 1
    path = tmp_path / "different_receiver.tsv"
    path.write_text(raw.replace(row, row[:-8] + "D6E7601E", 1))
    analysis = analyze_shared_trace(
        read_shared_trace(path), flux_path=DATA / "control/qnc_flux.tsv",
        upstream_path=DATA / "control/upstream_nc.tsv", run_id="synthetic_receiver_mutation",
    )
    assert not analysis["six_internal_faces"]["x_west"]["correction_bitwise_shared"]
    assert not analysis["all_captured_checks_pass"]


@pytest.mark.parametrize("case", ("control", "alpha025"))
def test_target_msfty_must_match_same_run_v2_trace(tmp_path, case):
    source = DATA / case
    raw = (source / "qnc_shared.tsv").read_text()
    old = "VAL 1 RK3_POST 221 6 63 MSFTY f32 3F7BEF54"
    assert raw.count(old) == 1
    path = tmp_path / "wrong_msfty.tsv"
    path.write_text(raw.replace(old, old[:-8] + "40000000", 1))
    result = analyze_shared_trace(
        read_shared_trace(path), flux_path=source / "qnc_flux.tsv",
        upstream_path=source / "upstream_nc.tsv", run_id="mutated_msfty",
    )
    assert result["same_run_pr457_target_join"]["MSFTY"] is False
    assert result["all_captured_checks_pass"] is False
