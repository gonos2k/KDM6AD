"""Classify saved RK3 QNC budgets at the 54 fixed-M0 liquid failure layers.

All exact values are rational calculations on recorded f32 words. The source
trace comes from a full-domain step, but only the pinned 54 layers were
recorded. This does not certify a physical number budget or a host variant.
"""
from __future__ import annotations

from collections import Counter
from fractions import Fraction
import hashlib
from itertools import product
import math
from pathlib import Path
import re
import struct

from harness.native_qnc_domain_preflight_advect_overlay import (
    ADVECT_SOURCE_SHA256, FAILURE_JSON_SHA256, TARGET_COORDS_SHA256,
    failure_layer_coordinates,
)
from harness.native_qnc_star_qi_records import (
    DONOR_BOOL, DONOR_F32, DONOR_I32, WRITER_HEADER, WRITER_MAGIC,
)
from harness.analyze_upstream_nc_trace import GENERIC_FIELDS, PD_FIELDS
from harness.native_qnc_representative_trace_records import MOMENTS
from harness.native_qnc_advect_qi_trace_records import QI_FIELDS
from harness.analyze_qnc_shared_face_trace import _add, _bits, _fma, _mul, _sub, _value
from harness.analyze_upstream_nc_trace import _div

import numpy as np


FIELDS = (
    "FIELD_OLD", "C1H", "C2H", "MU_OLD", "MU_BASE", "DT", "MSFTX", "MSFTY",
    "RDX", "RDY", "RDZW", "PH_LOW", "FLUX_OUT", "SCALE", "FX_LOW_WEST",
    "FX_LOW_EAST", "FY_LOW_SOUTH", "FY_LOW_NORTH", "FZ_LOW_BOTTOM",
    "FZ_LOW_TOP", "FX_POST_WEST", "FX_POST_EAST", "FY_POST_SOUTH",
    "FY_POST_NORTH", "FZ_POST_BOTTOM", "FZ_POST_TOP",
)
BOOL_FIELDS = frozenset(("HAVE_BCS_MOIST", "PERIODIC_X", "SPECIFIED", "TENDEC",
                         "X_START_ELIGIBLE", "X_WIND_NEGATIVE"))
I32_FIELDS = frozenset(("DONOR_I", "DONOR_J", "IDE", "IDS", "JDE", "JDS",
                        "SPEC_ZONE", "TILE_ITE", "TILE_ITS", "TILE_JTE", "TILE_JTS"))
WRITER_RECORD_COUNT = 8792
WRITER_INVENTORY_SHA256 = "72e646b9d65c0a445572daf7b2e0e7b03be95f0b2d303ce35a1dcd15808d2d8b"
WRITER_STAGE_FIELDS = {
    **{stage: frozenset(MOMENTS) for stage in (
        "POST_FINISH", "POST_MICROPHYSICS", "POST_SCALAR_BDY", "PRE_MICROPHYSICS",
        "QC_BDY_AFTER", "QC_RK_AFTER", "QC_RK_BEFORE", "QC_TEND_AFTER", "QC_TEND_BEFORE")},
    **{stage: frozenset(QI_FIELDS) for stage in (
        "QI_BDY_AFTER", "QI_RK_AFTER", "QI_RK_BEFORE", "QI_TEND_AFTER", "QI_TEND_BEFORE")},
    "QI_BDY_INPUT": frozenset(MOMENTS + DONOR_F32 + DONOR_I32 + DONOR_BOOL),
    **{stage: frozenset(MOMENTS + GENERIC_FIELDS) for stage in (
        "RKSCALAR_AFTER", "RKSCALAR_BEFORE")},
    **{stage: frozenset(MOMENTS + PD_FIELDS) for stage in (
        "RKSCALAR_PD_AFTER", "RKSCALAR_PD_BEFORE")},
}
_HEX = re.compile(r"[0-9A-F]{8}\Z")
_INT = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _number(token: str) -> int:
    if not _INT.fullmatch(token):
        raise ValueError("noncanonical integer in QNC trace")
    return int(token)


def _f32(word: str) -> float:
    if not _HEX.fullmatch(word):
        raise ValueError("noncanonical f32 word")
    value = struct.unpack(">f", bytes.fromhex(word))[0]
    if not math.isfinite(value):
        raise ValueError("nonfinite f32 word")
    return value


def _frac(word: str) -> Fraction:
    return Fraction.from_float(_f32(word))


def read_advect(path: Path, target_coords: tuple[tuple[int, int, int], ...]) -> dict:
    raw = path.read_bytes()
    lines = raw.decode("ascii").splitlines()
    expected = (
        "# KDM6AD_QNC_DOMAIN_PREFLIGHT_V1",
        f"# SOURCE_SHA256 {ADVECT_SOURCE_SHA256}",
        f"# FAILURE_JSON_SHA256 {FAILURE_JSON_SHA256}",
        f"# TARGET_COORDS_SHA256 {TARGET_COORDS_SHA256}",
    )
    if tuple(lines[:4]) != expected or len(lines) < 8:
        raise ValueError("QNC domain preflight header/source pin differs")
    if not lines[4].startswith("# CALL id ") or not lines[5].startswith("# VAL call "):
        raise ValueError("QNC domain preflight record header differs")
    calls = {}
    values = {}
    for line in lines[6:]:
        parts = line.split()
        if parts[0] == "CALL" and len(parts) == 20:
            fields = tuple(_number(token) for token in parts[1:19])
            call_id = fields[0]
            if (call_id != len(calls) + 1 or fields[1:4] != (20, 20, 3) or
                    parts[19] != "41A00000"):
                raise ValueError("QNC domain preflight call metadata differs")
            calls[call_id] = fields
        elif parts[0] == "VAL" and len(parts) == 49:
            metadata = tuple(_number(token) for token in parts[1:23])
            call_id, _, _, rk, i, k, j = metadata[:7]
            words = parts[23:]
            if (call_id not in calls or rk != 3 or metadata[1:4] != (20, 20, 3) or
                    metadata[7:21] != calls[call_id][4:18] or metadata[21] not in (0, 1) or
                    len(words) != len(FIELDS) or any(not _HEX.fullmatch(w) for w in words)):
                raise ValueError("QNC domain preflight value metadata differs")
            ids, ide, jds, jde = metadata[7:11]
            its, ite, jts, jte, kts, kte = metadata[15:21]
            if ((ids, ide, jds, jde) != (1, 235, 1, 283) or
                    not (its <= i <= min(ite, ide - 1)) or
                    not (jts <= j <= min(jte, jde - 1)) or
                    not (kts <= k < kte)):
                raise ValueError("QNC domain preflight target is not owned by recorded tile")
            coord = (i, k, j)
            if coord in values or coord not in target_coords:
                raise ValueError("QNC domain preflight target duplicate/unexpected")
            row = dict(zip(FIELDS, words))
            for word in words:
                _f32(word)
            row["limit_hit"] = bool(metadata[21])
            row["call_id"] = call_id
            values[coord] = row
        else:
            raise ValueError("QNC domain preflight record type/count differs")
    if len(calls) != 2 or set(values) != set(target_coords):
        raise ValueError("QNC domain preflight missing a tile or liquid target")
    owned = []
    for fields in calls.values():
        ids, ide, jds, jde = fields[4:8]
        its, ite, jts, jte, kts, kte = fields[12:18]
        if ((ids, ide, jds, jde, kts, kte) != (1, 235, 1, 283, 1, 40) or
                not (ids <= its <= ite <= ide) or not (jds <= jts <= jte <= jde)):
            raise ValueError("QNC domain preflight tile bounds differ")
        owned.append((its, min(ite, ide - 1), jts, min(jte, jde - 1)))
    area = sum((i2 - i1 + 1) * (j2 - j1 + 1) for i1, i2, j1, j2 in owned)
    a, b = owned
    overlap = max(a[0], b[0]) <= min(a[1], b[1]) and max(a[2], b[2]) <= min(a[3], b[3])
    if overlap or area != 234 * 282:
        raise ValueError("QNC domain preflight tile interiors overlap or omit native columns")
    return {"sha256": _sha(raw), "bytes": len(raw), "calls": calls, "values": values}


def read_writer(path: Path) -> dict:
    raw = path.read_bytes()
    lines = raw.decode("ascii").splitlines()
    if lines[:2] != [WRITER_MAGIC, WRITER_HEADER]:
        raise ValueError("expanded QNC writer header differs")
    values = {}
    for line in lines[2:]:
        parts = line.split()
        if len(parts) != 10 or parts[0] != "VAL":
            raise ValueError("expanded QNC writer record differs")
        _, step, rk, stage, i, k, j, field, dtype, word = parts
        integers = tuple(_number(x) for x in (step, rk, i, k, j))
        expected_dtype = "bool" if field in BOOL_FIELDS else "i32" if field in I32_FIELDS else "f32"
        if (integers[0] != 3 or dtype != expected_dtype or
                field not in WRITER_STAGE_FIELDS.get(stage, ())):
            raise ValueError("expanded QNC writer step/dtype differs")
        if dtype == "f32":
            _f32(word)
        elif dtype == "bool":
            if word not in ("00", "01"):
                raise ValueError("expanded QNC writer bool differs")
        elif not _HEX.fullmatch(word):
            raise ValueError("expanded QNC writer i32 differs")
        key = (integers[1], stage, integers[2], integers[3], integers[4], field)
        if key in values:
            raise ValueError("expanded QNC writer duplicate value")
        values[key] = (dtype, word)
    inventory = "".join(
        "|".join(str(value) for value in (*key, record[0])) + "\n"
        for key, record in sorted(values.items())
    ).encode()
    if len(values) != WRITER_RECORD_COUNT or _sha(inventory) != WRITER_INVENTORY_SHA256:
        raise ValueError("expanded QNC writer record inventory differs")
    return {"sha256": _sha(raw), "bytes": len(raw), "values": values}


def _writer_f32(writer: dict, coord: tuple[int, int, int], stage: str, field: str) -> str:
    dtype, word = writer["values"][(3, stage, *coord, field)]
    if dtype != "f32":
        raise ValueError(f"{stage}/{field} is not f32")
    return word


def _amount(value: Fraction) -> dict:
    return {"exact": str(value), "approximately": float(value)}


def _compatible_axis_modes(row: dict, expected_hex: str) -> int:
    axes = (
        ("Z", "FZ_POST_TOP", "FZ_POST_BOTTOM", "FZ_LOW_TOP", "FZ_LOW_BOTTOM", "RDZW"),
        ("X", "FX_POST_EAST", "FX_POST_WEST", "FX_LOW_EAST", "FX_LOW_WEST", "RDX"),
        ("Y", "FY_POST_NORTH", "FY_POST_SOUTH", "FY_LOW_NORTH", "FY_LOW_SOUTH", "RDY"),
    )
    def v(field: str) -> np.float32:
        return _value(int(row[field], 16))

    matches = 0
    for mode in product((False, True), repeat=3):
        value = np.float32(0)
        for (axis, upper, lower, low_upper, low_lower, metric), fused in zip(axes, mode):
            delta = _sub(_add(_sub(v(upper), v(lower)), v(low_upper)), v(low_lower))
            factor = v(metric)
            inner = _mul(factor, delta)
            if axis == "Z":
                value = _fma(-factor, delta, value) if fused else _sub(value, inner)
            else:
                mx = v("MSFTX")
                value = _fma(-mx, inner, value) if fused else _sub(value, _mul(mx, inner))
        matches += _bits(value) == int(expected_hex, 16)
    return matches


def _compatible_rk_modes(writer: dict, coord: tuple[int, int, int],
                         expected_hex: str) -> int:
    def v(field: str) -> np.float32:
        return _value(int(_writer_f32(writer, coord, "RKSCALAR_BEFORE", field), 16))

    old = _add(v("MU_OLD"), v("MU_BASE"))
    new = _add(v("MU_NEW"), v("MU_BASE"))
    matches = 0
    for fused in (False, True):
        tendency = (_fma(v("ADVECT_TEND"), v("MSFTY"), v("SCALAR_TEND")) if fused else
                    _add(_mul(v("ADVECT_TEND"), v("MSFTY")), v("SCALAR_TEND")))
        old_factor = (_fma(v("C1H"), old, v("C2H")) if fused else
                      _add(_mul(v("C1H"), old), v("C2H")))
        new_factor = (_fma(v("C1H"), new, v("C2H")) if fused else
                      _add(_mul(v("C1H"), new), v("C2H")))
        dt_tendency = _mul(v("DT_RK"), tendency)
        numerator = (_fma(old_factor, v("SCALAR_OLD"), dt_tendency) if fused else
                     _add(_mul(old_factor, v("SCALAR_OLD")), dt_tendency))
        matches += _bits(_div(numerator, new_factor)) == int(expected_hex, 16)
    return matches


def analyze_case(advect: dict, writer: dict,
                 targets: tuple[tuple[int, int, int], ...]) -> dict:
    result = {}
    counts = Counter()
    stored_signs = Counter()
    source_nonzero = 0
    limiter_hits = 0
    for coord in targets:
        row = advect["values"][coord]
        def a(name: str) -> Fraction:
            return _frac(row[name])
        def w(stage: str, name: str) -> Fraction:
            return _frac(_writer_f32(writer, coord, stage, name))

        before = "RKSCALAR_BEFORE"
        after = "RKSCALAR_AFTER"
        if (_writer_f32(writer, coord, "RKSCALAR_PD_AFTER", "SCALAR_OLD") !=
                _writer_f32(writer, coord, before, "SCALAR_OLD") or
                _writer_f32(writer, coord, "RKSCALAR_PD_AFTER", "QNC") !=
                _writer_f32(writer, coord, before, "QNC")):
            raise ValueError(f"PD-prepared old buffer/live QNC handoff differs at {coord}")
        if writer["values"][(3, before, *coord, "TENDEC")] != ("bool", "00"):
            raise ValueError(f"non-default RK3 tendency path at {coord}")
        for a_field, w_field in (("FIELD_OLD", "SCALAR_OLD"), ("C1H", "C1H"),
                                 ("C2H", "C2H"), ("MU_OLD", "MU_OLD"),
                                 ("MU_BASE", "MU_BASE"), ("DT", "DT_RK"),
                                 ("MSFTY", "MSFTY")):
            if row[a_field] != _writer_f32(writer, coord, before, w_field):
                raise ValueError(f"advection/RK operand bits differ at {coord}: {a_field}")
        if _writer_f32(writer, coord, before, "SCALAR_OLD") != _writer_f32(
                writer, coord, after, "SCALAR_OLD"):
            raise ValueError(f"RK3 old buffer changed at {coord}")
        old_mass = a("C1H") * (a("MU_OLD") + a("MU_BASE")) + a("C2H")
        new_mass = a("C1H") * (w(before, "MU_NEW") + a("MU_BASE")) + a("C2H")
        if (old_mass <= 0 or new_mass <= 0 or a("MSFTX") <= 0 or
                a("MSFTY") <= 0 or a("RDX") <= 0 or a("RDY") <= 0 or
                a("RDZW") == 0):
            raise ValueError(f"nonpositive RK mass/metric at {coord}")
        z_low = -a("RDZW") * (a("FZ_LOW_TOP") - a("FZ_LOW_BOTTOM"))
        x_low = -a("MSFTX") * a("RDX") * (a("FX_LOW_EAST") - a("FX_LOW_WEST"))
        y_low = -a("MSFTX") * a("RDY") * (a("FY_LOW_NORTH") - a("FY_LOW_SOUTH"))
        z_post = -a("RDZW") * (a("FZ_POST_TOP") - a("FZ_POST_BOTTOM"))
        x_post = -a("MSFTX") * a("RDX") * (a("FX_POST_EAST") - a("FX_POST_WEST"))
        y_post = -a("MSFTX") * a("RDY") * (a("FY_POST_NORTH") - a("FY_POST_SOUTH"))
        source = w(before, "SCALAR_TEND")
        axis_matches = _compatible_axis_modes(row, _writer_f32(
            writer, coord, before, "ADVECT_TEND"))
        rk_matches = _compatible_rk_modes(writer, coord, _writer_f32(
            writer, coord, after, "QNC"))
        if not axis_matches or not rk_matches:
            raise ValueError(f"applied face/RK arithmetic has no compatible mode at {coord}")
        available = old_mass * a("FIELD_OLD") + a("DT") * (
            a("MSFTY") * (z_low + x_low + y_low) + source)
        residual = available + a("DT") * a("MSFTY") * (z_post + x_post + y_post)
        stored = w(after, "QNC")
        qc = w(after, "QC")
        if qc <= 0:
            raise ValueError(f"selected liquid failure has no positive RK3 QC at {coord}")
        if _writer_f32(writer, coord, after, "QNC") != _writer_f32(
                writer, coord, "POST_SCALAR_BDY", "QNC"):
            raise ValueError(f"scalar boundary changed failed-layer QNC at {coord}")
        if _writer_f32(writer, coord, after, "QC") != _writer_f32(
                writer, coord, "POST_SCALAR_BDY", "QC"):
            raise ValueError(f"scalar boundary changed failed-layer QC at {coord}")
        if available <= 0:
            category = "low_order_plus_source_nonpositive"
        elif residual <= 0:
            category = "applied_correction_exceeds_available"
        elif stored <= 0:
            category = "exact_positive_but_stored_nonpositive"
        else:
            category = "rk3_positive"
        counts[category] += 1
        stored_signs["negative" if stored < 0 else "zero" if stored == 0 else "positive"] += 1
        source_nonzero += source != 0
        limiter_hits += row["limit_hit"]
        key = f"i{coord[0]}_j{coord[2]}_k{coord[1]}"
        result[key] = {
            "ikj_one_based": list(coord), "call_id": row["call_id"],
            "limit_hit": row["limit_hit"], "scale_hex": row["SCALE"],
            "source_tendency_hex": _writer_f32(writer, coord, before, "SCALAR_TEND"),
            "rk3_input_qnc_hex": _writer_f32(writer, coord, before, "QNC"),
            "ph_low_hex": row["PH_LOW"], "available_exact": _amount(available),
            "applied_face_residual_exact": _amount(residual),
            "new_mass_factor_exact": _amount(new_mass),
            "rk3_qnc_hex": _writer_f32(writer, coord, after, "QNC"),
            "rk3_qnc_value": float(stored),
            "rk3_qc_hex": _writer_f32(writer, coord, after, "QC"),
            "category": category, "scalar_boundary_preserves_rk3_moment_pair": True,
            "pd_old_buffer_and_live_qnc_reach_rk": True,
            "compatible_axis_mode_count": axis_matches,
            "compatible_rk_mode_count": rk_matches,
        }
    return {"advect_trace_sha256": advect["sha256"],
            "writer_trace_sha256": writer["sha256"],
            "target_count": len(targets), "category_counts": dict(sorted(counts.items())),
            "rk3_qnc_sign_counts": dict(sorted(stored_signs.items())),
            "nonzero_rk3_scalar_source_count": source_nonzero,
            "active_outgoing_limiter_count": limiter_hits,
            "cells": result}


def analyze(control_advect: dict, control_writer: dict,
            alpha_advect: dict, alpha_writer: dict,
            failure_json: bytes) -> dict:
    targets = failure_layer_coordinates(failure_json)
    control = analyze_case(control_advect, control_writer, targets)
    alpha = analyze_case(alpha_advect, alpha_writer, targets)
    paired = Counter()
    for key, control_row in control["cells"].items():
        candidate_row = alpha["cells"][key]
        paired[(control_row["category"], candidate_row["category"])] += 1
    paired_categories = {f"{before}__to__{after}": count
                         for (before, after), count in sorted(paired.items())}
    return {"schema": "kdm6.native_qnc_domain_preflight_analysis.v1",
            "failure_rows_sha256": _sha(failure_json),
            "target_coords_sha256": TARGET_COORDS_SHA256,
            "control": control, "alpha025": alpha,
            "paired_category_counts": paired_categories,
            "offline_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
            "limits": {"selected_liquid_failure_layers_only": True,
                       "physical_number_units_certified": False,
                       "whole_domain_positive_candidate": False,
                       "host_correction_variant_executed": False}}
