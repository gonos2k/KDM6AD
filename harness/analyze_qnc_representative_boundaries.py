"""Compare four same-level native moment paths through one full-host step.

This reads executed, raw-f32 witnesses. A first *recorded* difference is a
stage bracket, not attribution to one named physical process or a derivative.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from harness.native_qnc_representative_trace_overlay import TARGETS_IJK
from harness.native_qnc_representative_trace_records import (
    MOMENTS,
    RepresentativeTrace,
    read_representative_trace,
)


TIMELINE = (
    (1, "RKSCALAR_BEFORE"), (1, "RKSCALAR_AFTER"),
    (2, "RKSCALAR_BEFORE"), (2, "RKSCALAR_AFTER"),
    (3, "RKSCALAR_PD_BEFORE"), (3, "RKSCALAR_PD_AFTER"),
    (3, "RKSCALAR_BEFORE"), (3, "RKSCALAR_AFTER"),
    (3, "POST_SCALAR_BDY"),
    (0, "PRE_MICROPHYSICS"), (0, "POST_MICROPHYSICS"), (0, "POST_FINISH"),
)
CHECKPOINT_NAMES = {"QNC": "QNCLOUD", "QC": "QCLOUD", "QI": "QICE", "NI": "QNICE"}
RK_INPUTS = ("SCALAR_OLD", "SCALAR_TEND", "ADVECT_TEND")
RK3_NUMERATOR_INPUTS = ("SCALAR_OLD", "SCALAR_TEND", "MU_OLD", "MU_BASE",
                        "C1H", "C2H", "MSFTY", "DT_RK")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hex(trace: RepresentativeTrace, stage: tuple[int, str],
         target: tuple[int, int, int], field: str) -> str:
    i, j, k = target
    bits = trace.bits(stage[0], stage[1], i, j, k, field)
    if type(bits) is not int:
        raise TypeError(f"moment {field} is not f32")
    return f"{bits:08X}"


def _value(trace: RepresentativeTrace, stage: tuple[int, str],
           target: tuple[int, int, int], field: str) -> float:
    i, j, k = target
    return float(trace.f32(stage[0], stage[1], i, j, k, field))


def _checkpoint_words(data: dict, target: tuple[int, int, int], *, control: bool) -> dict:
    i, j, k = target
    for row in data["rows"]:
        if (row["i_one_based"], row["j_one_based"]) != (i, j):
            continue
        layers = row["final_failed_levels"] if control else row["failing_level_words"]
        for layer in layers:
            if layer["native_k_one_based"] == k:
                return layer["control_f32_hex" if control else "final_f32_hex"]
    raise ValueError(f"checkpoint witness missing {target}")


def _saved_operand_rk3_sign(trace: RepresentativeTrace, target: tuple[int, int, int]) -> dict:
    point = (3, "RKSCALAR_BEFORE")

    def f(field: str) -> Fraction:
        return Fraction(_value(trace, point, target, field))

    old_factor = f("C1H") * (f("MU_OLD") + f("MU_BASE")) + f("C2H")
    new_factor = f("C1H") * (f("MU_NEW") + f("MU_BASE")) + f("C2H")
    numerator = (old_factor * f("SCALAR_OLD") +
                 f("DT_RK") * (f("ADVECT_TEND") * f("MSFTY") + f("SCALAR_TEND")))
    observed = _value(trace, (3, "RKSCALAR_AFTER"), target, "QNC")
    if (new_factor <= 0 or (numerator > 0) != (observed > 0) or
            (numerator < 0) != (observed < 0)):
        raise ValueError(f"saved-operand RK3 sign disagrees with recorded output at {target}")
    return {"numerator_approx": float(numerator), "new_mass_factor_approx": float(new_factor),
            "quotient_approx": float(numerator / new_factor),
            "observed_qnc": observed, "saved_operand_sign_matches_output": True}


def analyze(
    control: RepresentativeTrace,
    alpha: RepresentativeTrace,
    control_witness: dict,
    candidate_residual: dict,
) -> dict:
    result = {"schema": "kdm6.qnc_representative_boundaries.v1",
              "trace_sha256": {"control": control.sha256, "alpha025": alpha.sha256},
              "stage_order": [{"rk_step": rk, "stage": stage} for rk, stage in TIMELINE],
              "targets": [],
              "limits": {"first_measured_boundary_is_process_attribution": False,
                         "raw_number_physical_units_certified": False,
                         "exact_real_saved_operand_rk3_reproduces_executed_f32_order": False,
                         "full_M0_candidate_admissible": False,
                         "RTTOV_or_optimizer_called_by_replay": False}}
    for target in TARGETS_IJK:
        i, j, k = target
        control_final = _checkpoint_words(control_witness, target, control=True)
        candidate_final = _checkpoint_words(candidate_residual, target, control=False)
        rows = []
        first_bit_difference = {field: None for field in MOMENTS}
        first_rk_input_difference = {field: None for field in RK_INPUTS}
        first_liquid_split = None
        first_ice_split = None
        first_positive_to_nonpositive_nc = None
        for rk, stage in TIMELINE:
            point = (rk, stage)
            words = {name: {field: _hex(trace, point, target, field) for field in MOMENTS}
                     for name, trace in (("control", control), ("alpha025", alpha))}
            values = {name: {field: _value(trace, point, target, field) for field in MOMENTS}
                      for name, trace in (("control", control), ("alpha025", alpha))}
            marker = {"rk_step": rk, "stage": stage}
            rk_inputs = None
            if stage == "RKSCALAR_BEFORE":
                rk_inputs = {
                    name: {field: {"f32_hex": _hex(trace, point, target, field),
                                   "value": _value(trace, point, target, field)}
                           for field in RK_INPUTS}
                    for name, trace in (("control", control), ("alpha025", alpha))
                }
                for field in RK_INPUTS:
                    if (first_rk_input_difference[field] is None and
                            rk_inputs["control"][field]["f32_hex"] !=
                            rk_inputs["alpha025"][field]["f32_hex"]):
                        first_rk_input_difference[field] = marker
            for field in MOMENTS:
                if first_bit_difference[field] is None and words["control"][field] != words["alpha025"][field]:
                    first_bit_difference[field] = marker
            c, a = values["control"], values["alpha025"]
            c_liquid_bad = c["QC"] > 0 and c["QNC"] <= 0
            a_liquid_bad = a["QC"] > 0 and a["QNC"] <= 0
            c_ice_bad = c["QI"] > 0 and c["NI"] <= 0
            a_ice_bad = a["QI"] > 0 and a["NI"] <= 0
            if first_liquid_split is None and not c_liquid_bad and a_liquid_bad:
                first_liquid_split = marker
            if first_ice_split is None and not c_ice_bad and a_ice_bad:
                first_ice_split = marker
            if (first_positive_to_nonpositive_nc is None and c["QNC"] > 0 and
                    a["QNC"] <= 0 and c["QC"] > 0 and a["QC"] > 0):
                first_positive_to_nonpositive_nc = marker
            rows.append({**marker, "f32_hex": words, "value": values,
                         "rk_inputs": rk_inputs,
                         "liquid_pair_invalid": {"control": c_liquid_bad, "alpha025": a_liquid_bad},
                         "ice_pair_invalid": {"control": c_ice_bad, "alpha025": a_ice_bad}})
        for name, expected, trace in (("control", control_final, control),
                                      ("alpha025", candidate_final, alpha)):
            for field, checkpoint_name in CHECKPOINT_NAMES.items():
                actual = _hex(trace, (0, "POST_FINISH"), target, field)
                if actual != expected[checkpoint_name]:
                    raise ValueError(f"{name} POST_FINISH/{checkpoint_name} differs from checkpoint at {target}")
        saved_operand_sign = None
        if target in TARGETS_IJK[:3]:
            common = all(_hex(control, (3, "RKSCALAR_BEFORE"), target, field) ==
                         _hex(alpha, (3, "RKSCALAR_BEFORE"), target, field)
                         for field in RK3_NUMERATOR_INPUTS)
            advect_differs = (_hex(control, (3, "RKSCALAR_BEFORE"), target, "ADVECT_TEND") !=
                              _hex(alpha, (3, "RKSCALAR_BEFORE"), target, "ADVECT_TEND"))
            if not common or not advect_differs:
                raise ValueError(f"RK3 numerator operand comparison differs at {target}")
            saved_operand_sign = {"common_numerator_inputs_equal_bits": True,
                                  "advect_tend_differs": True,
                                  "control": _saved_operand_rk3_sign(control, target),
                                  "alpha025": _saved_operand_rk3_sign(alpha, target)}
        result["targets"].append({"i_one_based": i, "j_one_based": j, "k_one_based": k,
                                  "first_recorded_bit_difference": first_bit_difference,
                                  "first_recorded_rk_input_difference": first_rk_input_difference,
                                  "first_recorded_liquid_validity_split": first_liquid_split,
                                  "first_recorded_ice_validity_split": first_ice_split,
                                  "first_recorded_positive_control_nonpositive_candidate_NC":
                                      first_positive_to_nonpositive_nc,
                                  "checkpoint_words_match_post_finish": True,
                                  "saved_operand_exact_real_rk3_sign_check": saved_operand_sign,
                                  "stages": rows})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-trace", type=Path, required=True)
    parser.add_argument("--alpha-trace", type=Path, required=True)
    parser.add_argument("--control-witness", type=Path, required=True)
    parser.add_argument("--candidate-residual", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(args.output)
    cw = json.loads(args.control_witness.read_text())
    cr = json.loads(args.candidate_residual.read_text())
    result = analyze(read_representative_trace(args.control_trace),
                     read_representative_trace(args.alpha_trace), cw, cr)
    result["checkpoint_witness_sha256"] = {"control": _sha(args.control_witness),
                                            "alpha025": _sha(args.candidate_residual)}
    data = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(data)
    print(json.dumps({"status": "REPRESENTATIVE_BOUNDARY_ANALYSIS_PASSED",
                      "analysis_sha256": hashlib.sha256(data).hexdigest(),
                      "targets": len(result["targets"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
