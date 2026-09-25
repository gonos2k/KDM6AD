from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from replay_progb_validity import parse_event_lines, validate_events, validate_manifest  # noqa: E402


def _native_shape_event_lines():
    lines = []
    for lat in range(2, 282):
        found = int(lat == 40)
        lines.append(f"S10SCAN 1 {lat} 1 0 0 {found}")
    lines.append("S10TRACE 1 40 1 0 0 4 3 1 0 0 0 0 0 0")
    lines.append("S10TRS 1 40 1 0 0 4 3 1 0 0 0 0 0 1 1 1")
    for i in (113, 115):
        for k in range(1, 40):
            active = int((i == 113 and k <= 11)
                         or (i == 115 and 4 <= k <= 11))
            rhox_assigned = cmg_assigned = pidn_assigned = params_assigned = active
            lines.append(
                "S10PB " + " ".join(map(str, (
                    1, 73, 1, 0, 0, i, k, active, rhox_assigned,
                    cmg_assigned, pidn_assigned, params_assigned)))
            )
            lines.append(
                "S10CMG " + " ".join(map(str, (
                    1, 73, 1, 0, 0, i, k, cmg_assigned, 1)))
            )
            lines.append(
                "S10SLP " + " ".join(map(str, (
                    1, 73, 1, 0, 0, i, k,
                    rhox_assigned, cmg_assigned, pidn_assigned, params_assigned,
                    active, 1-active, 1, active, active, 1-active, 1)))
            )
    lines.append("S10RHO 1 73 1 0 0 115 12 3027 0 1")
    lines.append("S10DIAG 1 73 113 1 1 1 1")
    lines.append("S10DIAG 1 73 115 12 0 0 0")
    return lines


def test_replay_reports_reached_unassigned_reads_without_output_values():
    records = parse_event_lines(_native_shape_event_lines())
    result = validate_events(records)
    assert result["source_level_p2"]["cmg_intent_out_test_reached_without_assignment"]
    assert result["source_level_p2"]["slope_parameter_read_reached_without_defined_producer_chain"]
    assert result["source_level_p2"]["rhox_read_reached_without_assignment"]
    assert not result["source_level_p2"]["final_diagnostic_read_reached_without_assignment"]
    assert result["undefined_output_values_serialized"] is False
    assert result["undefined_output_physical_impact"] == "NOT_MEASURED"
    assert result["trace_qg_nonzero_inactive_gate_records"] == 1
    assert result["site1_observed_active_levels_by_i"]["115"] == list(range(4, 12))


def test_replay_rejects_missing_preselected_level():
    lines = _native_shape_event_lines()
    kept = []
    for line in lines:
        fields = line.split()
        if fields[0] in {"S10PB", "S10CMG", "S10SLP"}:
            key = tuple(map(int, fields[1:8]))
            if key == (1, 73, 1, 0, 0, 113, 11):
                continue
        kept.append(line)
    with pytest.raises(ValueError, match="selected-column coverage mismatch"):
        validate_events(parse_event_lines(kept))


def test_replay_rejects_numeric_or_non_flag_payloads():
    with pytest.raises(ValueError, match="integers only"):
        parse_event_lines(["S10PB 1 73 1 0 0 113 1 1 1 1 1 1.0"])
    with pytest.raises(ValueError, match="flag"):
        parse_event_lines(["S10DIAG 1 73 113 1 2 0 1"])


def test_prepared_manifest_cannot_be_replayed_as_native_evidence():
    with pytest.raises(ValueError, match="prepared manifest only"):
        validate_manifest({
            "schema": "progb-validity-run-v1",
            "execution_status": "PREPARED_NOT_RUN",
        })


def test_completed_manifest_requires_same_build_inputs_namelist_and_log_switch():
    manifest = {
        "schema": "progb-validity-run-v1",
        "execution_status": "completed",
        "source": {
            "variant": "mp37",
            "canonical_source_sha256": "fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5",
            "strip_exact": True,
        },
        "run": {
            "mp_physics": 37, "dt_s": 20, "actual_proc_grid": "1x1",
            "ranks": 1, "threads_per_rank": 1,
            "saved_times": ["2025-07-19_00:00:00", "2025-07-19_00:00:20"],
        },
        "input_sha256": {
            "wrfinput_d01": "5a9ae8da992028dbf3a2a7652eb61532c1efab2acea7ea0e393e4cac8fd4c970",
            "wrfbdy_d01": "d46e5d7117c076956d130b4ff905fc34a5d53dbd5a0d9571311582b0a60c5e6c",
            "wrfchainp_d01": "c8e300d2aa52f98c9060803438ab6f796bddd1e1cdd6b75a14e39a398cb0c4e3",
        },
        "noninterference": {
            "numeric_raw_bits_equal": True,
            "saved_times_equal": True,
            "history_sha256": {"control": "same", "capture": "same"},
            "executable_sha256": {"control": "exe", "capture": "exe"},
            "input_identity_sha256": {"control": "inputs", "capture": "inputs"},
            "namelist_sha256": {"control": "nml", "capture": "nml"},
            "logging_enabled": {"control": False, "capture": True},
        },
        "physical_validity_policy": "OPEN",
    }
    validate_manifest(manifest)
    manifest["noninterference"]["executable_sha256"]["capture"] = "other-exe"
    with pytest.raises(ValueError, match="same executable"):
        validate_manifest(manifest)
