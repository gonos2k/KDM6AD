import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from replay_s3_applied_face_budget import EVIDENCE, replay


def test_actual_five_cell_baseline_and_applied_rounding_ledger():
    result = replay(EVIDENCE.read_text())
    assert result["capture_sha256"] == "848eae8889159d880640134581f29b3e830638cfb5f68cd6c3219ae3969747dd"
    assert [c["before_bits"] for c in result["cells"]] == [
        "BAEC299F", "495954F4", "4543A4F3", "47EEE329", "4C13B223"]
    assert result["cells"][0]["after_bits"] == "3C35A32B"
    assert all(c["before_bits"] == c["after_bits"] for c in result["cells"][1:])
    assert all(f["residual"] == 0 for f in result["internal_faces"])
    assert result["external_xR"] == pytest.approx(0.17786327007619562)
    assert result["rounded_numerator_change"] == pytest.approx(56.4597924237205)
    assert result["stored_inventory_change"] == pytest.approx(56.45979023574415)
    assert result["change_in_divergence_and_RK_rounding"] > 56.0
    assert not result["native_candidate_executed"]
    assert not result["physical_number_basis_resolved"]
    assert not result["operational_fix_applied"]


@pytest.mark.parametrize("duplicate", [False, True])
def test_fixed_event_roster_rejects_missing_or_duplicate_axis(duplicate):
    lines = EVIDENCE.read_text().splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith("S3QNAX"))
    if duplicate:
        lines.append(lines[index])
    else:
        lines.pop(index)
    with pytest.raises(ValueError, match="duplicate|incomplete"):
        replay("\n".join(lines))


def test_replay_rejects_changed_recorded_rk_store():
    lines = EVIDENCE.read_text().splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith("S3QNRK"))
    words = lines[index].split()
    words[-1] = "00000000"
    lines[index] = " ".join(words)
    with pytest.raises(ValueError, match="baseline does not replay"):
        replay("\n".join(lines))
