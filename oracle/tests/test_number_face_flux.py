import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[2] / "harness"
sys.path.insert(0, str(HARNESS))

from replay_number_face_flux import (  # noqa: E402
    EVIDENCE,
    HISTORY,
    replay,
    scaled_faces,
)


@pytest.fixture(scope="module")
def evidence():
    return json.loads(EVIDENCE.read_text())


def _flux_row(data, variant, tag, step=1, target=1):
    return next(
        row
        for row in data["variants"][variant]["flux"]
        if row[0] == tag and row[1] == step and row[5] == target
    )


def test_replays_both_captured_variants(evidence):
    result = replay(evidence)

    assert result["scope"] == "arithmetic_replay_only"
    assert result["operational_fix_applied"] is False
    assert result["positivity_approved"] is False
    assert result["accepted_observation_cost"] is False
    assert result["variants"]["original"]["face_values"] == 192
    assert result["variants"]["original"]["directional_stores"] == 96
    assert result["variants"]["original"]["host_updates"] == 128
    assert result["variants"]["original"]["final_negative_counts"] == {
        "QNCLOUD": 4,
        "QNRAIN": 4,
        "QNICE": 3,
    }
    assert result["variants"]["normalized"]["final_negative_counts"] == {
        "QNCLOUD": 4,
        "QNRAIN": 1,
        "QNICE": 4,
    }


def test_z_faces_use_opposite_outflow_signs_and_the_matching_donor_budget():
    invalid = (0, 0.0, 0.0)
    budgets = [(1, 100.0, 100.0)] + [invalid] * 6
    budgets[5] = (1, 1.0, 2.0)  # bottom neighbor for inward negative bottom flux
    budgets[6] = (1, 3.0, 4.0)  # top neighbor for inward positive top flux

    bottom_in_top_in = scaled_faces([0.0, 0.0, 0.0, 0.0, -10.0, 20.0], budgets, 1.0e-6)
    bottom_out_top_out = scaled_faces(
        [0.0, 0.0, 0.0, 0.0, 10.0, -20.0], budgets, 1.0e-6
    )

    assert bottom_in_top_in[4] == pytest.approx(-5.0, rel=1e-6)
    assert bottom_in_top_in[5] == pytest.approx(15.0, rel=1e-6)
    assert bottom_out_top_out[4:] == [10.0, -20.0]


def test_missing_flux_phase_is_rejected(evidence):
    data = copy.deepcopy(evidence)
    data["variants"]["original"]["flux"] = [
        row for row in data["variants"]["original"]["flux"] if row[0] != "Z"
    ]

    with pytest.raises(AssertionError):
        replay(data)


def test_missing_donor_is_rejected(evidence):
    data = copy.deepcopy(evidence)
    data["variants"]["normalized"]["flux"] = [
        row for row in data["variants"]["normalized"]["flux"] if row[5] != 1
    ]

    with pytest.raises(AssertionError):
        replay(data)


def test_missing_summary_is_rejected(evidence):
    data = copy.deepcopy(evidence)
    data["variants"]["original"]["summaries"].pop()

    with pytest.raises(AssertionError):
        replay(data)


@pytest.mark.parametrize("record_kind", ["RK_OPERAND", "TRANSITION"])
def test_missing_event_is_rejected(evidence, record_kind):
    data = copy.deepcopy(evidence)
    events = data["variants"]["original"]["events"]
    index = next(i for i, row in enumerate(events) if row["record_kind"] == record_kind)
    events.pop(index)

    with pytest.raises(AssertionError):
        replay(data)


def test_mismatched_pre_post_face_row_is_rejected(evidence):
    data = copy.deepcopy(evidence)
    _flux_row(data, "original", "POST")[9] += 1.0

    with pytest.raises(AssertionError):
        replay(data)


def test_wrong_z_face_sign_is_rejected(evidence):
    data = copy.deepcopy(evidence)
    post = _flux_row(data, "original", "POST", step=2)
    assert post[31] != 0.0
    post[31] *= -1.0  # top z face in the recorded six-face segment

    with pytest.raises(AssertionError):
        replay(data)


def test_wrong_host_y_store_is_rejected(evidence):
    data = copy.deepcopy(evidence)
    y = _flux_row(data, "original", "Y", step=2, target=1)
    y[11] += 1.0  # tendency: vector offset 2 after the nine row identifiers

    with pytest.raises(AssertionError):
        replay(data)


def test_nonfinite_capture_is_rejected(evidence):
    data = copy.deepcopy(evidence)
    data["variants"]["original"]["flux"][0][9] = float("nan")

    with pytest.raises(AssertionError, match="nonfinite evidence"):
        replay(data)


def test_wrong_variant_history_proof_is_rejected(evidence):
    data = copy.deepcopy(evidence)
    data["variants"]["normalized"]["noninterference"]["capture_history_sha256"] = (
        HISTORY["original"]
    )

    with pytest.raises(AssertionError):
        replay(data)


def test_approval_claim_is_rejected(evidence):
    data = copy.deepcopy(evidence)
    data["positivity_approved"] = True

    with pytest.raises(AssertionError):
        replay(data)


def test_assertions_must_remain_enabled():
    code = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(HARNESS)!r})\n"
        "from replay_number_face_flux import EVIDENCE, replay\n"
        "try:\n"
        "    replay(json.loads(EVIDENCE.read_text()))\n"
        "except RuntimeError as exc:\n"
        "    print('guarded' if 'assertions must remain enabled' in str(exc) else 'wrong')\n"
        "else:\n"
        "    print('unguarded')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-O", "-c", code], capture_output=True, text=True, check=True
    )

    assert completed.stdout.strip() == "guarded"


@pytest.mark.parametrize(
    "kind,field",
    [
        ("summary", "selected"),
        ("transition", "selected"),
        ("transition", "rank"),
        ("transition", "species"),
    ],
)
def test_scan_provenance_labels_are_checked(evidence, kind, field):
    data = copy.deepcopy(evidence)
    variant = data["variants"]["original"]
    row = (
        variant["summaries"][0]
        if kind == "summary"
        else next(e for e in variant["events"] if e["record_kind"] == "TRANSITION")
    )
    row[field] += 100
    with pytest.raises(AssertionError):
        replay(data)
