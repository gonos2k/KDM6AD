"""Public arithmetic replay of already captured QR diagnostics."""

from pathlib import Path
from fractions import Fraction
import hashlib
import json
import math
import numpy as np
import pytest

E = Path(__file__).parents[1] / "evidence/qr_boundary_attribution_2026-10-24"


def test_all_forward_cases_bind_frozen_response_and_unchanged_object_members():
    run = json.loads((E / "execution.json").read_text())
    assert run["KDM_calls"] == 8 and run["host_steps"] == run["RTTOV_calls"] == 0
    assert len(run["receipts"]) == 8
    for mode in ["norm_actual", "raw_actual"]:
        for index in [34, 40]:
            rows = [
                r
                for r in run["receipts"]
                if r["mode"] == mode and r["batch_index"] == index
            ]
            assert {r["trace"] for r in rows} == {"off", "on"}
            assert (
                len({r["request_sha256"] for r in rows})
                == len({r["response_sha256"] for r in rows})
                == 1
            )
            assert all(r["frozen_response_bitwise_equal"] for r in rows)
    objects = json.loads((E / "archive_members.json").read_text())["objects"]
    assert len(objects) == 14 and sum(r["identical"] for r in objects) == 12
    assert {r["name"] for r in objects if not r["identical"]} == {
        "sedimentation.cpp.o",
        "coordinator.cpp.o",
    }


@pytest.mark.parametrize("mode", ["norm_actual", "raw_actual"])
@pytest.mark.parametrize("index", [34, 40])
def test_saved_whole_block_decomposition_and_independent_target_products(mode, index):
    path = E / f"analysis_{mode}_chunk{index:03d}.npz"
    with np.load(path, allow_pickle=False) as z:
        expected = (
            z["qr_reported_minus_applied_bottom"]
            - z["qr_internal_departure_minus_arrival"]
        )
        actual = z["qr_state_plus_qr_reported_diagnostic"]
        residual = np.array([math.fsum((a, -e)) for a, e in zip(actual, expected)])
        assert np.all(abs(residual) <= z["qr_decomposition_gate"])
        assert np.all(
            abs(z["step_state_plus_bottom_plus_internal_residual"])
            <= z["step_roundoff_gate"]
        )
        assert np.all(
            abs(z["qr_bottom_out_minus_in_minus_net"]) <= z["qr_decomposition_gate"]
        )
    rows = json.loads((E / "selected_rows.json").read_text())
    case = next(r for r in rows if r["mode"] == mode and r["chunk"] == index)
    trace = case["trace_rows"]
    chunks = {}
    for r in trace:
        chunks.setdefault(r["n"], []).append(r)
    exact_changes = []
    gaps = []
    bottom = []
    for n, levels in sorted(chunks.items()):
        levels.sort(key=lambda r: r["level_top0"])
        w = [float(r["DEND"] * r["DELZ"]) for r in levels]
        terms = [
            float(w[k] * (r["QR_after"] - r["QR_before"])) for k, r in enumerate(levels)
        ]
        exact_changes.append(
            float(sum((Fraction.from_float(x) for x in terms), Fraction()))
        )
        D = [float(w[k] * r["out_applied"]) for k, r in enumerate(levels)]
        A = [float(w[k] * r["arrival_applied"]) for k, r in enumerate(levels)]
        gaps.append(math.fsum(float(D[k] - A[k + 1]) for k in range(38)))
        bottom.append(D[-1])
    assert math.fsum(exact_changes) == case["state_change_kg_m2"]
    assert math.fsum(gaps) == case["internal_departure_minus_arrival_kg_m2"]
    assert math.fsum(bottom) == case["actual_bottom_departure_kg_m2"]
    if index == 34:
        assert (
            case["actual_bottom_arrival_kg_m2"] > case["actual_bottom_departure_kg_m2"]
        )
        assert case["net_bottom_depletion_kg_m2"] < 0
        assert (
            case["diagnostic_minus_actual_bottom_departure"]
            > case["internal_departure_minus_arrival_kg_m2"]
            > 0
        )
    else:
        assert (
            case["actual_bottom_departure_kg_m2"]
            == case["reported_qr_bottom_diagnostic_mm"]
            == 0
        )
        assert case["internal_departure_minus_arrival_kg_m2"] > 0


def test_first_order_three_way_products_match_exactly_within_each_variant():
    r = json.loads((E / "ad_receipts.json").read_text())["records"]
    for mode in ["norm_actual", "raw_actual"]:
        for index in [34, 40]:
            conditions = {
                row["condition"]: row
                for row in r
                if row["mode"] == mode and row["chunk"] == index
            }
            assert set(conditions) == {"control", "off", "on"}
            for key in conditions["control"]["products"]:
                expected = conditions["control"]["products"][key]["sha256"]
                for label in ["control", "off", "on"]:
                    path = E / f"ad_{mode}_{index:03d}_{label}.npz"
                    with np.load(path, allow_pickle=False) as z:
                        assert hashlib.sha256(z[key].tobytes()).hexdigest() == expected


def test_evidence_and_executed_source_hashes():
    manifest = json.loads((E / "manifest.json").read_text())
    root = E.parents[2]
    for group in ["source_sha256", "artifact_sha256"]:
        assert manifest[group]
        for path, expected in manifest[group].items():
            # Immutable old receipts bind the source bytes actually executed.
            archived = {
                "harness/analyze_rain_boundary_trace.py": "analyze_rain_boundary_trace.py.txt",
                "harness/tests/test_qr_boundary_evidence.py": "test_qr_boundary_evidence.py.txt",
            }
            source = root / path
            if group == "source_sha256" and path in archived:
                source = (
                    root
                    / "harness/evidence/readable_candidate_tools_2026-10-24/executed_sources"
                    / archived[path]
                )
            assert hashlib.sha256(source.read_bytes()).hexdigest() == expected, path
