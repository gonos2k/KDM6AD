"""Replay seven-cell RK3 QNC faces/states and the executed QI boundary input.

The one-ULP probe mirrors changed target faces to adjacent cells in memory.
It keeps the rest of the recorded operands fixed and never executes a host
variant; its exact-real and source-compatible f32 results are separate.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
from itertools import product
import json
from pathlib import Path

import numpy as np

from harness.analyze_qnc_shared_face_trace import _add, _bits, _fma, _mul, _sub, _value
from harness.analyze_upstream_nc_trace import _div, _fma32
from harness.native_qnc_advect_qi_trace_records import NativeValueTrace
from harness.native_qnc_advect_qi_trace_records import (
    read_qi_writer_trace,
    read_qnc_producer_trace,
)
from harness.native_qnc_star_qi_records import (
    AXES,
    POST_FIELDS,
    STAR_IKJ,
    read_qnc_star_trace,
    read_star_qi_writer_trace,
)


TARGET = STAR_IKJ[0]
SHARED = (
    ("x_west", "FX_WEST", STAR_IKJ[1], "FX_EAST", "FX_LOW_WEST", "FX_LOW_EAST"),
    ("x_east", "FX_EAST", STAR_IKJ[2], "FX_WEST", "FX_LOW_EAST", "FX_LOW_WEST"),
    ("y_south", "FY_SOUTH", STAR_IKJ[3], "FY_NORTH", "FY_LOW_SOUTH", "FY_LOW_NORTH"),
    ("y_north", "FY_NORTH", STAR_IKJ[4], "FY_SOUTH", "FY_LOW_NORTH", "FY_LOW_SOUTH"),
    ("z_bottom", "FZ_BOTTOM", STAR_IKJ[5], "FZ_TOP", "FZ_LOW_BOTTOM", "FZ_LOW_TOP"),
    ("z_top", "FZ_TOP", STAR_IKJ[6], "FZ_BOTTOM", "FZ_LOW_TOP", "FZ_LOW_BOTTOM"),
)
AXIS_FIELDS = (
    ("Z", "FZ_TOP", "FZ_BOTTOM", "FZ_LOW_TOP", "FZ_LOW_BOTTOM", "RDZW"),
    ("X", "FX_EAST", "FX_WEST", "FX_LOW_EAST", "FX_LOW_WEST", "RDX"),
    ("Y", "FY_NORTH", "FY_SOUTH", "FY_LOW_NORTH", "FY_LOW_SOUTH", "RDY"),
)


def _amount(x: Fraction) -> dict:
    return {"exact": str(x), "approximately": float(x)}


def _frac(x: np.float32) -> Fraction:
    return Fraction.from_float(float(x))


def _word(bits: int) -> str:
    return f"{bits:08X}"


def _shared_value(shared: dict, stage: str, coord: tuple[int, int, int], field: str) -> np.float32:
    return _value(shared["records"][(shared["owner_call_id"], stage, *coord, field)])


def _writer_value(writer: NativeValueTrace, stage: str,
                  coord: tuple[int, int, int], field: str) -> np.float32:
    return writer.f32(3, stage, *coord, field)


def _axis_predict(shared: dict, coord: tuple[int, int, int],
                  mode: tuple[bool, bool, bool]) -> tuple[np.float32, tuple[int, int, int]]:
    value = _shared_value(shared, "RK3_POST", coord, "TENDENCY")
    words = []
    for (axis, upper, lower, low_upper, low_lower, metric), fused in zip(AXIS_FIELDS, mode):
        delta = _sub(_add(_sub(_shared_value(shared, "RK3_POST", coord, upper),
                               _shared_value(shared, "RK3_POST", coord, lower)),
                          _shared_value(shared, "RK3_POST", coord, low_upper)),
                     _shared_value(shared, "RK3_POST", coord, low_lower))
        factor = _shared_value(shared, "RK3_POST", coord, metric)
        inner = _mul(factor, delta)
        if axis == "Z":
            value = _fma(-factor, delta, value) if fused else _sub(value, inner)
        else:
            mx = _shared_value(shared, "RK3_POST", coord, "MSFTX")
            value = _fma(-mx, inner, value) if fused else _sub(value, _mul(mx, inner))
        words.append(_bits(value))
    return value, tuple(words)


def _axis_modes(shared: dict, coord: tuple[int, int, int]) -> tuple[tuple[bool, bool, bool], ...]:
    owner = shared["owner_call_id"]
    observed = tuple(shared["records"][(owner, stage, *coord, "TENDENCY")] for stage in AXES)
    modes = tuple(mode for mode in product((False, True), repeat=3)
                  if _axis_predict(shared, coord, mode)[1] == observed)
    if not modes:
        raise ValueError(f"original directional tendency has no source-compatible mode at {coord}")
    return modes


def _pd_modes(writer: NativeValueTrace, coord: tuple[int, int, int]) -> tuple[bool, ...]:
    before, after = "RKSCALAR_PD_BEFORE", "RKSCALAR_PD_AFTER"

    def v(field: str) -> np.float32:
        return _writer_value(writer, before, coord, field)

    mu_old = _add(v("MU_OLD_ARG"), v("MU_BASE"))
    mu_new = _add(v("MU_NEW_ARG"), v("MU_BASE"))
    tendency = _add(np.float32(0), v("SCALAR_TEND"))
    dt_tendency = _mul(v("DT_RK"), tendency)
    matches = []
    for fused in (False, True):
        old_factor = (_fma32(v("C1H"), mu_old, v("C2H")) if fused else
                      _add(_mul(v("C1H"), mu_old), v("C2H")))
        new_factor = (_fma32(v("C1H"), mu_new, v("C2H")) if fused else
                      _add(_mul(v("C1H"), mu_new), v("C2H")))
        numerator = (_fma32(old_factor, v("SCALAR_OLD"), dt_tendency) if fused else
                     _add(_mul(old_factor, v("SCALAR_OLD")), dt_tendency))
        predicted = _div(numerator, new_factor)
        if _bits(predicted) == writer.bits(3, after, *coord, "SCALAR_OLD"):
            matches.append(fused)
    if (not matches or writer.bits(3, before, *coord, "QNC") !=
            writer.bits(3, after, *coord, "QNC") or
            writer.bits(3, after, *coord, "SCALAR_TEND") != 0):
        raise ValueError(f"PD old-buffer preparation differs at {coord}")
    return tuple(matches)


def _rk3_predict(writer: NativeValueTrace, coord: tuple[int, int, int],
                 advect: np.float32, *, fused: bool) -> np.float32:
    def v(field: str) -> np.float32:
        return _writer_value(writer, "RKSCALAR_BEFORE", coord, field)

    old = _add(v("MU_OLD"), v("MU_BASE"))
    new = _add(v("MU_NEW"), v("MU_BASE"))
    tendency = (_fma32(advect, v("MSFTY"), v("SCALAR_TEND")) if fused else
                _add(_mul(advect, v("MSFTY")), v("SCALAR_TEND")))
    old_factor = (_fma32(v("C1H"), old, v("C2H")) if fused else
                  _add(_mul(v("C1H"), old), v("C2H")))
    new_factor = (_fma32(v("C1H"), new, v("C2H")) if fused else
                  _add(_mul(v("C1H"), new), v("C2H")))
    dt_tendency = _mul(v("DT_RK"), tendency)
    numerator = (_fma32(old_factor, v("SCALAR_OLD"), dt_tendency) if fused else
                 _add(_mul(old_factor, v("SCALAR_OLD")), dt_tendency))
    return _div(numerator, new_factor)


def _rk_modes(writer: NativeValueTrace, coord: tuple[int, int, int]) -> tuple[bool, ...]:
    original_advect = _writer_value(writer, "RKSCALAR_BEFORE", coord, "ADVECT_TEND")
    observed = writer.bits(3, "RKSCALAR_AFTER", *coord, "QNC")
    modes = tuple(fused for fused in (False, True)
                  if _bits(_rk3_predict(writer, coord, original_advect, fused=fused)) == observed)
    if not modes:
        raise ValueError(f"original RK3 QNC has no source-compatible mode at {coord}")
    return modes


def _exact_cell(shared: dict, writer: NativeValueTrace,
                coord: tuple[int, int, int]) -> dict:
    def f(field: str) -> Fraction:
        return _frac(_shared_value(shared, "RK3_POST", coord, field))

    def v(field: str) -> Fraction:
        return _frac(_writer_value(writer, "RKSCALAR_BEFORE", coord, field))

    z_corr = -f("RDZW") * (f("FZ_TOP") - f("FZ_BOTTOM"))
    x_corr = -f("MSFTX") * f("RDX") * (f("FX_EAST") - f("FX_WEST"))
    y_corr = -f("MSFTX") * f("RDY") * (f("FY_NORTH") - f("FY_SOUTH"))
    z_low = -f("RDZW") * (f("FZ_LOW_TOP") - f("FZ_LOW_BOTTOM"))
    x_low = -f("MSFTX") * f("RDX") * (f("FX_LOW_EAST") - f("FX_LOW_WEST"))
    y_low = -f("MSFTX") * f("RDY") * (f("FY_LOW_NORTH") - f("FY_LOW_SOUTH"))
    old_factor = v("C1H") * (v("MU_OLD") + v("MU_BASE")) + v("C2H")
    new_factor = v("C1H") * (v("MU_NEW") + v("MU_BASE")) + v("C2H")
    if v("SCALAR_TEND") != 0 or new_factor <= 0:
        raise ValueError(f"saved RK3 source or mass factor differs at {coord}")
    available = old_factor * v("SCALAR_OLD") + v("DT_RK") * v("MSFTY") * (
        z_low + x_low + y_low)
    outflow = -v("DT_RK") * v("MSFTY") * (z_corr + x_corr + y_corr)
    residual = available - outflow
    return {"available": _amount(available), "applied_outflow": _amount(outflow),
            "residual": _amount(residual), "qnc": _amount(residual / new_factor),
            "new_mass_factor": _amount(new_factor)}


def _boundary(writer: NativeValueTrace, old: NativeValueTrace) -> dict:
    coord = (1, 33, 168)
    stage = "QI_BDY_INPUT"

    def word(field: str) -> str:
        return writer.word(3, stage, *coord, field)

    observed = writer.word(3, "QI_BDY_AFTER", *coord, "QI")
    before = word("QI")
    donor = word("DONOR_QI")
    wind = writer.f32(3, stage, *coord, "X_WIND")
    negative = writer.bits(3, stage, *coord, "X_WIND_NEGATIVE")
    eligible = writer.bits(3, stage, *coord, "X_START_ELIGIBLE")
    periodic = writer.bits(3, stage, *coord, "PERIODIC_X")
    indices = {field: int(writer.bits(3, stage, *coord, field)) for field in
               ("DONOR_I", "DONOR_J", "SPEC_ZONE", "IDS", "IDE", "JDS", "JDE",
                "TILE_ITS", "TILE_ITE", "TILE_JTS", "TILE_JTE")}
    if (before != old.word(3, "QI_RK_AFTER", *coord, "QI") or
            observed != old.word(3, "QI_BDY_AFTER", *coord, "QI") or
            before != "00000007" or indices["DONOR_I"] != 2 or
            indices["DONOR_J"] != 168 or indices["SPEC_ZONE"] != 1 or
            (indices["IDS"], indices["IDE"], indices["JDS"], indices["JDE"]) !=
                (1, 235, 1, 283) or periodic is not False or eligible is not True or
            negative is not bool(wind < 0) or
            observed != (donor if negative else "00000000")):
        raise ValueError("QI x-start boundary donor/velocity/copy join differs")
    return {"target_before_hex": before, "donor_qi_hex": donor,
            "target_after_hex": observed, "ru_m_input_hex": word("X_WIND"),
            "ru_m_input_value": float(wind), "copy_branch": bool(negative),
            "x_start_eligible": True, "periodic_x": False,
            "indices_one_based": indices,
            "donor_or_zero_prediction_matches": True}


def analyze_case(shared: dict, writer: NativeValueTrace, prior_writer: NativeValueTrace,
                 prior_producer: NativeValueTrace, *, case: str) -> dict:
    if case not in ("control", "alpha025"):
        raise ValueError("unexpected native case")
    if any(writer.values.get(key) != bits for key, bits in prior_writer.values.items()):
        raise ValueError("PR469 representative stage word changed")
    if len(prior_writer.values) != 678 or len(writer.values) != 1550 or shared["typed_records"] != 147:
        raise ValueError("star/writer trace count differs")
    owner = shared["owner_call_id"]
    for field in POST_FIELDS:
        expected = (prior_producer.bits(3, "RK3_PD_PRE_LIMIT", *TARGET, "TENDENCY")
                    if field == "TENDENCY" else prior_producer.bits(
                        3, "RK3_PD_POST_LIMIT_FACES", *TARGET, field))
        if shared["records"][(owner, "RK3_POST", *TARGET, field)] != expected:
            raise ValueError(f"shared center {field} differs from PR469 producer")
    for stage in AXES:
        if shared["records"][(owner, stage, *TARGET, "TENDENCY")] != prior_producer.bits(
                3, stage, *TARGET, "TENDENCY"):
            raise ValueError("shared center directional tendency differs from PR469")
    faces = []
    for name, target_face, neighbor, neighbor_face, target_low, neighbor_low in SHARED:
        correction = shared["records"][(owner, "RK3_POST", *TARGET, target_face)]
        receiving = shared["records"][(owner, "RK3_POST", *neighbor, neighbor_face)]
        low = shared["records"][(owner, "RK3_POST", *TARGET, target_low)]
        low_receiving = shared["records"][(owner, "RK3_POST", *neighbor, neighbor_low)]
        if correction != receiving or low != low_receiving:
            raise ValueError(f"{name} internal shared face bits differ")
        faces.append({"name": name, "neighbor_ikj_one_based": list(neighbor),
                      "correction_hex": _word(correction), "low_order_hex": _word(low),
                      "correction_bitwise_shared": True, "low_order_bitwise_shared": True})
    cells = {}
    common_axis_modes = None
    common_pd_modes = None
    common_rk_modes = None
    for coord in STAR_IKJ:
        key = f"i{coord[0]}_j{coord[2]}_k{coord[1]}"
        modes = _axis_modes(shared, coord)
        pd_modes = _pd_modes(writer, coord)
        rk_modes = _rk_modes(writer, coord)
        common_axis_modes = set(modes) if common_axis_modes is None else common_axis_modes & set(modes)
        common_pd_modes = set(pd_modes) if common_pd_modes is None else common_pd_modes & set(pd_modes)
        common_rk_modes = set(rk_modes) if common_rk_modes is None else common_rk_modes & set(rk_modes)
        after_y = shared["records"][(owner, "RK3_AFTER_Y", *coord, "TENDENCY")]
        if (after_y != writer.bits(3, "RKSCALAR_BEFORE", *coord, "ADVECT_TEND") or
                writer.bits(3, "RKSCALAR_PD_AFTER", *coord, "QNC") !=
                    writer.bits(3, "RKSCALAR_BEFORE", *coord, "QNC") or
                writer.bits(3, "RKSCALAR_PD_AFTER", *coord, "SCALAR_OLD") !=
                    writer.bits(3, "RKSCALAR_BEFORE", *coord, "SCALAR_OLD") or
                writer.bits(3, "RKSCALAR_BEFORE", *coord, "SCALAR_OLD") !=
                    writer.bits(3, "RKSCALAR_AFTER", *coord, "SCALAR_OLD") or
                writer.bits(3, "RKSCALAR_BEFORE", *coord, "TENDEC") is not False):
            raise ValueError(f"{key}: PD/face/RK input handoff differs")
        cells[key] = {"ikj_one_based": list(coord),
                      "original_qnc_hex": writer.word(3, "RKSCALAR_AFTER", *coord, "QNC"),
                      "original_qnc_value": float(_writer_value(writer, "RKSCALAR_AFTER", coord, "QNC")),
                      "original_exact_saved_face": _exact_cell(shared, writer, coord),
                      "directional_fused_modes": [list(mode) for mode in modes],
                      "pd_fused_modes": list(pd_modes),
                      "rk_fused_modes": list(rk_modes),
                      "last_face_tendency_matches_rk_input": True,
                      "pd_old_buffer_reaches_rk": True}
    if not common_axis_modes or not common_pd_modes or not common_rk_modes:
        raise ValueError("no common source-compatible arithmetic mode across seven cells")
    return {"case": case, "shared_trace_sha256": shared["sha256"],
            "writer_trace_sha256": writer.sha256,
            "prior_writer_trace_sha256": prior_writer.sha256,
            "prior_producer_trace_sha256": prior_producer.sha256,
            "prior_writer_word_matches": len(prior_writer.values),
            "shared_owner_call_id": owner, "shared_face_pairs": faces,
            "common_directional_fused_modes": [list(mode) for mode in sorted(common_axis_modes)],
            "common_pd_fused_modes": sorted(common_pd_modes),
            "common_rk_fused_modes": sorted(common_rk_modes),
            "cells": cells, "qi_boundary": _boundary(writer, prior_writer)}


def _paired_one_ulp_probe(shared: dict, writer: NativeValueTrace,
                          producer: NativeValueTrace) -> dict:
    old_bits = producer.bits(3, "RK3_PD_LIMIT_CELL", *TARGET, "SCALE")
    if type(old_bits) is not int or old_bits != 0x3C54898F:
        raise ValueError("recorded target limiter scale differs from frozen probe")
    new_bits = old_bits - 1
    old_scale, new_scale = _value(old_bits), _value(new_bits)
    if not 0 < new_scale < old_scale < 1:
        raise ValueError("one-ULP lower scale is not positive")
    owner = shared["owner_call_id"]
    changed = deepcopy(shared)
    updates = []
    internal_keys = set()
    for name, target_face, neighbor, neighbor_face, _, _ in SHARED:
        original = producer.f32(3, "RK3_PD_PRE_LIMIT", *TARGET, target_face)
        old_face = _bits(_mul(original, old_scale))
        key_target = (owner, "RK3_POST", *TARGET, target_face)
        key_neighbor = (owner, "RK3_POST", *neighbor, neighbor_face)
        if (shared["records"][key_target] != old_face or
                shared["records"][key_neighbor] != old_face):
            raise ValueError(f"{name}: original target scale/share join differs")
        new_face = _bits(_mul(original, new_scale))
        changed["records"][key_target] = new_face
        changed["records"][key_neighbor] = new_face
        internal_keys.update((key_target, key_neighbor))
        updates.append({"name": name, "neighbor_ikj_one_based": list(neighbor),
                        "pre_hex": _word(_bits(original)),
                        "original_post_hex": _word(old_face),
                        "candidate_post_hex": _word(new_face),
                        "target_neighbor_candidate_bits_equal": True})
    if any(changed["records"][key] != bits for key, bits in shared["records"].items()
           if key not in internal_keys):
        raise ValueError("counterfactual changed a perimeter or low-order face")
    cell_results = {}
    weighted_change = Fraction(0)
    for coord in STAR_IKJ:
        name = f"i{coord[0]}_j{coord[2]}_k{coord[1]}"
        original = _exact_cell(shared, writer, coord)
        candidate = _exact_cell(changed, writer, coord)
        compatible_axes = _axis_modes(shared, coord)
        compatible_rk = _rk_modes(writer, coord)
        predictions = sorted({(_bits(qnc), float(qnc))
                              for mode in compatible_axes for fused in compatible_rk
                              for qnc in (_rk3_predict(writer, coord,
                                          _axis_predict(changed, coord, mode)[0], fused=fused),)})
        correction = (Fraction(candidate["residual"]["exact"])
                      - Fraction(original["residual"]["exact"]))
        msftx = _frac(_shared_value(shared, "RK3_POST", coord, "MSFTX"))
        rdzw = _frac(_shared_value(shared, "RK3_POST", coord, "RDZW"))
        msfty = _frac(_writer_value(writer, "RKSCALAR_BEFORE", coord, "MSFTY"))
        if msftx == 0 or rdzw == 0 or msfty == 0:
            raise ValueError(f"{name}: zero numerical operator weight")
        weighted_change -= correction / (msftx * rdzw * msfty)
        cell_results[name] = {"ikj_one_based": list(coord),
                              "original_recorded_qnc_hex": writer.word(3, "RKSCALAR_AFTER", *coord, "QNC"),
                              "candidate_exact_saved_face": candidate,
                              "candidate_source_compatible_f32_qnc": [
                                  {"hex": _word(bits), "value": value} for bits, value in predictions],
                              "all_candidate_f32_qnc_positive": all(value > 0 for _, value in predictions)}
    if weighted_change != 0:
        raise ValueError("seven-cell weighted internal-face change did not cancel exactly")
    target_key = f"i{TARGET[0]}_j{TARGET[2]}_k{TARGET[1]}"
    if (Fraction(cell_results[target_key]["candidate_exact_saved_face"]["residual"]["exact"]) >= 0 or
            not all(cell["all_candidate_f32_qnc_positive"] for cell in cell_results.values()) or
            not all(Fraction(cell["candidate_exact_saved_face"]["residual"]["exact"]) > 0
                    for name, cell in cell_results.items() if name != target_key)):
        raise ValueError("frozen one-ULP donor/receiver sign pattern differs")
    return {"original_target_scale_hex": _word(old_bits),
            "one_ulp_lower_target_scale_hex": _word(new_bits),
            "six_mirrored_internal_correction_faces": updates,
            "changed_distinct_face_word_count": sum(
                row["original_post_hex"] != row["candidate_post_hex"] for row in updates),
            "perimeter_face_incidences_unchanged": 30,
            "exact_weighted_internal_face_change": _amount(weighted_change),
            "target_exact_residual_still_negative": True,
            "all_six_neighbor_exact_residuals_positive": True,
            "all_seven_source_compatible_f32_qnc_positive": True,
            "cells": cell_results,
            "host_counterfactual_executed": False}


def analyze(control_shared: dict, alpha_shared: dict,
            control_writer: NativeValueTrace, alpha_writer: NativeValueTrace,
            control_prior_writer: NativeValueTrace, alpha_prior_writer: NativeValueTrace,
            control_prior_producer: NativeValueTrace,
            alpha_prior_producer: NativeValueTrace) -> dict:
    control = analyze_case(control_shared, control_writer, control_prior_writer,
                           control_prior_producer, case="control")
    alpha = analyze_case(alpha_shared, alpha_writer, alpha_prior_writer,
                         alpha_prior_producer, case="alpha025")
    if (control["qi_boundary"]["copy_branch"] is not True or
            alpha["qi_boundary"]["copy_branch"] is not True or
            control["qi_boundary"]["donor_qi_hex"] != "00000000" or
            alpha["qi_boundary"]["donor_qi_hex"] != "00000002" or
            control["qi_boundary"]["ru_m_input_hex"] != alpha["qi_boundary"]["ru_m_input_hex"]):
        raise ValueError("control/alpha QI donor explanation differs")
    counterfactual = _paired_one_ulp_probe(alpha_shared, alpha_writer, alpha_prior_producer)
    return {"schema": "kdm6.native_qnc_star_qi_analysis.v1",
            "control": control, "alpha025": alpha,
            "alpha025_frozen_paired_one_ulp_probe": counterfactual,
            "conclusions": {"six_internal_correction_and_low_pairs_bitwise_shared": True,
                            "seven_cell_face_tendency_rk_input_join": True,
                            "qi_same_copy_branch_different_donor": True},
            "offline_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
            "limits": {"physical_number_units_certified": False,
                       "whole_domain_conservation_certified": False,
                       "host_one_ulp_counterfactual_executed": False,
                       "full_fixed_support_candidate_admissible": False}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for case in ("control", "alpha025"):
        parser.add_argument(f"--{case}-star", type=Path, required=True)
        parser.add_argument(f"--{case}-writer", type=Path, required=True)
        parser.add_argument(f"--{case}-prior-writer", type=Path, required=True)
        parser.add_argument(f"--{case}-prior-producer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(args.output)
    cases = ("control", "alpha025")
    star = {case: read_qnc_star_trace(getattr(args, f"{case}_star")) for case in cases}
    writer = {case: read_star_qi_writer_trace(getattr(args, f"{case}_writer")) for case in cases}
    prior_writer = {case: read_qi_writer_trace(getattr(args, f"{case}_prior_writer"))
                    for case in cases}
    prior_producer = {case: read_qnc_producer_trace(getattr(args, f"{case}_prior_producer"))
                      for case in cases}
    result = analyze(star["control"], star["alpha025"],
                     writer["control"], writer["alpha025"],
                     prior_writer["control"], prior_writer["alpha025"],
                     prior_producer["control"], prior_producer["alpha025"])
    raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(raw)
    print(json.dumps({"status": "QNC_STAR_QI_ANALYSIS_PASSED",
                      "analysis_sha256": hashlib.sha256(raw).hexdigest()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
