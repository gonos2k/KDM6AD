"""Strict source-equation, request-binding and completeness tests."""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from harness import analyze_ice_boundary_trace as analyzer


def artifacts():
    base = Path(__file__).parents[1] / "evidence/ice_boundary_trace_2026-10-23"
    return {
        "trace": base / "native39_ice_trace.tsv",
        "manifest": base / "build_manifest.json",
        "request": base / "request.bin",
        "control": base / "response_control.bin",
        "traced": base / "response_trace.bin",
    }


def test_actual_capture_is_complete_source_reconstructable_and_noninterfering():
    p = artifacts()
    result = analyzer.analyze(
        p["trace"], p["manifest"], p["request"], p["control"], p["traced"]
    )
    assert result["record_counts"] == {"velocity": 78, "ice_layer": 39, "ice_bottom": 1}
    assert result["mstepmax_ice"] == 1
    assert result["response_noninterference"]["full_response_bitwise_equal"]
    column = result["columns"][0]
    assert column["qi_arrival_cap_bound_count"] == 5
    assert column["ni_arrival_cap_bound_count"] == 5
    assert column["qi_bottom_applied_outflow_kg_m2"] == 0.0
    assert column["qi_bottom_stored_falk_equivalent_kg_m2"] == 0.0
    assert column["qi_interface_defect_kg_m2"] == pytest.approx(0.0012979597722250025)
    assert abs(column["qi_state_export_defect_identity_residual_kg_m2"]) < 1e-15
    assert column["ni_interface_defect_number_m2"] == pytest.approx(620092374.2268972)
    assert abs(column["ni_state_export_defect_identity_residual_number_m2"]) < 1e-5


@pytest.mark.parametrize(
    "mutation,pattern",
    [
        ("drop_layer", "incomplete or out of order"),
        ("duplicate_key", "duplicate key"),
        ("noninteger", "non-integer"),
        ("density", "DEND differs"),
        ("safe_density", "DEND safe value"),
        ("above_dz", "upstream DELZ"),
        ("bottom_dz", "bottom diagnostic DELZ"),
        ("dtcld", "dtcld"),
        ("qi_input", "first ICE state differs"),
        ("bad_mstep", "mstep"),
    ],
)
def test_analyzer_refuses_incomplete_or_mismatched_trace(tmp_path, mutation, pattern):
    p = artifacts()
    lines = p["trace"].read_text().splitlines()
    layer_index = next(i for i, line in enumerate(lines) if "record=ice_layer" in line)
    if mutation == "drop_layer":
        lines.pop(layer_index)
    elif mutation == "duplicate_key":
        lines[layer_index] += " mstep=1"
    elif mutation == "noninteger":
        lines[layer_index] = lines[layer_index].replace("substep=1", "substep=1.5", 1)
    elif mutation == "density":
        lines[layer_index] = lines[layer_index].replace(
            "DEND_kg_m3=", "DEND_kg_m3=9", 1
        )
    elif mutation == "safe_density":
        lines[layer_index] = re.sub(
            r"DEND_safe_kg_m3=[^ ]+", "DEND_safe_kg_m3=9", lines[layer_index], count=1
        )
    elif mutation == "above_dz":
        inner = next(
            i
            for i, line in enumerate(lines)
            if "record=ice_layer" in line and "level_top0=1" in line
        )
        lines[inner] = re.sub(
            r"DELZ_above_m=[^ ]+", "DELZ_above_m=999", lines[inner], count=1
        )
    elif mutation == "bottom_dz":
        bottom = next(i for i, line in enumerate(lines) if "record=ice_bottom" in line)
        lines[bottom] = re.sub(
            r"DELZ_bottom_m=[^ ]+", "DELZ_bottom_m=999", lines[bottom], count=1
        )
    elif mutation == "dtcld":
        lines[layer_index] = re.sub(
            r"dtcld_s=[^ ]+", "dtcld_s=21", lines[layer_index], count=1
        )
    elif mutation == "qi_input":
        lines[layer_index] = re.sub(
            r"QI_before_kg_kg=[^ ]+", "QI_before_kg_kg=0.1", lines[layer_index], count=1
        )
    else:
        lines[layer_index] = lines[layer_index].replace(
            " mstep=1 gate=", " mstep=2 gate=", 1
        )
    bad = tmp_path / "mutated.tsv"
    bad.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match=pattern):
        analyzer.analyze(bad, p["manifest"], p["request"])


def test_analyzer_refuses_request_or_manifest_hash_mismatch(tmp_path):
    p = artifacts()
    request = tmp_path / "request.bin"
    request.write_bytes(p["request"].read_bytes() + b"extra")
    with pytest.raises(ValueError, match="payload length"):
        analyzer.analyze(p["trace"], p["manifest"], request)
    manifest = json.loads(p["manifest"].read_text())
    manifest["source_sha256"]["coordinator.cpp"] = "not-a-hash"
    bad_manifest = tmp_path / "manifest.json"
    bad_manifest.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="manifest .*SHA mismatch|invalid hash"):
        analyzer.analyze(p["trace"], bad_manifest, p["request"])


def test_analyzer_refuses_changed_control_response(tmp_path):
    p = artifacts()
    bad_response = tmp_path / "changed.bin"
    changed = bytearray(p["traced"].read_bytes())
    # Corrupt the returned state while preserving request echoes and precip tail.
    changed[16 + 16 * 39 * 8] ^= 1
    bad_response.write_bytes(changed)
    with pytest.raises(ValueError, match="response bytes"):
        analyzer.analyze(
            p["trace"], p["manifest"], p["request"], p["control"], bad_response
        )
