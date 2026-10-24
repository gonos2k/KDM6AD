import math
from fractions import Fraction

import numpy as np
import pytest

from harness import analyze_localized_ice_stage as stage


def _water_row(stage_name, column, level, dend, delz, values, *, mode="raw_actual"):
    names = ("qv_kg_kg", "qc_kg_kg", "qr_kg_kg", "qi_kg_kg", "qs_kg_kg", "qg_kg_kg")
    fields = [
        "schema=kdm6.ice_factorial_water_stage.v1",
        "record=water_stage",
        f"stage={stage_name}",
        f"factor_mode={mode}",
        "subcycle=0",
        "dt_call_s=20",
        "loops=1",
        "dtcld_s=20",
        f"column={column}",
        f"level_bottom0={level}",
        f"DEND_kg_m3={dend:.17g}",
        f"DELZ_m={delz:.17g}",
    ]
    fields.extend(f"{name}={value:.17g}" for name, value in zip(names, values))
    return " ".join(fields)


def _layer_row(
    top, *, qi_before, qi_after, out, arrival, dend, delz, column=0, mode="raw_actual"
):
    fields = [
        "schema=kdm6.ice_factorial_layer.v1",
        "record=ice_factor_layer",
        "order=top_first",
        f"factor_mode={mode}",
        "recurrence=actual_departure",
        "substep=1",
        "dtcld_s=20",
        f"column={column}",
        f"level_top0={top}",
        "mstep=1",
        "gate=1",
        f"DEND_kg_m3={dend:.17g}",
        f"DEND_safe_kg_m3={dend:.17g}",
        f"DELZ_m={delz:.17g}",
        f"DELZ_safe_m={delz:.17g}",
        "work1_qi=0.1",
        "workn_qi=0.2",
        f"QI_before_kg_kg={qi_before:.17g}",
        "NI_before_number_m3=0",
        "falk_qi_code_value=0.3",
        "falk_ni_code_value=0",
        f"out_attempt_qi={out:.17g}",
        "out_attempt_ni=0",
        f"out_applied_qi={out:.17g}",
        "out_applied_ni=0",
        f"arrival_applied_qi={arrival:.17g}",
        "arrival_applied_ni=0",
        f"QI_after_kg_kg={qi_after:.17g}",
        "NI_after_number_m3=0",
    ]
    return " ".join(fields)


def _records(lines):
    return [
        stage.parse_record(line, source="fixture.tsv", line_number=i + 1)
        for i, line in enumerate(lines)
    ]


def test_rounded_inventory_uses_rounded_binary64_products_then_fsum():
    state = np.array([[[1.0e16, 1.0, -1.0e16]]], dtype=np.float64)
    density = np.ones((1, 3), dtype=np.float64)
    thickness = np.ones((1, 3), dtype=np.float64)
    result = stage.rounded_mass_inventory(state, density, thickness)
    assert result[0, 0] == math.fsum([1.0e16, 1.0, -1.0e16]) == 1.0


def test_stage_change_uses_delta_products_not_subtracted_large_inventories():
    # The accepted contract weights the already-rounded state delta. Subtracting
    # two large rounded inventories would erase the one-unit increment here.
    before = np.array([[[1.0e16, 0.0]]], dtype=np.float64)
    after = np.array([[[1.0e16, 1.0]]], dtype=np.float64)
    density = np.ones((1, 2), dtype=np.float64)
    thickness = np.ones((1, 2), dtype=np.float64)
    subtracted = stage.rounded_mass_inventory(
        after, density, thickness
    ) - stage.rounded_mass_inventory(before, density, thickness)
    delta = stage.rounded_mass_inventory(after - before, density, thickness)
    assert subtracted[0, 0] == 0.0
    assert delta[0, 0] == 1.0

    multispecies = np.zeros((2, 1, 2), dtype=np.float64)
    multispecies[0, 0] = [1.0e16, 1.0]
    multispecies[1, 0] = [-1.0e16, 2.0]
    weights = density * thickness
    rounded_products = [
        float(multispecies[f, 0, k] * weights[0, k]) for f in range(2) for k in range(2)
    ]
    exact_sum_of_rounded_products = float(
        sum((Fraction.from_float(value) for value in rounded_products), Fraction())
    )
    assert stage.rounded_total_mass_change(multispecies, density, thickness)[0] == 3.0
    assert exact_sum_of_rounded_products == 3.0


def test_water_stage_parser_preserves_bottom_first_order_and_request_measure():
    batch, levels = 2, 3
    forcing = np.zeros((4, batch, levels), dtype=np.float64)
    forcing[0] = [[2.0, 3.0, 5.0], [7.0, 11.0, 13.0]]
    forcing[3] = [[17.0, 19.0, 23.0], [29.0, 31.0, 37.0]]
    rows = []
    for name in stage.WATER_STAGES:
        for col in range(batch):
            for level in range(levels):
                rows.append(
                    _water_row(
                        name,
                        col,
                        level,
                        forcing[0, col, level],
                        forcing[3, col, level],
                        [0.1 + col + level / 10.0 + f / 100.0 for f in range(6)],
                    )
                )
    parsed = stage.parse_water_stage_rows(
        _records(rows), mode="raw_actual", batch=batch, levels=levels, forcing=forcing
    )
    assert parsed["states"].shape == (3, 6, batch, levels)
    np.testing.assert_allclose(
        parsed["states"][0, 0, 0], [0.1, 0.2, 0.3], rtol=0, atol=1e-16
    )
    np.testing.assert_array_equal(parsed["dend"], forcing[0])
    np.testing.assert_array_equal(parsed["delz"], forcing[3])


def test_water_stage_parser_rejects_duplicate_wrong_orientation_and_bad_measure():
    batch, levels = 1, 2
    forcing = np.zeros((4, batch, levels), dtype=np.float64)
    forcing[0, 0] = [1.0, 2.0]
    forcing[3, 0] = [3.0, 4.0]
    rows = [
        _water_row(s, 0, k, forcing[0, 0, k], forcing[3, 0, k], [0.0] * 6)
        for s in stage.WATER_STAGES
        for k in range(levels)
    ]
    with pytest.raises(stage.StageAuditError, match="order/orientation"):
        stage.parse_water_stage_rows(
            _records([rows[1], rows[0], *rows[2:]]),
            mode="raw_actual",
            batch=batch,
            levels=levels,
            forcing=forcing,
        )
    with pytest.raises(stage.StageAuditError, match="row"):
        stage.parse_water_stage_rows(
            _records([*rows, rows[-1]]),
            mode="raw_actual",
            batch=batch,
            levels=levels,
            forcing=forcing,
        )
    wrong = list(rows)
    wrong[0] = _water_row("pre_sed", 0, 0, 1.25, forcing[3, 0, 0], [0.0] * 6)
    with pytest.raises(stage.StageAuditError, match="differs bitwise"):
        stage.parse_water_stage_rows(
            _records(wrong),
            mode="raw_actual",
            batch=batch,
            levels=levels,
            forcing=forcing,
        )
    nonfinite = list(rows)
    nonfinite[0] = nonfinite[0].replace("qv_kg_kg=0", "qv_kg_kg=nan")
    with pytest.raises(stage.StageAuditError, match="nonfinite"):
        stage.parse_water_stage_rows(
            _records(nonfinite),
            mode="raw_actual",
            batch=batch,
            levels=levels,
            forcing=forcing,
        )


def test_ice_layer_parser_maps_top_first_trace_to_bottom_first_state():
    batch, levels = 1, 2
    forcing = np.zeros((4, batch, levels), dtype=np.float64)
    forcing[0, 0] = [2.0, 1.0]  # bottomfirst
    forcing[3, 0] = [3.0, 4.0]
    water = np.zeros((3, 6, batch, levels), dtype=np.float64)
    water[0, 3, 0] = [0.1, 0.2]
    water[1, 3, 0] = [0.08333333333333333, 0.18]
    # topfirst row top=0 maps to bottomfirst level=1; top=1 maps to level=0.
    rows = [
        _layer_row(
            0, qi_before=0.2, qi_after=0.18, out=0.02, arrival=0.0, dend=1.0, delz=4.0
        ),
        _layer_row(
            1,
            qi_before=0.1,
            qi_after=0.08333333333333333,
            out=0.03,
            arrival=0.013333333333333333,
            dend=2.0,
            delz=3.0,
        ),
    ]
    parsed = stage.parse_ice_layer_rows(
        _records(rows),
        mode="raw_actual",
        batch=batch,
        levels=levels,
        forcing=forcing,
        water_states=water,
    )
    np.testing.assert_array_equal(parsed["QI_before_kg_kg"][0], water[0, 3])
    np.testing.assert_array_equal(parsed["QI_after_kg_kg"][0], water[1, 3])
    with pytest.raises(stage.StageAuditError, match="orientation"):
        stage.parse_ice_layer_rows(
            _records([rows[1], rows[0]]),
            mode="raw_actual",
            batch=batch,
            levels=levels,
            forcing=forcing,
            water_states=water,
        )
    bad = [rows[0].replace("order=top_first", "order=bottom_first"), rows[1]]
    with pytest.raises(stage.StageAuditError, match="orientation"):
        stage.parse_ice_layer_rows(
            _records(bad),
            mode="raw_actual",
            batch=batch,
            levels=levels,
            forcing=forcing,
            water_states=water,
        )


def test_ice_budget_separates_departure_from_bottom_net_depletion_with_arrival():
    before = np.array([[0.1, 0.2]], dtype=np.float64)  # bottomfirst
    weights = np.array([[6.0, 4.0]], dtype=np.float64)
    departure = np.array([[0.03, 0.02]], dtype=np.float64)
    arrival = np.array([[0.013333333333333333, 0.0]], dtype=np.float64)
    after = before - departure + arrival
    result = stage.ice_transfer_budget(before, after, departure, arrival, weights)
    assert result["actual_bottom_departure"][0] == 0.18
    assert result["bottom_net_depletion"][0] == pytest.approx(0.1)
    assert result["total_arrival"][0] == pytest.approx(0.08)
    assert abs(result["ice_boundary_residual"][0]) <= result["roundoff_gate"][0]
    assert abs(result["transfer_identity_residual"][0]) <= result["roundoff_gate"][0]


def test_trace_parser_uses_the_verified_buffer_even_if_file_changes(tmp_path):
    from harness.analyze_localized_ice_stage import read_records

    path = tmp_path / "trace.tsv"
    original = b"key=original value=1\n"
    path.write_bytes(original)
    admitted = path.read_bytes()
    path.write_text("key=replacement value=2\n")
    assert read_records(path, admitted) == [{"key": "original", "value": "1"}]
