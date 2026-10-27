from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from harness.analyze_native_qnc_state7_trace import read_state7_trace
from harness.analyze_qnc_shared_face_trace import read_shared_trace
from harness.analyze_saved_qnc_scale_backoff import analyze_one_ulp_backoff
from harness.replay_qnc_flux_limiter_trace import read_qnc_flux_trace


DATA = Path(__file__).resolve().parents[1] / "evidence/native_qnc_state7_2026-10-27/data"


def _inputs(case: str):
    source = DATA / case
    return (read_state7_trace(source / "qnc_state7.tsv"),
            read_shared_trace(source / "qnc_shared.tsv"),
            read_qnc_flux_trace(source / "qnc_flux.tsv").select_qnc_scalar_group())


@pytest.mark.parametrize(
    ("case", "old_hex", "new_hex", "exact_target", "f32_target", "changed_words", "common_modes", "rounded_sum"),
    (("control", "3F4C9A4E", "3F4C9A4D", 5.211649185969273, 10.699481010437012, 6, 4, 12836.142997904923),
     ("alpha025", "3F4C9A3C", "3F4C9A3B", 1.6487862901338577, 1.9911521673202515, 5, 2, 10268.913337873133)),
)
def test_saved_one_ulp_backoff_is_shared_and_locally_nonnegative(
    case, old_hex, new_hex, exact_target, f32_target, changed_words, common_modes, rounded_sum,
):
    result = analyze_one_ulp_backoff(*_inputs(case), case=case)
    target = result["cells"]["i221_j63_k6"]
    assert result["original_scale"]["hex"] == old_hex
    assert result["candidate_scale"]["hex"] == new_hex
    assert target["candidate_exact_stored_pd_qnc_raw"]["approximately"] == pytest.approx(exact_target)
    assert target["candidate_source_compatible_f32_qnc_raw"] == pytest.approx([f32_target])
    assert len(result["changed_shared_correction_faces"]) == 6
    assert result["changed_face_word_count"] == changed_words
    assert result["internal_component_pairs_canceled"] == 12
    assert result["perimeter_face_incidences"] == 30
    assert result["perimeter_exact_unchanged"] is True
    assert result["weighted_exact_stored_pd_state_change"]["exact"] == "0"
    rounded = result["weighted_f32_state_change_individually_compatible_range"]
    assert rounded["minimum"]["approximately"] == pytest.approx(rounded_sum, abs=1e-8)
    assert rounded["minimum"] == rounded["maximum"]
    assert result["unchanged_neighbor_f32_cell_count"] == 6
    assert result["all_seven_exact_stored_pd_qnc_nonnegative"] is True
    assert result["all_seven_source_compatible_replays_nonnegative"] is True
    assert len(result["common_original_direction_modes"]) == common_modes
    assert result["common_original_rk_modes_fused"] == [True]
    assert result["minimum_seven_source_compatible_f32_qnc_raw"] == pytest.approx(f32_target)
    assert result["limits"]["host_execution_or_global_positivity_verified"] is False


def test_backoff_rejects_unpaired_saved_face():
    state, shared, flux = _inputs("alpha025")
    modified = deepcopy(shared)
    key = (modified["owner_call_id"], "RK3_POST", 221, 6, 63, "FX_WEST")
    modified["records"][key] += 1
    with pytest.raises(ValueError, match="shared face does not match"):
        analyze_one_ulp_backoff(state, modified, flux, case="mutated")


def test_backoff_rejects_disconnected_rk_input():
    state, shared, flux = _inputs("alpha025")
    modified = deepcopy(shared)
    key = (modified["owner_call_id"], "RK3_AFTER_Y", 221, 6, 63, "TENDENCY")
    modified["records"][key] += 1
    with pytest.raises(ValueError, match="shared face and RK input tendency differ"):
        analyze_one_ulp_backoff(state, modified, flux, case="mutated")


def test_backoff_rejects_false_limiter_operands():
    state, shared, flux = _inputs("alpha025")
    row = flux.at(3, "RK3_PD_LIMIT_CELL", "FLUX_OUT")
    values = dict(flux.values)
    values[(row.step, row.rk, row.stage, row.i, row.k, row.j, row.field)] = replace(
        row, bits=0x3F800000)
    with pytest.raises(ValueError, match="original limiter branch/scale/face replay differs"):
        analyze_one_ulp_backoff(state, shared, replace(flux, values=values), case="mutated")


def test_backoff_rejects_tenddec_path():
    state, shared, flux = _inputs("alpha025")
    row = state.at((221, 63, 6), 3, "RKSCALAR_BEFORE", "TENDEC")
    values = dict(state.values)
    values[(row.step, row.rk_step, row.stage, row.i, row.k, row.j, row.field)] = replace(
        row, bits=True)
    with pytest.raises(ValueError, match="non-tenddec path"):
        analyze_one_ulp_backoff(replace(state, values=values), shared, flux, case="mutated")


@pytest.mark.parametrize(("case", "changed"), (("control", "C6B384BC"),
                                              ("alpha025", "C6B384BA")))
def test_backoff_rejects_rk_coefficient_skew(tmp_path, case, changed):
    source = DATA / case
    raw = (source / "qnc_state7.tsv").read_text()
    for stage in ("RKSCALAR_BEFORE", "RKSCALAR_AFTER"):
        original = f"VAL\t3\t3\t{stage}\t221\t6\t63\tC2H\tf32\tC6B384BB"
        assert raw.count(original) == 1
        raw = raw.replace(original, original[:-8] + changed, 1)
    path = tmp_path / "rk_coefficient_skew.tsv"
    path.write_text(raw)
    _, shared, flux = _inputs(case)
    with pytest.raises(ValueError, match="PD/RK coefficient bits differ"):
        analyze_one_ulp_backoff(read_state7_trace(path), shared, flux, case="mutated")
