"""Fixed-work temporal and layerwise derivative witnesses, not forecast scores."""

import json
import math
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from replay_ice_time_accuracy import EVIDENCE, inventory_reference, run


@pytest.fixture(scope="module")
def measured():
    return run(json.loads(EVIDENCE.read_text()))


def test_two_cell_reference_has_known_inventory_and_sink():
    rate = torch.tensor([1.0, 1.0], dtype=torch.float64)
    initial = torch.tensor([1.0, 0.0], dtype=torch.float64)
    r = inventory_reference(rate, initial, 1.0)
    expected = torch.tensor(
        [math.exp(-1), math.exp(-1), 1 - 2 * math.exp(-1)], dtype=torch.float64
    )
    torch.testing.assert_close(r["matrix"], expected, rtol=2e-15, atol=2e-16)
    torch.testing.assert_close(r["series"], expected, rtol=2e-15, atol=2e-16)
    assert r["tail"] <= 1e-17


def test_zero_rate_reference_is_stationary():
    initial = torch.tensor([2.0, 3.0], dtype=torch.float64)
    r = inventory_reference(torch.zeros_like(initial), initial, 20.0)
    assert torch.equal(r["matrix"], torch.tensor([2.0, 3.0, 0.0], dtype=torch.float64))
    assert torch.equal(r["matrix"], r["series"])


def test_fixed_final_time_distribution_and_conservation_are_separate(measured):
    assert measured["final_seconds"] == 20 and not measured["work_recomputed"]
    assert not measured["operational_fix_applied"]
    for field in ("ni", "qi"):
        errors = [r["fields"][field]["normalized_l1"] for r in measured["curves"]]
        assert all(a > b > 0 for a, b in zip(errors, errors[1:]))
        assert measured["references"][field]["normalized_difference"] < 1e-13
        for r in measured["curves"]:
            assert r["substep_seconds"] * r["substeps"] == 20
            assert r["fields"][field]["nonnegative"]
            assert abs(r["fields"][field]["relative_closure"]) < 1e-13
    # Large redistribution error is retained despite excellent total closure.
    assert 0.8 < measured["curves"][0]["fields"]["ni"]["normalized_l1"] < 0.82
    assert 0.003 < measured["curves"][-1]["fields"]["ni"]["normalized_l1"] < 0.004


def test_nonuniform_layer_jvp_uses_forward_mode_and_independent_difference(measured):
    d = measured["layer_derivatives"]
    assert d["method"] == "torch.func.jvp / torch.func.vjp"
    assert set(d["fields"]) == {"qi", "ni", "fall_qi", "fall_ni"}
    assert all(v["max_norm_relative"] < 1e-6 for v in d["fields"].values())
    assert abs(d["dual_residual"]) < 1e-13
