"""Offline one-ULP donor-scale probe on the saved seven-cell QNC witness.

This changes six already captured target correction faces in a copy of the
trace and gives each neighboring cell the identical changed shared face. It
does not modify or execute the host limiter.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
from itertools import product

import numpy as np

from harness.analyze_native_qnc_saved_state_budget import analyze_saved_state_budget
from harness.analyze_qnc_shared_face_trace import (
    STAR, TARGET, _add, _bits, _fma, _mul, _sub, _value,
)
from harness.analyze_qnc_weighted_ledger import analyze_weighted_ledger
from harness.analyze_upstream_nc_trace import _generic_replay
from harness.replay_qnc_flux_limiter_trace import _limiter_replay


SHARED = (
    ("FX_WEST", (220, 6, 63), "FX_EAST", -1),
    ("FX_EAST", (222, 6, 63), "FX_WEST", +1),
    ("FY_SOUTH", (221, 6, 62), "FY_NORTH", -1),
    ("FY_NORTH", (221, 6, 64), "FY_SOUTH", +1),
    ("FZ_BOTTOM", (221, 5, 63), "FZ_TOP", +1),
    ("FZ_TOP", (221, 7, 63), "FZ_BOTTOM", -1),
)
AXES = (
    ("Z", "RK3_POST", "RK3_AFTER_Z", "FZ_TOP", "FZ_BOTTOM", "FZ_LOW_TOP", "FZ_LOW_BOTTOM", "RDZW"),
    ("X", "RK3_AFTER_Z", "RK3_AFTER_X", "FX_EAST", "FX_WEST", "FX_LOW_EAST", "FX_LOW_WEST", "RDX"),
    ("Y", "RK3_AFTER_X", "RK3_AFTER_Y", "FY_NORTH", "FY_SOUTH", "FY_LOW_NORTH", "FY_LOW_SOUTH", "RDY"),
)


def _face(shared: dict, coord: tuple[int, int, int], field: str) -> np.float32:
    return _value(shared["records"][(shared["owner_call_id"], "RK3_POST", *coord, field)])


def _tendency(shared: dict, coord: tuple[int, int, int], modes: tuple[bool, bool, bool]) -> np.float32:
    value = _face(shared, coord, "TENDENCY")
    for (axis, _, _, upper, lower, low_upper, low_lower, metric), fused in zip(AXES, modes):
        delta = _sub(_add(_sub(_face(shared, coord, upper), _face(shared, coord, lower)),
                          _face(shared, coord, low_upper)), _face(shared, coord, low_lower))
        factor = _face(shared, coord, metric)
        inner = _mul(factor, delta)
        if axis == "Z":
            value = _fma(-factor, delta, value) if fused else _sub(value, inner)
        else:
            mx = _face(shared, coord, "MSFTX")
            value = _fma(-mx, inner, value) if fused else _sub(value, _mul(mx, inner))
    return value


def _original_modes(shared: dict, coord: tuple[int, int, int]) -> tuple[tuple[bool, bool, bool], ...]:
    owner = shared["owner_call_id"]
    choices = []
    for axis, before, after, upper, lower, low_upper, low_lower, metric in AXES:
        previous = _value(shared["records"][(owner, before, *coord, "TENDENCY")])
        observed = shared["records"][(owner, after, *coord, "TENDENCY")]
        delta = _sub(_add(_sub(_face(shared, coord, upper), _face(shared, coord, lower)),
                          _face(shared, coord, low_upper)), _face(shared, coord, low_lower))
        factor = _face(shared, coord, metric)
        inner = _mul(factor, delta)
        if axis == "Z":
            separate, fused = _sub(previous, inner), _fma(-factor, delta, previous)
        else:
            mx = _face(shared, coord, "MSFTX")
            separate, fused = _sub(previous, _mul(mx, inner)), _fma(-mx, inner, previous)
        matching = tuple(mode for mode, candidate in ((False, separate), (True, fused))
                         if _bits(candidate) == observed)
        if not matching:
            raise ValueError(f"original {axis} tendency has no matching arithmetic at {coord}")
        choices.append(matching)
    return tuple(product(*choices))


def _rk_predictions(state, shared: dict, coord: tuple[int, int, int],
                    modes: tuple[tuple[bool, bool, bool], ...]) -> tuple[float, ...]:
    i, k, j = coord
    target = (i, j, k)
    original_modes = []
    for mode in (False, True):
        replay = _generic_replay(state, target, 3, fused=mode)
        if replay["qnc_bitwise_match"] and replay["scalar_old_bitwise_match"]:
            original_modes.append(mode)
    if not original_modes:
        raise ValueError(f"original RK3 has no matching arithmetic at {coord}")
    row = state.at(target, 3, "RKSCALAR_BEFORE", "ADVECT_TEND")
    key = (row.step, row.rk_step, row.stage, row.i, row.k, row.j, row.field)
    predictions = set()
    for choice in modes:
        adv = _tendency(shared, coord, choice)
        values = dict(state.values)
        values[key] = replace(row, bits=_bits(adv))
        changed = replace(state, values=values)
        for fused in original_modes:
            result = _generic_replay(changed, target, 3, fused=fused)
            predictions.add(result["predicted_qnc"]["value"])
    return tuple(sorted(predictions))


def _matching_rk_modes(state, coord: tuple[int, int, int]) -> set[bool]:
    target = (coord[0], coord[2], coord[1])
    matches = set()
    for mode in (False, True):
        replay = _generic_replay(state, target, 3, fused=mode)
        if replay["qnc_bitwise_match"] and replay["scalar_old_bitwise_match"]:
            matches.add(mode)
    return matches


def _exact_stored_pd_qnc(budget: dict, coord: tuple[int, int, int]) -> Fraction:
    i, k, j = coord
    terms = budget["cells"][f"i{i}_j{j}_k{k}"]["target_style_four_terms"]
    return (Fraction(terms["exact_saved_face_and_pd_baseline"]["exact"])
            + Fraction(terms["pd_old_buffer_storage_effect"]["exact"]))


def analyze_one_ulp_backoff(state, shared: dict, flux_group, *, case: str) -> dict:
    """Evaluate one representable scale decrement while holding saved inputs fixed."""
    original_limiter = _limiter_replay(flux_group, state)
    if not all((original_limiter["dt_step_matches_upstream_dt_rk"],
                original_limiter["pre_vs_target_limit_cell"],
                original_limiter["ph_low_replay"]["matches"] or bool(
                    original_limiter["ph_low_replay"]["matching_fma_candidates"]),
                original_limiter["flux_out_replay"]["matches"],
                all(row["branch_match"] and row["scale_match"]
                    for row in original_limiter["limit_cells"].values()),
                all(row["matches"] for row in original_limiter["correction_faces"].values()),
                all(original_limiter["low_order_faces_unchanged"].values()))):
        raise ValueError("original limiter branch/scale/face replay differs")
    limiter = flux_group.at(3, "RK3_PD_LIMIT_CELL", "LIMIT_HIT")
    scale_row = flux_group.at(3, "RK3_PD_LIMIT_CELL", "SCALE")
    if limiter.value is not True or not (0.0 < scale_row.value < 1.0):
        raise ValueError("target must have a taken positive outgoing limiter")
    old_bits = int(scale_row.bits)
    new_bits = old_bits - 1
    old_scale, new_scale = _value(old_bits), _value(new_bits)
    if not (0.0 < new_scale < old_scale):
        raise ValueError("one-ULP decrement did not reduce positive scale")
    modified = deepcopy(shared)
    owner = shared["owner_call_id"]
    for coord in STAR:
        i, k, j = coord
        if state.at((i, j, k), 3, "RKSCALAR_BEFORE", "TENDEC").bits is not False:
            raise ValueError(f"final RK3 at {coord} must use the non-tenddec path")
        recorded = shared["records"][(owner, "RK3_AFTER_Y", *coord, "TENDENCY")]
        applied = state.at((i, j, k), 3, "RKSCALAR_BEFORE", "ADVECT_TEND").bits
        if recorded != applied:
            raise ValueError(f"shared face and RK input tendency differ at {coord}")
    for field in ("FX_LOW_WEST", "FX_LOW_EAST", "FY_LOW_SOUTH", "FY_LOW_NORTH",
                  "FZ_LOW_BOTTOM", "FZ_LOW_TOP", "MSFTX", "MSFTY", "RDX", "RDY", "RDZW"):
        captured = flux_group.at(3, "RK3_PD_POST_LIMIT_FACES", field).bits
        if captured != shared["records"][(owner, "RK3_POST", *TARGET, field)]:
            raise ValueError(f"flux and shared-face target {field} differ")
    changes = []
    for field, neighbor, other, sign in SHARED:
        neighbor_limit = flux_group.at(3, "RK3_PD_LIMIT_CELL", "LIMIT_HIT", neighbor)
        neighbor_scale = flux_group.at(3, "RK3_PD_LIMIT_CELL", "SCALE", neighbor)
        if neighbor_limit.value is not False or neighbor_scale.bits != 0x3F800000:
            raise ValueError(f"neighbor at {neighbor} also changes this outgoing face")
        pre = flux_group.at(3, "RK3_PD_PRE_LIMIT", field).value
        if np.sign(pre) != sign:
            raise ValueError(f"{field} is not target outgoing in saved trace")
        old_face = _bits(_mul(pre, old_scale))
        target_key = (owner, "RK3_POST", *TARGET, field)
        neighbor_key = (owner, "RK3_POST", *neighbor, other)
        if shared["records"][target_key] != old_face or shared["records"][neighbor_key] != old_face:
            raise ValueError(f"original {field} shared face does not match the captured scale")
        new_face = _bits(_mul(pre, new_scale))
        modified["records"][target_key] = new_face
        modified["records"][neighbor_key] = new_face
        changes.append({"target_face": field, "neighbor_ikj": neighbor,
                        "before_hex": f"{old_face:08X}", "after_hex": f"{new_face:08X}"})
    before = analyze_saved_state_budget(state, shared, run_id=f"{case}_saved")
    after = analyze_saved_state_budget(state, modified, run_id=f"{case}_counterfactual")
    old_ledger = analyze_weighted_ledger(shared, run_id=f"{case}_saved")
    new_ledger = analyze_weighted_ledger(modified, run_id=f"{case}_counterfactual")
    if old_ledger["exact_face_total"]["exact"] != new_ledger["exact_face_total"]["exact"]:
        raise ValueError("seven-cell perimeter changed despite paired internal faces")
    cells = {}
    common_direction_modes: set[tuple[bool, bool, bool]] | None = None
    common_rk_modes: set[bool] | None = None
    for coord in STAR:
        modes = _original_modes(shared, coord)
        common_direction_modes = (set(modes) if common_direction_modes is None else
                                  common_direction_modes.intersection(modes))
        rk_modes = _matching_rk_modes(state, coord)
        common_rk_modes = (rk_modes if common_rk_modes is None else
                           common_rk_modes.intersection(rk_modes))
        original = _rk_predictions(state, shared, coord, modes)
        actual = float(state.at((coord[0], coord[2], coord[1]), 3, "RKSCALAR_AFTER", "QNC").f32)
        if actual not in original:
            raise ValueError(f"original source-compatible RK3 replay missed {coord}")
        proposed = _rk_predictions(state, modified, coord, modes)
        exact = _exact_stored_pd_qnc(after, coord)
        cells[f"i{coord[0]}_j{coord[2]}_k{coord[1]}"] = {
            "original_recorded_qnc_raw": actual,
            "original_exact_stored_pd_qnc_raw": float(_exact_stored_pd_qnc(before, coord)),
            "candidate_exact_stored_pd_qnc_raw": {"exact": str(exact), "approximately": float(exact)},
            "candidate_source_compatible_f32_qnc_raw": list(proposed),
            "candidate_all_replays_nonnegative": all(value >= 0 for value in proposed),
            "original_matching_direction_mode_count": len(modes),
        }
    if not common_direction_modes or not common_rk_modes:
        raise ValueError("no arithmetic mode is compatible across all seven cells")
    return {
        "schema": "kdm6.saved_qnc_one_ulp_backoff.v1", "case": case,
        "original_scale": {"hex": f"{old_bits:08X}", "value": float(old_scale)},
        "candidate_scale": {"hex": f"{new_bits:08X}", "value": float(new_scale)},
        "original_limiter_branch_scale_and_faces_replayed": True,
        "all_seven_rk3_non_tenddec": True,
        "common_original_direction_modes": [list(mode) for mode in sorted(common_direction_modes)],
        "common_original_rk_modes_fused": sorted(common_rk_modes),
        "changed_shared_correction_faces": changes,
        "changed_face_word_count": sum(face["before_hex"] != face["after_hex"] for face in changes),
        "internal_component_pairs_canceled": len(new_ledger["internal_face_component_pairs"]),
        "perimeter_face_incidences": new_ledger["perimeter_face_incidences"],
        "perimeter_exact_unchanged": True,
        "all_seven_exact_stored_pd_qnc_nonnegative": all(
            Fraction(cell["candidate_exact_stored_pd_qnc_raw"]["exact"]) >= 0
            for cell in cells.values()),
        "all_seven_source_compatible_replays_nonnegative": all(
            cell["candidate_all_replays_nonnegative"] for cell in cells.values()),
        "minimum_seven_source_compatible_f32_qnc_raw": min(
            min(cell["candidate_source_compatible_f32_qnc_raw"]) for cell in cells.values()),
        "cells": cells,
        "limits": {
            "saved_operand_counterfactual_only": True,
            "host_execution_or_global_positivity_verified": False,
            "physical_number_units_or_full_budget_certified": False,
            "compiler_instruction_sequence_identified": False,
            "candidate_RTTOV_cost_or_analysis_acceptance": False,
        },
    }
