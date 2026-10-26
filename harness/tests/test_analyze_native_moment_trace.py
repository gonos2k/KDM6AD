from __future__ import annotations

import struct

import numpy as np
import pytest

from harness.analyze_native_moment_trace import (
    analyze_native_moment_trace,
    compare_native_moment_runs,
)
from harness.native_moment_trace_records import (
    MomentCallHeader,
    MomentTraceInventory,
    MomentTraceValue,
)


TARGETS = {"T1": (3, 4), "T2": (6, 2), "T3": (5, 3)}
LEVELS = 39
DT_BITS = int.from_bytes(struct.pack(">d", 20.0), "big")
LAND_BITS = int.from_bytes(struct.pack(">d", 64.0), "big")
SEA_BITS = int.from_bytes(struct.pack(">d", 16.0), "big")
STAGES = (
    "MP_INPUT", "FP64_INPUT", "FP64_OUTPUT", "MP_OUTPUT", "HOST_WRITEBACK",
    "WRAPPER_POST", "ZERO_OUT_PRE", "MOMENTS_PRE", "MOMENTS_POST",
)


def _f32(value):
    return np.float32(value)


def _f32_bits(value):
    return int(np.asarray([np.float32(value)], dtype=np.float32).view(np.uint32)[0])


def _f64_bits(value):
    return int.from_bytes(struct.pack(">d", float(value)), "big")


def _header(call_id=1):
    return MomentCallHeader(
        call_id=call_id,
        step=3,
        its=1,
        ite=7,
        kts=1,
        kte=LEVELS,
        jts=1,
        jte=5,
        im=7,
        km=LEVELS,
        jm=5,
        dt_bits=DT_BITS,
        ncmin_land_bits=LAND_BITS,
        ncmin_sea_bits=SEA_BITS,
    )


def _make_case(ready_qc, ready_nc, *, overrides=None, call_ids=(1,)):
    overrides = overrides or {}
    headers = {call_id: _header(call_id) for call_id in call_ids}
    values = {}
    for call_id in call_ids:
        for target_index, (target_name, (i, j)) in enumerate(TARGETS.items()):
            for k in range(1, LEVELS + 1):
                current = {"QC": _f32(ready_qc[target_index, k - 1]), "NC": _f32(ready_nc[target_index, k - 1])}
                f64_state = None
                for stage in STAGES:
                    owner = "kernel" if stage.startswith("FP64_") else "host"
                    for field in ("QC", "NC"):
                        key = (call_id, target_name, k, stage, field)
                        override = overrides.get(key)
                        if stage == "MP_INPUT":
                            value = current[field]
                            bits = _f32_bits(value)
                            dtype = "f32"
                        elif stage == "FP64_INPUT":
                            value = float(current[field])
                            if override is not None:
                                value = float(override)
                            bits = _f64_bits(value)
                            f64_state = f64_state or {}
                            f64_state[field] = value
                            dtype = "f64"
                        elif stage == "FP64_OUTPUT":
                            value = f64_state[field]
                            if override is not None:
                                value = float(override)
                            f64_state[field] = value
                            bits = _f64_bits(value)
                            dtype = "f64"
                        else:
                            value = _f32(f64_state[field]) if stage == "MP_OUTPUT" else current[field]
                            if override is not None:
                                value = _f32(override)
                            current[field] = _f32(value)
                            bits = _f32_bits(value)
                            dtype = "f32"
                        values[(call_id, stage, i, k, j, field)] = MomentTraceValue(
                            owner=owner,
                            call_id=call_id,
                            stage=stage,
                            i=i,
                            k=k,
                            j=j,
                            dtype=dtype,
                            field=field,
                            bits=bits,
                        )
    inventory = MomentTraceInventory(
        headers=headers,
        header_owners={call_id: ("host", "kernel") for call_id in call_ids},
        values=values,
        call_ids_by_owner={"host": tuple(call_ids), "kernel": tuple(call_ids)},
        source_files={"host": "host.hex", "kernel": "kernel.hex"},
    )
    final_qc = np.asarray(
        [[np.float32(inventory.values[(call_ids[-1], "MOMENTS_POST", i, k, j, "QC")].value) for k in range(1, LEVELS + 1)]
         for i, j in TARGETS.values()], dtype=np.float32
    )
    final_nc = np.asarray(
        [[np.float32(inventory.values[(call_ids[-1], "MOMENTS_POST", i, k, j, "NC")].value) for k in range(1, LEVELS + 1)]
         for i, j in TARGETS.values()], dtype=np.float32
    )
    return inventory, final_qc, final_nc


def _analyze(label, inventory, ready_qc, ready_nc, final_qc, final_nc):
    return analyze_native_moment_trace(
        inventory,
        targets=TARGETS,
        ready_qc=ready_qc,
        ready_nc=ready_nc,
        final_qc=final_qc,
        final_nc=final_nc,
        run_id=label,
        expected_call_count=1,
        expected_ncmin_land=64.0,
        expected_ncmin_sea=16.0,
        levels=LEVELS,
        global_shape=(7, LEVELS, 5),
        levels_of_interest=(19, 6, 4),
    )


def test_first_invalid_pair_stage_and_ready_invalid_are_distinguished_and_raw_conversions_exact():
    ready_qc = np.zeros((3, LEVELS), dtype=np.float32)
    ready_nc = np.ones((3, LEVELS), dtype=np.float32)
    ready_qc[0, 18] = np.float32(0.1)
    ready_qc[1, 5] = np.float32(0.1)
    ready_nc[1, 5] = np.float32(0.0)  # T2, k6 invalid before the trace starts.

    inventory, final_qc, final_nc = _make_case(
        ready_qc,
        ready_nc,
        overrides={
            (1, "T1", 19, "MOMENTS_PRE", "NC"): 0.0,  # first becomes invalid here.
            (1, "T2", 6, "MOMENTS_PRE", "NC"): 0.5,  # initially invalid, then resolved.
            (1, "T3", 4, "ZERO_OUT_PRE", "QC"): 0.1,  # QC becomes active while NC stays zero.
            (1, "T3", 4, "ZERO_OUT_PRE", "NC"): 0.0,
            (1, "T3", 4, "MOMENTS_PRE", "QC"): 0.1,
            (1, "T3", 4, "MOMENTS_PRE", "NC"): 0.0,
            (1, "T3", 4, "MOMENTS_POST", "QC"): 0.1,
            (1, "T3", 4, "MOMENTS_POST", "NC"): 0.0,
        },
    )
    result = _analyze("alpha", inventory, ready_qc, ready_nc, final_qc, final_nc)

    t1 = result["targets"]["T1"]["levels"]["19"]
    assert t1["ready_pair_invalid"] is False
    assert t1["invalid_pair_classification"] == "first_invalid_pair_observed_after_READY"
    assert t1["first_invalid_pair_boundary"]["boundary"] == "MOMENTS_PRE"
    t2 = result["targets"]["T2"]["levels"]["6"]
    assert t2["ready_pair_invalid"] is True
    assert t2["first_invalid_pair_boundary"]["boundary"] == "READY"
    t3 = result["targets"]["T3"]["levels"]["4"]
    assert t3["first_invalid_pair_boundary"]["boundary"] == "ZERO_OUT_PRE"
    assert result["representation_checks"]["input_f32_to_f64_exact_widen_mismatch_count"] == 0
    assert result["representation_checks"]["output_f64_to_f32_exact_cast_mismatch_count"] == 0
    assert result["interpretation_limits"]["mechanistic_root_cause_inferred"] is False
    assert result["interpretation_limits"]["raw_number_unit_certification"] is False


def test_nc_first_positive_is_reported_as_observed_boundary_not_mechanism():
    ready_qc = np.zeros((3, LEVELS), dtype=np.float32)
    ready_nc = np.ones((3, LEVELS), dtype=np.float32)
    ready_nc[2, 3] = np.float32(0.0)
    inventory, final_qc, final_nc = _make_case(
        ready_qc,
        ready_nc,
        overrides={(1, "T3", 4, "FP64_OUTPUT", "NC"): 0.25},
    )
    result = _analyze("control", inventory, ready_qc, ready_nc, final_qc, final_nc)
    entry = result["targets"]["T3"]["levels"]["4"]
    assert entry["ready_nc_nonpositive"] is True
    assert entry["first_nc_positive_boundary"]["boundary"] == "FP64_OUTPUT"
    assert entry["first_nc_positive_boundary"]["NC"]["value"] == 0.25
    assert result["interpretation_limits"]["mechanistic_root_cause_inferred"] is False


def test_f64_representation_discrepancies_are_separate_and_raw_bit_exact():
    ready_qc = np.zeros((3, LEVELS), dtype=np.float32)
    ready_nc = np.ones((3, LEVELS), dtype=np.float32)
    inventory, final_qc, final_nc = _make_case(
        ready_qc,
        ready_nc,
        overrides={
            (1, "T1", 2, "FP64_INPUT", "QC"): np.nextafter(np.float64(0.0), np.float64(1.0)),
            (1, "T1", 3, "FP64_OUTPUT", "NC"): 1.00000001,
            (1, "T1", 3, "MP_OUTPUT", "NC"): 1.0000001192092896,
        },
    )
    result = _analyze("representation", inventory, ready_qc, ready_nc, final_qc, final_nc)
    checks = result["representation_checks"]
    assert checks["input_f32_to_f64_exact_widen_mismatch_count"] == 1
    assert checks["input_f32_to_f64_exact_widen_mismatch_examples"][0]["field"] == "QC"
    assert checks["output_f64_to_f32_exact_cast_mismatch_count"] == 1
    assert checks["output_f64_to_f32_exact_cast_mismatch_examples"][0]["field"] == "NC"


def test_control_resolved_candidate_initially_invalid_and_retained(tmp_path):
    ready_qc = np.zeros((3, LEVELS), dtype=np.float32)
    ready_nc = np.ones((3, LEVELS), dtype=np.float32)
    ready_qc[1, 5] = np.float32(0.1)
    ready_nc[1, 5] = np.float32(0.0)  # T2, k6 starts invalid in both runs.
    control_inventory, control_final_qc, control_final_nc = _make_case(
        ready_qc,
        ready_nc,
        overrides={(1, "T2", 6, "MOMENTS_PRE", "NC"): 0.5},
    )
    candidate_inventory, candidate_final_qc, candidate_final_nc = _make_case(
        ready_qc,
        ready_nc,
        overrides={(1, "T2", 6, "MOMENTS_PRE", "NC"): 0.0},
    )
    control = _analyze("control", control_inventory, ready_qc, ready_nc, control_final_qc, control_final_nc)
    candidate = _analyze("alpha", candidate_inventory, ready_qc, ready_nc, candidate_final_qc, candidate_final_nc)

    comparison = compare_native_moment_runs(control, candidate, levels_of_interest=(19, 6, 4))
    result = comparison["targets"]["T2"]["6"]
    assert result["first_differing_boundary"]["boundary"] == "MOMENTS_PRE"
    assert result["first_differing_boundary"]["field"] == "NC"
    assert result["contrast"] == "control_resolved_candidate_initially_invalid_retained"
    assert result["candidate_ready_pair_invalid"] is True
    assert result["mechanistic_cause_inferred"] is False


def test_comparison_rejects_same_target_name_with_different_global_coordinates():
    ready_qc = np.zeros((3, LEVELS), dtype=np.float32)
    ready_nc = np.ones((3, LEVELS), dtype=np.float32)
    inventory, final_qc, final_nc = _make_case(ready_qc, ready_nc)
    control = _analyze("control", inventory, ready_qc, ready_nc, final_qc, final_nc)
    candidate = _analyze("alpha", inventory, ready_qc, ready_nc, final_qc, final_nc)
    candidate["targets"]["T1"]["global_i"] += 1

    with pytest.raises(ValueError, match="global coordinates differ"):
        compare_native_moment_runs(control, candidate, levels_of_interest=(19, 6, 4))


def test_candidate_initially_invalid_is_not_called_control_resolved_without_control_ready_evidence():
    control_ready_qc = np.zeros((3, LEVELS), dtype=np.float32)
    control_ready_nc = np.ones((3, LEVELS), dtype=np.float32)
    candidate_ready_qc = control_ready_qc.copy()
    candidate_ready_nc = control_ready_nc.copy()
    candidate_ready_qc[1, 5] = np.float32(0.1)
    candidate_ready_nc[1, 5] = np.float32(0.0)
    control_inventory, control_final_qc, control_final_nc = _make_case(
        control_ready_qc,
        control_ready_nc,
        overrides={(1, "T2", 6, "MOMENTS_PRE", "NC"): 0.5},
    )
    candidate_inventory, candidate_final_qc, candidate_final_nc = _make_case(
        candidate_ready_qc,
        candidate_ready_nc,
    )
    control = _analyze("control", control_inventory, control_ready_qc, control_ready_nc, control_final_qc, control_final_nc)
    candidate = _analyze("alpha", candidate_inventory, candidate_ready_qc, candidate_ready_nc, candidate_final_qc, candidate_final_nc)

    result = compare_native_moment_runs(control, candidate, levels_of_interest=(6,))["targets"]["T2"]["6"]
    assert result["control_ready_pair_invalid"] is False
    assert result["candidate_ready_pair_invalid"] is True
    assert result["contrast"] == "candidate_initially_invalid_and_retained_without_control_resolution_proof"


def test_analyzer_rejects_non_f32_ready_or_final_arrays():
    ready_qc = np.zeros((3, LEVELS), dtype=np.float64)
    ready_nc = np.ones((3, LEVELS), dtype=np.float32)
    inventory, final_qc, final_nc = _make_case(ready_qc.astype(np.float32), ready_nc)
    with pytest.raises(ValueError, match="raw float32"):
        _analyze("bad", inventory, ready_qc, ready_nc, final_qc, final_nc)
