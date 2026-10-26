from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import numpy as np

import pytest

from harness.replay_qnc_flux_limiter_trace import (
    FACE_NEIGHBORS_IKJ,
    MAGIC,
    MAGIC_V1,
    NATIVE_STEP_SECONDS,
    PD_FACE_FIELDS,
    ROW_HEADER,
    STAGE_FIELDS,
    TARGET_IKJ,
    analyze_qnc_flux_limiter_trace,
    read_qnc_flux_trace,
)
from harness.analyze_upstream_nc_trace import UpstreamNCTrace, UpstreamValue


def _row(step: int, rk: int, stage: str, i: int, k: int, j: int, field: str, dtype: str, raw: str) -> str:
    return f"VAL\t{step}\t{rk}\t{stage}\t{i}\t{k}\t{j}\t{field}\t{dtype}\t{raw}"


def _valid_rows() -> list[str]:
    rows: list[str] = []
    plan = (
        (1, "RK1_START", (TARGET_IKJ,)),
        (1, "RK1_AFTER_Y", (TARGET_IKJ,)),
        (1, "RK1_AFTER_X", (TARGET_IKJ,)),
        (1, "RK1_AFTER_Z", (TARGET_IKJ,)),
        (3, "RK3_PD_PRE_LIMIT", (TARGET_IKJ,)),
        (3, "RK3_PD_LIMIT_CELL", (TARGET_IKJ, *sorted(FACE_NEIGHBORS_IKJ))),
        (3, "RK3_PD_POST_LIMIT_FACES", (TARGET_IKJ,)),
        (3, "RK3_AFTER_Z", (TARGET_IKJ,)),
        (3, "RK3_AFTER_X", (TARGET_IKJ,)),
        (3, "RK3_AFTER_Y", (TARGET_IKJ,)),
    )
    for rk, stage, coords in plan:
        for i, k, j in coords:
            for field in STAGE_FIELDS[stage]:
                dtype, raw = ("bool", "00") if field == "LIMIT_HIT" else ("f32", "00000000")
                rows.append(_row(NATIVE_STEP_SECONDS, rk, stage, i, k, j, field, dtype, raw))
    return rows


def _trace_text(rows: list[str], *, header: str = MAGIC) -> str:
    row_header = "# " + " ".join(ROW_HEADER)
    return "\n".join([header, row_header, *rows, ""])


def _write_trace(tmp_path, name: str, rows: list[str] | None = None):
    path = tmp_path / name
    path.write_text(_trace_text(_valid_rows() if rows is None else rows), encoding="ascii")
    return path


def _f32_hex(value: float) -> str:
    return f"{int(np.asarray([np.float32(value)], dtype=np.float32).view(np.uint32)[0]):08X}"


def _complete_synthetic_rows(*, wrong_post_face: bool = False, wrong_scale: bool = False) -> list[str]:
    rows: list[str] = []

    def emit(rk, stage, coords, vals_by_coord):
        for coord in coords:
            for field in STAGE_FIELDS[stage]:
                value = vals_by_coord[coord].get(field, False if field == "LIMIT_HIT" else 0.0)
                dtype = "bool" if field == "LIMIT_HIT" else "f32"
                raw = ("01" if value else "00") if dtype == "bool" else _f32_hex(value)
                rows.append(_row(NATIVE_STEP_SECONDS, rk, stage, *coord, field, dtype, raw))

    emit(1, "RK1_START", (TARGET_IKJ,), {TARGET_IKJ: {"TENDENCY": 0.0}})
    emit(1, "RK1_AFTER_Y", (TARGET_IKJ,), {TARGET_IKJ: {"TENDENCY": -1.0, "F_Y_LOWER": 0.0, "F_Y_UPPER": 2.0, "MRDY": 0.5}})
    emit(1, "RK1_AFTER_X", (TARGET_IKJ,), {TARGET_IKJ: {"TENDENCY": -1.5, "F_X_LOWER": 1.0, "F_X_UPPER": 3.0, "MRDX": 0.25}})
    emit(1, "RK1_AFTER_Z", (TARGET_IKJ,), {TARGET_IKJ: {"TENDENCY": -1.8, "F_Z_LOWER": 2.0, "F_Z_UPPER": 5.0, "RDZW": 0.1}})

    pre = {field: 0.0 for field in PD_FACE_FIELDS}
    pre.update(FX_EAST=2.0, TENDENCY=0.0, PH_LOW=1.0, FLUX_OUT=2.0)
    emit(3, "RK3_PD_PRE_LIMIT", (TARGET_IKJ,), {TARGET_IKJ: pre})

    limits = {}
    for coord in (TARGET_IKJ, *sorted(FACE_NEIGHBORS_IKJ)):
        hit = coord == TARGET_IKJ
        limits[coord] = {"PH_LOW": 1.0, "FLUX_OUT": 2.0 if hit else 0.0,
                         "LIMIT_HIT": hit, "SCALE": 0.25 if (hit and wrong_scale) else (0.5 if hit else 1.0)}
    emit(3, "RK3_PD_LIMIT_CELL", (TARGET_IKJ, *sorted(FACE_NEIGHBORS_IKJ)), limits)

    post = {field: value for field, value in pre.items() if field in PD_FACE_FIELDS}
    post["FX_EAST"] = 0.75 if wrong_post_face else 1.0
    post.update(MSFTX=1.0, MSFTY=1.0, RDX=1.0, RDY=1.0, RDZW=1.0, DT_STEP=1.0)
    emit(3, "RK3_PD_POST_LIMIT_FACES", (TARGET_IKJ,), {TARGET_IKJ: post})
    emit(3, "RK3_AFTER_Z", (TARGET_IKJ,), {TARGET_IKJ: {"TENDENCY": 0.0}})
    emit(3, "RK3_AFTER_X", (TARGET_IKJ,), {TARGET_IKJ: {"TENDENCY": -1.0}})
    emit(3, "RK3_AFTER_Y", (TARGET_IKJ,), {TARGET_IKJ: {"TENDENCY": -1.0}})
    return rows


def _upstream_for_synthetic(advect_rk1=-1.8, advect_rk3=-1.0):
    coord = (TARGET_IKJ[0], TARGET_IKJ[2], TARGET_IKJ[1])
    records = [
        (1, "RKSCALAR_BEFORE", "ADVECT_TEND", advect_rk1),
        (3, "RKSCALAR_BEFORE", "ADVECT_TEND", advect_rk3),
        (3, "RKSCALAR_BEFORE", "MSFTY", 1.0),
        (3, "RKSCALAR_PD_AFTER", "SCALAR_OLD", 1.0),
        (3, "RKSCALAR_PD_AFTER", "C1H", 0.0),
        (3, "RKSCALAR_PD_AFTER", "C2H", 1.0),
        (3, "RKSCALAR_PD_AFTER", "MU_OLD_ARG", 0.0),
        (3, "RKSCALAR_PD_AFTER", "MU_BASE", 1.0),
        (3, "RKSCALAR_PD_AFTER", "DT_RK", 1.0),
    ]
    values = {}
    order = []
    for rk, stage, field, value in records:
        bits = int(np.asarray([np.float32(value)], dtype=np.float32).view(np.uint32)[0])
        row = UpstreamValue(3, rk, stage, coord[0], coord[2], coord[1], field, "f32", bits)
        key = (3, rk, stage, coord[0], coord[2], coord[1], field)
        values[key] = row
        order.append(key)
    return UpstreamNCTrace(values, tuple(order), "a" * 64, 100, "upstream_nc.tsv")


def _analyze_synthetic(tmp_path, *, wrong_post_face=False, wrong_scale=False, upstream_rk1=-1.8, upstream_rk3=-1.0, upstream_run_id="control_v6"):
    trace = read_qnc_flux_trace(_write_trace(tmp_path, "full.tsv", _complete_synthetic_rows(wrong_post_face=wrong_post_face, wrong_scale=wrong_scale)))
    upstream = _upstream_for_synthetic(upstream_rk1, upstream_rk3)
    config = {"scalar_adv_opt": 1, "rk_ord": 3, "h_sca_adv_order": 5, "v_sca_adv_order": 3, "zadvect_implicit": 0}
    return analyze_qnc_flux_limiter_trace(
        trace, upstream_trace=upstream, run_id="control_v6", upstream_run_id=upstream_run_id, run_config=config
    )


def test_analyzer_replays_directional_stores_pd_limit_and_same_run_advect_join(tmp_path):
    result = _analyze_synthetic(tmp_path)
    assert result["same_run_advect_tend_join"][0]["matches"]
    assert result["same_run_advect_tend_join"][1]["matches"]
    assert all(axis["separate_match"] or axis["outer_fma_match"] for axis in result["rk1_directional_tendency_replay"])
    assert all(axis["separate_match"] or axis["outer_fma_match"] for axis in result["rk3_pd_applied_divergence_replay"])
    limiter = result["rk3_pd_limiter"]
    assert limiter["ph_low_replay"]["matches"]
    assert limiter["ph_low_replay"]["source_terms_missing"] == []
    assert limiter["ph_low_replay"]["all_advect_scalar_pd_ph_low_operands_captured"]
    assert limiter["flux_out_replay"]["matches"]
    assert all(row["branch_match"] for row in limiter["limit_cells"].values())
    assert all(row["scale_match"] for row in limiter["limit_cells"].values())
    assert all(row["matches"] for row in limiter["correction_faces"].values())
    assert all(limiter["low_order_faces_unchanged"].values())
    assert result["all_captured_replays_match_a_source_or_outer_fma_candidate"]
    json.dumps(result, allow_nan=False)


def test_analyzer_preserves_face_or_limiter_scale_mismatches(tmp_path):
    wrong_face = _analyze_synthetic(tmp_path, wrong_post_face=True)
    assert not wrong_face["rk3_pd_limiter"]["correction_faces"]["FX_EAST"]["matches"]
    assert not wrong_face["all_captured_replays_match_a_source_or_outer_fma_candidate"]

    wrong_scale = _analyze_synthetic(tmp_path, wrong_scale=True)
    assert not wrong_scale["rk3_pd_limiter"]["limit_cells"]["i221_k6_j63"]["scale_match"]
    assert not wrong_scale["rk3_pd_limiter"]["correction_faces"]["FX_EAST"]["matches"]


def test_analyzer_rejects_cross_run_join_and_reports_wrong_advect_tend_bits(tmp_path):
    with pytest.raises(ValueError, match="same explicit run_id"):
        _analyze_synthetic(tmp_path, upstream_run_id="different_run")
    wrong_join = _analyze_synthetic(tmp_path, upstream_rk1=-2.0)
    assert not wrong_join["same_run_advect_tend_join"][0]["matches"]
    assert not wrong_join["all_captured_replays_match_a_source_or_outer_fma_candidate"]


def test_ph_low_full_source_formula_mismatch_fails_captured_replay_gate(tmp_path):
    trace = read_qnc_flux_trace(_write_trace(tmp_path, "ph_formula.tsv", _complete_synthetic_rows()))
    upstream = _upstream_for_synthetic()
    values = dict(upstream.values)
    key = (3, 3, "RKSCALAR_PD_AFTER", TARGET_IKJ[0], TARGET_IKJ[1], TARGET_IKJ[2], "SCALAR_OLD")
    row = values[key]
    values[key] = replace(row, bits=int(np.asarray([2.0], dtype=np.float32).view(np.uint32)[0]))
    partial_upstream = replace(upstream, values=values)
    result = analyze_qnc_flux_limiter_trace(
        trace,
        upstream_trace=partial_upstream,
        run_id="control_v6",
        upstream_run_id="control_v6",
        run_config={"scalar_adv_opt": 1, "rk_ord": 3, "h_sca_adv_order": 5, "v_sca_adv_order": 3, "zadvect_implicit": 0},
    )

    ph_low = result["rk3_pd_limiter"]["ph_low_replay"]
    assert not ph_low["matches"]
    assert ph_low["all_advect_scalar_pd_ph_low_operands_captured"]
    assert not ph_low["matching_fma_candidates"]
    assert not result["all_captured_replays_match_a_source_or_outer_fma_candidate"]
    json.dumps(result, allow_nan=False)


def _replace_row(rows: list[str], old_stage: str, field: str, new_line: str, *, coordinate=TARGET_IKJ) -> list[str]:
    i, k, j = coordinate
    out = rows.copy()
    index = next(
        n for n, line in enumerate(out)
        if line.split()[3] == old_stage and line.split()[4:7] == [str(i), str(k), str(j)] and line.split()[7] == field
    )
    out[index] = new_line
    return out


def test_parser_keeps_f32_signed_zero_and_bool_raw_bits_and_hash(tmp_path):
    rows = _valid_rows()
    rows = _replace_row(rows, "RK1_START", "TENDENCY", _row(NATIVE_STEP_SECONDS, 1, "RK1_START", *TARGET_IKJ, "TENDENCY", "f32", "80000000"))
    rows = _replace_row(rows, "RK3_PD_PRE_LIMIT", "PH_LOW", _row(NATIVE_STEP_SECONDS, 3, "RK3_PD_PRE_LIMIT", *TARGET_IKJ, "PH_LOW", "f32", "3F800000"))
    neighbor = (220, 6, 63)
    rows = _replace_row(rows, "RK3_PD_LIMIT_CELL", "LIMIT_HIT", _row(NATIVE_STEP_SECONDS, 3, "RK3_PD_LIMIT_CELL", *neighbor, "LIMIT_HIT", "bool", "01"), coordinate=neighbor)
    rows = _replace_row(rows, "RK3_PD_LIMIT_CELL", "SCALE", _row(NATIVE_STEP_SECONDS, 3, "RK3_PD_LIMIT_CELL", *neighbor, "SCALE", "f32", "3F000000"), coordinate=neighbor)
    rows = _replace_row(rows, "RK3_PD_POST_LIMIT_FACES", "FX_WEST", _row(NATIVE_STEP_SECONDS, 3, "RK3_PD_POST_LIMIT_FACES", *TARGET_IKJ, "FX_WEST", "f32", "BF800000"))
    raw = _trace_text(rows).encode("ascii")
    path = tmp_path / "qnc_flux.tsv"
    path.write_bytes(raw)
    trace = read_qnc_flux_trace(path)
    group = trace.select_qnc_scalar_group()

    assert trace.sha256 == hashlib.sha256(raw).hexdigest()
    assert trace.byte_count == len(raw)
    assert group.at(1, "RK1_START", "TENDENCY").raw_hex == "80000000"
    assert group.at(3, "RK3_PD_PRE_LIMIT", "PH_LOW").value == 1.0
    assert group.at(3, "RK3_PD_LIMIT_CELL", "LIMIT_HIT", neighbor).value is True
    assert group.at(3, "RK3_PD_LIMIT_CELL", "SCALE", neighbor).value == 0.5
    assert group.at(3, "RK3_PD_POST_LIMIT_FACES", "FX_WEST").value == -1.0


def test_legacy_v1_is_rejected_as_unattributed(tmp_path):
    rows = _valid_rows()
    v1_row_header = "# VAL step rk_step stage i k j field dtype raw_hex"
    path = tmp_path / "legacy_v1.tsv"
    path.write_text("\n".join([MAGIC_V1, v1_row_header, *rows, *rows, ""]) , encoding="ascii")
    with pytest.raises(ValueError, match="lacks moist-step namespace"):
        read_qnc_flux_trace(path)


def test_reader_accepts_exact_schema_comment_and_space_delimited_fortran_rows(tmp_path):
    rows = [line.replace("\t", " ") for line in _valid_rows()]
    path = _write_trace(tmp_path, "space_delimited.tsv", rows)
    trace = read_qnc_flux_trace(path)
    assert len(trace.select_qnc_scalar_group().values) == len(rows)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row.replace(f"VAL\t{NATIVE_STEP_SECONDS}\t1\tRK1_START", "VAL\t19\t1\tRK1_START"),
        lambda row: row.replace(f"VAL\t{NATIVE_STEP_SECONDS}\t1\tRK1_START", f"VAL\t{NATIVE_STEP_SECONDS}\t2\tRK1_START"),
        lambda row: row.replace("RK1_START", "RK3_AFTER_Y"),
        lambda row: row.replace("\t221\t6\t63\tTENDENCY", "\t220\t6\t63\tTENDENCY"),
        lambda row: row.replace("RK1_START", "UNKNOWN_STAGE"),
    ],
)
def test_parser_rejects_wrong_step_rk_stage_or_coordinate(tmp_path, mutate):
    rows = _valid_rows()
    rows[0] = mutate(rows[0])
    with pytest.raises(ValueError):
        read_qnc_flux_trace(_write_trace(tmp_path, "bad.tsv", rows))


@pytest.mark.parametrize(
    "replacement",
    [
        lambda row: row.replace("00000000", "7FC00000"),
        lambda row: row.replace("TENDENCY\tf32\t", "TENDENCY\tf64\t"),
        lambda row: row.replace("TENDENCY\tf32\t00000000", "TENDENCY\tf32\t0000000"),
    ],
)
def test_parser_rejects_nonfinite_or_bad_f32_encodings(tmp_path, replacement):
    rows = _valid_rows()
    rows[0] = replacement(rows[0])
    with pytest.raises(ValueError):
        read_qnc_flux_trace(_write_trace(tmp_path, "bad.tsv", rows))


def test_parser_rejects_wrong_boolean_encoding_and_boolean_on_other_field(tmp_path):
    rows = _valid_rows()
    index = next(n for n, row in enumerate(rows) if "RK3_PD_LIMIT_CELL" in row and "LIMIT_HIT" in row)
    rows[index] = rows[index].replace("bool\t00", "bool\t02")
    with pytest.raises(ValueError):
        read_qnc_flux_trace(_write_trace(tmp_path, "bad_bool.tsv", rows))

    rows = _valid_rows()
    rows[0] = rows[0].replace("TENDENCY\tf32\t00000000", "TENDENCY\tbool\t00")
    with pytest.raises(ValueError):
        read_qnc_flux_trace(_write_trace(tmp_path, "bad_type.tsv", rows))


def test_parser_rejects_duplicate_missing_and_bad_magic(tmp_path):
    rows = _valid_rows()
    with pytest.raises(ValueError, match="duplicate"):
        read_qnc_flux_trace(_write_trace(tmp_path, "duplicate.tsv", rows + [rows[1]]))
    with pytest.raises(ValueError, match="incomplete"):
        read_qnc_flux_trace(_write_trace(tmp_path, "missing.tsv", rows[:2] + rows[3:]))
    with pytest.raises(ValueError, match="start with"):
        path = tmp_path / "bad_magic.tsv"
        path.write_text(_trace_text(rows, header="# OTHER"), encoding="ascii")
        read_qnc_flux_trace(path)
