"""Exact-rational seven-cell QNC face/tendency ledger on saved f32 operands.

The weights undo the *recorded numerical operator* coefficients. They are not
certified cell masses, volumes, or physical particle-number units.
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np

from harness.analyze_qnc_shared_face_trace import STAR


FACE_SIDES = (
    ("x", "west", -1, -1, 0, 0, "FX_WEST", "FX_LOW_WEST"),
    ("x", "east", 1, 1, 0, 0, "FX_EAST", "FX_LOW_EAST"),
    ("y", "south", -1, 0, 0, -1, "FY_SOUTH", "FY_LOW_SOUTH"),
    ("y", "north", 1, 0, 0, 1, "FY_NORTH", "FY_LOW_NORTH"),
    ("z", "bottom", -1, 0, -1, 0, "FZ_BOTTOM", "FZ_LOW_BOTTOM"),
    ("z", "top", 1, 0, 1, 0, "FZ_TOP", "FZ_LOW_TOP"),
)
STAGE_PAIR = {
    "z": ("RK3_POST", "RK3_AFTER_Z"),
    "x": ("RK3_AFTER_Z", "RK3_AFTER_X"),
    "y": ("RK3_AFTER_X", "RK3_AFTER_Y"),
}


def _fraction(bits: int) -> Fraction:
    value = np.asarray([bits], dtype=np.uint32).view(np.float32)[0]
    if not np.isfinite(value):
        raise ValueError("weighted ledger requires finite binary32 operands")
    return Fraction.from_float(float(value))


def _amount(value: Fraction) -> dict[str, object]:
    return {"exact": str(value), "approximately": float(value)}


def analyze_weighted_ledger(shared: dict, *, run_id: str) -> dict:
    """Compare exact face algebra with exact differences of recorded f32 stores."""
    owner = shared["owner_call_id"]
    records = shared["records"]
    star = set(STAR)

    def bits(stage: str, coord: tuple[int, int, int], field: str) -> int:
        return records[(owner, stage, *coord, field)]

    def value(stage: str, coord: tuple[int, int, int], field: str) -> Fraction:
        return _fraction(bits(stage, coord, field))

    face_by_axis = {axis: {"correction": Fraction(0), "low_order": Fraction(0)}
                    for axis in ("z", "x", "y")}
    observed_by_axis = {axis: Fraction(0) for axis in ("z", "x", "y")}
    internal: dict[tuple[str, tuple[int, int, int], tuple[int, int, int], str], list] = {}
    external = {"correction": Fraction(0), "low_order": Fraction(0)}
    counts = {"internal_incidents": 0, "external_incidents": 0}
    for coord in STAR:
        i, k, j = coord
        mx, rz = value("RK3_POST", coord, "MSFTX"), value("RK3_POST", coord, "RDZW")
        rx, ry = value("RK3_POST", coord, "RDX"), value("RK3_POST", coord, "RDY")
        if mx == 0 or rz == 0:
            raise ValueError(f"zero map/vertical metric at {coord}")
        weight = -1 / (mx * rz)
        for axis, (before, after) in STAGE_PAIR.items():
            observed_by_axis[axis] += weight * (value(after, coord, "TENDENCY")
                                                  - value(before, coord, "TENDENCY"))
        for axis, side, sign, di, dk, dj, correction_field, low_field in FACE_SIDES:
            neighbor = (i + di, k + dk, j + dj)
            coefficient = (rx / rz if axis == "x" else ry / rz if axis == "y" else 1 / mx)
            counts["internal_incidents" if neighbor in star else "external_incidents"] += 1
            for component, field in (("correction", correction_field), ("low_order", low_field)):
                contribution = sign * coefficient * value("RK3_POST", coord, field)
                face_by_axis[axis][component] += contribution
                if neighbor in star:
                    key = (axis, min(coord, neighbor), max(coord, neighbor), component)
                    internal.setdefault(key, []).append((coord, bits("RK3_POST", coord, field), contribution))
                else:
                    external[component] += contribution
    if counts != {"internal_incidents": 12, "external_incidents": 30}:
        raise ValueError("seven-cell star does not have six internal and 30 outer incidences")
    if len(internal) != 12:
        raise ValueError("six shared faces must each have correction and low-order entries")
    paired = {}
    for key, entries in internal.items():
        if len(entries) != 2:
            raise ValueError(f"shared face is not represented twice: {key}")
        same_bits = entries[0][1] == entries[1][1]
        cancels = entries[0][2] + entries[1][2] == 0
        paired["%s_%s_%s_%s" % key] = {"same_face_bits": same_bits, "exact_coefficient_cancellation": cancels}
        if not same_bits or not cancels:
            raise ValueError(f"internal face failed exact cancellation: {key}")
    axis_result = {}
    face_total, observed_total = Fraction(0), Fraction(0)
    for axis in ("z", "x", "y"):
        face = face_by_axis[axis]["correction"] + face_by_axis[axis]["low_order"]
        observed = observed_by_axis[axis]
        face_total += face
        observed_total += observed
        axis_result[axis] = {
            "correction_face": _amount(face_by_axis[axis]["correction"]),
            "low_order_face": _amount(face_by_axis[axis]["low_order"]),
            "total_face": _amount(face),
            "recorded_weighted_tendency_change": _amount(observed),
            "recorded_minus_face": _amount(observed - face),
        }
    outer_total = external["correction"] + external["low_order"]
    if face_total != outer_total:
        raise ValueError("total face ledger differs from 30-face outer boundary")
    return {
        "schema": "kdm6.native_qnc_weighted_ledger.v1",
        "run_id": run_id,
        "shared_trace_sha256": shared["sha256"],
        "native_weight": "w_i=-1/(MSFTX_i*RDZW_i); source Y tendency uses MSFTX, not MSFTY",
        "internal_face_component_pairs": paired,
        "internal_correction_exact": _amount(Fraction(0)),
        "internal_low_order_exact": _amount(Fraction(0)),
        "perimeter_face_incidences": 30,
        "perimeter_correction": _amount(external["correction"]),
        "perimeter_low_order": _amount(external["low_order"]),
        "perimeter_total": _amount(outer_total),
        "axis": axis_result,
        "exact_face_total": _amount(face_total),
        "recorded_weighted_tendency_total": _amount(observed_total),
        "recorded_minus_exact_face": _amount(observed_total - face_total),
        "limits": {
            "exact_identity_for_saved_binary32_operands_only": True,
            "executed_fma_instruction_certified": False,
            "physical_number_units_certified": False,
            "old_new_QNC_state_budget_closed": False,
            "whole_domain_conservation_certified": False,
        },
    }
