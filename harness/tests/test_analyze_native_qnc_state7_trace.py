from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.analyze_native_qnc_state7_trace import analyze_state7, read_state7_trace, STAR_IJK
from harness.analyze_qnc_shared_face_trace import read_shared_trace
from harness.analyze_upstream_nc_trace import read_upstream_nc_trace


DATA = Path(__file__).resolve().parents[1] / "evidence/native_qnc_state7_2026-10-27/data"
OLD = Path(__file__).resolve().parents[1] / "evidence/native_qnc_shared_face_2026-10-27/data"


@pytest.mark.parametrize("case", ("control", "alpha025"))
def test_saved_state7_connects_pd_to_rk_to_checkpoint(case):
    source = DATA / case
    trace = read_state7_trace(source / "qnc_state7.tsv")
    result = analyze_state7(
        trace, run_id=f"{case}_state7_v1_on",
        checkpoint_context=json.loads((source / "checkpoint_context.json").read_text()),
        shared_face_trace=read_shared_trace(source / "qnc_shared.tsv"),
    )
    assert result["trace_rows"] == 728
    assert len(result["cells"]) == 7
    for cell in result["cells"].values():
        assert cell["pd_live_qnc_unchanged"]
        assert cell["pd_to_rk_old_bitwise"]
        assert cell["pd_to_rk_tendency_zero_bitwise"]
        assert cell["face_tendency_to_rk_advect_bitwise"]
        assert cell["pd_prepared_old"]["all_fused_candidate_matches"]
        assert cell["ordinary_rk3_fma_candidate"]["qnc_bitwise_match"]
        assert cell["rk_to_boundary_bitwise"] and cell["boundary_to_pre_microphysics_bitwise"]
    target = result["cells"]["i221_j63_k6"]
    assert target["immediate_rk_qnc_bits_hex"] == (
        "405C5296" if case == "control" else "C0741F1E")
    assert target["final_checkpoint_nc_bits_hex"] == (
        "405C5296" if case == "control" else "00000000")
    assert result["limits"]["whole_domain_number_budget_closed"] is False
    original = read_upstream_nc_trace(OLD / case / "upstream_nc.tsv")
    assert all(trace.values[key].bits == row.bits for key, row in original.values.items()
               if (row.i, row.k, row.j) == (221, 6, 63))


def test_state7_reader_rejects_missing_and_duplicate_field(tmp_path):
    raw = (DATA / "control/qnc_state7.tsv").read_text()
    row = "VAL\t3\t3\tRKSCALAR_PD_AFTER\t221\t6\t63\tSCALAR_OLD\tf32\t4BAD4BDA\n"
    assert raw.count(row) == 1
    for name, changed in (("missing", raw.replace(row, "", 1)), ("duplicate", raw + row)):
        path = tmp_path / f"{name}.tsv"
        path.write_text(changed)
        with pytest.raises(ValueError):
            read_state7_trace(path)


def test_state7_analyzer_detects_broken_pd_handoff(tmp_path):
    raw = (DATA / "control/qnc_state7.tsv").read_text()
    row = "VAL\t3\t3\tRKSCALAR_BEFORE\t221\t6\t63\tSCALAR_OLD\tf32\t4BAD4BDA"
    assert raw.count(row) == 1
    path = tmp_path / "wrong_handoff.tsv"
    path.write_text(raw.replace(row, row[:-8] + "4BAD4BDB", 1))
    with pytest.raises(ValueError, match="state7 PD/RK transition failed"):
        analyze_state7(
            read_state7_trace(path), run_id="control_state7_v1_on",
            checkpoint_context=json.loads((DATA / "control/checkpoint_context.json").read_text()),
            shared_face_trace=read_shared_trace(DATA / "control/qnc_shared.tsv"),
        )


@pytest.mark.parametrize("case", ("control", "alpha025"))
def test_state7_analyzer_rejects_rk3_old_buffer_change(tmp_path, case):
    source = DATA / case
    raw = (source / "qnc_state7.tsv").read_text()
    row = "VAL\t3\t3\tRKSCALAR_AFTER\t221\t6\t63\tSCALAR_OLD\tf32\t4BAD4BDA"
    assert raw.count(row) == 1
    path = tmp_path / "wrong_rk3_old.tsv"
    path.write_text(raw.replace(row, row[:-8] + "4BAD4BDB", 1))
    with pytest.raises(ValueError, match="state7 PD/RK transition failed"):
        analyze_state7(
            read_state7_trace(path), run_id=f"{case}_state7_v1_on",
            checkpoint_context=json.loads((source / "checkpoint_context.json").read_text()),
            shared_face_trace=read_shared_trace(source / "qnc_shared.tsv"),
        )


def test_state7_after_boundary_is_distinguished_from_immediate_rk(tmp_path):
    raw = (DATA / "control/qnc_state7.tsv").read_text()
    row = "VAL\t3\t3\tPOST_SCALAR_BDY\t221\t6\t63\tQNC\tf32\t405C5296"
    assert raw.count(row) == 1
    path = tmp_path / "boundary_change.tsv"
    path.write_text(raw.replace(row, row[:-8] + "405C5297", 1))
    result = analyze_state7(
        read_state7_trace(path), run_id="control_state7_v1_on",
        checkpoint_context=json.loads((DATA / "control/checkpoint_context.json").read_text()),
        shared_face_trace=read_shared_trace(DATA / "control/qnc_shared.tsv"),
    )
    assert result["cells"]["i221_j63_k6"]["rk_to_boundary_bitwise"] is False


def test_exact_seven_native_cells_have_no_duplicates():
    assert len(STAR_IJK) == len(set(STAR_IJK)) == 7
