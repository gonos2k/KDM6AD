from __future__ import annotations

from pathlib import Path
import json
import runpy

import pytest

from harness.analyze_native_qnc_saved_state_budget import analyze_saved_state_budget
from harness.analyze_native_qnc_state7_trace import read_state7_trace
from harness.analyze_qnc_shared_face_trace import read_shared_trace


DATA = Path(__file__).resolve().parents[1] / "evidence/native_qnc_state7_2026-10-27/data"


@pytest.mark.parametrize(
    ("case", "target_base", "target_pd", "target_adv", "target_rk", "face", "residual"),
    (
        ("control", 2.0609254196874636, -1.7754986189994, 1.8040240461068937,
         1.353089798804408, -555352592727.6664, -24234.484276735995),
        ("alpha025", -0.06254197193127561, -1.7754985325661699, -3.214212456632311,
         1.2378537187286334, -555350891728.9988, 24776.38645346929),
    ),
)
def test_saved_seven_cell_state_budget_closes_exactly(
    case, target_base, target_pd, target_adv, target_rk, face, residual,
):
    source = DATA / case
    result = analyze_saved_state_budget(
        read_state7_trace(source / "qnc_state7.tsv"),
        read_shared_trace(source / "qnc_shared.tsv"), run_id=case,
    )
    target = result["cells"]["i221_j63_k6"]["target_style_four_terms"]
    for field, expected in (
        ("exact_saved_face_and_pd_baseline", target_base),
        ("pd_old_buffer_storage_effect", target_pd),
        ("advection_tendency_arithmetic_effect", target_adv),
        ("final_rk_arithmetic_and_storage_effect", target_rk),
    ):
        assert target[field]["approximately"] == pytest.approx(expected, abs=1e-12)
    assert all(cell["closure_exact"] == "0" for cell in result["cells"].values())
    assert result["seven_cell_closure_exact"] == "0"
    assert result["prior_face_internal_cancellation_pairs"] == 12
    assert result["prior_face_perimeter_incidences"] == 30
    assert result["seven_cell_terms"]["face_boundary"]["approximately"] == pytest.approx(face, abs=1e-3)
    assert result["seven_cell_terms"]["advection_tendency_arithmetic"]["approximately"] == pytest.approx(residual, abs=1e-7)
    assert result["limits"]["physical_number_units_certified"] is False


def test_changed_pd_mass_argument_rejects_state_budget(tmp_path):
    source = DATA / "control"
    raw = (source / "qnc_state7.tsv").read_text()
    row = "VAL\t3\t3\tRKSCALAR_PD_BEFORE\t221\t6\t63\tMU_NEW_ARG\tf32\t448D882B"
    assert raw.count(row) == 1
    path = tmp_path / "wrong_mu.tsv"
    path.write_text(raw.replace(row, row[:-8] + "448D882C", 1))
    with pytest.raises(ValueError, match="PD mass/source contract differs"):
        analyze_saved_state_budget(
            read_state7_trace(path), read_shared_trace(source / "qnc_shared.tsv"),
            run_id="mutated",
        )


def test_changed_shared_face_rejects_internal_budget(tmp_path):
    source = DATA / "control"
    raw = (source / "qnc_shared.tsv").read_text()
    row = "VAL 1 RK3_POST 220 6 63 FX_EAST f32 D6E7601F"
    assert raw.count(row) == 1
    path = tmp_path / "wrong_face.tsv"
    path.write_text(raw.replace(row, row[:-8] + "D6E7601E", 1))
    with pytest.raises(ValueError, match="internal face failed exact cancellation"):
        analyze_saved_state_budget(
            read_state7_trace(source / "qnc_state7.tsv"), read_shared_trace(path),
            run_id="mutated",
        )


def test_target_kdm_join_requires_a_call_that_owns_the_cell(tmp_path):
    source = DATA / "alpha025"
    for name in ("kernel.hex", "host.hex"):
        raw = (source / name).read_text()
        assert raw.count("CALL 1 3 2 233 1 39 2 142") == 1
        (tmp_path / name).write_text(raw.replace(
            "CALL 1 3 2 233 1 39 2 142", "CALL 1 3 2 233 1 39 2 62", 1))
    replay = runpy.run_path(str(DATA.parents[1] / "native_qnc_state_budget_2026-10-27/replay.py"))
    checkpoint = json.loads((source / "checkpoint_context.json").read_text())
    with pytest.raises(ValueError, match="exactly one wrapper call"):
        replay["_target_boundary"](
            tmp_path, read_state7_trace(source / "qnc_state7.tsv"), checkpoint)
