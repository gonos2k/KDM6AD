"""Evaluate supplied QNC donor-scale words on both sides of shared faces.

The acceptance predicate uses the exact residual of the *rounded face words*
and every source-compatible binary32 RK result. This is an offline diagnostic:
it neither changes the host limiter nor certifies a physical number budget.
The caller owns input provenance; the versioned replay checks source and raw
packet hashes before constructing these in-memory trace objects.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from math import isfinite

from harness.analyze_qnc_star_qi_trace import (
    SHARED, STAR_IKJ, TARGET, _axis_modes, _axis_predict, _bits,
    _exact_cell, _frac, _mul, _rk3_predict, _rk_modes, _shared_value,
    _value, _writer_value,
)


OUTGOING_SIGNS = (-1, +1, -1, +1, +1, -1)


def _weighted_state_change(original: dict, changed: dict, writer, predictions: dict) -> Fraction:
    total = Fraction(0)
    for coord in STAR_IKJ:
        mx = _frac(_shared_value(original, "RK3_POST", coord, "MSFTX"))
        rz = _frac(_shared_value(original, "RK3_POST", coord, "RDZW"))
        my = _frac(_writer_value(writer, "RKSCALAR_BEFORE", coord, "MSFTY"))
        before = _frac(_writer_value(writer, "RKSCALAR_AFTER", coord, "QNC"))
        after = _frac(_value(predictions[coord][0]))
        mass = Fraction(_exact_cell(changed, writer, coord)["new_mass_factor"]["exact"])
        if mx == 0 or rz == 0 or my == 0:
            raise ValueError("zero numerical weight")
        total -= mass * (after - before) / (mx * rz * my)
    return total


def evaluate_scale(shared: dict, writer, producer, scale_bits: int) -> dict:
    """Apply one scale to supplied faces and receivers, assuming caller-checked provenance."""
    original_bits = producer.bits(3, "RK3_PD_LIMIT_CELL", *TARGET, "SCALE")
    if type(scale_bits) is not int or not (0 < scale_bits <= original_bits):
        raise ValueError("invalid candidate scale word")
    scale = _value(scale_bits)
    if not 0 < scale <= _value(original_bits) < 1:
        raise ValueError("candidate scale is outside the active limiter branch")
    modified = deepcopy(shared)
    owner = shared["owner_call_id"]
    changed_faces = 0
    for row, sign in zip(SHARED, OUTGOING_SIGNS):
        _, target_face, neighbor, neighbor_face, _, _ = row
        pre = producer.f32(3, "RK3_PD_PRE_LIMIT", *TARGET, target_face)
        if pre == 0 or (pre > 0) != (sign > 0):
            raise ValueError(f"{target_face} is not an outgoing correction face")
        old_word = _bits(_mul(pre, _value(original_bits)))
        new_word = _bits(_mul(pre, scale))
        target_key = (owner, "RK3_POST", *TARGET, target_face)
        neighbor_key = (owner, "RK3_POST", *neighbor, neighbor_face)
        if shared["records"][target_key] != old_word or shared["records"][neighbor_key] != old_word:
            raise ValueError(f"{target_face} original shared face/scale differs")
        modified["records"][target_key] = new_word
        modified["records"][neighbor_key] = new_word
        changed_faces += new_word != old_word

    cells = {}
    predictions = {}
    weighted_exact_change = Fraction(0)
    for coord in STAR_IKJ:
        old = _exact_cell(shared, writer, coord)
        new = _exact_cell(modified, writer, coord)
        residual = Fraction(new["residual"]["exact"])
        weighted_exact_change -= (
            residual - Fraction(old["residual"]["exact"])
        ) / (
            _frac(_shared_value(shared, "RK3_POST", coord, "MSFTX"))
            * _frac(_shared_value(shared, "RK3_POST", coord, "RDZW"))
            * _frac(_writer_value(writer, "RKSCALAR_BEFORE", coord, "MSFTY"))
        )
        predicted = sorted({
            _bits(_rk3_predict(writer, coord, _axis_predict(modified, coord, mode)[0],
                               fused=fused))
            for mode in _axis_modes(shared, coord) for fused in _rk_modes(writer, coord)
        })
        predictions[coord] = predicted
        cells[f"i{coord[0]}_j{coord[2]}_k{coord[1]}"] = {
            "exact_residual": str(residual),
            "compatible_f32_words": [f"{word:08X}" for word in predicted],
            "exact_residual_positive": residual > 0,
            "all_compatible_f32_positive": all(
                isfinite(float(_value(word))) and _value(word) > 0 for word in predicted
            ),
        }
    if weighted_exact_change != 0:
        raise ValueError("internal shared-face numerical ledger does not cancel")
    if any(len(words) != 1 for words in predictions.values()):
        raise ValueError("rounded state change is not uniquely predicted by compatible modes")
    accepted = all(row["exact_residual_positive"] and row["all_compatible_f32_positive"]
                   for row in cells.values())
    rounded_change = _weighted_state_change(shared, modified, writer, predictions)
    return {
        "scale_hex": f"{scale_bits:08X}",
        "decrements": original_bits - scale_bits,
        "changed_distinct_face_words": changed_faces,
        "cells": cells,
        "exact_weighted_internal_face_change": str(weighted_exact_change),
        "rounded_weighted_state_change": str(rounded_change),
        "passes_selected_star_predicate": accepted,
    }


def first_passing_scale(shared: dict, writer, producer, *, max_decrements: int) -> dict:
    """Find the largest recorded-scale word passing this selected-star predicate."""
    if type(max_decrements) is not int or max_decrements < 0:
        raise ValueError("max_decrements must be a nonnegative integer")
    old_bits = producer.bits(3, "RK3_PD_LIMIT_CELL", *TARGET, "SCALE")
    if max_decrements >= old_bits:
        raise ValueError("search would reach zero scale")
    checked = []
    for decrement in range(max_decrements + 1):
        result = evaluate_scale(shared, writer, producer, old_bits - decrement)
        checked.append(result)
        if result["passes_selected_star_predicate"]:
            return {"checked": checked, "first_passing_decrements": decrement}
    return {"checked": checked, "first_passing_decrements": None}
