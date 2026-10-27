"""Read and replay the saved seven-cell QNC PD preparation and RK3 update.

All observations are raw binary32 words. A matching f32/FMA contraction is
arithmetic evidence, not proof of emitted instructions or physical number
conservation.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
from itertools import product
from pathlib import Path
import re

import numpy as np

from harness.analyze_qnc_shared_face_trace import STAR
from harness.analyze_upstream_nc_trace import (
    GENERIC_FIELDS, PD_FIELDS, ROW_HEADER, UpstreamNCTrace, UpstreamValue,
    _add, _bits_row, _div, _f32_bits, _f32_summary, _fma32, _generic_replay,
    _mul, _val,
)


MAGIC = "# KDM6AD_QNC_STATE7_TRACE_V2"
STAGES = {
    "RKSCALAR_BEFORE": GENERIC_FIELDS,
    "RKSCALAR_AFTER": GENERIC_FIELDS,
    "RKSCALAR_PD_BEFORE": PD_FIELDS,
    "RKSCALAR_PD_AFTER": PD_FIELDS,
    "POST_SCALAR_BDY": ("QNC",),
    "PRE_MICROPHYSICS": ("QNC",),
}
_HEX32 = re.compile(r"[0-9A-F]{8}\Z")
_BOOL = re.compile(r"(?:00|01)\Z")
_INTEGER = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")
STAR_IJK = tuple((i, j, k) for i, k, j in STAR)


def _integer(text: str) -> int:
    if not _INTEGER.fullmatch(text):
        raise ValueError(f"state7 row integer is not canonical: {text!r}")
    return int(text)


def read_state7_trace(path: Path) -> UpstreamNCTrace:
    source = Path(path)
    raw = source.read_bytes()
    lines = raw.decode("ascii").splitlines()
    if len(lines) < 3 or lines[0] != MAGIC or tuple(lines[1][1:].split()) != ROW_HEADER:
        raise ValueError("state7 version or column header differs")
    allowed = set(STAR_IJK)
    values, order = {}, []
    for line_no, line in enumerate(lines[2:], start=3):
        parts = line.split()
        if len(parts) != 10 or parts[0] != "VAL":
            raise ValueError(f"state7 line {line_no}: expected one ten-field VAL")
        _, step_text, rk_text, stage, i_text, k_text, j_text, field, dtype, word = parts
        step, rk, i, k, j = map(_integer, (step_text, rk_text, i_text, k_text, j_text))
        if step != 3 or (i, j, k) not in allowed or stage not in STAGES or field not in STAGES[stage]:
            raise ValueError(f"state7 line {line_no}: unexpected step/cell/stage/field")
        if (stage == "PRE_MICROPHYSICS" and rk != 0) or (stage != "PRE_MICROPHYSICS" and
                (rk not in (1, 2, 3) or (stage in ("RKSCALAR_PD_BEFORE", "RKSCALAR_PD_AFTER", "POST_SCALAR_BDY") and rk != 3))):
            raise ValueError(f"state7 line {line_no}: wrong RK stage")
        if field == "TENDEC":
            if dtype != "bool" or not _BOOL.fullmatch(word):
                raise ValueError(f"state7 line {line_no}: TENDEC requires bool 00/01")
            bits: int | bool = word == "01"
        else:
            if dtype != "f32" or not _HEX32.fullmatch(word):
                raise ValueError(f"state7 line {line_no}: {field} requires f32 raw hex")
            bits = int(word, 16)
            if not np.isfinite(np.asarray([bits], dtype=np.uint32).view(np.float32)[0]):
                raise ValueError(f"state7 line {line_no}: nonfinite f32")
        row = UpstreamValue(step, rk, stage, i, k, j, field, dtype, bits)
        key = (step, rk, stage, i, k, j, field)
        if key in values:
            raise ValueError(f"state7 line {line_no}: duplicate key")
        values[key] = row
        order.append(key)
    trace = UpstreamNCTrace(values, tuple(order), hashlib.sha256(raw).hexdigest(), len(raw), source.name)
    expected = set()
    sequence = []
    for rk in (1, 2):
        sequence.extend(((rk, "RKSCALAR_BEFORE"), (rk, "RKSCALAR_AFTER")))
    sequence.extend(((3, "RKSCALAR_PD_BEFORE"), (3, "RKSCALAR_PD_AFTER"),
                     (3, "RKSCALAR_BEFORE"), (3, "RKSCALAR_AFTER"),
                     (3, "POST_SCALAR_BDY"), (0, "PRE_MICROPHYSICS")))
    for i, j, k in STAR_IJK:
        for rk, stage in sequence:
            expected.update((3, rk, stage, i, k, j, field) for field in STAGES[stage])
        grouped = []
        for key in trace.row_order:
            if key[3:6] != (i, k, j):
                continue
            event = (key[1], key[2])
            if not grouped or grouped[-1] != event:
                grouped.append(event)
        if grouped != sequence:
            raise ValueError(f"state7 unexpected per-cell event order at {(i,j,k)}")
    if set(values) != expected or len(values) != 728:
        raise ValueError(f"state7 incomplete/unexpected seven-cell inventory: {len(values)}")
    global_order = []
    for key in trace.row_order:
        event = (key[1], key[2])
        if not global_order or global_order[-1] != event:
            global_order.append(event)
    if global_order != sequence:
        raise ValueError("state7 global event order differs")
    return trace


def _pd_candidates(trace: UpstreamNCTrace, target: tuple[int, int, int]) -> dict:
    rk, stage = 3, "RKSCALAR_PD_BEFORE"

    def value(field: str) -> np.float32:
        return _val(trace, target, rk, stage, field)

    mu_old = _add(value("MU_OLD_ARG"), value("MU_BASE"))
    mu_new = _add(value("MU_NEW_ARG"), value("MU_BASE"))
    c1, c2 = value("C1H"), value("C2H")
    old = value("SCALAR_OLD")
    dt_term = _mul(value("DT_RK"), _add(np.float32(0), value("SCALAR_TEND")))
    observed = _val(trace, target, rk, "RKSCALAR_PD_AFTER", "SCALAR_OLD")
    candidates = []
    for fused_coefficient, fused_denominator, fused_numerator in product((False, True), repeat=3):
        coefficient = _fma32(c1, mu_old, c2) if fused_coefficient else _add(_mul(c1, mu_old), c2)
        denominator = _fma32(c1, mu_new, c2) if fused_denominator else _add(_mul(c1, mu_new), c2)
        numerator = _fma32(coefficient, old, dt_term) if fused_numerator else _add(_mul(coefficient, old), dt_term)
        predicted = _div(numerator, denominator)
        candidates.append({
            "fused_coefficient": fused_coefficient,
            "fused_denominator": fused_denominator,
            "fused_numerator": fused_numerator,
            "predicted_bits_hex": f"{_f32_bits(predicted):08X}",
            "bitwise_match": _f32_bits(predicted) == _f32_bits(observed),
        })
    return {"observed_old": _f32_summary(observed),
            "matching_candidates": [row for row in candidates if row["bitwise_match"]],
            "all_fused_candidate_matches": candidates[-1]["bitwise_match"],
            "separate_candidate_matches": candidates[0]["bitwise_match"]}


def _delta(before_bits: int, after_bits: int) -> dict[str, object]:
    before = np.asarray([before_bits], dtype=np.uint32).view(np.float32)[0]
    after = np.asarray([after_bits], dtype=np.uint32).view(np.float32)[0]
    exact = Fraction.from_float(float(after)) - Fraction.from_float(float(before))
    return {"exact": str(exact), "approximately": float(exact)}


def analyze_state7(trace: UpstreamNCTrace, *, run_id: str, checkpoint_context: dict,
                   shared_face_trace: dict) -> dict:
    expected_checkpoint = {
        "control_state7_v1_on": "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
        "alpha025_state7_v1_on": "77be4282ef36a06ca59473fc69b21334eb719fdcdcea0d211d0238c40387657a",
    }
    if checkpoint_context["source_checkpoint_sha256"] != expected_checkpoint.get(run_id):
        raise ValueError("state7 checkpoint context differs from the executed cases")
    cells = {}
    for target in STAR_IJK:
        i, j, k = target
        pd = _pd_candidates(trace, target)
        generic_separate = _generic_replay(trace, target, 3, fused=False)
        generic_fma = _generic_replay(trace, target, 3, fused=True)
        pd_unchanged_qnc = _bits_row(trace, target, 3, "RKSCALAR_PD_BEFORE", "QNC") == _bits_row(trace, target, 3, "RKSCALAR_PD_AFTER", "QNC")
        old_handoff = _bits_row(trace, target, 3, "RKSCALAR_PD_AFTER", "SCALAR_OLD") == _bits_row(trace, target, 3, "RKSCALAR_BEFORE", "SCALAR_OLD")
        tendency_handoff = _bits_row(trace, target, 3, "RKSCALAR_PD_AFTER", "SCALAR_TEND") == _bits_row(trace, target, 3, "RKSCALAR_BEFORE", "SCALAR_TEND") == 0
        live_handoff = _bits_row(trace, target, 3, "RKSCALAR_PD_AFTER", "QNC") == _bits_row(trace, target, 3, "RKSCALAR_BEFORE", "QNC")
        ordinary_after = int(_bits_row(trace, target, 3, "RKSCALAR_AFTER", "QNC"))
        post_boundary = int(_bits_row(trace, target, 3, "POST_SCALAR_BDY", "QNC"))
        pre_micro = int(_bits_row(trace, target, 0, "PRE_MICROPHYSICS", "QNC"))
        label = f"i{i}_j{j}_k{k}"
        checkpoint = checkpoint_context["cells"][label]
        final_bits = int(checkpoint["final_nc_bits_hex"], 16)
        shared_bits = shared_face_trace["records"][
            (shared_face_trace["owner_call_id"], "RK3_AFTER_Y", i, k, j, "TENDENCY")]
        face_to_rk = shared_bits == _bits_row(trace, target, 3, "RKSCALAR_BEFORE", "ADVECT_TEND")
        if not all((pd_unchanged_qnc, old_handoff, tendency_handoff, live_handoff,
                    face_to_rk, pd["matching_candidates"],
                    generic_separate["qnc_bitwise_match"] or generic_fma["qnc_bitwise_match"])):
            raise ValueError(f"state7 PD/RK transition failed at {label}")
        cells[label] = {
            "pd_prepared_old": pd,
            "pd_live_qnc_unchanged": pd_unchanged_qnc,
            "pd_to_rk_old_bitwise": old_handoff,
            "pd_to_rk_tendency_zero_bitwise": tendency_handoff,
            "pd_to_rk_live_qnc_bitwise": live_handoff,
            "face_tendency_to_rk_advect_bitwise": face_to_rk,
            "ordinary_rk3_separate": generic_separate,
            "ordinary_rk3_fma_candidate": generic_fma,
            "immediate_rk_qnc_bits_hex": f"{ordinary_after:08X}",
            "post_boundary_qnc_bits_hex": f"{post_boundary:08X}",
            "pre_microphysics_qnc_bits_hex": f"{pre_micro:08X}",
            "rk_to_boundary_bitwise": ordinary_after == post_boundary,
            "boundary_to_pre_microphysics_bitwise": post_boundary == pre_micro,
            "final_checkpoint_nc_bits_hex": f"{final_bits:08X}",
            "final_checkpoint_qc_bits_hex": checkpoint["final_qc_bits_hex"],
            "rk_input_to_output_delta": _delta(int(_bits_row(trace, target, 3, "RKSCALAR_BEFORE", "QNC")), ordinary_after),
            "pre_microphysics_to_checkpoint_delta": _delta(pre_micro, final_bits),
        }
    return {
        "schema": "kdm6.native_qnc_state7_replay.v1",
        "run_id": run_id,
        "trace_sha256": trace.sha256,
        "same_run_shared_face_trace_sha256": shared_face_trace["sha256"],
        "trace_rows": len(trace.values),
        "cells": cells,
        "all_seven_pd_and_rk_matches": True,
        "limits": {
            "pd_changes_live_qnc": False,
            "fma_instruction_certified": False,
            "physical_number_units_certified": False,
            "microphysics_process_attribution": False,
            "whole_domain_number_budget_closed": False,
        },
    }
