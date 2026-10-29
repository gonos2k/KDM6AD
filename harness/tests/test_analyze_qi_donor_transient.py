from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from harness.analyze_qi_donor_transient import PACKET, analyze


def _mutated_packet(tmp_path, replacements: dict[str, str]):
    packet = tmp_path / "packet"
    shutil.copytree(PACKET, packet, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    trace = packet / "data/alpha025/qi_donor.tsv"
    lines = trace.read_text().splitlines()
    for original, replacement in replacements.items():
        assert lines.count(original) == 1
        lines[lines.index(original)] = replacement
    trace.write_text("\n".join(lines) + "\n")

    receipt_path = packet / "execution_summary.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["runs"]["alpha025"]["on"]["trace_sha256"]["qi_donor"] = (
        hashlib.sha256(trace.read_bytes()).hexdigest())
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return packet


def test_saved_qi_donor_analysis_reproduces_published_bytes():
    expected = json.loads((PACKET / "analysis.json").read_text())
    assert analyze() == expected


def test_boundary_donor_word_cannot_change_independently_of_target(tmp_path):
    original = "VAL 3 3 QI_BDY_INPUT 2 33 168 QI 00000002"
    replacement = "VAL 3 3 QI_BDY_INPUT 2 33 168 QI 00000000"
    packet = _mutated_packet(tmp_path, {original: replacement})
    with pytest.raises(ValueError, match="QI donor boundary input disagrees"):
        analyze(packet)


def test_earlier_donor_word_divergence_cannot_be_reported_as_rk3_output(tmp_path):
    packet = _mutated_packet(tmp_path, {
        "VAL 3 3 QI_TEND_BEFORE 2 33 168 QI 80000000":
            "VAL 3 3 QI_TEND_BEFORE 2 33 168 QI 00000001",
        "VAL 3 3 QI_TEND_AFTER 2 33 168 QI 80000000":
            "VAL 3 3 QI_TEND_AFTER 2 33 168 QI 00000001",
    })
    with pytest.raises(ValueError, match="donor QI diverged before RK3 update"):
        analyze(packet)


def test_same_boundary_branch_claim_requires_same_wind_word(tmp_path):
    packet = _mutated_packet(tmp_path, {
        "VAL 3 3 QI_BDY_INPUT 1 33 168 RU_M C7B997A8":
            "VAL 3 3 QI_BDY_INPUT 1 33 168 RU_M BF800000",
    })
    with pytest.raises(ValueError, match="QI boundary wind word differs"):
        analyze(packet)
