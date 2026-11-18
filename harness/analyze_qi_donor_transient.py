"""Analyze the transient QI donor and X-start copy from two native traces.

This source-compatible saved-word analysis locates the first measured donor
subnormal. It does not derive a full QI advection face budget or propose a
cleanup rule for the remaining fixed-support failure.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from harness.analyze_qnc_candidate_inputs import read_writer


PACKET = Path(__file__).resolve().parent / "evidence/native_qi_donor_transient_2026-10-30"
PARENT = Path(__file__).resolve().parent / "evidence/native_qnc_live_guard_2026-10-30"
RK_STAGES = ("QI_TEND_BEFORE", "QI_TEND_AFTER", "QI_RK_BEFORE",
             "QI_RK_AFTER", "QI_BDY_INPUT", "QI_BDY_AFTER")
MICRO_STAGES = ("PRE_MICROPHYSICS", "POST_MICROPHYSICS", "POST_FINISH")
BOUNDARY_FIELDS = ("RU_M", "SPEC_ZONE", "SPECIFIED", "HAVE_BCS_MOIST",
                   "PERIODIC_X", "IDS", "DONOR_I", "DONOR_J")
DONOR_RK_FIELDS = ("MOIST_OLD", "MOIST_TEND", "MU_OLD", "MU_NEW", "MU_BASE",
                   "C1H", "C2H", "DT_RK", "MSFTY", "ADVECT_TEND",
                   "H_TENDENCY", "Z_TENDENCY")
F32_FIELDS = {"QI", "NI", "RU_M", *DONOR_RK_FIELDS}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def f32(word: str) -> np.float32:
    return np.asarray([int(word, 16)], dtype=np.uint32).view(np.float32)[0]


def fraction(word: str) -> Fraction:
    return Fraction.from_float(float(f32(word)))


def read_trace(path: Path) -> dict[tuple[int, str, int, str], str]:
    lines = path.read_text(encoding="ascii").splitlines()
    if lines[:2] != ["# KDM6AD_QI_DONOR_TRANSIENT_V1",
                     "# VAL step rk stage i k j field raw_word_hex"]:
        raise ValueError("QI donor trace header differs")
    values = {}
    for line in lines[2:]:
        parts = line.split()
        if len(parts) != 9 or parts[0] != "VAL":
            raise ValueError("QI donor trace row differs")
        _, step, rk, stage, i, k, j, field, word = parts
        if (step != "3" or rk not in ("0", "1", "2", "3") or
                (i, k, j) not in (("1", "33", "168"), ("2", "33", "168")) or
                len(word) != 8 or any(x not in "0123456789ABCDEF" for x in word)):
            raise ValueError("QI donor trace coordinate/type differs")
        if field in F32_FIELDS and not math.isfinite(float(f32(word))):
            raise ValueError("QI donor trace has nonfinite f32")
        key = (int(rk), stage, int(i), field)
        if key in values:
            raise ValueError("duplicate QI donor trace word")
        values[key] = word
    expected = set()
    for rk in (1, 2, 3):
        for stage in RK_STAGES:
            for i in (1, 2):
                fields = {"QI", "NI", *BOUNDARY_FIELDS}
                if i == 2 and stage != "QI_TEND_BEFORE":
                    fields.update(DONOR_RK_FIELDS)
                expected.update((rk, stage, i, field) for field in fields)
    for stage in MICRO_STAGES:
        expected.update((0, stage, i, field) for i in (1, 2) for field in ("QI", "NI"))
    if set(values) != expected or len(values) != 552:
        raise ValueError("QI donor trace stage/field inventory differs")
    return values


def _rk3_exact_and_f32(values: dict) -> dict:
    def word(name: str) -> str:
        return values[(3, "QI_RK_BEFORE", 2, name)]

    old_mass = fraction(word("C1H")) * (fraction(word("MU_OLD")) +
                                         fraction(word("MU_BASE"))) + fraction(word("C2H"))
    new_mass = fraction(word("C1H")) * (fraction(word("MU_NEW")) +
                                         fraction(word("MU_BASE"))) + fraction(word("C2H"))
    if old_mass <= 0 or new_mass <= 0:
        raise ValueError("nonpositive donor RK mass factor")
    exact = (old_mass * fraction(word("MOIST_OLD")) +
             fraction(word("DT_RK")) *
             (fraction(word("MSFTY")) * fraction(word("ADVECT_TEND")) +
              fraction(word("MOIST_TEND")))) / new_mass
    subnormal_unit = Fraction(1, 2**149)
    rounded_word = f"{round(exact / subnormal_unit):08X}"
    with np.errstate(under="ignore"):
        advect = f32(word("ADVECT_TEND"))
        msfty = f32(word("MSFTY"))
        source = f32(word("MOIST_TEND"))
        dt = f32(word("DT_RK"))
        old = f32(word("MOIST_OLD"))
        c1 = f32(word("C1H"))
        c2 = f32(word("C2H"))
        mu_old = f32(word("MU_OLD"))
        mu_new = f32(word("MU_NEW"))
        mu_base = f32(word("MU_BASE"))
        tendency = np.float32(np.float32(advect * msfty) + source)
        old_factor = np.float32(np.float32(c1 * np.float32(mu_old + mu_base)) + c2)
        new_factor = np.float32(np.float32(c1 * np.float32(mu_new + mu_base)) + c2)
        result = np.float32(np.float32(np.float32(old_factor * old) +
                                       np.float32(dt * tendency)) / new_factor)
    separate_word = f"{int(result.view(np.uint32)):08X}"
    actual = values[(3, "QI_RK_AFTER", 2, "QI")]
    if rounded_word != actual or separate_word != actual:
        raise ValueError("donor RK3 output does not match saved-word calculation")
    return {"old_mass_exact": str(old_mass), "new_mass_exact": str(new_mass),
            "exact_QI_in_subnormal_ULP": str(exact / subnormal_unit),
            "exact_QI_in_subnormal_ULP_approximately": float(exact / subnormal_unit),
            "exact_round_to_nearest_even_word": rounded_word,
            "source_compatible_separate_word": separate_word,
            "recorded_QI_word": actual,
            "recorded_ADVECT_TEND_word": word("ADVECT_TEND")}


def analyze(packet: Path = PACKET) -> dict:
    execution = json.loads((packet / "execution_summary.json").read_text())
    parent_manifest = PARENT / "manifest.json"
    parent_analysis = PARENT / "analysis.json"
    parent_execution = json.loads((PARENT / "receipts/execution_summary.json").read_text())
    if (execution["parent_manifest_sha256"] != sha(parent_manifest) or
            execution["parent_analysis_sha256"] != sha(parent_analysis) or
            execution["host_steps_completed"] != 4 or
            execution["RTTOV_calls"] != 0 or execution["optimizer_calls"] != 0 or
            execution["changed_archive_members"] != ["solve_em.o"] or
            execution["base_executable_sha256"] != parent_execution["executable_sha256"] or
            execution["base_dso_sha256"] != parent_execution["dso_sha256"] or
            execution["dso_sha256"] != parent_execution["dso_sha256"]):
        raise ValueError("QI donor trace source/execution scope differs")
    traces = {}
    for case in ("control", "alpha025"):
        runs = execution["runs"][case]
        if (runs["off"]["checkpoint_sha256"] != runs["on"]["checkpoint_sha256"] or
                runs["off"]["applied_ack_sha256"] != runs["on"]["applied_ack_sha256"]):
            raise ValueError(f"QI donor trace off/on differs: {case}")
        for mode in ("off", "on"):
            if (runs[mode]["checkpoint_sha256"] !=
                    parent_execution["runs"][case][mode]["checkpoint_sha256"] or
                    runs[mode]["applied_ack_sha256"] !=
                    parent_execution["runs"][case][mode]["ack_sha256"]):
                raise ValueError(f"QI donor trace changed V7 endpoint/ACK: {case}/{mode}")
        path = packet / "data" / case / "qi_donor.tsv"
        if sha(path) != runs["on"]["trace_sha256"]["qi_donor"]:
            raise ValueError(f"QI donor trace/receipt hash differs: {case}")
        parent_writer_path = PARENT / "data" / case / "rk_writer.tsv"
        parent_faces_path = PARENT / "data" / case / "faces.tsv"
        if (runs["on"]["trace_sha256"]["rk_writer"] != sha(parent_writer_path) or
                runs["on"]["trace_sha256"]["qnc_candidate_faces"] != sha(parent_faces_path)):
            raise ValueError(f"inherited QNC traces changed: {case}")
        values = read_trace(path)
        parent_writer = read_writer(parent_writer_path)["values"]
        if (values[(0, "POST_FINISH", 1, "QI")] !=
                parent_writer[(0, "POST_FINISH", 1, 33, 168, "QI")][1]):
            raise ValueError(f"QI target finish disagrees with V7: {case}")
        if parent_writer[(0, "POST_FINISH", 1, 33, 168, "NI")][1] != "00000000":
            raise ValueError(f"QI target finish NI differs from V7: {case}")
        if (values[(3, "QI_BDY_INPUT", 2, "QI")] !=
                parent_writer[(3, "QI_BDY_INPUT", 1, 33, 168, "DONOR_QI")][1]):
            raise ValueError(f"QI donor boundary input disagrees with V7: {case}")
        for rk in (1, 2, 3):
            for i in (1, 2):
                if values[(rk, "QI_TEND_BEFORE", i, "QI")] != (
                        values[(rk, "QI_TEND_AFTER", i, "QI")]):
                    raise ValueError(f"QI tendency call changed live QI: {case}/{rk}/{i}")
                if values[(rk, "QI_RK_AFTER", i, "QI")] != (
                        values[(rk, "QI_BDY_INPUT", i, "QI")]):
                    raise ValueError(f"QI changed between RK and boundary: {case}/{rk}/{i}")
            target = 1
            fields = values
            for key, expected in (("SPECIFIED", "00000001"),
                                  ("HAVE_BCS_MOIST", "00000000"),
                                  ("PERIODIC_X", "00000000"),
                                  ("SPEC_ZONE", "00000001"),
                                  ("IDS", "00000001"),
                                  ("DONOR_I", "00000002"),
                                  ("DONOR_J", "000000A8")):
                if fields[(rk, "QI_BDY_INPUT", target, key)] != expected:
                    raise ValueError(f"QI X-start branch input differs: {case}/{rk}/{key}")
            if f32(fields[(rk, "QI_BDY_INPUT", target, "RU_M")]) >= 0:
                raise ValueError(f"QI X-start wind is nonnegative: {case}/{rk}")
            if fields[(rk, "QI_BDY_AFTER", target, "QI")] != (
                    fields[(rk, "QI_BDY_INPUT", 2, "QI")]):
                raise ValueError(f"QI target did not copy donor word: {case}/{rk}")
        traces[case] = values
    control, alpha = traces["control"], traces["alpha025"]
    for rk in (1, 2):
        for stage in RK_STAGES:
            if control[(rk, stage, 2, "QI")] != alpha[(rk, stage, 2, "QI")]:
                raise ValueError("donor QI diverged before RK3")
            if stage != "QI_TEND_BEFORE" and (
                    control[(rk, stage, 2, "ADVECT_TEND")] !=
                    alpha[(rk, stage, 2, "ADVECT_TEND")]):
                raise ValueError("donor advection tendency diverged before RK3")
    for stage in ("QI_TEND_BEFORE", "QI_TEND_AFTER", "QI_RK_BEFORE"):
        if (control[(3, stage, 2, "QI")] != "80000000" or
                alpha[(3, stage, 2, "QI")] != "80000000"):
            raise ValueError("donor QI diverged before RK3 update")
    for rk in (1, 2, 3):
        if (control[(rk, "QI_BDY_INPUT", 1, "RU_M")] !=
                alpha[(rk, "QI_BDY_INPUT", 1, "RU_M")]):
            raise ValueError("QI boundary wind word differs across cases")
    if (control[(3, "QI_TEND_AFTER", 2, "ADVECT_TEND")] != "00000000" or
            alpha[(3, "QI_TEND_AFTER", 2, "ADVECT_TEND")] != "000021A3" or
            control[(3, "QI_RK_AFTER", 2, "QI")] != "00000000" or
            alpha[(3, "QI_RK_AFTER", 2, "QI")] != "00000002"):
        raise ValueError("first QI donor divergence differs")
    for case, values, target_word in (("control", control, "00000000"),
                                      ("alpha025", alpha, "00000002")):
        if (values[(0, "PRE_MICROPHYSICS", 1, "QI")] != target_word or
                values[(0, "PRE_MICROPHYSICS", 2, "QI")] != target_word or
                values[(0, "POST_MICROPHYSICS", 1, "QI")] != target_word or
                values[(0, "POST_MICROPHYSICS", 2, "QI")] != "00000000" or
                values[(0, "POST_FINISH", 1, "QI")] != target_word or
                values[(0, "POST_FINISH", 2, "QI")] != "00000000"):
            raise ValueError(f"QI microphysics/finish path differs: {case}")
        if any(word != "00000000" for (rk, stage, i, field), word in values.items()
               if field == "NI"):
            raise ValueError(f"QI-stage NI snapshot differs: {case}")
    return {
        "schema": "kdm6.native_qi_donor_transient.v1",
        "records_per_case": 552,
        "host_steps_completed": 4,
        "trace_off_on_checkpoint_equal": True,
        "trace_off_on_applied_ACK_equal": True,
        "parent_V7_checkpoint_equal": True,
        "first_saved_advection_difference": {
            "stage": "RK3 QI_TEND_AFTER", "coord_ikj": [2, 33, 168],
            "control_ADVECT_TEND_word": "00000000",
            "alpha025_ADVECT_TEND_word": "000021A3",
        },
        "first_saved_donor_QI_difference": {
            "stage": "RK3 QI_RK_AFTER", "coord_ikj": [2, 33, 168],
            "control_QI_word": "00000000", "alpha025_QI_word": "00000002",
        },
        "rk3_saved_operand_calculation": {
            case: _rk3_exact_and_f32(traces[case]) for case in ("control", "alpha025")
        },
        "boundary_copy": {
            "target_ikj": [1, 33, 168], "donor_ikj": [2, 33, 168],
            "same_branch_inputs_in_both_runs": True,
            "rk3_target_RU_M_word": control[(3, "QI_BDY_INPUT", 1, "RU_M")],
            "control_donor_and_target_after_word": "00000000",
            "alpha025_donor_and_target_after_word": "00000002",
        },
        "post_microphysics": {
            "control_target_and_donor_QI_word": "00000000",
            "alpha025_target_QI_word": "00000002",
            "alpha025_donor_QI_word": "00000000",
            "QI_loop_NI_snapshot_nonzero_count": 0,
        },
        "limits": {
            "QI_advection_face_producer_identified": False,
            "emitted_f32_instruction_sequence_identified": False,
            "QI_loop_NI_synchronized_post_RK_pair": False,
            "blanket_subnormal_cleanup_justified": False,
            "whole_M0_supported": False,
            "whole_M0_RTTOV_cost_defined": False,
            "accepted_analysis": False,
        },
        "replay_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=PACKET)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(args.output)
    result = analyze(args.packet)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": "QI_DONOR_TRANSIENT_ANALYZED",
                      "first_difference": result["first_saved_donor_QI_difference"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
