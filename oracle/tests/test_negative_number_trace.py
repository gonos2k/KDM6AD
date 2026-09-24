import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from replay_negative_number_trace import EVIDENCE, fma32, replay
from replay_native_number import f32


def test_fma_witness_avoids_binary64_double_rounding():
    a = 1 + 2**-23
    assert fma32(a, 1.5, -(2**-100)) == 1.5 + 2**-23
    assert f32(a * 1.5 - 2**-100) == 1.5 + 2**-22


def test_fma_witness_preserves_subnormal_and_ties_to_even():
    assert fma32(2**-126, 2**-23, 0.0) == 2**-149
    assert fma32(2**-126, 2**-24, 0.0) == 0.0


def test_captured_updates_and_copy_chain():
    data = json.loads(EVIDENCE.read_text())
    result = replay(data)
    assert (result["rk_updates_exact"], result["pd_updates_exact"]) == (132, 44)
    assert len(result["chains"]) == 11
    assert result["chains"][8]["first_negative_rk"] == 1
    # Chronology comes from step/stage keys, not JSON storage order.
    data["records"].reverse()
    assert replay(data) == result


@pytest.mark.parametrize(
    "fault", ["missing_pd", "advective_sign", "inflow_sign", "history"]
)
def test_corrupted_causal_evidence_is_rejected(fault):
    data = copy.deepcopy(json.loads(EVIDENCE.read_text()))

    def row(stage, target):
        return next(
            r
            for r in data["records"]
            if (r["stage"], r["step"], r["rk"], r["target"]) == (stage, 2, 3, target)
        )

    if fault == "missing_pd":
        data["records"].remove(row("PD_BEFORE", 14))
    elif fault == "advective_sign":
        row("RK_BEFORE", 14)["advect_tend"] *= -1
    elif fault == "inflow_sign":
        row("FLOW_DEP_BDY_BEFORE", 3)["sc_tend"] *= -1
    else:
        data["history_targets"][2]["value"] = 0.0
    with pytest.raises(AssertionError):
        replay(data)
