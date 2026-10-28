"""Exact saved-face QNC residual and one-ULP local scale probe.

The trace is frozen. A counterfactual changes six target correction-face words
in memory and keeps the recorded low-order faces, mass factors and RK inputs.
It does not run the host or update a neighboring cell's shared-face state.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
from itertools import product
import json
from pathlib import Path

import numpy as np

from harness.analyze_qnc_shared_face_trace import _add, _bits, _fma, _mul, _sub
from harness.analyze_upstream_nc_trace import _div, _fma32
from harness.native_qnc_advect_qi_trace_records import (
    FACES,
    QNC_IKJ,
    NativeValueTrace,
    read_qnc_producer_trace,
)
from harness.native_qnc_representative_trace_records import (
    RepresentativeTrace,
    read_representative_trace,
)


OUTGOING_SIGN = {"FX_WEST": -1, "FX_EAST": 1,
                 "FY_SOUTH": -1, "FY_NORTH": 1,
                 "FZ_BOTTOM": 1, "FZ_TOP": -1}
AXES = (
    ("Z", "FZ_TOP", "FZ_BOTTOM", "FZ_LOW_TOP", "FZ_LOW_BOTTOM", "RDZW"),
    ("X", "FX_EAST", "FX_WEST", "FX_LOW_EAST", "FX_LOW_WEST", "RDX"),
    ("Y", "FY_NORTH", "FY_SOUTH", "FY_LOW_NORTH", "FY_LOW_SOUTH", "RDY"),
)


def _amount(value: Fraction) -> dict[str, str | float]:
    return {"exact": str(value), "approximately": float(value)}


def _fraction(value: np.float32) -> Fraction:
    return Fraction.from_float(float(value))


def _read_source(trace: NativeValueTrace, stage: str, field: str) -> np.float32:
    return trace.f32(3, stage, *QNC_IKJ, field)


def _read_rk(state: RepresentativeTrace, field: str) -> np.float32:
    i, k, j = QNC_IKJ
    return state.f32(3, "RKSCALAR_BEFORE", i, j, k, field)


def _faces(trace: NativeValueTrace, stage: str) -> dict[str, np.float32]:
    return {field: _read_source(trace, stage, field) for field in FACES}


def _exact_divergence(
    trace: NativeValueTrace, faces: dict[str, np.float32], *, low: bool,
) -> Fraction:
    metric = {field: _fraction(_read_source(trace, "RK3_PD_POST_LIMIT_FACES", field))
              for field in ("MSFTX", "RDX", "RDY", "RDZW")}

    def face(name: str) -> Fraction:
        if low:
            family, side = name.split("_", 1)
            name = f"{family}_LOW_{side}"
        return _fraction(faces[name])

    z = -metric["RDZW"] * (face("FZ_TOP") - face("FZ_BOTTOM"))
    x = -metric["MSFTX"] * metric["RDX"] * (face("FX_EAST") - face("FX_WEST"))
    y = -metric["MSFTX"] * metric["RDY"] * (face("FY_NORTH") - face("FY_SOUTH"))
    return z + x + y


def _exact_budget(
    trace: NativeValueTrace, state: RepresentativeTrace,
    correction: dict[str, np.float32],
) -> dict:
    low = _faces(trace, "RK3_PD_POST_LIMIT_FACES")
    rk = {field: _fraction(_read_rk(state, field)) for field in
          ("C1H", "C2H", "MU_OLD", "MU_NEW", "MU_BASE", "SCALAR_OLD",
           "SCALAR_TEND", "DT_RK", "MSFTY")}
    if rk["SCALAR_TEND"] != 0 or state.bits(3, "RKSCALAR_BEFORE", QNC_IKJ[0],
                                           QNC_IKJ[2], QNC_IKJ[1], "TENDEC") is not False:
        raise ValueError("recorded RK3 source/tenddec contract differs")
    a_old = rk["C1H"] * (rk["MU_OLD"] + rk["MU_BASE"]) + rk["C2H"]
    a_new = rk["C1H"] * (rk["MU_NEW"] + rk["MU_BASE"]) + rk["C2H"]
    if a_new <= 0:
        raise ValueError("recorded new mass factor is nonpositive")
    low_div = _exact_divergence(trace, low, low=True)
    correction_div = _exact_divergence(trace, correction, low=False)
    available = a_old * rk["SCALAR_OLD"] + rk["DT_RK"] * rk["MSFTY"] * low_div
    outflow = -rk["DT_RK"] * rk["MSFTY"] * correction_div
    residual = available - outflow
    return {"available": _amount(available), "applied_outflow": _amount(outflow),
            "residual": _amount(residual), "exact_real_qnc": _amount(residual / a_new),
            "new_mass_factor": _amount(a_new)}


def _directional_tendency(
    trace: NativeValueTrace, correction: dict[str, np.float32],
    mode: tuple[bool, bool, bool],
) -> tuple[np.float32, tuple[int, int, int]]:
    low = _faces(trace, "RK3_PD_POST_LIMIT_FACES")
    value = _read_source(trace, "RK3_PD_PRE_LIMIT", "TENDENCY")
    words = []
    for (axis, upper, lower, low_upper, low_lower, spacing), fused in zip(AXES, mode):
        delta = _sub(_add(_sub(correction[upper], correction[lower]), low[low_upper]),
                     low[low_lower])
        factor = _read_source(trace, "RK3_PD_POST_LIMIT_FACES", spacing)
        inner = _mul(factor, delta)
        if axis == "Z":
            value = _fma(-factor, delta, value) if fused else _sub(value, inner)
        else:
            mx = _read_source(trace, "RK3_PD_POST_LIMIT_FACES", "MSFTX")
            value = _fma(-mx, inner, value) if fused else _sub(value, _mul(mx, inner))
        words.append(_bits(value))
    return value, tuple(words)


def _compatible_modes(
    trace: NativeValueTrace, original: dict[str, np.float32],
) -> tuple[tuple[bool, bool, bool], ...]:
    observed = tuple(trace.bits(3, f"RK3_AFTER_{axis}", *QNC_IKJ, "TENDENCY")
                     for axis in ("Z", "X", "Y"))
    modes = tuple(mode for mode in product((False, True), repeat=3)
                  if _directional_tendency(trace, original, mode)[1] == observed)
    if not modes:
        raise ValueError("recorded RK3 directional tendencies have no compatible arithmetic")
    return modes


def _rk3_output(state: RepresentativeTrace, advect: np.float32, *, fused: bool) -> np.float32:
    def f(field: str) -> np.float32:
        return _read_rk(state, field)

    mu_old = _add(f("MU_OLD"), f("MU_BASE"))
    mu_new = _add(f("MU_NEW"), f("MU_BASE"))
    tendency = (_fma32(advect, f("MSFTY"), f("SCALAR_TEND")) if fused else
                _add(_mul(advect, f("MSFTY")), f("SCALAR_TEND")))
    old_factor = (_fma32(f("C1H"), mu_old, f("C2H")) if fused else
                  _add(_mul(f("C1H"), mu_old), f("C2H")))
    new_factor = (_fma32(f("C1H"), mu_new, f("C2H")) if fused else
                  _add(_mul(f("C1H"), mu_new), f("C2H")))
    dt_term = _mul(f("DT_RK"), tendency)
    numerator = (_fma32(old_factor, f("SCALAR_OLD"), dt_term) if fused else
                 _add(_mul(old_factor, f("SCALAR_OLD")), dt_term))
    return _div(numerator, new_factor)


def _rk_modes(state: RepresentativeTrace, original_advect: np.float32) -> tuple[bool, ...]:
    i, k, j = QNC_IKJ
    observed = state.bits(3, "RKSCALAR_AFTER", i, j, k, "QNC")
    modes = tuple(fused for fused in (False, True)
                  if _bits(_rk3_output(state, original_advect, fused=fused)) == observed)
    if not modes:
        raise ValueError("recorded RK3 output has no compatible arithmetic")
    return modes


def analyze_case(trace: NativeValueTrace, state: RepresentativeTrace, *, case: str) -> dict:
    if case not in {"control", "alpha025"}:
        raise ValueError("case must be control or alpha025")
    scale_bits = trace.bits(3, "RK3_PD_LIMIT_CELL", *QNC_IKJ, "SCALE")
    if type(scale_bits) is not int or scale_bits != 0x3C54898F or trace.bits(
            3, "RK3_PD_LIMIT_CELL", *QNC_IKJ, "LIMIT_HIT") is not True:
        raise ValueError("recorded target limiter scale/branch differs")
    scale = _read_source(trace, "RK3_PD_LIMIT_CELL", "SCALE")
    ph_low = _read_source(trace, "RK3_PD_LIMIT_CELL", "PH_LOW")
    flux_out = _read_source(trace, "RK3_PD_LIMIT_CELL", "FLUX_OUT")
    for field, value in (("PH_LOW", ph_low), ("FLUX_OUT", flux_out)):
        if _bits(value) != _bits(_read_source(trace, "RK3_PD_PRE_LIMIT", field)):
            raise ValueError(f"target limiter {field} input differs from pre-limit capture")
    source_scale = np.float32(max(np.float32(0), np.float32(
        ph_low / np.float32(flux_out + np.float32(1e-20)))))
    if _bits(source_scale) != scale_bits:
        raise ValueError("target limiter scale differs from source-compatible f32 formula")
    lower_bits = scale_bits - 1
    lower = np.asarray([lower_bits], dtype=np.uint32).view(np.float32)[0]
    if not (0 < lower < scale < 1):
        raise ValueError("one-ULP scale decrement is not positive and smaller")
    limiter_margin = _fraction(ph_low) - _fraction(flux_out) * _fraction(scale)
    lower_limiter_margin = _fraction(ph_low) - _fraction(flux_out) * _fraction(lower)
    pre, post = (_faces(trace, stage) for stage in
                 ("RK3_PD_PRE_LIMIT", "RK3_PD_POST_LIMIT_FACES"))
    face_rows = []
    changed = dict(post)
    for field, sign in OUTGOING_SIGN.items():
        original = pre[field]
        if np.sign(original) != sign or _bits(_mul(original, scale)) != _bits(post[field]):
            raise ValueError(f"recorded {field} is not a target-scaled outgoing face")
        next_face = _mul(original, lower)
        changed[field] = next_face
        face_rows.append({"field": field,
                          "pre_hex": f"{_bits(original):08X}",
                          "post_hex": f"{_bits(post[field]):08X}",
                          "counterfactual_post_hex": f"{_bits(next_face):08X}"})
    for field in FACES:
        if field.startswith(("FX_LOW", "FY_LOW", "FZ_LOW")) and _bits(pre[field]) != _bits(post[field]):
            raise ValueError(f"recorded {field} low-order face changed")
    original_adv = _read_source(trace, "RK3_AFTER_Y", "TENDENCY")
    if _bits(original_adv) != state.bits(3, "RKSCALAR_BEFORE", QNC_IKJ[0],
                                         QNC_IKJ[2], QNC_IKJ[1], "ADVECT_TEND"):
        raise ValueError("recorded post-limiter tendency differs from RK3 input")
    modes = _compatible_modes(trace, post)
    rk_modes = _rk_modes(state, original_adv)
    predictions = sorted({(_bits(value), float(value))
                          for mode in modes for fused in rk_modes
                          for value in (_rk3_output(
                              state, _directional_tendency(trace, changed, mode)[0], fused=fused),)})
    return {"case": case, "producer_trace_sha256": trace.sha256,
            "rk3_state_trace_sha256": state.sha256,
            "target_scale": {"hex": f"{scale_bits:08X}", "value": float(scale)},
            "one_ulp_lower_scale": {"hex": f"{lower_bits:08X}", "value": float(lower)},
            "target_limiter_hit": True,
            "target_scale_source_compatible": True,
            "limiter_threshold_inputs": {
                "ph_low": {"hex": f"{_bits(ph_low):08X}", "value": float(ph_low)},
                "flux_out": {"hex": f"{_bits(flux_out):08X}", "value": float(flux_out)},
                "exact_ph_low_minus_flux_out_times_scale": _amount(limiter_margin),
                "exact_ph_low_minus_flux_out_times_lower_scale": _amount(lower_limiter_margin),
            },
            "six_outgoing_correction_faces_replayed": True,
            "low_order_faces_unchanged": True,
            "faces": face_rows,
            "original_exact_saved_face": _exact_budget(trace, state, post),
            "one_ulp_exact_saved_face": _exact_budget(trace, state, changed),
            "original_compatible_direction_modes": [list(mode) for mode in modes],
            "original_compatible_rk_fused_modes": list(rk_modes),
            "one_ulp_compatible_f32_qnc": [
                {"hex": f"{bits:08X}", "value": value} for bits, value in predictions],
            "all_compatible_f32_qnc_positive": all(value > 0 for _, value in predictions),
    }


def analyze(control_trace: NativeValueTrace, alpha_trace: NativeValueTrace,
            control_state: RepresentativeTrace, alpha_state: RepresentativeTrace) -> dict:
    control = analyze_case(control_trace, control_state, case="control")
    alpha = analyze_case(alpha_trace, alpha_state, case="alpha025")
    common = set(tuple(mode) for mode in control["original_compatible_direction_modes"]) & set(
        tuple(mode) for mode in alpha["original_compatible_direction_modes"])
    original_alpha = Fraction(alpha["original_exact_saved_face"]["residual"]["exact"])
    one_ulp_alpha = Fraction(alpha["one_ulp_exact_saved_face"]["residual"]["exact"])
    if (len(common) != 4 or original_alpha >= 0 or one_ulp_alpha >= 0 or
            not alpha["all_compatible_f32_qnc_positive"]):
        raise ValueError("saved-face counterfactual sign pattern differs")
    return {"schema": "kdm6.native_qnc_saved_face_residual_probe.v1",
            "control": control, "alpha025": alpha,
            "common_original_direction_modes": [list(mode) for mode in sorted(common)],
            "conclusion": "ONE_ULP_F32_POSITIVE_EXACT_SAVED_FACE_RESIDUAL_NEGATIVE",
            "offline_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
            "limits": {"host_variant_executed_for_one_ulp_probe": False,
                       "neighbor_shared_face_state_evaluated": False,
                       "physical_number_units_certified": False,
                       "full_fixed_support_candidate_admissible": False,
                       "compiler_instruction_sequence_identified": False}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for case in ("control", "alpha025"):
        parser.add_argument(f"--{case}-producer", type=Path, required=True)
        parser.add_argument(f"--{case}-state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(args.output)
    cases = ("control", "alpha025")
    producer = {case: read_qnc_producer_trace(getattr(args, f"{case}_producer")) for case in cases}
    state = {case: read_representative_trace(getattr(args, f"{case}_state")) for case in cases}
    result = analyze(producer["control"], producer["alpha025"],
                     state["control"], state["alpha025"])
    raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(raw)
    print(json.dumps({"status": "QNC_SAVED_FACE_RESIDUAL_PASSED",
                      "analysis_sha256": hashlib.sha256(raw).hexdigest()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
