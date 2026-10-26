from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import numpy as np
import pytest

from harness import analyze_activation_trace as analyzer


def _receipt():
    return {
        "schema": analyzer.SOURCE_RECEIPT_SCHEMA,
        "source_sha256": analyzer.PINNED_SOURCE_SHA256,
        "coordinator_sha256": analyzer.PINNED_COORDINATOR_SHA256,
        "producer_sha256": analyzer.PINNED_PRODUCER_SHA256,
        "trace_env": analyzer.TRACE_ENV,
        "B": analyzer.BATCH,
        "L": analyzer.LEVELS,
        "row0": analyzer.TRACE_ROW,
        "levels_bottom0": list(analyzer.TRACE_LEVELS),
        "scope": "value-only fixture",
    }


def _fixture(*, extra_mask_bit=None, second_call=False, second_call_extra_bit=None):
    records = []
    dt = 20.0
    calls = (1, 2) if second_call else (1,)
    for call in calls:
        # A consistent supersaturated case: activation consumes the available
        # NCCN coordinate before the post-satadj lower-bound clamp restores it.
        entry = {
            "t": 280.0,
            "qv": 0.0053,
            "qc": 1.0e-5,
            "nc": 323406.78125,
            "nccn": 1.0e8,
            "qs1": 0.005,
            "p": 90000.0,
            "rho_d": 1.1,
            "xl": 2.5e6,
            "cpm": 1004.0,
        }
        sw = (entry["qv"] / max(entry["qs1"], analyzer.QCRMIN) - 1.0) * 100.0
        ratio = max(sw / 0.48, 0.0)
        frac = min(1.0, max(ratio, analyzer.EPS) ** analyzer.ACTK)
        ncact_raw = max((entry["nccn"] + entry["nc"]) * frac - entry["nc"], 0.0) / dt
        ncact_cap = min(ncact_raw, entry["nccn"] / dt)
        ncact = ncact_cap if sw > 0 else 0.0
        pcact_raw = analyzer.PCACT_MASS_CONST * ncact / (3.0 * entry["rho_d"])
        pcact = min(pcact_raw, max(entry["qv"], 0.0) / dt)
        cpm_safe = max(entry["cpm"], analyzer.QCRMIN)
        qv_pp_raw = entry["qv"] - pcact * dt
        qv_pp = max(qv_pp_raw, 0.0) if sw > 0 else qv_pp_raw
        qc_pp = max(entry["qc"] + pcact * dt, 0.0)
        t_pp = entry["t"] + (pcact * entry["xl"] / cpm_safe) * dt
        nc_pp = max(entry["nc"] + ncact * dt, 0.0)
        nccn_pp = max(entry["nccn"] - ncact * dt, 0.0)
        qv_final = qv_pp
        qc_final = qc_pp
        t_final = t_pp
        nc_final = nc_pp
        nccn_raw = nccn_pp
        nccn_final = min(max(nccn_raw, analyzer.NCCN_MIN), analyzer.NCCN_MAX)

        bool_values = {
            "activation_fraction": {
                "sw_positive": sw > 0,
                "sw_at_zero": sw == 0,
                "fraction_saturated": frac >= 1,
                "sw_ratio_at_one": ratio == 1,
            },
            "activation_pre_gate": {
                "raw_zero": ncact_raw <= 0,
                "reservoir_tie": ncact_raw == entry["nccn"] / dt,
                "reservoir_cap": ncact_raw > entry["nccn"] / dt,
            },
            "activation_gated": {
                "qv_cap_tie": pcact_raw == max(entry["qv"], 0.0) / dt,
                "qv_cap": pcact_raw > max(entry["qv"], 0.0) / dt,
            },
            "post_satadj": {
                "complete_evap": False,
                "pcond_positive": False,
                "nccn_below_min": nccn_raw < analyzer.NCCN_MIN,
                "nccn_at_min": nccn_raw == analyzer.NCCN_MIN,
                "nccn_at_max": nccn_raw == analyzer.NCCN_MAX,
                "nccn_above_max": nccn_raw > analyzer.NCCN_MAX,
            },
            "threshold_masks": {
                "keep_qc": True,
                "keep_qi": True,
                "keep_qr": True,
                "keep_qs": True,
                "keep_qg": True,
            },
            "final_dsd_before_absolute_cap": {
                "nc_snap_gate": True,
                "nc_snap_changed": False,
                "nc_at_absolute_max": False,
                "nc_absolute_cap_would_apply": False,
            },
        }
        stage_values = {
            "micro_entry": {k: entry[k] for k in ("t", "qv", "qc", "nc", "nccn")},
            "post_state_update": {k: entry[k] for k in ("t", "qv", "qc", "nc", "nccn")},
            "post_reclass_ice": {k: entry[k] for k in ("t", "qv", "qc", "nc", "nccn")},
            "post_reclass_rain": {k: entry[k] for k in ("t", "qv", "qc", "nc", "nccn")},
            "post_threshold": {
                "t": t_final, "qv": qv_final, "qc": qc_final,
                "nc": nc_final, "nccn": nccn_final,
            },
            "post_final_dsd": {
                "t": t_final, "qv": qv_final, "qc": qc_final,
                "nc": nc_final, "nccn": nccn_final,
            },
            "activation_entry": entry,
            "activation_fraction": {
                "qs1_safe": max(entry["qs1"], analyzer.QCRMIN),
                "sw_percent": sw,
                "sw_ratio": ratio,
                "activated_fraction": frac,
            },
            "activation_pre_gate": {"ncact_raw": ncact_raw, "ncact_capped": ncact_cap},
            "activation_gated": {"ncact": ncact, "pcact_raw": pcact_raw, "pcact": pcact},
            "post_activation": {
                "qv_pp_raw": qv_pp_raw, "qv_pp": qv_pp, "qc_pp": qc_pp,
                "t_pp": t_pp, "nc_pp": nc_pp, "nccn_pp": nccn_pp,
                "qs1_pp": entry["qs1"],
            },
            "post_satadj": {
                "qv_final": qv_final, "qc_final": qc_final, "t_final": t_final,
                "nc_final": nc_final, "nccn_final_raw": nccn_raw,
                "nccn_final": nccn_final, "nc_evap_amount": 0.0, "pcond": 0.0,
            },
            "final_dsd_before_absolute_cap": {
                "nc_before": nc_final, "nc_snapped": nc_final, "nc_gated": nc_final,
                "ncmin": 100.0, "nc_at_max": 1.0,
            },
        }
        bool_arrays = {}
        for stage, (_, bool_fields) in analyzer.STAGE_FIELDS.items():
            if not bool_fields:
                continue
            bool_arrays[stage] = {}
            for field in bool_fields:
                arr = np.zeros((analyzer.BATCH, analyzer.LEVELS), dtype=bool)
                for level in analyzer.TRACE_LEVELS:
                    arr[analyzer.TRACE_ROW, level] = bool_values[stage][field]
                changed_bit = extra_mask_bit if call == 1 else second_call_extra_bit
                if changed_bit == (stage, field):
                    arr[7, 8] = True
                elif (
                    isinstance(changed_bit, tuple)
                    and len(changed_bit) == 4
                    and changed_bit[:2] == (stage, field)
                ):
                    row0, level = changed_bit[2:]
                    arr[row0, level] = not arr[row0, level]
                bool_arrays[stage][field] = arr

        for stage in analyzer.REQUIRED_STAGES:
            floats, bools = analyzer.STAGE_FIELDS[stage]
            for field in sorted(floats):
                for level in analyzer.TRACE_LEVELS:
                    value = stage_values[stage][field]
                    records.append([call, stage, analyzer.TRACE_ROW, level, dt, field, "f64", value])
            for field in sorted(bools):
                arr = bool_arrays[stage][field]
                for level in analyzer.TRACE_LEVELS:
                    records.append([call, stage, analyzer.TRACE_ROW, level, dt, field, "bool", int(arr[analyzer.TRACE_ROW, level])])
                packed = np.packbits(arr.reshape(-1).astype(np.uint8), bitorder="little").tobytes()
                records.append([call, stage, -1, -1, dt, field, "bits", packed.hex()])

        for row0 in range(-1, analyzer.BATCH):
            main = 3 if row0 == -1 else 1 + row0 % 3
            ice = 2 if row0 == -1 else 1 + row0 % 2
            records.append([call, "schedule", row0, -1, dt, "mstepmax_main" if row0 == -1 else "mstep_main", "f64", main])
            records.append([call, "schedule", row0, -1, dt, "mstepmax_ice" if row0 == -1 else "mstep_ice", "f64", ice])

    stream = io.StringIO()
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerow(analyzer.HEADER)
    writer.writerows(records)
    return stream.getvalue().encode()


def _inputs(tmp_path: Path, *, trace_bytes=None, receipt=None):
    trace = tmp_path / "trace.tsv"
    trace.write_bytes(_fixture() if trace_bytes is None else trace_bytes)
    source_receipt = tmp_path / "source_receipt.json"
    source_receipt.write_text(json.dumps(_receipt() if receipt is None else receipt))
    return trace, source_receipt


def test_reader_analyzer_validates_full_b512_schedule_and_replays_captured_rates(tmp_path):
    trace, receipt = _inputs(tmp_path)
    parsed = analyzer.read_trace(trace, receipt)
    report = analyzer.analyze_trace(parsed)
    assert parsed["trace_name"] == "trace.tsv"
    assert report["trace"]["source_receipt"]["name"] == "source_receipt.json"
    assert len(report["calls"]) == 1
    assert report["required_stages"][0] == "micro_entry"
    assert report["required_stages"].index("activation_entry") < report["required_stages"].index("post_satadj")
    call = report["calls"][0]
    assert call["schedule"]["mstepmax_main"] == 3
    assert call["schedule"]["mstepmax_ice"] == 2
    assert call["schedule"]["mstep_main_counts"] == {"1": 171, "2": 171, "3": 170}
    target = next(row for row in call["targets"] if row["level_bottom0"] == 17)
    assert target["source_formula_replay"]["formula_values"]["ncact"] == pytest.approx(5.0e6)
    assert target["stage_values"]["post_activation"]["nccn_pp"] == 0.0
    assert target["stage_values"]["post_satadj"]["nccn_final"] == analyzer.NCCN_MIN
    ledger = target["NC_plus_NCCN_coordinate_ledger"]
    assert ledger["nccn_clamp_add_coordinate"] == analyzer.NCCN_MIN
    assert "not certified" in ledger["coordinate_scope"]
    activation_pair = ledger["activation_rate_transfer_and_residuals"]
    assert activation_pair["signed_transfer_amount"] == pytest.approx(1.0e8)
    assert activation_pair["species_delta_fsum"] == pytest.approx(0.0)
    assert activation_pair["donor_delta_plus_transfer_residual"] == pytest.approx(0.0)
    assert activation_pair["receiver_delta_minus_transfer_residual"] == pytest.approx(0.0)
    assert set(activation_pair["species_rate_transfer_residuals"]) == {"NC", "NCCN"}
    assert activation_pair["species_rate_transfer_residuals"]["NC"] == pytest.approx(0.0)
    assert activation_pair["species_rate_transfer_residuals"]["NCCN"] == pytest.approx(0.0)
    assert "not a physical" in ledger["pair_accounting_limit"]
    for key in ("activation_pcact_mass_pair_and_residuals_kg_kg", "satadj_pcond_mass_pair_and_residuals_kg_kg"):
        assert "species_delta_fsum" in ledger[key]
    assert target["state_replay_using_captured_rates_and_operands"]["captured_vs_recomputed"]["post_activation"]["nc_pp"]["exact_equal"]
    assert target["captured_branch_flag_checks"]["all_recomputed_flags_match"]
    assert target["captured_branch_flag_checks"]["not_recomputed_due_to_missing_state_operands"] == [
        "threshold_masks.keep_qi", "threshold_masks.keep_qr",
        "threshold_masks.keep_qs", "threshold_masks.keep_qg",
    ]
    assert call["branch_masks"]["activation_fraction"]["sw_positive"]["true_cells"] == 4


def test_reader_rejects_bool_sample_that_disagrees_with_full_mask(tmp_path):
    bad = _fixture().decode()
    bad = bad.replace("1\tactivation_fraction\t368\t17\t20.0\tsw_positive\tbool\t1\n", "1\tactivation_fraction\t368\t17\t20.0\tsw_positive\tbool\t0\n", 1)
    trace, receipt = _inputs(tmp_path, trace_bytes=bad.encode())
    with pytest.raises(analyzer.TraceError, match="disagrees with full mask"):
        analyzer.read_trace(trace, receipt)


@pytest.mark.parametrize(
    "mutate,pattern",
    [
        (lambda text: text + text.splitlines()[1] + "\n", "duplicate trace record"),
        (lambda text: text.replace("\t20.0\t", "\t21.0\t", 1), "dt_s differs"),
        (lambda text: text.replace("mstepmax_main\tf64\t3", "mstepmax_main\tf64\t2", 1), "schedule maximum"),
        (lambda text: text.replace("micro_entry\t368\t18", "micro_entry\t368\t19", 1), "sample must be row"),
    ],
)
def test_reader_rejects_duplicate_dt_schedule_and_coordinate_mutations(tmp_path, mutate, pattern):
    bad = mutate(_fixture().decode()).encode()
    trace, receipt = _inputs(tmp_path, trace_bytes=bad)
    with pytest.raises(analyzer.TraceError, match=pattern):
        analyzer.read_trace(trace, receipt)


def test_compare_branches_counts_changed_cells_and_recorded_ties(tmp_path):
    base_trace, receipt = _inputs(tmp_path)
    probe_path = tmp_path / "probe.tsv"
    probe_path.write_bytes(_fixture(extra_mask_bit=("activation_fraction", "sw_positive")))
    base = analyzer.read_trace(base_trace, receipt)
    probe = analyzer.read_trace(probe_path, receipt)
    compared = analyzer.compare_branches(base, probe)
    row = next(item for item in compared["calls"][0]["mask_changes"] if item["stage"] == "activation_fraction" and item["field"] == "sw_positive")
    assert row["changed_cells"] == 1
    assert row["target_row_changed_levels"] == []
    assert row["base_true_target_levels"] == [4, 16, 17, 18]
    assert row["probe_true_target_levels"] == [4, 16, 17, 18]
    assert "not complete" in compared["scope"]


def test_compare_call_pair_reads_baseline_and_probe_from_one_trace(tmp_path):
    trace, receipt = _inputs(
        tmp_path,
        trace_bytes=_fixture(
            second_call=True,
            second_call_extra_bit=("activation_fraction", "sw_positive"),
        ),
    )
    parsed = analyzer.read_trace(trace, receipt)
    compared = analyzer.compare_call_pair(parsed, 1, 2)
    row = next(item for item in compared["calls"][0]["mask_changes"] if item["stage"] == "activation_fraction" and item["field"] == "sw_positive")
    assert compared["base_call"] == 1
    assert compared["probe_call"] == 2
    assert row["changed_cells"] == 1


def test_compare_cross_file_calls_with_different_ordinals_and_target_level_change(tmp_path):
    base_trace, receipt = _inputs(
        tmp_path,
        trace_bytes=_fixture(second_call=True),
    )
    probe_path = tmp_path / "probe.tsv"
    probe_path.write_bytes(
        _fixture(
            second_call=True,
            extra_mask_bit=("activation_fraction", "sw_positive", analyzer.TRACE_ROW, 4),
        )
    )
    base = analyzer.read_trace(base_trace, receipt)
    probe = analyzer.read_trace(probe_path, receipt)
    compared = analyzer.compare_trace_calls(base, 2, probe, 1)
    row = next(item for item in compared["calls"][0]["mask_changes"] if item["stage"] == "activation_fraction" and item["field"] == "sw_positive")
    assert compared["base_call"] == 2
    assert compared["probe_call"] == 1
    assert compared["base_trace"]["trace_sha256"] == base["trace_sha256"]
    assert compared["probe_trace"]["trace_sha256"] == probe["trace_sha256"]
    assert row["changed_cells"] == 1
    assert row["target_row_changed_levels"] == [4]
    assert row["base_true_target_levels"] == [4, 16, 17, 18]
    assert row["probe_true_target_levels"] == [16, 17, 18]


def test_receipt_and_new_output_path_are_pinned_and_no_clobber(tmp_path):
    bad_receipt = _receipt()
    bad_receipt["coordinator_sha256"] = "0" * 64
    trace, receipt = _inputs(tmp_path, receipt=bad_receipt)
    with pytest.raises(analyzer.TraceError, match="coordinator_sha256"):
        analyzer.read_trace(trace, receipt)
    output = tmp_path / "report.json"
    output.write_text("prior")
    with pytest.raises(FileExistsError, match="must be new"):
        analyzer._write_new(output, {"schema": "test"})


def test_compare_requires_exact_dt_pairing_and_cli_preflights_output(tmp_path):
    base_path, receipt = _inputs(tmp_path)
    probe_path = tmp_path / "probe.tsv"
    probe = _fixture().decode().replace("\t20.0\t", "\t21.0\t")
    probe_path.write_text(probe)
    base = analyzer.read_trace(base_path, receipt)
    changed = analyzer.read_trace(probe_path, receipt)
    with pytest.raises(analyzer.TraceError, match="dt_s differs"):
        analyzer.compare_branches(base, changed)

    output = tmp_path / "already-there.json"
    output.write_text("preserve")
    with pytest.raises(FileExistsError, match="must be new"):
        analyzer.main([
            "--trace", str(tmp_path / "missing.tsv"),
            "--receipt", str(receipt),
            "--output", str(output),
        ])


def test_replay_comparison_distinguishes_numeric_zero_from_signed_zero():
    result = analyzer._field_residuals({"value": -0.0}, {"value": 0.0})
    assert result["value"]["exact_equal"]
    assert not result["value"]["same_binary64_bits"]
    assert result["value"]["captured_signbit"]
    assert not result["value"]["recomputed_signbit"]
