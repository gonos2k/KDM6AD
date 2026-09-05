"""Small, portable regressions for the PR208 evidence/build boundaries."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "g33_fortran"))

import gateb_g33m_check as gate  # noqa: E402
import g33_evidence_validate as ev  # noqa: E402
import g33_fortran_dump as fd  # noqa: E402
import g33_replay as replay  # noqa: E402
import g33_schedule_probe as schedule  # noqa: E402
import g33_update_replay as update  # noqa: E402


def test_schedule_uses_positive_nint_round_half_up():
    import struct

    def authority(dt):
        return {"common_parameters": {"dt": struct.pack(">f", dt).hex()}}

    assert schedule.step_schedule(authority(120.5))[0] == 1
    assert schedule.step_schedule(authority(180.0))[0] == 2


def test_malformed_probe_hex_is_a_probe_error():
    line = "KDM6SCHED 1 main 1 work1_qr f32 1 zzzzzzzz\n"
    with pytest.raises(schedule.ProbeError, match="payload"):
        schedule.parse_sched_stream(line)


def test_result_index_is_executable_and_current_null_is_explicit():
    index = gate.validate_result_index()
    assert index["current_decision_result"] is None


def test_invalid_evidence_cannot_become_decision_valid(tmp_path):
    out = tmp_path / "result.json"
    gate._write(out, {"verdict": "INVALID_EVIDENCE", "provenance": {},
                      "supersession": {"status": "current", "valid_for_decision": True}})
    assert out.exists()
    import json
    assert json.loads(out.read_text())["supersession"]["valid_for_decision"] is False


def test_unattested_candidate_cannot_become_decision_valid(tmp_path):
    out = tmp_path / "result.json"
    gate._write(out, {
        "verdict": "UNATTESTED_MECHANISM_CANDIDATE", "attested": False,
        "anchored": False, "decision_valid": False, "evidence_tier": "debug",
        "provenance": {},
        "supersession": {"status": "current", "valid_for_decision": True},
    })
    import json
    result = json.loads(out.read_text())
    assert result["supersession"]["valid_for_decision"] is False


def test_result_index_rejects_a_valid_bit_without_attested_contract(tmp_path):
    import json
    artifact = {
        "verdict": "UNATTESTED_MECHANISM_CANDIDATE", "attested": False,
        "supersession": {"status": "current", "superseded_by": None,
                          "valid_for_decision": True, "withdrawal_reason": None},
    }
    (tmp_path / "g33m_candidate_result.json").write_text(json.dumps(artifact))
    (tmp_path / "RESULT_INDEX.json").write_text(json.dumps({
        "index_schema_version": 1,
        "current_decision_result": "g33m_candidate_result.json",
        "superseded": [],
    }))
    with pytest.raises(ValueError, match="complete attested/anchored"):
        gate.validate_result_index(tmp_path / "RESULT_INDEX.json")


def test_result_index_rejects_a_retired_successor_when_a_current_result_exists(tmp_path):
    import json
    old = {"verdict": "INCONCLUSIVE", "attested": True,
           "anchored": True, "decision_valid": True, "evidence_tier": "decision",
           "supersession": {"status": "superseded", "superseded_by":
                             "g33m_withdrawn_result.json",
                             "valid_for_decision": False, "withdrawal_reason": None}}
    withdrawn = {"verdict": "INCONCLUSIVE", "attested": True,
                 "supersession": {"status": "withdrawn", "superseded_by": None,
                                   "valid_for_decision": False,
                                   "withdrawal_reason": "retired result"}}
    current = {"verdict": "INCONCLUSIVE", "attested": True,
               "anchored": True, "decision_valid": True,
               "evidence_tier": "decision", "debug_only": False,
               "supersession": {"status": "current", "superseded_by": None,
                                 "valid_for_decision": True,
                                 "withdrawal_reason": None}}
    for name, data in (("g33m_old_result.json", old),
                       ("g33m_withdrawn_result.json", withdrawn),
                       ("g33m_current_result.json", current)):
        (tmp_path / name).write_text(json.dumps(data))
    (tmp_path / "RESULT_INDEX.json").write_text(json.dumps({
        "index_schema_version": 1,
        "current_decision_result": "g33m_current_result.json",
        "superseded": [
            {"file": "g33m_old_result.json", "status": "superseded"},
            {"file": "g33m_withdrawn_result.json", "status": "withdrawn"},
        ],
    }))
    with pytest.raises(ValueError, match="without an explicit no-replacement"):
        gate.validate_result_index(tmp_path / "RESULT_INDEX.json")


def test_result_index_rejects_supersession_cycles(tmp_path):
    import json
    for name, successor in (("g33m_a_result.json", "g33m_b_result.json"),
                            ("g33m_b_result.json", "g33m_a_result.json")):
        (tmp_path / name).write_text(json.dumps({
            "supersession": {"status": "superseded", "superseded_by": successor,
                              "valid_for_decision": False, "withdrawal_reason": None},
        }))
    (tmp_path / "RESULT_INDEX.json").write_text(json.dumps({
        "index_schema_version": 1, "current_decision_result": None,
        "superseded": [
            {"file": "g33m_a_result.json", "status": "superseded"},
            {"file": "g33m_b_result.json", "status": "superseded"},
        ],
    }))
    with pytest.raises(ValueError, match="supersession cycle"):
        gate.validate_result_index(tmp_path / "RESULT_INDEX.json")


def _sched_line(loop, chain, n, field, values):
    import struct
    words = " ".join(struct.pack(">f", float(v)).hex() for v in values)
    return f"KDM6SCHED {loop} {chain} {n} {field} f32 {len(values)} {words}"


def _sched_scope(n, *, only=None):
    values = {
        "work1_qr": [0.015, 0.015], "workn_qr": [0.0, 0.0],
        "work1_qs": [0.0, 0.0], "work1_qg": [0.0, 0.0],
        "mstep_native": [2.0], "dtcld": [100.0],
    }
    if only is not None:
        values = {key: value for key, value in values.items() if key in only}
    return "\n".join(_sched_line(1, "main", n, key, value)
                     for key, value in values.items()) + "\n"


def test_schedule_seal_rejects_incomplete_n_greater_than_one_payload():
    raw = _sched_scope(1) + _sched_scope(2, only={"mstep_native"})
    with pytest.raises(schedule.ProbeError, match="n=2.*missing"):
        schedule.probe_from_stream(raw, expected_shape=(1, 2))


def test_update_replay_coverage_rejects_all_nan_cells():
    nan = update.bits32(float("nan"))
    pre = {("qr", 1, 0): nan, ("t", 1, 0): nan}
    names = {name for _sign, name in update.COLD_TERMS + update.WARM_TERMS}
    operands = {(name, 1, 0): nan for name in names}
    post = {("qr", 1, 0): nan}
    with pytest.raises(ValueError, match="finite f32"):
        update.coverage(pre, operands, post, 100.0)


def test_stage_domain_rejects_nan_and_negative_carried_state():
    base = {"stage": "outer_post_micro", "loop": 1, "chain": "-", "n": 0,
            "col": 1, "k": 0, "field": "qr", "dtype": "f32", "bits": 0xBF800000}
    with pytest.raises(ev.GateSemanticsError, match="negative carried state"):
        ev.validate_stage_domains({"stages": [base]})
    nan = dict(base, bits=0x7FC00000)
    with pytest.raises(ev.GateSemanticsError, match="non-finite stage"):
        ev.validate_stage_domains({"stages": [nan]})


def test_replay_rejects_duplicate_stage_identity():
    stage = {"stage": "substep_pre", "loop": 1, "chain": "main", "n": 1,
             "col": 1, "k": -1, "field": "dtcld", "dtype": "f32",
             "bits": 0x42C80000}
    run = {"algorithm": "legacy", "backend": "cpp", "ops": [],
           "stages": [stage, dict(stage)]}
    with pytest.raises(replay.FidelityError, match="duplicate stage identity"):
        replay.replay_report(run)


def test_fortran_parser_does_not_mix_record_grammars():
    sample = (ROOT / "tests" / "data" / "g33_legacy_sample.g33f").read_text()
    old = "G33F MSTEP 1 main 1 i32 00000001"
    assert old in sample
    mixed = sample.replace(old, "G33F MSTEP 1 i32 00000001", 1)
    with pytest.raises(fd.FortranRunError, match="malformed/unknown"):
        fd.parse_fortran_run(mixed, "legacy", K=4, B=3)


def test_refine_driver_declares_and_emits_canonical_k_order():
    source = (ROOT / "g33_overlay" / "g33_refine_driver.cpp").read_text()
    assert "to_host_order" in source
    assert "torch::flip(value.detach()" in source
