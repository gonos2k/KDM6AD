"""Measured opt-in host stores; no operational or unit approval."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from replay_conservative_native import EVIDENCE, replay


def test_measured_native_stores_and_paired_transfer():
    result = replay(json.loads(EVIDENCE.read_text()))
    assert not result["operational_fix_applied"]
    case = result["cases"][1]
    interface = next(r for r in case["rows"] if r["native_k"] == 23)["ni"]
    assert interface["arrival_source_order_reconstructed"] == 432432.1875
    for case in result["cases"]:
        for b in case["budgets"].values():
            scale = (
                b["internal_departure"] + b["internal_arrival"] + b["bottom_outflow"]
            )
            assert (
                abs(b["balance_residual"]) <= 1e-14 * scale
                if scale
                else b["balance_residual"] == 0
            )
            if b["internal_departure"]:
                # Conditional f32 transfer measure, not physical unit certification.
                assert abs(b["relative_interface_mismatch"]) < 16 * 2**-23


@pytest.mark.parametrize(
    "fault",
    ["missing", "post", "upper", "nan", "approval", "invalid_run", "changed_source"],
)
def test_incomplete_or_changed_measured_evidence_is_rejected(fault):
    data = copy.deepcopy(json.loads(EVIDENCE.read_text()))
    row = next(
        r
        for r in data["records"]
        if r["step"] == 2 and r["native_k"] == 23 and r["stage"] == "after"
    )
    if fault == "missing":
        data["records"].pop()
    elif fault == "post":
        row["ni"] += 1
    elif fault == "upper":
        row["upper_departure_ni"] = 0
    elif fault == "nan":
        row["qi"] = float("nan")
    elif fault == "invalid_run":
        data["provenance"]["capture_valid"]["experiment_valid"] = False
    elif fault == "changed_source":
        data["provenance"]["source_capture_stripped_exact"] = False
    else:
        data["operational_fix_applied"] = True
    with pytest.raises(AssertionError):
        replay(data)
