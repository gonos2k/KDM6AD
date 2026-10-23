"""Public arithmetic/coverage replay, not a private KDM or host execution."""

from fractions import Fraction
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from harness.analyze_domain_ice_factorial import distribution

EVIDENCE = Path(__file__).parents[1] / "evidence/domain_ice_factorial_2026-10-23"
MODES = ("raw_cap", "norm_cap", "raw_actual", "norm_actual")


def test_all_516_receipts_cover_the_same_fixed_native_packet():
    receipts = json.loads((EVIDENCE / "chunk_receipts.json").read_text())["receipts"]
    summary = json.loads((EVIDENCE / "execution_summary.json").read_text())
    assert len(receipts) == summary["calls"] == 516
    assert summary["pilot_calls"] == 4
    assert summary["model_host_steps"] == summary["observation_calls"] == 0
    for mode in MODES:
        arm = [r for r in receipts if r["mode"] == mode]
        assert len(arm) == 129
        for index, receipt in enumerate(arm):
            assert receipt["index"] == index
            assert receipt["start_flat"] == index * 512
            assert receipt["stop_flat_exclusive"] == min((index + 1) * 512, 65988)
            assert receipt["B"] == (452 if index == 128 else 512)
            assert receipt["L"] == 39 and receipt["dt_seconds"] == 20
            assert receipt["ncmin_land"] == receipt["ncmin_sea"] == 10
            assert receipt["manifest_sha256"] == summary["manifest_sha256"]
            assert (
                receipt["tool_sha256"]
                == receipt["tool_sha256_after"]
                == summary["tool_sha256"]
            )
            assert receipt["status"] == "complete"
    for index in range(129):
        matched = [r for r in receipts if r["index"] == index]
        for key in ("request_sha256", "source_chunk_sha256", "tensor_sha256"):
            assert len({r[key] for r in matched}) == 1


@pytest.mark.parametrize("mode", MODES)
def test_full_column_statistics_and_gate_replay(mode):
    summary = json.loads((EVIDENCE / "analysis.json").read_text())["modes"][mode]
    with np.load(EVIDENCE / f"{mode}.columns.npz", allow_pickle=False) as columns:
        for name, expected in summary["statistics"].items():
            assert columns[name].shape == (65988,)
            assert distribution(columns[name]) == expected
        outside = (
            np.abs(columns["raw_plus_reported_precip_residual"])
            > columns["numerical_gate"]
        )
        assert int(outside.sum()) == summary["outside_diagnostic_balance_gate_columns"]
        assert summary["closed_water_budget_certified"] is False


def exact_rounded_products(difference, weights):
    terms = [
        Fraction.from_float(float(difference[field, k]) * float(weights[k]))
        for field in range(difference.shape[0])
        for k in range(39)
    ]
    return float(sum(terms, Fraction()))


@pytest.mark.parametrize("mode", MODES)
def test_selected_actual_batch_slices_reproduce_species_budgets(mode):
    with np.load(EVIDENCE / "selected_columns.npz", allow_pickle=False) as sample:
        state = sample[mode + "_state_in"]
        forcing = sample[mode + "_forcing_in"]
        raw = sample[mode + "_state_out"]
        precip = sample[mode + "_precip"]
        indices = sample["flat_indices"]
        clean = raw.copy()
        clean[1] = np.maximum(raw[1], 0.0)
        clean[2:7] = np.where(raw[2:7] < 9.99999993922529e-9, 0.0, raw[2:7])
        with np.load(EVIDENCE / f"{mode}.columns.npz", allow_pickle=False) as columns:
            for j, flat in enumerate(indices):
                weights = forcing[0, j] * forcing[3, j]
                for key, diff in (
                    ("raw_water_change", raw[1:7, j] - state[1:7, j]),
                    ("cleanup_water_change", clean[1:7, j] - raw[1:7, j]),
                    ("applied_water_change", clean[1:7, j] - state[1:7, j]),
                ):
                    assert exact_rounded_products(diff, weights) == columns[key][flat]
                assert precip[0, j] == columns["reported_total_precip_mm"][flat]
                assert precip[1, j] == columns["snow_ice_subset_mm"][flat]
                assert precip[2, j] == columns["graupel_subset_mm"][flat]


def test_evidence_and_reviewed_source_hash_inventory():
    manifest = json.loads((EVIDENCE / "manifest.json").read_text())
    root = EVIDENCE.parents[2]
    for group in ("source_sha256", "artifact_sha256"):
        assert manifest[group]
        for relative, expected in manifest[group].items():
            assert (
                hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected
            ), relative
    executed = EVIDENCE / "execution_sources/run_domain_ice_factorial.py.txt"
    assert (
        hashlib.sha256(executed.read_bytes()).hexdigest()
        == manifest["executed_runner_sha256"]
    )
