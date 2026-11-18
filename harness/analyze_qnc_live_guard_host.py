"""Replay the selected-54 live QNC guard from public face and RK records.

The packet contains host-produced trace words and checkpoint receipts. This
analysis redoes the saved-word numerical checks; it cannot rerun the private
host or reconstruct every unexported checkpoint field from the trace.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
from itertools import product
import json
import math
from pathlib import Path

from harness.analyze_qnc_candidate_inputs import FACE_PAIRS, read_faces, read_writer
from harness.analyze_qnc_selected_adaptive_pilot import (
    V2_INPUT_PINS, _apply_scale_map, _axis_tendency, _exact_budget, _f32,
    _mul, _post_field, _pre_field, _rk_update, _word, _writer_word,
)
from harness.native_qnc_candidate_face_overlay import receiver_union
from harness.native_qnc_domain_preflight_advect_overlay import failure_layer_coordinates


PACKET = Path(__file__).resolve().parent / "evidence/native_qnc_live_guard_2026-10-30"
PARENT = Path(__file__).resolve().parent / "evidence/native_qnc_candidate_inputs_2026-10-28"
FAILURES = Path(__file__).resolve().parent / "evidence/native_qnc_host_backoff_review_2026-10-28/residual_reason_rows.json"
FIELDS26 = (
    "FIELD_OLD", "C1H", "C2H", "MU_OLD", "MU_BASE", "DT", "MSFTX", "MSFTY",
    "RDX", "RDY", "RDZW", "PH_LOW", "FLUX_OUT", "SCALE", "FX_LOW_WEST",
    "FX_LOW_EAST", "FY_LOW_SOUTH", "FY_LOW_NORTH", "FZ_LOW_BOTTOM", "FZ_LOW_TOP",
    "FX_POST_WEST", "FX_POST_EAST", "FY_POST_SOUTH", "FY_POST_NORTH",
    "FZ_POST_BOTTOM", "FZ_POST_TOP",
)
POST = FIELDS26[20:]
AXIS_MODES = tuple(product((False, True), repeat=3))
RK_MODES = tuple((*sites, numerator) for sites in product((False, True), repeat=3)
                 for numerator in range(3))
BEFORE_FIELDS = ("QNC", "SCALAR_OLD", "C1H", "C2H", "MU_OLD", "MU_BASE",
                 "MU_NEW", "DT_RK", "MSFTY", "SCALAR_TEND")
ZERO_RECEIVERS = ((152, 12, 268), (214, 14, 181),
                  (214, 15, 182), (225, 20, 205))


def _operand_map(writer: dict, coord: tuple[int, int, int]) -> dict:
    return {name: _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", name))
            for name in ("MU_OLD", "MU_BASE", "MU_NEW", "C1H", "C2H",
                         "MSFTY", "SCALAR_TEND", "DT_RK", "SCALAR_OLD")}


def _predictions(row: dict, writer: dict, coord: tuple[int, int, int],
                 operands: dict) -> tuple[set[str], set[str]]:
    axes = {_word(_axis_tendency(row, mode)) for mode in AXIS_MODES}
    qnc = {_word(_rk_update(writer, coord, _axis_tendency(row, axis), rk, operands))
           for axis in AXIS_MODES for rk in RK_MODES}
    if len(qnc) == 0 or any(not math.isfinite(float(_f32(word))) for word in qnc):
        raise ValueError(f"nonfinite QNC prediction at {coord}")
    return axes, qnc


def _passes(row: dict, writer: dict, coord: tuple[int, int, int],
            operands: dict) -> tuple[bool, bool, set[str], set[str]]:
    budget = _exact_budget(row, writer, coord)
    axes, qnc = _predictions(row, writer, coord, operands)
    exact_positive = budget["residual"] > Fraction(0)
    f32_positive = all(_f32(word) > 0 for word in qnc)
    return exact_positive, f32_positive, axes, qnc


def _trial_row(original: dict, scale_word: str) -> dict:
    row = dict(original)
    row["SCALE"] = scale_word
    scale = _f32(scale_word)
    for _, face, _, outward_sign in FACE_PAIRS:
        pre = _f32(original[_pre_field(face)])
        if pre != 0 and (pre > 0) == (outward_sign > 0):
            row[_post_field(face)] = _word(_mul(pre, scale))
    return row


def _stage_word(writer: dict, coord: tuple[int, int, int], stage: str,
                field: str) -> str:
    rk = 3 if stage.startswith("RKSCALAR") else 0
    dtype, word = writer["values"][(rk, stage, *coord, field)]
    if dtype != "f32":
        raise ValueError(f"unexpected writer type at {coord}/{stage}/{field}")
    return word


def _check_parent_input_hashes() -> None:
    from harness.analyze_qnc_selected_adaptive_pilot import _sha

    for case in ("control", "alpha025"):
        for part, filename in (("faces", "faces.tsv"), ("writer", "rk_writer.tsv")):
            path = PARENT / "data" / case / filename
            if _sha(path.read_bytes()) != V2_INPUT_PINS[f"{case}_{part}"]:
                raise ValueError(f"PR475 parent input changed: {case}/{filename}")


def analyze(packet: Path = PACKET) -> dict:
    _check_parent_input_hashes()
    failure_json = FAILURES.read_bytes()
    coords = receiver_union(failure_json)
    donors = failure_layer_coordinates(failure_json)
    donor_set = set(donors)
    if len(coords) != 382 or len(donors) != 54:
        raise ValueError("selected donor/capture inventory differs")
    execution = json.loads((packet / "receipts/execution_summary.json").read_text())
    if (execution["host_steps_completed"] != 4 or execution["RTTOV_calls"] != 0 or
            execution["optimizer_calls"] != 0 or execution["private_full_checkpoint_public"] is not False):
        raise ValueError("live execution receipt scope differs")
    cases = {}
    for case in ("control", "alpha025"):
        original_faces = read_faces(PARENT / "data" / case / "faces.tsv", coords)
        original_writer = read_writer(PARENT / "data" / case / "rk_writer.tsv")
        live_faces = read_faces(packet / "data" / case / "faces.tsv", coords)
        live_writer = read_writer(packet / "data" / case / "rk_writer.tsv")
        if original_faces["calls"] != live_faces["calls"]:
            raise ValueError(f"tile/call inventory changed: {case}")
        if execution["runs"][case]["off"]["checkpoint_sha256"] != (
                execution["runs"][case]["on"]["checkpoint_sha256"]):
            raise ValueError(f"trace off/on checkpoint differs: {case}")
        if execution["runs"][case]["off"]["ack_sha256"] != (
                execution["runs"][case]["on"]["ack_sha256"]):
            raise ValueError(f"trace off/on applied ACK differs: {case}")
        from harness.analyze_qnc_selected_adaptive_pilot import _sha

        for part, filename in (("qnc_candidate_faces", "faces.tsv"),
                               ("rk_writer", "rk_writer.tsv")):
            if _sha((packet / "data" / case / filename).read_bytes()) != (
                    execution["runs"][case]["on"]["trace_files_sha256"][part]):
                raise ValueError(f"run receipt/trace file differs: {case}/{part}")

        choices = {}
        histogram: Counter[int] = Counter()
        for coord in coords:
            original = original_faces["values"][coord]
            live = live_faces["values"][coord]
            for field in FIELDS26[:20]:
                if field != "SCALE" and original[field] != live[field]:
                    raise ValueError(f"fixed face/RK operand changed: {case}/{coord}/{field}")
            if coord not in donor_set and original["SCALE"] != live["SCALE"]:
                raise ValueError(f"receiver scale changed: {case}/{coord}")
            for field in BEFORE_FIELDS:
                if _stage_word(original_writer, coord, "RKSCALAR_BEFORE", field) != (
                        _stage_word(live_writer, coord, "RKSCALAR_BEFORE", field)):
                    raise ValueError(f"non-advection RK input changed: {case}/{coord}/{field}")
        for coord in donors:
            original = original_faces["values"][coord]
            live = live_faces["values"][coord]
            base_bits = int(original["SCALE"], 16)
            selected_bits = int(live["SCALE"], 16)
            step = base_bits - selected_bits
            if (original["limit_hit"] != 1 or live["limit_hit"] != 1 or
                    not 0 <= step <= 16 or not 0 < _f32(live["SCALE"]) < 1):
                raise ValueError(f"selected scale outside bounded active search: {case}/{coord}")
            operands = _operand_map(live_writer, coord)
            for earlier in range(step + 1):
                trial = _trial_row(original, f"{base_bits-earlier:08X}")
                exact, f32, _, _ = _passes(trial, live_writer, coord, operands)
                if (exact and f32) != (earlier == step):
                    raise ValueError(f"not the first all-mode passing scale: {case}/{coord}/{earlier}")
            choices[coord] = {"scale_hex": live["SCALE"]}
            histogram[step] += 1
        expected_rows, changed_faces = _apply_scale_map(original_faces, choices)
        for coord in coords:
            live = live_faces["values"][coord]
            for field in POST:
                if live[field] != expected_rows[coord][field]:
                    raise ValueError(f"applied shared face differs: {case}/{coord}/{field}")

        baseline_failures = candidate_failures = 0
        writer_bit_matches = tendency_matches = final_liquid_valid = 0
        for coord in coords:
            before = original_faces["values"][coord]
            after = live_faces["values"][coord]
            operands = _operand_map(live_writer, coord)
            old_exact, old_f32, _, _ = _passes(before, original_writer, coord, operands)
            new_exact, new_f32, axes, qnc = _passes(after, live_writer, coord, operands)
            baseline_failed = not (old_exact and old_f32)
            candidate_failed = not (new_exact and new_f32)
            baseline_failures += baseline_failed
            candidate_failures += candidate_failed
            if coord in donor_set and candidate_failed:
                raise ValueError(f"selected donor fails after simultaneous application: {case}/{coord}")
            if coord not in donor_set and candidate_failed and (
                    not baseline_failed or any(before[name] != after[name] for name in FIELDS26)):
                raise ValueError(f"new or worsened receiver failure: {case}/{coord}")
            actual_tendency = _stage_word(live_writer, coord, "RKSCALAR_BEFORE", "ADVECT_TEND")
            actual_qnc = _stage_word(live_writer, coord, "RKSCALAR_AFTER", "QNC")
            if actual_tendency not in axes or actual_qnc not in qnc:
                raise ValueError(f"recorded tendency/RK output outside model envelope: {case}/{coord}")
            tendency_matches += 1
            writer_bit_matches += 1
            if coord in donor_set:
                if _f32(actual_qnc) <= 0 or actual_qnc != (
                        _stage_word(live_writer, coord, "PRE_MICROPHYSICS", "QNC")):
                    raise ValueError(f"donor RK state not positive through KDM entry: {case}/{coord}")
                qc = _f32(_stage_word(live_writer, coord, "POST_FINISH", "QC"))
                nc = _f32(_stage_word(live_writer, coord, "POST_FINISH", "QNC"))
                if qc <= 0 or nc > 0:
                    final_liquid_valid += 1
                else:
                    raise ValueError(f"selected donor remains liquid-invalid: {case}/{coord}")

        support = json.loads((packet / "receipts" / f"{case}_support_analysis.json").read_text())
        between = json.loads((packet / "receipts" / f"{case}_between_variant.json").read_text())
        if (support["checkpoint_sha256"] != execution["runs"][case]["off"]["checkpoint_sha256"] or
                support["M0_profiles"] != 53906 or support["M0_channel_cells"] != 377342 or
                between["candidate_sha256"] != support["checkpoint_sha256"] or
                between["variable_count"] != 652 or between["numeric_elements_compared"] != 322426586):
            raise ValueError(f"checkpoint support/diff receipt differs: {case}")
        for coord in ZERO_RECEIVERS:
            if (_f32(_stage_word(live_writer, coord, "PRE_MICROPHYSICS", "QC")) <= 0 or
                    _stage_word(live_writer, coord, "PRE_MICROPHYSICS", "QNC") != "00000000" or
                    _stage_word(live_writer, coord, "POST_FINISH", "QC") != "00000000" or
                    _stage_word(live_writer, coord, "POST_FINISH", "QNC") != "00000000"):
                raise ValueError(f"preexisting zero receiver finish path differs: {case}/{coord}")
        cases[case] = {
            "selected_donors": len(donors),
            "captured_cells": len(coords),
            "selected_ulp_histogram": {str(k): v for k, v in sorted(histogram.items())},
            "changed_unique_shared_faces": changed_faces,
            "baseline_joint_failures_in_capture": baseline_failures,
            "candidate_joint_failures_in_capture": candidate_failures,
            "face_to_tendency_matches": tendency_matches,
            "source_compatible_rk_output_matches": writer_bit_matches,
            "selected_donors_valid_at_finish": final_liquid_valid,
            "preexisting_zero_receivers_valid_at_finish": len(ZERO_RECEIVERS),
            "qi_target_finish_word": _stage_word(live_writer, (1, 33, 168), "POST_FINISH", "QI"),
            "checkpoint_sha256": support["checkpoint_sha256"],
            "M0_lost_profiles": support["lost_profiles"],
            "M0_lost_channel_cells": support["lost_channel_cells"],
            "M0_reason_profile_counts": support["reason_profile_counts"],
            "between_variant_changed_variables": between["changed_variables"],
            "between_variant_numeric_element_mismatches": between["numeric_element_mismatches"],
        }
    if (cases["control"]["M0_lost_profiles"] != 0 or
            cases["alpha025"]["M0_lost_profiles"] != 1 or
            cases["alpha025"]["M0_lost_channel_cells"] != 7 or
            cases["alpha025"]["M0_reason_profile_counts"]["ice_QI_positive_NI_nonpositive"] != 1 or
            cases["alpha025"]["M0_reason_profile_counts"]["liquid_QC_positive_NC_nonpositive"] != 0):
        raise ValueError("published M0 outcome differs")
    return {
        "schema": "kdm6.native_qnc_live_guard_host.v1",
        "cases": cases,
        "execution": {
            "host_steps_completed": 4,
            "checkpoint_trace_off_on_equal": True,
            "applied_ack_trace_off_on_equal": True,
            "KDM_wrapper_entries_expected": execution["KDM_wrapper_entries_expected"],
            "RTTOV_calls": 0,
            "optimizer_calls": 0,
        },
        "limits": {
            "fixed_selected_54_donors": True,
            "full_original_M0_supported_for_alpha": False,
            "whole_M0_RTTOV_cost_defined": False,
            "accepted_analysis": False,
            "second_assimilation_run": False,
            "raw_NC_physical_units_certified": False,
            "emitted_FMA_instruction_sequence_identified": False,
        },
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
    print(json.dumps({"status": "QNC_LIVE_GUARD_ANALYZED",
                      "alpha_M0_lost_profiles": result["cases"]["alpha025"]["M0_lost_profiles"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
