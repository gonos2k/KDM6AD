import numpy as np
import pytest

from harness.analyze_rain_boundary_trace import (
    TraceError,
    compare_post_sed_qr,
    parse_qr_trace,
    parse_surface_trace,
    validate_qr_trace,
)
from harness.rain_boundary_budget import surface_component, step_budget


def test_post_sed_trace_endpoint_matches_independent_bottom_first_snapshot_bitwise():
    stage = np.arange(512 * 39, dtype=np.float64).reshape(512, 39) / 32.0
    trace_top_first = stage[:, ::-1].copy()
    converted = compare_post_sed_qr(trace_top_first, stage)
    assert np.array_equal(converted.view(np.uint64), stage.view(np.uint64))

    changed = stage.copy()
    changed[0, 0] = np.nextafter(changed[0, 0], np.inf)
    with pytest.raises(TraceError, match="differs.*bitwise"):
        compare_post_sed_qr(trace_top_first, changed)


def fixture_qr():
    batch, levels, steps = 2, 3, 2
    density = np.array([[1.0, 1.2, 1.4], [0.8, 1.1, 1.3]], dtype=np.float64)
    depth = np.array([[2.0, 3.0, 5.0], [1.5, 2.5, 4.0]], dtype=np.float64)
    state = np.zeros((12, batch, levels), dtype=np.float64)
    state[3] = np.array([[2.0, 3.0, 4.0], [0.5, 1.0, 2.0]])
    forcing = np.ones((4, batch, levels), dtype=np.float64)
    forcing[0], forcing[3] = density, depth
    q = state[3, :, ::-1].copy()  # C++ trace is top-first.
    falk_accum = np.zeros_like(q)
    msteps = np.array([2, 1], dtype=np.int32)
    lines = []
    for n in range(1, steps + 1):
        previous_falk = np.zeros(batch, dtype=np.float64)
        previous_after = np.zeros(batch, dtype=np.float64)
        for k in range(levels):
            for b in range(batch):
                dend = density[b, levels - 1 - k]
                dz = depth[b, levels - 1 - k]
                dz_above = 0.0 if k == 0 else depth[b, levels - k]
                safe_dend, safe_dz = max(dend, 1e-9), max(dz, 1e-9)
                before = float(q[b, k])
                gate = int(n <= msteps[b])
                work = 0.02
                fall_before = float(falk_accum[b, k])
                falk = dend * before * work / float(msteps[b]) * gate
                falk_prev = 0.0 if k == 0 else previous_falk[b]
                out_attempt = falk * 20.0 / safe_dend
                out_min = min(out_attempt, before)
                above_post = before if k == 0 else previous_after[b]
                if k == 0:
                    arr_attempt = arr_min = arr_applied = 0.0
                    after = max(before - out_attempt, 0.0)
                    out_operand, out_present = 0.0, 0
                else:
                    arr_attempt = falk_prev * dz_above / safe_dz * 20.0 / safe_dend
                    arr_min = min(arr_attempt, above_post)
                    arr_applied = arr_min
                    after = max(before - out_min + arr_applied, 0.0)
                    out_operand, out_present = out_min, 1
                row = {
                    "schema": "kdm6.rain_boundary.v1",
                    "record": "qr_layer",
                    "factor_mode": "norm_actual",
                    "call_index": "0",
                    "n": str(n),
                    "dtcld_s": "20",
                    "column": str(b),
                    "level_top0": str(k),
                    "top": str(int(k == 0)),
                    "mstep": str(msteps[b]),
                    "gate": str(gate),
                    "DEND_code": dend,
                    "DEND_safe_code": safe_dend,
                    "DELZ_code": dz,
                    "DELZ_safe_code": safe_dz,
                    "DELZ_above_code": dz_above,
                    "work1_qr_code": work,
                    "workn_qr_code": 0.0,
                    "QR_before_code": before,
                    "falk_qr_stored_code": falk,
                    "falk_qr_prev_stored_code": falk_prev,
                    "QR_out_cap_operand_code": before,
                    "QR_above_cap_operand_post_update_code": above_post,
                    "dqr_out_attempt_reconstructed_code": out_attempt,
                    "dqr_out_min_attempt_before_diagnostic_code": out_min,
                    "dqr_out_applied_operand_code": out_operand,
                    "dqr_out_operand_present": str(out_present),
                    "dqr_arrival_attempt_reconstructed_code": arr_attempt,
                    "dqr_arrival_min_attempt_above_diagnostic_code": arr_min,
                    "dqr_arrival_applied_operand_code": arr_applied,
                    "arrival_operand_present": str(int(k > 0)),
                    "QR_realized_before_minus_after_code": before - after,
                    "QR_after_code": after,
                    "fall_qr_accum_before_code": fall_before,
                    "fall_qr_accum_after_code": fall_before + falk,
                }
                lines.append(
                    " ".join(
                        f"{key}={value:.17g}"
                        if isinstance(value, float)
                        else f"{key}={value}"
                        for key, value in row.items()
                    )
                )
                q[b, k] = after
                falk_accum[b, k] += falk
                previous_falk[b] = falk
                previous_after[b] = after
    return state, forcing, q, falk_accum, ("\n".join(lines) + "\n").encode("ascii")


def test_qr_parser_checks_exact_top_first_n_level_column_order_and_source_operands():
    state, forcing, end_qr, falls, data = fixture_qr()
    trace = parse_qr_trace(data, "norm_actual", batch=2, levels=3, steps=2)
    out, incoming, _ = validate_qr_trace(trace, state, forcing, steps=2)
    assert out.shape == incoming.shape == (2, 3, 2)
    assert np.array_equal(trace["QR_after_code"][-1].T, end_qr)
    assert np.array_equal(trace["fall_qr_accum_after_code"][-1].T, falls)
    assert trace["mstep"][0, 0].tolist() == [2, 1]

    rows = data.decode().splitlines()
    rows[1], rows[2] = rows[2], rows[1]
    with pytest.raises(TraceError, match="row order"):
        parse_qr_trace(
            ("\n".join(rows) + "\n").encode(), "norm_actual", batch=2, levels=3, steps=2
        )


def test_qr_parser_rejects_mismatched_upper_post_update_cap_and_dt():
    state, forcing, _, _, data = fixture_qr()
    rows = data.decode().splitlines()
    # First lower receiver: its arrival cap operand must equal the upper cell's
    # post-update QR, not its entry value or the receiver state.
    fields = rows[2].split()
    rows[2] = " ".join(
        "QR_above_cap_operand_post_update_code=99"
        if x.startswith("QR_above_cap_operand_post_update_code=")
        else x
        for x in fields
    )
    trace = parse_qr_trace(
        ("\n".join(rows) + "\n").encode(), "norm_actual", batch=2, levels=3, steps=2
    )
    with pytest.raises(TraceError, match="post-update QR"):
        validate_qr_trace(trace, state, forcing, steps=2)

    state, forcing, _, _, data = fixture_qr()
    rows = data.decode().splitlines()
    rows[0] = rows[0].replace("dtcld_s=20", "dtcld_s=10")
    trace = parse_qr_trace(
        ("\n".join(rows) + "\n").encode(), "norm_actual", batch=2, levels=3, steps=2
    )
    with pytest.raises(TraceError, match="dtcld"):
        validate_qr_trace(trace, state, forcing, steps=2)


def test_qr_budget_keeps_positive_bottom_arrival_separate_from_net_depletion():
    state, forcing, end_qr, _, data = fixture_qr()
    trace = parse_qr_trace(data, "norm_actual", batch=2, levels=3, steps=2)
    out, incoming, _ = validate_qr_trace(trace, state, forcing, steps=2)
    w = trace["DEND_code"][0].T * trace["DELZ_code"][0].T
    before = trace["QR_before_code"][0].T
    after = trace["QR_after_code"][0].T
    b = step_budget(
        before,
        after,
        out[0].T,
        incoming[0].T,
        w / np.array([[2.0, 3.0, 5.0], [1.5, 2.5, 4.0]]),
        np.array([[2.0, 3.0, 5.0], [1.5, 2.5, 4.0]]),
    )
    assert b["actual_bottom_arrival"].shape == (2,)
    assert np.all(b["actual_bottom_arrival"] > 0)
    assert np.all(b["actual_bottom_departure"] > 0)
    assert np.any(b["actual_bottom_departure"] != b["bottom_net_depletion"])
    assert end_qr.shape == (2, 3)


def test_surface_formula_keeps_qr_component_separate_from_total_precipitation():
    state, forcing, _, falls, _ = fixture_qr()
    batch, levels = 2, 3
    qr_bottom = falls[:, -1]
    qs_bottom, qg_bottom, qi_bottom = (
        np.array([0.01, 0.02]),
        np.array([0.03, 0.04]),
        np.array([0.05, 0.06]),
    )
    dz_bottom = forcing[3, :, 0]
    qr_mm = surface_component(qr_bottom, dz_bottom, 20.0)
    snow_mm = surface_component(qs_bottom + qi_bottom, dz_bottom, 20.0)
    graupel_mm = surface_component(qg_bottom, dz_bottom, 20.0)
    total_rate = ((qr_bottom + qs_bottom) + qg_bottom) + qi_bottom
    total_mm = surface_component(total_rate, dz_bottom, 20.0)
    response = np.stack((total_mm, snow_mm, graupel_mm))
    lines = []
    for b in range(batch):
        row = {
            "schema": "kdm6.rain_boundary.v1",
            "record": "surface",
            "factor_mode": "norm_actual",
            "call_index": 0,
            "column": b,
            "bottom_level_top0": levels - 1,
            "dtcld_s": 20.0,
            "fall_qr_bottom_code": qr_bottom[b],
            "fall_qs_bottom_code": qs_bottom[b],
            "fall_qg_bottom_code": qg_bottom[b],
            "fall_qi_bottom_code": qi_bottom[b],
            "DELZ_bottom_m": dz_bottom[b],
            "DENR_surface_constant": 1000.0,
            "surface_total_from_rain_increment_mm": total_mm[b],
            "surface_snow_ice_subset_mm": snow_mm[b],
            "surface_graupel_subset_mm": graupel_mm[b],
        }
        lines.append(
            " ".join(
                f"{k}={v:.17g}" if isinstance(v, float) else f"{k}={v}"
                for k, v in row.items()
            )
        )
    parsed, reported_qr = parse_surface_trace(
        ("\n".join(lines) + "\n").encode(),
        "norm_actual",
        response,
        qr_bottom,
        dz_bottom,
        batch=batch,
        levels=levels,
    )
    np.testing.assert_array_equal(reported_qr.view("u8"), qr_mm.view("u8"))
    assert not np.array_equal(reported_qr.view("u8"), response[0].view("u8"))


def test_surface_reader_rejects_total_subset_mismatch():
    state, forcing, _, falls, _ = fixture_qr()
    qr_bottom = falls[:, -1]
    dz_bottom = forcing[3, :, 0]
    response = np.zeros((3, 2), dtype=np.float64)
    lines = []
    for b in range(2):
        row = {
            "schema": "kdm6.rain_boundary.v1",
            "record": "surface",
            "factor_mode": "norm_actual",
            "call_index": 0,
            "column": b,
            "bottom_level_top0": 2,
            "dtcld_s": 20.0,
            "fall_qr_bottom_code": qr_bottom[b],
            "fall_qs_bottom_code": 0.0,
            "fall_qg_bottom_code": 0.0,
            "fall_qi_bottom_code": 0.0,
            "DELZ_bottom_m": dz_bottom[b],
            "DENR_surface_constant": 1000.0,
            "surface_total_from_rain_increment_mm": 0.0,
            "surface_snow_ice_subset_mm": 0.0,
            "surface_graupel_subset_mm": 0.0,
        }
        lines.append(
            " ".join(
                f"{k}={v:.17g}" if isinstance(v, float) else f"{k}={v}"
                for k, v in row.items()
            )
        )
    with pytest.raises(TraceError, match="surface_total"):
        parse_surface_trace(
            ("\n".join(lines) + "\n").encode(),
            "norm_actual",
            response,
            qr_bottom,
            dz_bottom,
            batch=2,
            levels=3,
        )
