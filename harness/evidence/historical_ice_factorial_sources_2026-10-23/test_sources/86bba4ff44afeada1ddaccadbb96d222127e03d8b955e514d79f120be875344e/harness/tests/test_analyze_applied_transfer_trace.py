import csv
import io
import math
from pathlib import Path

import pytest

from harness.analyze_applied_transfer_trace import (
    EXPECTED_COLUMNS,
    HEADER,
    LIMITER_GROUPS,
    TraceError,
    analyze_trace,
    _weighted_stage_change,
)


def make_trace(*, mutate=None):
    rows = []
    dt = 20.0
    for target_index, (chunk, column, level) in enumerate(EXPECTED_COLUMNS):
        snapshots = {
            stage: {
                "qv": 0.010,
                "qc": 0.001,
                "qr": 0.002,
                "qi": 0.003,
                "qs": 0.004,
                "qg": 0.005,
                "t": 260.0,
            }
            for stage in (
                "micro_entry",
                "pre_limits",
                "post_limits",
                "state_update_raw",
                "post_state_update",
                "post_reclass_ice",
                "post_reclass_rain",
                "post_satadj",
                "post_threshold",
                "micro_exit",
            )
        }
        snapshots["pre_limits"]["qs"] += 1e-10
        snapshots["post_limits"]["qs"] += 1e-10
        for field, value in {
            "psdep": 0.00001,
            "pgdep": 0.00002,
            "psevp": -0.00003,
            "pgevp": -0.00004,
        }.items():
            snapshots["pre_limits"][field] = value
            snapshots["post_limits"][field] = value * 0.5
        snapshots["state_update_raw"].update(
            {
                **{
                    f"{field}_before": value
                    for field, value in snapshots["post_limits"].items()
                    if field in ("qv", "qc", "qr", "qi", "qs", "qg")
                },
                "dqv_sum": -0.0002,
                "dqs_sum": 0.0001,
                "dqg_rate_sum": 0.0001,
                "dqg_amount": 0.0,
                "dqc_rate_sum": 0.0,
                "dqc_amount": 0.0,
                "dqr_rate_sum": 0.0,
                "dqr_amount": 0.0,
                "dqi_rate_sum": 0.0,
                "dqi_amount": 0.0,
                "cold_mask": 0.0 if target_index == 1 else 1.0,
                "warm_mask": 1.0 if target_index == 1 else 0.0,
                "psdep": 0.00001,
                "pgdep": 0.00002,
                "psevp": -0.00003,
                "pgevp": -0.00004,
            }
        )
        snapshots["state_update_raw"]["qv"] -= 0.0002 * dt
        snapshots["state_update_raw"]["qs"] += 0.0001 * dt
        snapshots["state_update_raw"]["qg"] += 0.0001 * dt
        snapshots["post_state_update"].update(snapshots["state_update_raw"])
        snapshots["post_state_update"].pop("dqv_sum")
        snapshots["post_state_update"].pop("dqs_sum")
        snapshots["post_state_update"].pop("dqg_rate_sum")
        snapshots["post_state_update"].pop("dqg_amount")
        snapshots["post_state_update"].pop("cold_mask")
        snapshots["post_state_update"].pop("warm_mask")
        snapshots["post_state_update"].pop("psdep")
        snapshots["post_state_update"].pop("pgdep")
        snapshots["post_state_update"].pop("psevp")
        snapshots["post_state_update"].pop("pgevp")
        snapshots["post_reclass_ice"].update(snapshots["post_state_update"])
        snapshots["post_reclass_rain"].update(snapshots["post_state_update"])
        snapshots["post_satadj"].update(snapshots["post_state_update"])
        snapshots["post_satadj"]["qg"] = 8e-10
        snapshots["post_threshold"].update(snapshots["post_satadj"])
        snapshots["post_threshold"]["qg"] = 0.0
        snapshots["micro_exit"].update(snapshots["post_threshold"])
        snapshots["micro_entry"]["rho"] = 0.6
        snapshots["micro_entry"]["delz"] = 700.0
        for stage, values in snapshots.items():
            for field, value in values.items():
                rows.append([1, stage, "0", chunk, column, level, dt, field, value])
        pre_rate = {"psdep": 1.0, "pgdep": 2.0, "psevp": -3.0, "pgevp": -4.0}
        post_rate = {name: value * 0.5 for name, value in pre_rate.items()}
        for group in LIMITER_GROUPS:
            for stage, rates in (
                ("limiter_before", pre_rate),
                ("limiter_after", post_rate),
            ):
                for field, value in rates.items():
                    rows.append(
                        [1, stage, group, chunk, column, level, dt, field, value]
                    )
                for field, value in {
                    "value": 1.0e-15,
                    "source": 0.0,
                    "factor": 1.0,
                    "gate": 1.0,
                }.items():
                    rows.append(
                        [1, stage, group, chunk, column, level, dt, field, value]
                    )
        if mutate is not None:
            mutate(rows, target_index)
    stream = io.StringIO()
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(rows)
    return stream.getvalue().encode()


def test_analyzer_keeps_nominal_pair_amounts_separate_from_aggregate_rounding():
    report = analyze_trace(make_trace())
    assert len(report["calls"]) == 1
    first = report["calls"][0]["targets"][0]
    pairs = first["signed_pair_transfer_nominals"]
    assert pairs["psdep"]["nominal_signed_amount_kg_kg"] == pytest.approx(0.0002)
    assert pairs["psdep"]["nominal_signed_endpoint_changes_kg_kg"] == {
        "qv": pytest.approx(-0.0002),
        "qs": pytest.approx(0.0002),
    }
    warm_pairs = report["calls"][0]["targets"][1]["signed_pair_transfer_nominals"]
    assert warm_pairs["psevp"]["nominal_signed_amount_kg_kg"] == pytest.approx(-0.0006)
    assert warm_pairs["psevp"]["nominal_signed_endpoint_changes_kg_kg"] == {
        "qv": pytest.approx(0.0006),
        "qs": pytest.approx(-0.0006),
    }
    assert (
        first["rate_fields_before_after_group_limiters"]["psdep"][
            "post_process_local_cap_pre_group_limiter"
        ]
        == 0.00001
    )
    assert (
        first["rate_fields_before_after_group_limiters"]["psdep"]["post_group_limiter"]
        == 0.000005
    )
    assert report["cleanup_thresholds"]["precipitating_qcrmin"] == 1.0e-9
    assert "do not explain why qg entered" in report["interpretation_limits"][3]
    assert (
        first["aggregate_state_update_reconstruction"]["qg"]["source_order"]
        == "(qg_before + dqg_amount) + dqg_rate_sum*dt"
    )
    assert "qc" in first["aggregate_state_update_reconstruction"]
    assert len(first["limiter_groups"]["limiter_groups"]) == 14
    assert first["limiter_groups"]["limiter_groups"][0]["budget_name"] == "cold_mass_qc"
    assert (
        first["limiter_groups"]["limiter_groups"][-1]["budget_name"] == "warm_number_nr"
    )


def test_parser_rejects_duplicate_fields_and_unexpected_targets():
    duplicate = make_trace()
    duplicate += b"1\tmicro_entry\t0\t34\t281\t17\t20\tqv\t0.01\n"
    with pytest.raises(TraceError, match="duplicate field"):
        analyze_trace(duplicate)

    def wrong_target(rows, target_index):
        if target_index == 2:
            rows[:] = [row for row in rows if not (row[3] == 40 and row[4] == 250)]

    with pytest.raises(TraceError, match="targets must be exactly"):
        analyze_trace(make_trace(mutate=wrong_target))


def test_parser_rejects_nonfinite_values_and_branch_masks_that_overlap():
    def bad_value(rows, target_index):
        if target_index == 0:
            for row in rows:
                if row[1] == "micro_entry" and row[7] == "qv":
                    row[8] = "nan"
                    break

    with pytest.raises(TraceError, match="finite"):
        analyze_trace(make_trace(mutate=bad_value))

    def bad_mask(rows, target_index):
        if target_index == 0:
            for row in rows:
                if row[1] == "state_update_raw" and row[7] == "warm_mask":
                    row[8] = 1.0

    with pytest.raises(TraceError, match="select exactly one branch"):
        analyze_trace(make_trace(mutate=bad_mask))


def test_cleanup_endpoint_loss_is_reported_as_its_own_later_boundary():
    report = analyze_trace(make_trace())
    target = report["calls"][0]["targets"][0]
    cleanup = next(
        item
        for item in target["stage_water_changes"]
        if item["from_stage"] == "post_satadj" and item["to_stage"] == "post_threshold"
    )
    assert cleanup["field_delta_kg_kg"]["qg"] == pytest.approx(-8e-10)
    assert cleanup["water_total_delta_kg_kg"] == pytest.approx(-8e-10)
    assert "do not explain why qg entered" in report["interpretation_limits"][3]
    finding = report["observed_threshold_cleanup_boundary"]["targets"][0]
    assert finding["qg_before_is_nonnegative_and_at_or_below_qcrmin"]
    assert finding["qg_signed_cleanup_delta_kg_kg"] == pytest.approx(-8e-10)
    assert finding["changed_water_fields"] == ["qg"]


def test_independently_traced_chunks_merge_by_native_target():
    rows = make_trace().decode().splitlines()
    header = rows[0]
    chunk34 = [row for row in rows[1:] if row.split("\t")[3] == "34"]
    chunk40 = [row for row in rows[1:] if row.split("\t")[3] == "40"]
    report = analyze_trace(
        [
            (header + "\n" + "\n".join(chunk34) + "\n").encode(),
            (header + "\n" + "\n".join(chunk40) + "\n").encode(),
        ]
    )
    assert len(report["source_traces_sha256"]) == 2
    assert len(report["calls"][0]["targets"]) == 3


def test_qg_reconstruction_preserves_inline_amount_then_rate_order():
    def qg_amount(rows, target_index):
        if target_index != 0:
            return
        for row in rows:
            if row[1] == "state_update_raw" and row[3:6] == [34, 281, 17]:
                if row[7] == "qg_before":
                    row[8] = 0.1
                elif row[7] == "dqg_amount":
                    row[8] = -0.09
                elif row[7] == "dqg_rate_sum":
                    row[8] = -0.0001
                elif row[7] == "qg":
                    row[8] = (0.1 - 0.09) + (-0.0001 * 20.0)

    report = analyze_trace(make_trace(mutate=qg_amount))
    qg = report["calls"][0]["targets"][0]["aggregate_state_update_reconstruction"]["qg"]
    assert qg["expected_unclamped_state"] == (0.1 - 0.09) + (-0.0001 * 20.0)
    assert qg["raw_state_minus_nominal_reconstruction"] == 0.0


def test_parser_rejects_missing_limiter_group_or_required_event_field():
    def remove_group14(rows, target_index):
        if target_index == 0:
            rows[:] = [
                row
                for row in rows
                if not (
                    row[1] in ("limiter_before", "limiter_after") and row[2] == "14"
                )
            ]

    with pytest.raises(TraceError, match="groups 1..14"):
        analyze_trace(make_trace(mutate=remove_group14))

    def remove_factor(rows, target_index):
        if target_index == 0:
            rows[:] = [
                row
                for row in rows
                if not (
                    row[1] == "limiter_after" and row[2] == "7" and row[7] == "factor"
                )
            ]

    with pytest.raises(TraceError, match="exact fields"):
        analyze_trace(make_trace(mutate=remove_factor))

    def remove_stage_rate(rows, target_index):
        if target_index == 0:
            rows[:] = [
                row
                for row in rows
                if not (row[1] == "pre_limits" and row[7] == "pgdep")
            ]

    with pytest.raises(TraceError, match="all four selected rate fields"):
        analyze_trace(make_trace(mutate=remove_stage_rate))


def test_reference_npz_crosscheck_rejects_nonmatching_saved_endpoints():
    repo_root = Path(__file__).resolve().parents[2]
    npz_paths = [
        repo_root / "harness/evidence/actual_qr_transport_2026-10-24/chunk034.npz",
        repo_root / "harness/evidence/actual_qr_transport_2026-10-24/chunk040.npz",
    ]
    with pytest.raises(TraceError, match="differs bitwise"):
        analyze_trace(make_trace(), reference_npz_paths=npz_paths)


def test_primary_water_delta_sums_per_field_changes_before_weighting():
    before = {field: 0.0 for field in ("qv", "qc", "qr", "qi", "qs", "qg")}
    after = dict(before)
    before["qv"] = 1.0e16
    before["qc"] = 0.5
    after["qv"] = 1.0e16
    after["qc"] = math.nextafter(0.5, math.inf)
    weight = 465.4281181978131
    result = _weighted_stage_change(before, after, weight)
    field_delta = after["qc"] - before["qc"]
    assert result["water_total_delta_kg_kg"] == math.fsum([field_delta])
    assert result["water_total_delta_from_inventory_subtraction_kg_kg"] == 0.0
    assert result["water_total_delta_kg_m2_local_level"] == weight * field_delta
    assert result["water_total_delta_cancellation_remainder_kg_kg"] == -field_delta
