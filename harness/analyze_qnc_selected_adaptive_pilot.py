"""Sequential per-donor ULP pilot on the frozen v2 QNC face/RK records.

This is an offline, selected-neighborhood calculation. It searches every
positive f32 scale word downward, never assumes monotonicity, mirrors each
rounded correction face to its receiver, and checks both exact saved-word
residuals and all original-compatible RK f32 modes. RK compatibility
enumerates 24 source-valid patterns: independent fused/separate choices at
tendency and both mass factors, crossed with separate, FMA-left, or FMA-right
numerator orientations. No host is executed, and these models do not assert
which FMA instructions were emitted.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
from itertools import product
import json
import math
from pathlib import Path

import numpy as np

from harness.analyze_qnc_candidate_inputs import (
    FACE_PAIRS, analyze_case as validate_original_case, read_faces, read_writer,
)
from harness.native_qnc_domain_preflight_advect_overlay import failure_layer_coordinates
from harness.analyze_qnc_shared_face_trace import _add, _bits, _fma, _mul, _sub
from harness.native_qnc_candidate_face_overlay import receiver_union


SCHEMA = "kdm6.native_qnc_selected_adaptive_pilot.v3"
DEFAULT_MAX_ULP = 256
PACKET = Path(__file__).resolve().parent / "evidence/native_qnc_candidate_inputs_2026-10-28"
FAILURES = Path(__file__).resolve().parent / "evidence/native_qnc_host_backoff_review_2026-10-28/residual_reason_rows.json"
V2_INPUT_PINS = {
    "control_faces": "95a134ec4ca31d66a8dc5c5bd7f00098ea3ee6745d586f4bfa0762951fc100dd",
    "control_writer": "db89d4545d555932e34a60d1922092d84f77d4eb9a98b7324e72556d314574e4",
    "alpha025_faces": "5e0bda1d389e6d660f54b7f3591ebd55a23368a9532dcd851e2bcf5d98164ad4",
    "alpha025_writer": "91798ec13cf875bc179821cb53ca6448ece4fb6f962a899fe7ca08f820628a87",
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _f32(word: str) -> np.float32:
    return np.asarray([int(word, 16)], dtype=np.uint32).view(np.float32)[0]


def _word(value: np.float32) -> str:
    return f"{int(_bits(np.float32(value))):08X}"


def _fraction(word: str) -> Fraction:
    return Fraction.from_float(float(_f32(word)))


def _amount(value: Fraction) -> dict:
    return {"exact": str(value), "approximately": float(value)}


def _pre_field(face: str) -> str:
    return face.replace("FX_", "FX_PRE_").replace("FY_", "FY_PRE_").replace("FZ_", "FZ_PRE_")


def _post_field(face: str) -> str:
    return face.replace("FX_", "FX_POST_").replace("FY_", "FY_POST_").replace("FZ_", "FZ_POST_")


def _writer_word(writer: dict, coord: tuple[int, int, int], stage: str, field: str) -> str:
    key = (3, stage, *coord, field)
    dtype, word = writer["values"][key]
    if dtype != "f32":
        raise ValueError(f"expected f32 RK writer word: {key}")
    return word


def _face_key(coord: tuple[int, int, int], face: str) -> tuple:
    i, k, j = coord
    return {
        "FX_WEST": ("X", i, k, j), "FX_EAST": ("X", i + 1, k, j),
        "FY_SOUTH": ("Y", i, k, j), "FY_NORTH": ("Y", i, k, j + 1),
        "FZ_BOTTOM": ("Z", i, k, j), "FZ_TOP": ("Z", i, k + 1, j),
    }[face]


def _axis_tendency(row: dict, mode: tuple[bool, bool, bool]) -> np.float32:
    value = np.float32(0)
    axes = (
        ("Z", "FZ_POST_TOP", "FZ_POST_BOTTOM", "FZ_LOW_TOP", "FZ_LOW_BOTTOM", "RDZW", mode[0]),
        ("X", "FX_POST_EAST", "FX_POST_WEST", "FX_LOW_EAST", "FX_LOW_WEST", "RDX", mode[1]),
        ("Y", "FY_POST_NORTH", "FY_POST_SOUTH", "FY_LOW_NORTH", "FY_LOW_SOUTH", "RDY", mode[2]),
    )
    for axis, upper, lower, low_upper, low_lower, metric, fused in axes:
        delta = _sub(_add(_sub(_f32(row[upper]), _f32(row[lower])),
                          _f32(row[low_upper])), _f32(row[low_lower]))
        factor = _f32(row[metric])
        inner = _mul(factor, delta)
        if axis == "Z":
            value = _fma(-factor, delta, value) if fused else _sub(value, inner)
        else:
            msftx = _f32(row["MSFTX"])
            value = _fma(-msftx, inner, value) if fused else _sub(value, _mul(msftx, inner))
    return np.float32(value)


def _rk_update(writer: dict, coord: tuple[int, int, int], advect: np.float32,
               fused_sites: tuple[bool, bool, bool, int],
               operands: dict[str, np.float32] | None = None) -> np.float32:
    if operands is None:
        operands = {field: _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", field))
                    for field in ("MU_OLD", "MU_BASE", "MU_NEW", "C1H", "C2H",
                                  "MSFTY", "SCALAR_TEND", "DT_RK", "SCALAR_OLD")}

    def v(field: str) -> np.float32:
        return operands[field]

    mu_old = _add(v("MU_OLD"), v("MU_BASE"))
    mu_new = _add(v("MU_NEW"), v("MU_BASE"))
    fused_tendency, fused_old_factor, fused_new_factor, numerator_mode = fused_sites
    tendency = (_fma(advect, v("MSFTY"), v("SCALAR_TEND")) if fused_tendency else
                _add(_mul(advect, v("MSFTY")), v("SCALAR_TEND")))
    old_factor = (_fma(v("C1H"), mu_old, v("C2H")) if fused_old_factor else
                  _add(_mul(v("C1H"), mu_old), v("C2H")))
    new_factor = (_fma(v("C1H"), mu_new, v("C2H")) if fused_new_factor else
                  _add(_mul(v("C1H"), mu_new), v("C2H")))
    dt_tendency = _mul(v("DT_RK"), tendency)
    old_product = _mul(old_factor, v("SCALAR_OLD"))
    if numerator_mode == 0:
        numerator = _add(old_product, dt_tendency)
    elif numerator_mode == 1:
        # FMA-left: round dt*tendency first, then fuse old_factor*scalar + term.
        numerator = _fma(old_factor, v("SCALAR_OLD"), dt_tendency)
    elif numerator_mode == 2:
        # FMA-right: round old_factor*scalar first, then fuse dt*tendency + term.
        numerator = _fma(v("DT_RK"), tendency, old_product)
    else:
        raise ValueError(f"unknown numerator contraction mode: {numerator_mode}")
    return np.float32(numerator / new_factor)


def _mode_sets(row: dict, writer: dict, coord: tuple[int, int, int],
               operands: dict[str, np.float32] | None = None) -> tuple:
    if operands is None:
        operands = {field: _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", field))
                    for field in ("MU_OLD", "MU_BASE", "MU_NEW", "C1H", "C2H",
                                  "MSFTY", "SCALAR_TEND", "DT_RK", "SCALAR_OLD")}
    observed_advect = _writer_word(writer, coord, "RKSCALAR_BEFORE", "ADVECT_TEND")
    axis_modes = tuple(mode for mode in product((False, True), repeat=3)
                       if _word(_axis_tendency(row, mode)) == observed_advect)
    observed_qnc = _writer_word(writer, coord, "RKSCALAR_AFTER", "QNC")
    # The three upstream sites are independent, and the numerator has three
    # source-valid operand orientations. Preserve every
    # per-site pattern that reproduces the recorded original QNC word.
    rk_modes = tuple((*site_modes, numerator_mode)
                     for site_modes in product((False, True), repeat=3)
                     for numerator_mode in range(3)
                     if _word(_rk_update(writer, coord, _f32(observed_advect),
                                         (*site_modes, numerator_mode), operands)) == observed_qnc)
    if not axis_modes or not rk_modes:
        raise ValueError(f"no original-compatible binary32 update mode at {coord}")
    return axis_modes, rk_modes


def _exact_budget(row: dict, writer: dict, coord: tuple[int, int, int]) -> dict:
    def a(name: str) -> Fraction:
        return _fraction(row[name])

    def w(stage: str, name: str) -> Fraction:
        return _fraction(_writer_word(writer, coord, stage, name))

    old_mass = a("C1H") * (a("MU_OLD") + a("MU_BASE")) + a("C2H")
    new_mass = a("C1H") * (w("RKSCALAR_BEFORE", "MU_NEW") + a("MU_BASE")) + a("C2H")
    if old_mass <= 0 or new_mass <= 0:
        raise ValueError(f"nonpositive RK mass factor at {coord}")
    low = (-a("RDZW") * (a("FZ_LOW_TOP") - a("FZ_LOW_BOTTOM"))
           - a("MSFTX") * a("RDX") * (a("FX_LOW_EAST") - a("FX_LOW_WEST"))
           - a("MSFTX") * a("RDY") * (a("FY_LOW_NORTH") - a("FY_LOW_SOUTH")))
    correction = (-a("RDZW") * (a("FZ_POST_TOP") - a("FZ_POST_BOTTOM"))
                  - a("MSFTX") * a("RDX") * (a("FX_POST_EAST") - a("FX_POST_WEST"))
                  - a("MSFTX") * a("RDY") * (a("FY_POST_NORTH") - a("FY_POST_SOUTH")))
    source = w("RKSCALAR_BEFORE", "SCALAR_TEND")
    available = old_mass * a("FIELD_OLD") + a("DT") * (a("MSFTY") * low + source)
    residual = available + a("DT") * a("MSFTY") * correction
    return {"available": available, "residual": residual,
            "old_mass": old_mass, "new_mass": new_mass}


def _apply_scale_map(faces: dict, choices: dict) -> tuple[dict, int]:
    """Apply only donor-owned outflow faces; mirror each one rounded word."""
    original = faces["values"]
    rows = {coord: dict(row) for coord, row in original.items()}
    assignments: dict[tuple, str] = {}
    changed = 0
    for coord, scale_choice in choices.items():
        donor = original[coord]
        scale = _f32(scale_choice["scale_hex"])
        for offset, target_face, receiver_face, outward_sign in FACE_PAIRS:
            pre_word = donor[_pre_field(target_face)]
            pre = _f32(pre_word)
            if pre == 0 or ((pre > 0) != (outward_sign > 0)):
                continue
            neighbor = tuple(a + b for a, b in zip(coord, offset))
            if neighbor not in rows:
                raise ValueError(f"captured receiver missing at {coord}/{neighbor}")
            target_post, receiver_post = _post_field(target_face), _post_field(receiver_face)
            receiver = original[neighbor]
            if (pre_word != receiver[_pre_field(receiver_face)] or
                    donor[target_post] != receiver[receiver_post]):
                raise ValueError(f"original shared f32 face words differ at {coord}/{neighbor}")
            new_word = _word(_mul(pre, scale))
            key = _face_key(coord, target_face)
            if key in assignments:
                raise ValueError(f"shared face assigned more than once: {key}")
            assignments[key] = new_word
            changed += new_word != donor[target_post]
            rows[coord][target_post] = new_word
            rows[neighbor][receiver_post] = new_word
    return rows, changed


def _evaluate_rows(faces: dict, writer: dict, rows: dict,
                   modes: dict[tuple[int, int, int], tuple],
                   donors: tuple[tuple[int, int, int], ...],
                   operands: dict[tuple[int, int, int], dict[str, np.float32]]) -> dict:
    donor_set = set(donors)
    cells = {}
    failures = {"all": set(), "donors": set(), "receivers": set(),
                "qc_positive": set(), "qc_positive_donors": set(),
                "qc_positive_receivers": set()}
    counts = Counter()
    for coord, row in sorted(rows.items()):
        budget = _exact_budget(row, writer, coord)
        axis_modes, rk_modes = modes[coord]
        predictions = tuple(sorted({_word(_rk_update(
            writer, coord, _axis_tendency(row, mode), pattern, operands[coord]))
            for mode in axis_modes for pattern in rk_modes}))
        qnc_word = _writer_word(writer, coord, "RKSCALAR_AFTER", "QNC")
        qc_word = _writer_word(writer, coord, "RKSCALAR_AFTER", "QC")
        qc_positive = _f32(qc_word) > 0
        exact_positive = budget["residual"] > 0
        f32_positive = all(math.isfinite(float(_f32(word))) and _f32(word) > 0
                           for word in predictions)
        failed = not (exact_positive and f32_positive)
        counts["cells"] += 1
        counts["qc_positive_cells"] += int(qc_positive)
        counts["exact_positive_cells"] += exact_positive
        counts["exact_nonpositive_cells"] += not exact_positive
        counts["all_compatible_f32_positive_cells"] += f32_positive
        counts["some_compatible_f32_nonpositive_cells"] += not f32_positive
        counts["joint_positive_cells"] += not failed
        if failed:
            failures["all"].add(coord)
            failures["donors" if coord in donor_set else "receivers"].add(coord)
            if qc_positive:
                failures["qc_positive"].add(coord)
                failures["qc_positive_donors" if coord in donor_set else
                         "qc_positive_receivers"].add(coord)
        cells[f"i{coord[0]}_j{coord[2]}_k{coord[1]}"] = {
            "coord_ikj": list(coord),
            "selected_donor": coord in donor_set,
            "qc_hex": qc_word,
            "qnc_original_hex": qnc_word,
            "available_exact": _amount(budget["available"]),
            "exact_residual": _amount(budget["residual"]),
            "new_mass_exact": _amount(budget["new_mass"]),
            "compatible_f32_qnc_words": list(predictions),
            "exact_positive": exact_positive,
            "all_compatible_f32_positive": f32_positive,
            "passes_joint_sign_check": not failed,
        }
    return {"counts": dict(counts), "cells": cells,
            "failures_ikj": {name: [list(c) for c in sorted(coords)]
                             for name, coords in failures.items()}}


def _find_first_pass(faces: dict, writer: dict,
                     modes: dict[tuple[int, int, int], tuple],
                     operands: dict[tuple[int, int, int], dict[str, np.float32]],
                     coord: tuple[int, int, int], max_ulp: int) -> dict | None:
    original = faces["values"][coord]
    if not original["limit_hit"]:
        raise ValueError(f"selected donor did not take limiter branch at {coord}")
    original_bits = int(original["SCALE"], 16)
    original_scale = _f32(original["SCALE"])
    if not (0 < original_scale < 1):
        raise ValueError(f"selected donor SCALE is not positive and limited at {coord}")
    checked = []
    for steps in range(max_ulp + 1):
        candidate_bits = original_bits - steps
        if candidate_bits <= 0:
            break
        scale_hex = f"{candidate_bits:08X}"
        # Each trial is a fresh copy. The scan is sequential and intentionally
        # does not assume monotonic pass/fail behavior under f32 rounding.
        trial_rows, changed = _apply_scale_map(
            faces, {coord: {"scale_hex": scale_hex}})
        row = trial_rows[coord]
        budget = _exact_budget(row, writer, coord)
        predictions = tuple(sorted({_word(_rk_update(
            writer, coord, _axis_tendency(row, mode), pattern, operands[coord]))
            for mode in modes[coord][0] for pattern in modes[coord][1]}))
        f32_positive = all(math.isfinite(float(_f32(word))) and _f32(word) > 0
                           for word in predictions)
        passed = budget["residual"] > 0 and f32_positive
        checked.append({"ulp_steps": steps, "scale_hex": scale_hex,
                        "changed_face_word_count": changed,
                        "exact_residual": _amount(budget["residual"]),
                        "compatible_f32_qnc_words": list(predictions),
                        "all_compatible_f32_positive": f32_positive,
                        "passes": passed})
        if passed:
            return {"coord_ikj": list(coord),
                    "coord_ijk": [coord[0], coord[2], coord[1]],
                    "original_scale_hex": original["SCALE"],
                    "candidate_scale_hex": scale_hex,
                    "ulp_steps": steps,
                    "checked_steps": [row["ulp_steps"] for row in checked],
                    "checked_candidates": checked,
                    "selected_exact_residual": _amount(budget["residual"]),
                    "selected_compatible_f32_qnc_words": list(predictions)}
    return None


def _scale_search(faces: dict, writer: dict,
                  donors: tuple[tuple[int, int, int], ...], max_ulp: int,
                  modes: dict[tuple[int, int, int], tuple],
                  operands: dict[tuple[int, int, int], dict[str, np.float32]]) -> dict:
    choices = {}
    unresolved = []
    rows = []
    for coord in donors:
        choice = _find_first_pass(faces, writer, modes, operands, coord, max_ulp)
        if choice is None:
            unresolved.append({"coord_ikj": list(coord),
                               "original_scale_hex": faces["values"][coord]["SCALE"],
                               "max_ulp_cap": max_ulp})
            choices[coord] = {"scale_hex": faces["values"][coord]["SCALE"],
                              "ulp_steps": None}
            rows.append({"coord_ikj": list(coord),
                         "coord_ijk": [coord[0], coord[2], coord[1]],
                         "original_scale_hex": faces["values"][coord]["SCALE"],
                         "candidate_scale_hex": faces["values"][coord]["SCALE"],
                         "ulp_steps": None, "checked_steps": list(range(max_ulp + 1)),
                         "checked_candidates": [], "unresolved_within_cap": True})
        else:
            choices[coord] = {"scale_hex": choice["candidate_scale_hex"],
                              "ulp_steps": choice["ulp_steps"]}
            rows.append(choice)
    histogram = Counter(str(row["ulp_steps"]) for row in rows
                        if row["ulp_steps"] is not None)
    steps = [row["ulp_steps"] for row in rows if row["ulp_steps"] is not None]
    return {"choices": choices, "choice_rows": rows, "unresolved": unresolved,
            "step_histogram": dict(sorted(histogram.items(), key=lambda item: int(item[0]))),
            "max_ulp_steps": max(steps) if steps else None,
            "median_ulp_steps": float(np.median(steps)) if steps else None,
            "compatible_modes": {
                f"i{coord[0]}_j{coord[2]}_k{coord[1]}":
                 {"axis_mode_count": len(modes[coord][0]),
                 "rk_per_site_pattern_count": len(modes[coord][1]),
                 "rk_patterns_tendency_old_new_numerator": [
                     "".join("1" if bit else "0" for bit in pattern[:3])
                     + ("S", "L", "R")[pattern[3]]
                     for pattern in modes[coord][1]]}
                for coord in faces["values"]}}


def _failure_delta(baseline: dict, candidate: dict,
                   donors: tuple[tuple[int, int, int], ...]) -> dict:
    base_all = {tuple(coord) for coord in baseline["failures_ikj"]["all"]}
    cand_all = {tuple(coord) for coord in candidate["failures_ikj"]["all"]}
    base_qc = {tuple(coord) for coord in baseline["failures_ikj"]["qc_positive"]}
    cand_qc = {tuple(coord) for coord in candidate["failures_ikj"]["qc_positive"]}
    donor_set = set(donors)
    base_receivers = {coord for coord in base_qc if coord not in donor_set}
    cand_receivers = {coord for coord in cand_qc if coord not in donor_set}
    return {"new_sign_failures_all_cells_ikj": [list(coord) for coord in sorted(cand_all - base_all)],
            "resolved_sign_failures_all_cells_ikj": [list(coord) for coord in sorted(base_all - cand_all)],
            "new_qc_positive_failures_ikj": [list(coord) for coord in sorted(cand_qc - base_qc)],
            "resolved_qc_positive_failures_ikj": [list(coord) for coord in sorted(base_qc - cand_qc)],
            "new_qc_positive_receiver_failures_ikj": [list(coord) for coord in sorted(cand_receivers - base_receivers)],
            "resolved_qc_positive_receiver_failures_ikj": [list(coord) for coord in sorted(base_receivers - cand_receivers)]}


def _evaluate_scale_map(faces: dict, writer: dict,
                        modes: dict[tuple[int, int, int], tuple],
                        operands: dict[tuple[int, int, int], dict[str, np.float32]],
                        choices: dict, donors: tuple[tuple[int, int, int], ...]) -> dict:
    rows, changed = _apply_scale_map(faces, choices)
    result = _evaluate_rows(faces, writer, rows, modes, donors, operands)
    return {"changed_face_word_count": changed, **result}


def _case_analysis(faces: dict, writer: dict,
                   donors: tuple[tuple[int, int, int], ...], max_ulp: int,
                   modes: dict[tuple[int, int, int], tuple],
                   operands: dict[tuple[int, int, int], dict[str, np.float32]]) -> dict:
    original_validation = validate_original_case(faces, writer, donors)
    baseline_rows = {coord: dict(row) for coord, row in faces["values"].items()}
    baseline = _evaluate_rows(faces, writer, baseline_rows, modes, donors, operands)
    search = _scale_search(faces, writer, donors, max_ulp, modes, operands)
    candidate = _evaluate_scale_map(faces, writer, modes, operands,
                                    search["choices"], donors)
    public_search = {key: value for key, value in search.items() if key != "choices"}
    return {"face_trace_sha256": faces["sha256"],
            "writer_trace_sha256": writer["sha256"],
            "original_source_validation": {
                "captured_cells": original_validation["captured_cells"],
                "shared_face_checks": original_validation["shared_face_checks"],
                "seam_pairs": original_validation["seam_pairs"],
                "source_compatible_cells": original_validation["source_compatible_cells"]},
            "scale_search": public_search,
            "baseline": baseline,
            "case_specific_candidate": candidate,
            "baseline_to_candidate_failures": _failure_delta(baseline, candidate, donors)}


def _same_operator(control_faces: dict, control_writer: dict,
                   alpha_faces: dict, alpha_writer: dict,
                   donors: tuple[tuple[int, int, int], ...],
                   control_result: dict, alpha_result: dict,
                   control_modes: dict[tuple[int, int, int], tuple],
                   alpha_modes: dict[tuple[int, int, int], tuple],
                   control_operands: dict[tuple[int, int, int], dict[str, np.float32]],
                   alpha_operands: dict[tuple[int, int, int], dict[str, np.float32]]) -> dict | None:
    def choices_from_result(result: dict) -> dict:
        return {tuple(row["coord_ikj"]): {
                    "scale_hex": row["candidate_scale_hex"],
                    "ulp_steps": row["ulp_steps"]}
                for row in result["scale_search"]["choice_rows"]}

    control_choices = choices_from_result(control_result)
    alpha_choices = choices_from_result(alpha_result)
    if control_result["scale_search"]["unresolved"] or alpha_result["scale_search"]["unresolved"]:
        return None
    n_i = {coord: max(control_choices[coord]["ulp_steps"],
                      alpha_choices[coord]["ulp_steps"])
           for coord in donors}
    table = [{"coord_ikj": list(coord), "coord_ijk": [coord[0], coord[2], coord[1]],
              "n_ulp": n_i[coord]} for coord in donors]
    per_case = {}
    for case, faces, writer, case_result, modes, operands in (
            ("control", control_faces, control_writer, control_result,
             control_modes, control_operands),
            ("alpha025", alpha_faces, alpha_writer, alpha_result,
             alpha_modes, alpha_operands)):
        case_specific = choices_from_result(case_result)
        choices = {}
        for coord in donors:
            scale_bits = int(faces["values"][coord]["SCALE"], 16) - n_i[coord]
            if scale_bits <= 0:
                raise ValueError(f"same-operator table reaches nonpositive scale at {coord}")
            choices[coord] = {"scale_hex": f"{scale_bits:08X}", "ulp_steps": n_i[coord]}
        candidate = _evaluate_scale_map(faces, writer, modes, operands, choices, donors)
        per_case[case] = {
            "scale_choices": [
                {"coord_ikj": list(coord),
                 "original_scale_hex": faces["values"][coord]["SCALE"],
                 "candidate_scale_hex": choices[coord]["scale_hex"],
                 "n_ulp": n_i[coord]} for coord in donors],
            "scale_offsets_different_from_case_specific": sum(
                n_i[coord] != case_specific[coord]["ulp_steps"]
                for coord in donors),
            "same_operator_candidate": candidate,
            "baseline_to_candidate_failures": _failure_delta(
                case_result["baseline"], candidate, donors)}
    counts = Counter(n_i.values())
    return {"n_i_table": table,
            "max_ulp_steps": max(n_i.values()),
            "median_ulp_steps": float(np.median(list(n_i.values()))),
            "step_histogram": {str(k): counts[k] for k in sorted(counts)},
            "cases": per_case}


def analyze_pilot(control_faces: dict, control_writer: dict,
                  alpha_faces: dict, alpha_writer: dict,
                  failure_json: bytes, *, max_ulp: int = DEFAULT_MAX_ULP) -> dict:
    if type(max_ulp) is not int or max_ulp < 0:
        raise ValueError("max_ulp must be a nonnegative integer")
    donors = failure_layer_coordinates(failure_json)
    selected = receiver_union(failure_json)
    if len(donors) != 54 or len(selected) != 382:
        raise ValueError("pilot is pinned to 54 donors and 382 captured cells")
    for case, faces, writer in (("control", control_faces, control_writer),
                                ("alpha025", alpha_faces, alpha_writer)):
        if set(faces["values"]) != set(selected):
            raise ValueError(f"{case} raw face trace does not cover the 382-cell union")
        if len(writer["values"]) != 54516:
            raise ValueError(f"{case} RK writer inventory differs")
    def cache_modes_and_operands(faces: dict, writer: dict):
        operands = {
            coord: {field: _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", field))
                    for field in ("MU_OLD", "MU_BASE", "MU_NEW", "C1H", "C2H",
                                  "MSFTY", "SCALAR_TEND", "DT_RK", "SCALAR_OLD")}
            for coord in faces["values"]}
        modes = {coord: _mode_sets(faces["values"][coord], writer, coord,
                                   operands[coord])
                 for coord in faces["values"]}
        return modes, operands

    control_modes, control_operands = cache_modes_and_operands(control_faces, control_writer)
    alpha_modes, alpha_operands = cache_modes_and_operands(alpha_faces, alpha_writer)
    control = _case_analysis(control_faces, control_writer, donors, max_ulp,
                              control_modes, control_operands)
    alpha = _case_analysis(alpha_faces, alpha_writer, donors, max_ulp,
                           alpha_modes, alpha_operands)
    common = _same_operator(control_faces, control_writer,
                            alpha_faces, alpha_writer, donors, control, alpha,
                            control_modes, alpha_modes, control_operands, alpha_operands)
    return {"schema": SCHEMA,
            "failure_rows_sha256": _sha(failure_json),
            "selected_donor_count": len(donors),
            "selected_capture_cell_count": len(selected),
            "max_ulp_cap": max_ulp,
            "cases": {"control": control, "alpha025": alpha},
            "same_operator": common,
            "offline_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
            "limits": {"frozen_v2_selected_donor_pilot": True,
                       "whole_domain_limiter_rule_certified": False,
                       "candidate_host_executed": False,
                       "physical_number_basis_certified": False,
                       "compiled_fma_instruction_sequence_identified": False,
                       "uncaptured_active_donors_certified": False}}


def load_v2_inputs(packet: Path, failure_json_path: Path) -> tuple[dict, dict, dict, dict, bytes]:
    failure_json = failure_json_path.read_bytes()
    selected = receiver_union(failure_json)
    traces = {}
    for case in ("control", "alpha025"):
        root = packet / "data" / case
        face_path, writer_path = root / "faces.tsv", root / "rk_writer.tsv"
        if _sha(face_path.read_bytes()) != V2_INPUT_PINS[f"{case}_faces"]:
            raise ValueError(f"{case} frozen-v2 face trace hash differs")
        if _sha(writer_path.read_bytes()) != V2_INPUT_PINS[f"{case}_writer"]:
            raise ValueError(f"{case} frozen-v2 RK writer hash differs")
        traces[case] = (read_faces(face_path, selected), read_writer(writer_path))
    return traces["control"][0], traces["control"][1], traces["alpha025"][0], traces["alpha025"][1], failure_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=PACKET)
    parser.add_argument("--failure-json", type=Path, default=FAILURES)
    parser.add_argument("--max-ulp", type=int, default=DEFAULT_MAX_ULP)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError("selected adaptive pilot output must be new")
    inputs = load_v2_inputs(args.packet, args.failure_json)
    result = analyze_pilot(*inputs[:4], inputs[4], max_ulp=args.max_ulp)
    raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(raw)
    print(json.dumps({"status": "SELECTED_ADAPTIVE_PILOT_ANALYZED",
                      "analysis_sha256": _sha(raw),
                      "max_ulp_cap": args.max_ulp,
                      "unresolved_donors": {
                          case: len(result["cases"][case]["scale_search"]["unresolved"])
                          for case in ("control", "alpha025")}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
