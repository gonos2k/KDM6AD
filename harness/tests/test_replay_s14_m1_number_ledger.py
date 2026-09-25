import copy
import hashlib
import json
from pathlib import Path

import pytest

from harness.replay_s2_number_trace import TraceError, parse_capture
from harness.replay_s14_m1_number_ledger import (
    EXPECTED_MSTEP_BY_STEP,
    _verify_branch_event_census,
    replay,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/native_s14_m1_number_transfer_2026-09-25.json"
CAPTURE = ROOT / "evidence/native_s14_m1_number_transfer_2026-09-25.txt"


@pytest.fixture(scope="module")
def bundle():
    return json.loads(EVIDENCE.read_text()), CAPTURE.read_text()


def test_matched_600s_mp37_ledger_replays_and_keeps_basis_open(bundle):
    evidence, text = bundle
    result = replay(evidence, text)

    assert result["physical_number_basis_resolved"] is False
    assert result["capture_records"] == 25235
    assert result["host_kernel_boundary"]["steps"] == 30
    assert result["host_kernel_boundary"]["host_entry_layers"] == 1170
    assert result["host_kernel_boundary"]["entry_negative_clamps"] == {
        "nr": 3, "qr": 1, "qc": 13}
    assert result["transport_groups"] == 95
    assert result["active_interface_occurrences"] == 1480
    assert {step: {g["mstep"] for g in result["transport_ledgers_by_group"]
                   if g["step"] == step}
            for step in EXPECTED_MSTEP_BY_STEP} == {
        step: {mstep} for step, mstep in EXPECTED_MSTEP_BY_STEP.items()}
    assert all(g["internal_faces"] == 38 and g["levels"] == 39
               for g in result["transport_ledgers_by_group"])
    assert result["direct_source_events"]["counts"] == {
        "snow_melt": 48, "graupel_melt": 4, "rain_freeze_sink": 1}
    assert result["nraut_checks"]["positive_rate_records"] == 0
    assert len(result["intercall_dynamics_remainders"]) == 29
    assert max(abs(x["call_ledger_closure_raw"])
               for x in result["within_call_process_ledgers"]) < 1e-9

    grouped = result["transport_ledgers_by_group"]
    dz = sum(x["measures"]["dz_n"]["observed"] for x in grouped)
    moist = sum(x["measures"]["rho_m_dz_n"]["observed"] for x in grouped)
    dry = sum(x["measures"]["rho_d_dz_n"]["observed"] for x in grouped)
    assert dz == pytest.approx(-0.007950696539468333, rel=0, abs=1e-12)
    assert moist == pytest.approx(113405.2205961411, rel=0, abs=1e-8)
    assert dry == pytest.approx(110211.75141521676, rel=0, abs=1e-8)
    for measure in ("dz_n", "rho_m_dz_n", "rho_d_dz_n"):
        assert sum(x["measures"][measure]["cap_unmatched"] for x in grouped) == 0
        assert sum(x["measures"][measure]["ledger_closure"]
                   - x["measures"][measure]["source_ordered_store_rounding"]
                   for x in grouped) == pytest.approx(0.0, rel=0, abs=1e-8)


def test_deleted_face_cannot_be_hidden_by_updating_manifest_sha(bundle):
    evidence, text = bundle
    changed = "".join(line for line in text.splitlines(keepends=True)
                      if not (line.startswith("S2NR NR_FACE_PRE 30 ")
                              and int(line.split()[7]) <= 6))
    altered = copy.deepcopy(evidence)
    altered["capture"]["sha256"] = hashlib.sha256(changed.encode()).hexdigest()
    altered["capture"]["records"] -= sum(
        line.startswith("S2NR NR_FACE_PRE 30 ")
        and int(line.split()[7]) <= 6 for line in text.splitlines())

    with pytest.raises(TraceError, match="capture payload SHA"):
        replay(altered, changed)


def test_same_count_event_outside_600s_schedule_is_rejected(bundle):
    evidence, text = bundle
    lines = text.splitlines()
    index = next(i for i, line in enumerate(lines)
                 if line.startswith("S2NR DSD_PRE_GATE 30 "))
    parts = lines[index].split()
    parts[2] = "31"
    lines[index] = " ".join(parts)
    changed = "\n".join(lines) + "\n"
    altered = copy.deepcopy(evidence)
    altered["capture"]["sha256"] = hashlib.sha256(changed.encode()).hexdigest()

    with pytest.raises(TraceError, match="capture payload SHA"):
        replay(altered, changed)


def test_late_mstep_group_face_deletion_is_rejected(bundle):
    evidence, text = bundle
    changed = "".join(line for line in text.splitlines(keepends=True)
                      if not (line.startswith("S2NR NR_FACE_PRE 30 ")
                              and int(line.split()[6]) == 3
                              and int(line.split()[7]) == 38))
    altered = copy.deepcopy(evidence)
    altered["capture"]["sha256"] = hashlib.sha256(changed.encode()).hexdigest()

    with pytest.raises(TraceError, match="capture payload SHA"):
        replay(altered, changed)


def test_warm_update_branch_cannot_be_relocated_into_cold_levels(bundle):
    evidence, text = bundle
    lines = text.splitlines()
    index = next(i for i, line in enumerate(lines)
                 if line.startswith("S2NR NR_UPDATE_WARM_PRE 30 ")
                 and int(line.split()[7]) == 39)
    parts = lines[index].split()
    parts[7] = "15"
    lines[index] = " ".join(parts)
    s2_manifest = json.loads(
        (ROOT / "evidence/native_s2_number_trace_2026-09-25.json").read_text())
    rows = parse_capture("\n".join(lines) + "\n",
                         s2_manifest["capture_source"]["tags"],
                         allowed_steps=range(1, 31))

    with pytest.raises(TraceError, match="warm branch event census"):
        _verify_branch_event_census(rows)
