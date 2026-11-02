"""Public arithmetic replay of the new observer evidence; no model dependency."""

from pathlib import Path
import csv
import hashlib
import json
import math

import numpy as np
import pytest

E = Path(__file__).parents[1] / "evidence/applied_transfer_2026-10-24"
WATER = ("qv", "qc", "qr", "qi", "qs", "qg")


def test_isolated_build_and_frozen_candidate_value_identity():
    build = json.loads((E / "build_receipt.json").read_text())
    assert build["changed_object_members"] == ["coordinator.cpp.o"]
    assert (
        build["unchanged_object_members"] == 13
        and not build["operational_install_changed"]
    )
    assert (
        "-ffp-contract=off"
        in json.loads((E / "build_prepared.json").read_text())["compile_command"]
    )
    execution = json.loads((E / "execution.json").read_text())
    assert (
        execution["KDM_calls"] == 4
        and execution["RTTOV_calls"]
        == execution["host_steps"]
        == execution["DA_trials"]
        == 0
    )
    assert len(execution["receipts"]) == 4
    prior = json.loads(
        (
            E.parents[2]
            / "harness/evidence/actual_qr_transport_2026-10-24/block_execution.json"
        ).read_text()
    )
    for chunk in [34, 40]:
        original = next(
            r
            for r in prior["receipts"]
            if r["chunk"] == chunk and r["condition"] == "actual_off"
        )
        rows = [r for r in execution["receipts"] if r["chunk"] == chunk]
        assert all(r["request_sha256"] == original["request_sha256"] for r in rows)
        assert all(
            r["prior_candidate_response_sha256"] == original["response_sha256"]
            for r in rows
        )
        assert {r["trace"] for r in rows} == {"off", "on"}
        assert len({r["response_sha256"] for r in rows}) == 1
        assert all(
            r["response_sha256"] == r["prior_candidate_response_sha256"] for r in rows
        )
        assert all(r["tool_sha256"] == build["batch_tool_sha256"] for r in rows)
        trace = E / f"chunk{chunk:03d}.trace.tsv"
        expected = next(r["trace_sha256"] for r in rows if r["trace"] == "on")
        assert hashlib.sha256(trace.read_bytes()).hexdigest() == expected


def _rows(chunk, level):
    cells = {}
    with (E / f"chunk{chunk:03d}.trace.tsv").open() as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if int(row["level_bottom0"]) != level:
                continue
            assert int(row["call"]) == 1 and float(row["dt"]) == 20.0
            cells.setdefault((row["stage"], int(row["group"])), {})[row["field"]] = (
                float(row["value"])
            )
    return cells


@pytest.mark.parametrize(
    "chunk,level,column", [(34, 17, 281), (34, 18, 281), (40, 17, 250)]
)
def test_actual_rate_application_then_qg_cleanup_sink(chunk, level, column):
    rows = _rows(chunk, level)
    entry = rows["micro_entry", 0]
    weight = entry["rho"] * entry["delz"]
    pre = rows["pre_limits", 0]
    post = rows["post_limits", 0]
    raw = rows["state_update_raw", 0]
    updated = rows["post_state_update", 0]
    assert raw["cold_mask"] == 1 and raw["warm_mask"] == 0 and raw["supcol"] > 0
    for rate in ["psdep", "pgdep"]:
        assert pre[rate] == post[rate] == raw[rate] and raw[rate] < 0
    assert all(raw[k] == 0 for k in ["psevp", "pgevp", "prevp", "pinud", "pidep"])
    assert raw["dqv_sum"] == -raw["psdep"] - raw["pgdep"]
    assert (
        raw["dqs_sum"] == raw["psdep"]
        and raw["dqg_rate_sum"] == raw["pgdep"]
        and raw["dqg_amount"] == 0
    )
    assert raw["qv"] == pre["qv"] + raw["dqv_sum"] * 20.0
    assert raw["qs"] == pre["qs"] + raw["dqs_sum"] * 20.0
    assert raw["qg"] == (pre["qg"] + raw["dqg_amount"]) + raw["dqg_rate_sum"] * 20.0
    assert all(raw[q] == updated[q] for q in WATER)  # No final max projection here.
    update_net = math.fsum(float(updated[q] - pre[q]) * weight for q in WATER)
    assert (
        abs(update_net) < 1e-14
    )  # Arithmetic replay scale, not a widened physical gate.
    for group in range(1, 15):
        before, after = rows["limiter_before", group], rows["limiter_after", group]
        assert before["factor"] == 1 and after["factor"] == 1
        assert all(before[k] == after[k] for k in ["psdep", "pgdep", "psevp", "pgevp"])
    before, after = rows["post_satadj", 0], rows["post_threshold", 0]
    assert 0 < before["qg"] <= 1e-9 and after["qg"] == 0
    assert (
        all(before[q] == after[q] for q in WATER if q != "qg")
        and before["t"] == after["t"]
    )
    sink = -before["qg"] * weight
    report = json.loads((E / "analysis.json").read_text())
    finding = next(
        r
        for r in report["observed_threshold_cleanup_boundary"]["targets"]
        if (r["chunk"], r["column"], r["level_bottom0"]) == (chunk, column, level)
    )
    assert finding["water_total_delta_kg_m2_local_level"] == sink
    assert finding["qg_signed_cleanup_delta_kg_kg"] == -before["qg"]
    assert finding["changed_water_fields"] == ["qg"]
    old = (
        E.parents[2]
        / f"harness/evidence/actual_qr_transport_2026-10-24/chunk{chunk:03d}.npz"
    )
    with np.load(old, allow_pickle=False) as data:
        for i, q in enumerate(WATER):
            assert (
                np.float64(entry[q]).tobytes()
                == data["water_stages_bottomfirst"][1, i, column, level].tobytes()
            )
            assert (
                np.float64(rows["micro_exit", 0][q]).tobytes()
                == data["water_stages_bottomfirst"][2, i, column, level].tobytes()
            )


@pytest.mark.parametrize("chunk", [34, 40])
def test_selected_first_order_products_match_control_off_on(chunk):
    record = json.loads((E / "ad_noninterference.json").read_text())
    assert record["KDM_calls"] == 6
    row = next(r for r in record["comparisons"] if r["chunk"] == chunk)
    assert all(row["all_products_bitwise_equal"].values())
    with (
        np.load(E / f"ad_chunk{chunk:03d}_control.npz") as control,
        np.load(E / f"ad_chunk{chunk:03d}_off.npz") as off,
        np.load(E / f"ad_chunk{chunk:03d}_on.npz") as on,
    ):
        assert set(control.files) == set(off.files) == set(on.files)
        for name in control.files:
            assert np.isfinite(control[name]).all()
            assert np.array_equal(control[name].view("u8"), off[name].view("u8"))
            assert np.array_equal(control[name].view("u8"), on[name].view("u8"))


def test_current_source_and_artifact_pins():
    manifest = json.loads((E / "manifest.json").read_text())
    root = E.parents[2]
    for group in ["source_sha256", "input_sha256", "artifact_sha256"]:
        assert manifest[group]
        for path, digest in manifest[group].items():
            assert hashlib.sha256((root / path).read_bytes()).hexdigest() == digest, (
                path
            )
