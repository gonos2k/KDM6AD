"""Offline, value-only analysis of V2 native QC/NC stage traces.

This module reports first observed states and exact representation crossings.
It does not infer a mechanistic cause, certify number units, calculate a
derivative, or calculate an observation cost.
"""
from __future__ import annotations

import struct
from typing import Any, Mapping

import numpy as np

from harness.native_moment_trace_records import (
    MomentTraceInventory,
    validate_moment_trace_v2,
)


TRACE_BOUNDARY_ORDER = (
    "MP_INPUT",
    "FP64_INPUT",
    "FP64_OUTPUT",
    "MP_OUTPUT",
    "HOST_WRITEBACK",
    "WRAPPER_POST",
    "ZERO_OUT_PRE",
    "MOMENTS_PRE",
    "MOMENTS_POST",
)
INTEREST_LEVELS = (19, 6, 4)
MOMENT_FIELDS = ("QC", "NC")


def _require_f32_array(name: str, values: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    array = np.asarray(values)
    if array.dtype != np.float32 or array.shape != shape:
        raise ValueError(f"{name} must be a raw float32 array with shape {shape}; got {array.dtype}/{array.shape}")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} contains nonfinite values")
    return array


def _f32_bits(value: np.float32) -> int:
    return int(np.asarray([value], dtype=np.float32).view(np.uint32)[0])


def _f64_bits(value: float) -> int:
    return int.from_bytes(struct.pack(">d", float(value)), "big")


def _hex(bits: int, dtype: str) -> str:
    return f"{bits:08X}" if dtype == "f32" else f"{bits:016X}"


def _snapshot(boundary: str, call_id: int | None, qc_dtype: str, qc_bits: int, nc_dtype: str, nc_bits: int) -> dict[str, Any]:
    qc_value = float(np.float32(np.asarray([qc_bits], dtype=np.uint32).view(np.float32)[0])) if qc_dtype == "f32" else struct.unpack(">d", qc_bits.to_bytes(8, "big"))[0]
    nc_value = float(np.float32(np.asarray([nc_bits], dtype=np.uint32).view(np.float32)[0])) if nc_dtype == "f32" else struct.unpack(">d", nc_bits.to_bytes(8, "big"))[0]
    return {
        "boundary": boundary,
        "call_id": call_id,
        "QC": {"dtype": qc_dtype, "bits_hex": _hex(qc_bits, qc_dtype), "value": qc_value},
        "NC": {"dtype": nc_dtype, "bits_hex": _hex(nc_bits, nc_dtype), "value": nc_value},
    }


def _pair_is_invalid(snapshot: dict[str, Any]) -> bool:
    return snapshot["QC"]["value"] > 0.0 and snapshot["NC"]["value"] <= 0.0


def _first_state(snapshots: list[dict[str, Any]], predicate) -> dict[str, Any] | None:
    for snapshot in snapshots:
        if predicate(snapshot):
            return snapshot
    return None


def analyze_native_moment_trace(
    inventory: MomentTraceInventory,
    *,
    targets: Mapping[str, tuple[int, int]],
    ready_qc: np.ndarray,
    ready_nc: np.ndarray,
    final_qc: np.ndarray,
    final_nc: np.ndarray,
    run_id: str,
    expected_call_count: int | None,
    expected_ncmin_land: float,
    expected_ncmin_sea: float,
    levels: int = 39,
    expected_step: int = 3,
    dt_seconds: float = 20.0,
    global_shape: tuple[int, int, int] = (234, 39, 282),
    levels_of_interest: tuple[int, ...] = INTEREST_LEVELS,
    max_mismatch_examples: int = 50,
) -> dict[str, Any]:
    """Analyze one run's READY→trace→FINAL QC/NC trajectories.

    QC/NC arrays must be f32 `[target, level]`, ordered by ``targets`` insertion
    order. Trace values remain in their recorded f32/f64 type; all comparisons
    are exact bit comparisons at representation boundaries. Analysis requires
    complete trace coverage; use the reader validator directly for partial
    diagnostic inventories.
    """
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a nonempty string")
    if not isinstance(targets, Mapping) or not targets:
        raise ValueError("targets must be a nonempty mapping of target name to global (i,j)")
    target_names = tuple(targets)
    target_coords = tuple(targets[name] for name in target_names)
    if len(set(target_coords)) != len(target_coords):
        raise ValueError("target global coordinates must be unique")
    shape = (len(target_names), levels)
    ready_qc = _require_f32_array("ready_qc", ready_qc, shape)
    ready_nc = _require_f32_array("ready_nc", ready_nc, shape)
    final_qc = _require_f32_array("final_qc", final_qc, shape)
    final_nc = _require_f32_array("final_nc", final_nc, shape)
    if any(type(level) is not int or level < 1 or level > levels for level in levels_of_interest):
        raise ValueError(f"levels_of_interest must be one-based levels within 1..{levels}")
    coverage = validate_moment_trace_v2(
        inventory,
        targets=targets,
        levels=levels,
        expected_call_count=expected_call_count,
        expected_step=expected_step,
        expected_dt=dt_seconds,
        expected_ncmin_land=expected_ncmin_land,
        expected_ncmin_sea=expected_ncmin_sea,
        expected_global_shape=global_shape,
        require_complete=True,
    )

    target_analyses: dict[str, dict[str, Any]] = {}
    conversion_widen_mismatches: list[dict[str, Any]] = []
    conversion_cast_mismatches: list[dict[str, Any]] = []
    widen_mismatch_count = 0
    cast_mismatch_count = 0
    call_ids = tuple(inventory.headers)

    for target_index, target_name in enumerate(target_names):
        i, j = target_coords[target_index]
        level_analyses: dict[str, Any] = {}
        for k in range(1, levels + 1):
            snapshots = [
                _snapshot(
                    "READY", None, "f32", _f32_bits(ready_qc[target_index, k - 1]),
                    "f32", _f32_bits(ready_nc[target_index, k - 1]),
                )
            ]
            for call_id in call_ids:
                if not inventory.headers[call_id].owns(i, j):
                    continue
                for stage in TRACE_BOUNDARY_ORDER:
                    qc = inventory.values[(call_id, stage, i, k, j, "QC")]
                    nc = inventory.values[(call_id, stage, i, k, j, "NC")]
                    snapshots.append(_snapshot(stage, call_id, qc.dtype, qc.bits, nc.dtype, nc.bits))
            snapshots.append(
                _snapshot(
                    "FINAL", None, "f32", _f32_bits(final_qc[target_index, k - 1]),
                    "f32", _f32_bits(final_nc[target_index, k - 1]),
                )
            )

            first_mp_input = next(state for state in snapshots if state["boundary"] == "MP_INPUT")
            last_moments_post = next(state for state in reversed(snapshots) if state["boundary"] == "MOMENTS_POST")
            final_state = snapshots[-1]
            ready_mp_bitwise = {
                field: snapshots[0][field]["bits_hex"] == first_mp_input[field]["bits_hex"]
                for field in MOMENT_FIELDS
            }
            moments_final_bitwise = {
                field: last_moments_post[field]["bits_hex"] == final_state[field]["bits_hex"]
                for field in MOMENT_FIELDS
            }

            first_invalid = _first_state(snapshots, _pair_is_invalid)
            ready_invalid = _pair_is_invalid(snapshots[0])
            if ready_invalid:
                invalid_class = "already_invalid_at_READY"
            elif first_invalid is None:
                invalid_class = "no_invalid_pair_observed"
            else:
                invalid_class = "first_invalid_pair_observed_after_READY"
            first_nc_positive = _first_state(snapshots, lambda state: state["NC"]["value"] > 0.0)
            ready_nc_nonpositive = snapshots[0]["NC"]["value"] <= 0.0
            if first_nc_positive is None:
                nc_positive_class = "never_observed_positive"
            elif first_nc_positive["boundary"] == "READY":
                nc_positive_class = "already_positive_at_READY"
            else:
                nc_positive_class = "first_observed_positive_after_READY"
            level_analyses[str(k)] = {
                "ready_pair_invalid": ready_invalid,
                "invalid_pair_classification": invalid_class,
                "first_invalid_pair_boundary": first_invalid,
                "ready_nc_nonpositive": ready_nc_nonpositive,
                "nc_positive_classification": nc_positive_class,
                "first_nc_positive_boundary": first_nc_positive,
                "ready_to_first_MP_INPUT_bitwise_match": ready_mp_bitwise,
                "MOMENTS_POST_to_final_NetCDF_bitwise_match": moments_final_bitwise,
                "trajectory": snapshots,
            }

        target_analyses[target_name] = {
            "global_i": int(i),
            "global_j": int(j),
            "levels": level_analyses,
        }

    # Compare the exact f32↔f64 boundary pairings across all target levels and calls.
    for call_id in call_ids:
        for target_name, (i, j) in targets.items():
            if not inventory.headers[call_id].owns(i, j):
                continue
            for k in range(1, levels + 1):
                for field in MOMENT_FIELDS:
                    source_f32 = inventory.values[(call_id, "MP_INPUT", i, k, j, field)]
                    kernel_f64 = inventory.values[(call_id, "FP64_INPUT", i, k, j, field)]
                    expected_widen_bits = _f64_bits(float(np.float32(source_f32.value)))
                    if kernel_f64.bits != expected_widen_bits:
                        widen_mismatch_count += 1
                        if len(conversion_widen_mismatches) < max_mismatch_examples:
                            conversion_widen_mismatches.append({
                                "call_id": call_id,"target": target_name,"global_i":i,"global_j":j,"k":k,"field":field,
                                "source_f32_hex":_hex(source_f32.bits,"f32"),"kernel_f64_hex":_hex(kernel_f64.bits,"f64"),
                                "expected_widened_f64_hex":_hex(expected_widen_bits,"f64"),
                            })
                    kernel_out = inventory.values[(call_id, "FP64_OUTPUT", i, k, j, field)]
                    host_out = inventory.values[(call_id, "MP_OUTPUT", i, k, j, field)]
                    expected_cast = np.float32(kernel_out.value)
                    expected_cast_bits = _f32_bits(expected_cast)
                    if host_out.bits != expected_cast_bits:
                        cast_mismatch_count += 1
                        if len(conversion_cast_mismatches) < max_mismatch_examples:
                            conversion_cast_mismatches.append({
                                "call_id":call_id,"target":target_name,"global_i":i,"global_j":j,"k":k,"field":field,
                                "kernel_f64_hex":_hex(kernel_out.bits,"f64"),"host_f32_hex":_hex(host_out.bits,"f32"),
                                "expected_cast_f32_hex":_hex(expected_cast_bits,"f32"),
                            })

    interest = {}
    for target_name, target in target_analyses.items():
        selected = {}
        for k in levels_of_interest:
            level = target["levels"][str(k)]
            selected[str(k)] = {
                "ready_pair_invalid": level["ready_pair_invalid"],
                "first_invalid_pair_boundary": level["first_invalid_pair_boundary"],
                "first_nc_positive_boundary": level["first_nc_positive_boundary"],
            }
        interest[target_name] = selected

    return {
        "schema": "kdm6.native_moment_trace_analysis.v1",
        "run_id": run_id,
        "status": "ANALYZED_COMPLETE_TRACE" if coverage.complete else "ANALYZED_PARTIAL_TRACE_DIAGNOSTIC_ONLY",
        "targets": target_analyses,
        "levels_of_interest": {name: list(levels_of_interest) for name in target_names},
        "selected_level_summary": interest,
        "trace_completeness": {
            "call_count": coverage.call_count,
            "recorded_value_count": coverage.values_count,
            "complete": coverage.complete,
            "calls_without_kernel_witness": list(coverage.calls_without_kernel_witness),
            "calls_with_owned_targets_without_kernel_witness": list(coverage.calls_with_owned_targets_without_kernel_witness),
            "unowned_targets": list(coverage.unowned_targets),
            "stage_coverage_records": len(coverage.coverage),
        },
        "representation_checks": {
            "input_f32_to_f64_exact_widen_mismatch_count": widen_mismatch_count,
            "input_f32_to_f64_exact_widen_mismatch_examples": conversion_widen_mismatches,
            "output_f64_to_f32_exact_cast_mismatch_count": cast_mismatch_count,
            "output_f64_to_f32_exact_cast_mismatch_examples": conversion_cast_mismatches,
            "comparisons": "raw IEEE bits; no numerical tolerance",
        },
        "interpretation_limits": {
            "mechanistic_root_cause_inferred": False,
            "raw_number_unit_certification": False,
            "QC_RATE_used_as_QC": False,
            "derivative_or_cost_claim": False,
            "description": "First observed QC>0/NC<=0 boundary and first observed positive NC are classifications of saved stages only; they do not establish process causality or physical number units.",
        },
    }


def compare_native_moment_runs(
    control: dict[str, Any],
    candidate: dict[str, Any],
    *,
    levels_of_interest: tuple[int, ...] = INTEREST_LEVELS,
) -> dict[str, Any]:
    """Compare control/candidate raw QC/NC histories at selected native levels."""
    if control.get("schema") != "kdm6.native_moment_trace_analysis.v1" or candidate.get("schema") != "kdm6.native_moment_trace_analysis.v1":
        raise ValueError("inputs must be outputs from analyze_native_moment_trace")
    if tuple(control["targets"]) != tuple(candidate["targets"]):
        raise ValueError("control and candidate target names/order differ")
    for target_name in control["targets"]:
        control_coords = (control["targets"][target_name]["global_i"], control["targets"][target_name]["global_j"])
        candidate_coords = (candidate["targets"][target_name]["global_i"], candidate["targets"][target_name]["global_j"])
        if control_coords != candidate_coords:
            raise ValueError(f"control/candidate global coordinates differ for target {target_name!r}")
    comparisons = {}
    for target_name in control["targets"]:
        levels = {}
        for k in levels_of_interest:
            control_level = control["targets"][target_name]["levels"].get(str(k))
            candidate_level = candidate["targets"][target_name]["levels"].get(str(k))
            if control_level is None or candidate_level is None:
                raise ValueError(f"level {k} missing from control/candidate analysis")
            control_path = control_level["trajectory"]
            candidate_path = candidate_level["trajectory"]
            control_keys = [(row["boundary"], row["call_id"]) for row in control_path]
            candidate_keys = [(row["boundary"], row["call_id"]) for row in candidate_path]
            first_difference = None
            schedule_diff = None
            if control_keys != candidate_keys:
                max_len = max(len(control_keys), len(candidate_keys))
                for pos in range(max_len):
                    left = control_keys[pos] if pos < len(control_keys) else None
                    right = candidate_keys[pos] if pos < len(candidate_keys) else None
                    if left != right:
                        schedule_diff = {"position":pos,"control":left,"candidate":right}
                        break
            else:
                for left, right in zip(control_path, candidate_path):
                    for field in MOMENT_FIELDS:
                        if left[field]["dtype"] != right[field]["dtype"] or left[field]["bits_hex"] != right[field]["bits_hex"]:
                            first_difference = {
                                "boundary":left["boundary"],"call_id":left["call_id"],"field":field,
                                "control_dtype":left[field]["dtype"],"control_bits_hex":left[field]["bits_hex"],
                                "candidate_dtype":right[field]["dtype"],"candidate_bits_hex":right[field]["bits_hex"],
                            }
                            break
                    if first_difference is not None:
                        break
            c_ready = control_level["ready_pair_invalid"]
            a_ready = candidate_level["ready_pair_invalid"]
            c_first = control_level["first_invalid_pair_boundary"]
            a_first = candidate_level["first_invalid_pair_boundary"]
            control_final_invalid = _pair_is_invalid(control_level["trajectory"][-1])
            candidate_final_invalid = _pair_is_invalid(candidate_level["trajectory"][-1])
            if a_ready and candidate_final_invalid and c_ready and not control_final_invalid:
                state_contrast = "control_resolved_candidate_initially_invalid_retained"
            elif a_ready and candidate_final_invalid:
                state_contrast = "candidate_initially_invalid_and_retained_without_control_resolution_proof"
            elif a_ready:
                state_contrast = "candidate_initially_invalid_but_not_retained_at_FINAL"
            elif a_first is not None:
                state_contrast = "candidate_first_invalid_pair_observed_after_READY"
            elif c_first is not None:
                state_contrast = "control_invalid_pair_candidate_not_invalid_by_FINAL"
            else:
                state_contrast = "no_invalid_pair_observed_in_either_run"
            levels[str(k)] = {
                "first_differing_boundary": first_difference,
                "schedule_mismatch": schedule_diff,
                "control_ready_pair_invalid": c_ready,
                "candidate_ready_pair_invalid": a_ready,
                "control_first_invalid_pair_boundary": c_first,
                "candidate_first_invalid_pair_boundary": a_first,
                "control_first_nc_positive_boundary": control_level["first_nc_positive_boundary"],
                "candidate_first_nc_positive_boundary": candidate_level["first_nc_positive_boundary"],
                "contrast": state_contrast,
                "mechanistic_cause_inferred": False,
            }
        comparisons[target_name] = levels
    return {
        "schema": "kdm6.native_moment_trace_run_comparison.v1",
        "control_run_id": control["run_id"],
        "candidate_run_id": candidate["run_id"],
        "levels_of_interest": list(levels_of_interest),
        "targets": comparisons,
        "interpretation": "Raw QC/NC state-boundary comparison only. Initially invalid READY pairs are distinguished from the first later observed boundary; no physical creation mechanism, number units, derivative, or cost is inferred.",
    }
