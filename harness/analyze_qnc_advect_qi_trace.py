"""Join executed QNC flux and moist-writer witnesses to PR #468 RK inputs.

The arithmetic replays use recorded binary32 operands. They identify source
compatible operation sequences and exact-real budgets, not machine opcodes or
certified physical number units.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import numpy as np

from harness.g33_s15_probe import fma32
from harness.native_qnc_advect_qi_trace_records import (
    FACES,
    QC_IKJ,
    QC_STAGES,
    QI_IKJ,
    QI_STAGES,
    QNC_IKJ,
    STAR_IKJ,
    NativeValueTrace,
    read_qi_writer_trace,
    read_qnc_producer_trace,
)
from harness.native_qnc_representative_trace_records import (
    RepresentativeTrace,
    read_representative_trace,
)


AXES_RK2 = (("Y", "MRDY"), ("X", "MRDX"), ("Z", "RDZW"))
AXES_RK3 = ("Z", "X", "Y")
QI_EXTRA = ("MOIST_OLD", "MOIST_TEND", "ADVECT_TEND", "H_TENDENCY",
            "Z_TENDENCY", "MU_OLD", "MU_NEW", "MU_BASE", "C1H", "C2H",
            "MSFTY", "DT_RK", "SPECIFIED", "HAVE_BCS_MOIST")


def _f32_word(value: np.float32) -> str:
    return f"{int(np.asarray([value], dtype=np.float32).view(np.uint32)[0]):08X}"


def _snapshot(trace: NativeValueTrace, rk: int, stage: str,
              coord: tuple[int, int, int], fields: tuple[str, ...]) -> dict:
    i, k, j = coord
    return {field: {"raw_hex": trace.word(rk, stage, i, k, j, field),
                    "value": (bool(trace.bits(rk, stage, i, k, j, field))
                              if type(trace.bits(rk, stage, i, k, j, field)) is bool else
                              float(trace.f32(rk, stage, i, k, j, field)))}
            for field in fields}


def _rk2(trace: NativeValueTrace) -> dict:
    i, k, j = QNC_IKJ
    initial = trace.f32(2, "RK2_START", i, k, j, "TENDENCY")
    if _f32_word(initial) != "00000000":
        raise ValueError("RK2 ordinary advection did not start from zero tendency")
    separate = initial
    fused = initial
    rows = [{"stage": "RK2_START", "tendency": _snapshot(
        trace, 2, "RK2_START", QNC_IKJ, ("TENDENCY",))["TENDENCY"]}]
    for axis, metric in AXES_RK2:
        stage = f"RK2_AFTER_{axis}"
        fields = ("TENDENCY", f"F_{axis}_LOWER", f"F_{axis}_UPPER", metric)
        values = _snapshot(trace, 2, stage, QNC_IKJ, fields)
        lower = trace.f32(2, stage, i, k, j, f"F_{axis}_LOWER")
        upper = trace.f32(2, stage, i, k, j, f"F_{axis}_UPPER")
        factor = trace.f32(2, stage, i, k, j, metric)
        difference = np.float32(upper - lower)
        separate = np.float32(separate - np.float32(factor * difference))
        fused = np.float32(fma32(float(-factor), float(difference), float(fused)))
        rows.append({"stage": stage, "values": values,
                     "separate_f32_predicted": _f32_word(separate),
                     "fma_candidate_predicted": _f32_word(fused),
                     "separate_f32_matches": _f32_word(separate) == values["TENDENCY"]["raw_hex"],
                     "fma_candidate_matches": _f32_word(fused) == values["TENDENCY"]["raw_hex"]})
    if not all(row["fma_candidate_matches"] for row in rows[1:]):
        raise ValueError("RK2 source-compatible FMA candidate differs from captured tendency")
    return {"stages": rows, "fma_candidate_all_axes_match": True,
            "separate_f32_all_axes_match": all(row["separate_f32_matches"] for row in rows[1:])}


def _rk3(trace: NativeValueTrace) -> dict:
    i, k, j = QNC_IKJ
    pre = _snapshot(trace, 3, "RK3_PD_PRE_LIMIT", QNC_IKJ,
                    ("TENDENCY", "PH_LOW", "FLUX_OUT") + FACES)
    limit = [{"ikj_one_based": list(coord), "fields": _snapshot(
        trace, 3, "RK3_PD_LIMIT_CELL", coord,
        ("PH_LOW", "FLUX_OUT", "SCALE", "LIMIT_HIT"))} for coord in STAR_IKJ]
    post_fields = FACES + ("MSFTX", "MSFTY", "RDX", "RDY", "RDZW", "DT_STEP")
    post = _snapshot(trace, 3, "RK3_PD_POST_LIMIT_FACES", QNC_IKJ, post_fields)

    def f(field: str) -> Fraction:
        return Fraction(float(trace.f32(3, "RK3_PD_POST_LIMIT_FACES", i, k, j, field)))

    z = -f("RDZW") * ((f("FZ_TOP") - f("FZ_BOTTOM")) +
                       (f("FZ_LOW_TOP") - f("FZ_LOW_BOTTOM")))
    x = -f("MSFTX") * f("RDX") * ((f("FX_EAST") - f("FX_WEST")) +
                                  (f("FX_LOW_EAST") - f("FX_LOW_WEST")))
    y = -f("MSFTX") * f("RDY") * ((f("FY_NORTH") - f("FY_SOUTH")) +
                                  (f("FY_LOW_NORTH") - f("FY_LOW_SOUTH")))
    contributions = {"Z": z, "X": x, "Y": y}
    cumulative = Fraction(pre["TENDENCY"]["value"])
    rows = []
    for axis in AXES_RK3:
        cumulative += contributions[axis]
        observed = _snapshot(trace, 3, f"RK3_AFTER_{axis}", QNC_IKJ, ("TENDENCY",))[
            "TENDENCY"]
        rows.append({"stage": f"RK3_AFTER_{axis}",
                     "exact_real_face_contribution_approx": float(contributions[axis]),
                     "exact_real_cumulative_approx": float(cumulative),
                     "recorded_tendency": observed,
                     "recorded_minus_exact_real_approx": observed["value"] - float(cumulative)})
    if not limit[0]["fields"]["LIMIT_HIT"]["value"]:
        raise ValueError("target outgoing limiter branch was not taken")
    return {"pre_limit": pre, "limiter_cells": limit, "post_limit_faces": post,
            "directional_budget": rows,
            "target_limiter_hit": True,
            "target_limiter_scale": limit[0]["fields"]["SCALE"]}


def analyze(
    producer: dict[str, NativeValueTrace],
    writer: dict[str, NativeValueTrace],
    previous: dict[str, RepresentativeTrace],
) -> dict:
    cases = {}
    for case in ("control", "alpha025"):
        old = previous[case]
        new = writer[case]
        if any(new.values.get(key) != bits for key, bits in old.values.items()):
            raise ValueError(f"{case}: prior representative stage words changed")
        if len(old.values) != 568 or len(new.values) != 678:
            raise ValueError("representative writer trace inventory differs")
        p = producer[case]
        for rk, stage, prior_stage in ((2, "RK2_AFTER_Z", "RKSCALAR_BEFORE"),
                                       (3, "RK3_AFTER_Y", "RKSCALAR_BEFORE")):
            if p.bits(rk, stage, *QNC_IKJ, "TENDENCY") != old.bits(
                    rk, prior_stage, QNC_IKJ[0], QNC_IKJ[2], QNC_IKJ[1], "ADVECT_TEND"):
                raise ValueError(f"{case}: produced QNC tendency differs from RK input")
        qi = [{"stage": stage, "fields": _snapshot(new, 3, stage, QI_IKJ,
                                               ("QNC", "QC", "QI", "NI") + QI_EXTRA)}
              for stage in QI_STAGES]
        qc = [{"stage": stage, "fields": _snapshot(new, 1, stage, QC_IKJ,
                                               ("QNC", "QC", "QI", "NI"))}
              for stage in QC_STAGES]
        flags = qi[2]["fields"]
        if not flags["SPECIFIED"]["value"] or flags["HAVE_BCS_MOIST"]["value"]:
            raise ValueError("QI boundary-call configuration differs")
        cases[case] = {"producer_trace_sha256": p.sha256,
                       "writer_trace_sha256": new.sha256,
                       "previous_representative_trace_sha256": old.sha256,
                       "prior_stage_word_matches": len(old.values),
                       "qnc_rk_input_joins": {"rk2": True, "rk3": True},
                       "qnc_rk2": _rk2(p), "qnc_rk3": _rk3(p),
                       "qi_writer": qi, "qc_writer": qc}
    control_rk2 = cases["control"]["qnc_rk2"]["stages"]
    alpha_rk2 = cases["alpha025"]["qnc_rk2"]["stages"]
    first_applied = next((left["stage"] for left, right in zip(control_rk2, alpha_rk2)
                          if left.get("tendency", left.get("values", {}).get("TENDENCY")) !=
                             right.get("tendency", right.get("values", {}).get("TENDENCY"))), None)
    control_qi = {row["stage"]: row["fields"]["QI"]["raw_hex"] for row in cases["control"]["qi_writer"]}
    alpha_qi = {row["stage"]: row["fields"]["QI"]["raw_hex"] for row in cases["alpha025"]["qi_writer"]}
    control_qc = {row["stage"]: row["fields"]["QC"]["raw_hex"] for row in cases["control"]["qc_writer"]}
    alpha_qc = {row["stage"]: row["fields"]["QC"]["raw_hex"] for row in cases["alpha025"]["qc_writer"]}
    if (first_applied != "RK2_AFTER_X" or
            any(group["QI_RK_BEFORE"] != "80000000" or group["QI_RK_AFTER"] != "00000007"
                for group in (control_qi, alpha_qi)) or
            control_qi["QI_BDY_AFTER"] != "00000000" or
            alpha_qi["QI_BDY_AFTER"] != "00000002" or
            any(group["QC_RK_BEFORE"] != "00000000" or group["QC_RK_AFTER"] != "354ECF22"
                for group in (control_qc, alpha_qc))):
        raise ValueError("QNC/QI/QC source boundary conclusion differs")
    return {"schema": "kdm6.native_qnc_advect_qi_analysis.v1", "cases": cases,
            "conclusions": {"first_recorded_rk2_cumulative_tendency_split": first_applied,
                            "qi_after_rk3_update_both": "00000007",
                            "qi_after_flow_boundary": {"control": "00000000", "alpha025": "00000002"},
                            "qc_after_rk1_moist_update_both": "354ECF22"},
            "offline_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
            "limits": {"executed_fma_instructions_identified": False,
                       "raw_nc_physical_units_certified": False,
                       "boundary_copy_donor_value_directly_recorded": False,
                       "full_fixed_support_candidate_admissible": False}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for case in ("control", "alpha025"):
        parser.add_argument(f"--{case}-producer", type=Path, required=True)
        parser.add_argument(f"--{case}-writer", type=Path, required=True)
        parser.add_argument(f"--{case}-previous", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(args.output)
    producer = {case: read_qnc_producer_trace(getattr(args, f"{case}_producer"))
                for case in ("control", "alpha025")}
    writer = {case: read_qi_writer_trace(getattr(args, f"{case}_writer"))
              for case in ("control", "alpha025")}
    previous = {case: read_representative_trace(getattr(args, f"{case}_previous"))
                for case in ("control", "alpha025")}
    result = analyze(producer, writer, previous)
    raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(raw)
    print(json.dumps({"status": "ADVECT_QI_ANALYSIS_PASSED",
                      "analysis_sha256": hashlib.sha256(raw).hexdigest()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
