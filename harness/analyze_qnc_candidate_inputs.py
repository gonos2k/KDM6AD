"""Validate frozen pre/post QNC faces and RK states for a 54-donor pilot.

The trace samples 54 failing donor cells, their six receiving neighbors and
four unchanged Y-seam face pairs. It does not execute a changed limiter.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from harness.analyze_qnc_domain_preflight import (
    BOOL_FIELDS, FIELDS, I32_FIELDS, WRITER_STAGE_FIELDS,
    _compatible_axis_modes, _compatible_rk_modes, _f32, _number, _writer_f32,
)
from harness.native_qnc_candidate_face_overlay import (
    SEAM_SENTINELS_IKJ, SOURCE_SHA256, UNION_SHA256, receiver_union,
)
from harness.native_qnc_domain_preflight_advect_overlay import (
    FAILURE_JSON_SHA256, failure_layer_coordinates,
)
from harness.native_qnc_star_qi_records import WRITER_HEADER, WRITER_MAGIC
from harness.analyze_qnc_shared_face_trace import _bits, _mul, _value


PRE_FIELDS = ("FX_PRE_WEST", "FX_PRE_EAST", "FY_PRE_SOUTH", "FY_PRE_NORTH",
              "FZ_PRE_BOTTOM", "FZ_PRE_TOP")
CAPTURE_FIELDS = FIELDS + PRE_FIELDS
WRITER_RECORD_COUNT = 54516
WRITER_INVENTORY_SHA256 = "d8402d3c86e047a4bdf732a8c2d024748af59990b27c8a90df44280d0f0f18d2"
FACE_PAIRS = (
    ((-1, 0, 0), "FX_WEST", "FX_EAST", -1),
    ((1, 0, 0), "FX_EAST", "FX_WEST", +1),
    ((0, 0, -1), "FY_SOUTH", "FY_NORTH", -1),
    ((0, 0, 1), "FY_NORTH", "FY_SOUTH", +1),
    ((0, -1, 0), "FZ_BOTTOM", "FZ_TOP", +1),
    ((0, 1, 0), "FZ_TOP", "FZ_BOTTOM", -1),
)
HEADER_PREFIX = (
    "VAL", "call", "time_step", "trace_step", "rk", "i", "k", "j", "ids",
    "ide", "jds", "jde", "ims", "ime", "jms", "jme", "its", "ite", "jts",
    "jte", "kts", "kte", "limit_hit",
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_faces(path: Path, expected_coords: tuple[tuple[int, int, int], ...]) -> dict:
    raw = path.read_bytes()
    lines = raw.decode("ascii").splitlines()
    if (tuple(lines[:4]) != (
            "# KDM6AD_QNC_CANDIDATE_FACES_V1", f"# SOURCE_SHA256 {SOURCE_SHA256}",
            f"# FAILURE_JSON_SHA256 {FAILURE_JSON_SHA256}",
            f"# CAPTURE_COORDS_SHA256 {UNION_SHA256}") or
            not lines[4].startswith("# CALL id ") or
            lines[5][2:].split() != list(HEADER_PREFIX + CAPTURE_FIELDS)):
        raise ValueError("candidate-face trace header/field order differs")
    calls = {}
    values = {}
    for line in lines[6:]:
        parts = line.split()
        if parts[0] == "CALL" and len(parts) == 20:
            fields = tuple(_number(token) for token in parts[1:19])
            call_id = fields[0]
            if (call_id != len(calls) + 1 or fields[1:4] != (20, 20, 3) or
                    parts[19] != "41A00000"):
                raise ValueError("candidate-face CALL metadata differs")
            calls[call_id] = fields
        elif parts[0] == "VAL" and len(parts) == 55:
            meta = tuple(_number(token) for token in parts[1:23])
            call_id, _, _, rk, i, k, j = meta[:7]
            if (call_id not in calls or meta[1:4] != (20, 20, 3) or rk != 3 or
                    meta[7:21] != calls[call_id][4:18] or meta[21] not in (0, 1)):
                raise ValueError("candidate-face VAL metadata differs")
            ids, ide, jds, jde = meta[7:11]
            its, ite, jts, jte, kts, kte = meta[15:21]
            if ((ids, ide, jds, jde) != (1, 235, 1, 283) or
                    not (its <= i <= min(ite, ide - 1)) or
                    not (jts <= j <= min(jte, jde - 1)) or
                    not (kts <= k < kte)):
                raise ValueError("candidate-face target is outside its owned tile")
            coord = (i, k, j)
            if coord not in expected_coords or coord in values:
                raise ValueError("candidate-face coordinate missing/duplicate/unexpected")
            words = parts[23:]
            if len(words) != len(CAPTURE_FIELDS):
                raise ValueError("candidate-face raw word count differs")
            for word in words:
                _f32(word)
            values[coord] = dict(zip(CAPTURE_FIELDS, words)) | {
                "call_id": call_id, "limit_hit": bool(meta[21])}
        else:
            raise ValueError("candidate-face trace record type/count differs")
    if len(calls) != 2 or set(values) != set(expected_coords):
        raise ValueError("candidate-face trace lacks a tile or captured cell")
    owned = []
    for fields in calls.values():
        ids, ide, jds, jde = fields[4:8]
        its, ite, jts, jte, kts, kte = fields[12:18]
        if ((ids, ide, jds, jde, kts, kte) != (1, 235, 1, 283, 1, 40) or
                not (ids <= its <= ite <= ide) or not (jds <= jts <= jte <= jde)):
            raise ValueError("candidate-face tile bounds differ")
        owned.append((its, min(ite, ide - 1), jts, min(jte, jde - 1)))
    a, b = owned
    area = sum((i2 - i1 + 1) * (j2 - j1 + 1) for i1, i2, j1, j2 in owned)
    overlap = max(a[0], b[0]) <= min(a[1], b[1]) and max(a[2], b[2]) <= min(a[3], b[3])
    if overlap or area != 234 * 282:
        raise ValueError("candidate-face tile interiors overlap or omit columns")
    return {"sha256": sha(raw), "bytes": len(raw), "calls": calls, "values": values}


def read_writer(path: Path) -> dict:
    raw = path.read_bytes()
    lines = raw.decode("ascii").splitlines()
    if lines[:2] != [WRITER_MAGIC, WRITER_HEADER]:
        raise ValueError("candidate RK writer header differs")
    values = {}
    for line in lines[2:]:
        parts = line.split()
        if len(parts) != 10 or parts[0] != "VAL":
            raise ValueError("candidate RK writer record differs")
        _, step, rk, stage, i, k, j, field, dtype, word = parts
        ints = tuple(_number(x) for x in (step, rk, i, k, j))
        expected_dtype = "bool" if field in BOOL_FIELDS else "i32" if field in I32_FIELDS else "f32"
        if (ints[0] != 3 or dtype != expected_dtype or
                field not in WRITER_STAGE_FIELDS.get(stage, ())):
            raise ValueError("candidate RK writer stage/field/dtype differs")
        if dtype == "f32":
            _f32(word)
        elif dtype == "bool":
            if word not in ("00", "01"):
                raise ValueError("candidate RK writer bool differs")
        elif len(word) != 8 or any(char not in "0123456789ABCDEF" for char in word):
            raise ValueError("candidate RK writer i32 differs")
        key = (ints[1], stage, ints[2], ints[3], ints[4], field)
        if key in values:
            raise ValueError("candidate RK writer duplicate value")
        values[key] = (dtype, word)
    inventory = "".join(
        "|".join(str(value) for value in (*key, record[0])) + "\n"
        for key, record in sorted(values.items())
    ).encode()
    if len(values) != WRITER_RECORD_COUNT or sha(inventory) != WRITER_INVENTORY_SHA256:
        raise ValueError("candidate RK writer record inventory differs")
    return {"sha256": sha(raw), "bytes": len(raw), "values": values}


def _face(row: dict, name: str, stage: str) -> str:
    axis, side = name.split("_")
    return row[f"{axis}_{stage}_{side}"]


def analyze_case(faces: dict, writer: dict,
                 donors: tuple[tuple[int, int, int], ...]) -> dict:
    values = faces["values"]
    mode_counts = {"axis_matched": 0, "rk_matched": 0}
    for coord, row in values.items():
        if (_writer_f32(writer, coord, "RKSCALAR_PD_AFTER", "SCALAR_OLD") !=
                _writer_f32(writer, coord, "RKSCALAR_BEFORE", "SCALAR_OLD") or
                _writer_f32(writer, coord, "RKSCALAR_PD_AFTER", "QNC") !=
                _writer_f32(writer, coord, "RKSCALAR_BEFORE", "QNC")):
            raise ValueError(f"candidate PD old-buffer/live QNC handoff differs: {coord}")
        for a_field, rk_field in (("FIELD_OLD", "SCALAR_OLD"), ("C1H", "C1H"),
                                   ("C2H", "C2H"), ("MU_OLD", "MU_OLD"),
                                   ("MU_BASE", "MU_BASE"), ("DT", "DT_RK"),
                                   ("MSFTY", "MSFTY")):
            if row[a_field] != _writer_f32(writer, coord, "RKSCALAR_BEFORE", rk_field):
                raise ValueError(f"candidate face/RK input differs at {coord}: {a_field}")
        axis = _compatible_axis_modes(row, _writer_f32(writer, coord,
                                    "RKSCALAR_BEFORE", "ADVECT_TEND"))
        rk = _compatible_rk_modes(writer, coord, _writer_f32(writer, coord,
                                  "RKSCALAR_AFTER", "QNC"))
        if not axis or not rk:
            raise ValueError(f"candidate source-compatible face/RK mode missing at {coord}")
        if (any(_writer_f32(writer, coord, "RKSCALAR_AFTER", field) !=
                _writer_f32(writer, coord, "POST_SCALAR_BDY", field)
                for field in ("QC", "QNC"))):
            raise ValueError(f"candidate scalar boundary changed QC/NC: {coord}")
        mode_counts["axis_matched"] += 1
        mode_counts["rk_matched"] += 1
    shared = {"pre": 0, "post": 0, "low": 0, "applied_scale": 0,
              "target_outgoing": 0, "neighbor_outgoing": 0}
    face_rows = []
    for i, k, j in donors:
        target = values[(i, k, j)]
        for (di, dk, dj), target_face, neighbor_face, outward_sign in FACE_PAIRS:
            neighbor_coord = (i + di, k + dk, j + dj)
            neighbor = values[neighbor_coord]
            for stage in ("PRE", "POST", "LOW"):
                if _face(target, target_face, stage) != _face(neighbor, neighbor_face, stage):
                    raise ValueError(f"candidate shared {stage} face differs: {(i, k, j)}")
                shared[stage.lower()] += 1
            pre_word = _face(target, target_face, "PRE")
            pre = _value(int(pre_word, 16))
            donor = target if (pre > 0) == (outward_sign > 0) else neighbor
            donor_kind = "target_outgoing" if donor is target else "neighbor_outgoing"
            shared[donor_kind] += 1
            scale_word = donor["SCALE"] if donor["limit_hit"] else "3F800000"
            predicted = f"{_bits(_mul(pre, _value(int(scale_word, 16)))):08X}"
            post_word = _face(target, target_face, "POST")
            if predicted != post_word:
                raise ValueError(f"candidate post face does not match donor scale: {(i, k, j)}")
            shared["applied_scale"] += 1
            face_rows.append({"target_ikj": [i, k, j], "neighbor_ikj": list(neighbor_coord),
                              "target_face": target_face, "pre_hex": pre_word,
                              "post_hex": post_word, "low_hex": _face(target, target_face, "LOW"),
                              "owner": donor_kind, "owner_scale_hex": scale_word})
    seams = []
    for i, k, j in SEAM_SENTINELS_IKJ:
        if j != 142:
            continue
        left, right = values[(i, k, j)], values[(i, k, j + 1)]
        if left["call_id"] == right["call_id"]:
            raise ValueError("candidate seam sentinels did not cross tile calls")
        for stage in ("PRE", "POST", "LOW"):
            if left[f"FY_{stage}_NORTH"] != right[f"FY_{stage}_SOUTH"]:
                raise ValueError(f"candidate tile-seam Y {stage} face differs at {(i, k)}")
        seams.append({"i": i, "k": k, "j_south": j, "j_north": j + 1,
                      "pre_hex": left["FY_PRE_NORTH"],
                      "post_hex": left["FY_POST_NORTH"],
                      "low_hex": left["FY_LOW_NORTH"],
                      "both_tile_incidences_equal": True})
    if len(face_rows) != 324 or len(seams) != 4:
        raise ValueError("candidate donor-neighbor/seam incidence count differs")
    return {"face_trace_sha256": faces["sha256"], "rk_writer_sha256": writer["sha256"],
            "captured_cells": len(values), "source_compatible_cells": mode_counts,
            "pd_handoff_and_scalar_boundary_pair_matches": len(values),
            "shared_face_checks": shared, "face_pairs": face_rows,
            "seam_pairs": seams}


def analyze(cases: dict, parent_cases: dict,
            failure_json: bytes) -> dict:
    donors = failure_layer_coordinates(failure_json)
    selected = receiver_union(failure_json)
    output = {}
    for case in ("control", "alpha025"):
        faces, writer = cases[case]
        prior_faces, prior_writer = parent_cases[case]
        for coord in donors:
            if any(faces["values"][coord][field] != prior_faces["values"][coord][field]
                   for field in FIELDS):
                raise ValueError(f"{case} PR474 donor operand changed: {coord}")
        for key, record in prior_writer["values"].items():
            if writer["values"].get(key) != record:
                raise ValueError(f"{case} PR474 writer word changed: {key}")
        result = analyze_case(faces, writer, donors)
        result["pr474_donor_operand_rows_unchanged"] = len(donors)
        result["pr474_writer_words_unchanged"] = len(prior_writer["values"])
        output[case] = result
    if (output["control"]["shared_face_checks"] !=
            output["alpha025"]["shared_face_checks"]):
        raise ValueError("control/candidate shared-face check inventory differs")
    return {"schema": "kdm6.native_qnc_candidate_input_analysis.v1",
            "failure_rows_sha256": sha(failure_json),
            "capture_coords_sha256": UNION_SHA256,
            "selected_donor_count": len(donors),
            "selected_capture_cell_count": len(selected),
            "cases": output,
            "offline_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
            "limits": {"changed_host_limiter_executed": False,
                       "all_active_QNC_donors_captured": False,
                       "whole_domain_or_multi_rank_face_identity_certified": False,
                       "physical_number_basis_certified": False,
                       "fixed_M0_candidate_admissible": False}}
