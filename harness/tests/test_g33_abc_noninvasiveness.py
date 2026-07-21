#!/usr/bin/env python3
"""Pure fail-closed tests for the C++ A/B/C non-invasiveness harness."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_abc_noninvasiveness as abc
import g33_dump as gd
import g33_expectation as ge


def _valid_output(algorithm="legacy", case_name="closure3"):
    B, K = abc.CASES[case_name]
    lines = [f"KDM6ABC 1 {algorithm} {case_name} {B} {K}"]
    for name in abc.EXPECTED_FIELDS:
        shape = (B, K) if name in abc.STATE_FIELDS else (B,)
        n = 1
        for d in shape:
            n *= d
        # finite +0 f32 words; parser validates structure, the live driver supplies
        # the physically nondegenerate values used by the actual A/B/C gate.
        lines.append(" ".join([
            "FIELD", name, "f32", str(len(shape)), *(str(d) for d in shape),
            str(n), *("00000000" for _ in range(n)),
        ]))
    lines.append("END")
    return ("\n".join(lines) + "\n").encode()


def _contract_env(path: Path, contract) -> dict:
    body = json.dumps(contract, sort_keys=True).encode()
    path.mkdir()
    (path / "run_contract.json").write_bytes(body)
    return {"KDM6_G33_RUN_CONTRACT_SHA256": hashlib.sha256(body).hexdigest()}


def test_parse_output_accepts_the_exact_complete_protocol():
    parsed = abc.parse_output(_valid_output(), "legacy", "closure3")
    assert tuple(parsed) == abc.EXPECTED_FIELDS
    assert parsed["qr"]["shape"] == (3, 4)
    assert parsed["rain_increment"]["shape"] == (3,)


@pytest.mark.parametrize("edit,match", [
    (lambda b: b.replace(b"\nEND\n", b"\n"), "END"),
    (lambda b: b.replace(b"FIELD th", b"FIELD wrong", 1), "order/name"),
    (lambda b: b.replace(b" 12 00000000", b" 11 00000000", 1), "shape/count"),
    (lambda b: b.replace(b"00000000", b"7f800000", 1), "non-finite"),
    (lambda b: b.replace(b"00000000", b"xyz", 1), "raw-bit"),
])
def test_parse_output_rejects_truncated_or_relabelled_results(edit, match):
    with pytest.raises(gd.G33Corruption, match=match):
        abc.parse_output(edit(_valid_output()), "legacy", "closure3")


def test_contract_loader_rejects_a_missing_contract(tmp_path):
    with pytest.raises(gd.G33Corruption, match="contract missing"):
        abc._load_contract_specs(
            tmp_path / "missing", {"KDM6_G33_RUN_CONTRACT_SHA256": "0" * 64})


@pytest.mark.parametrize("contract,match", [
    ({"containers": "not-a-list"}, "containers must be a list"),
    ({"containers": ["not-an-object"]}, r"containers\[0\] must be an object"),
    ({"containers": [{}]}, "container_id"),
])
def test_contract_loader_rejects_malformed_container_specs(tmp_path, contract, match):
    outdir = tmp_path / "case"
    env = _contract_env(outdir, contract)
    with pytest.raises(gd.G33Corruption, match=match):
        abc._load_contract_specs(outdir, env)


def test_cpp_records_inherit_header_identity_before_multiset_comparison():
    schedule = abc._schedule("legacy", "closure3")
    expected = ge.expected_records(schedule)[0]
    # C++ stores case/pair/backend once in the container header, not redundantly
    # in every record key. The checker must normalize them before record_key().
    record = {k: v for k, v in expected.items()
              if k not in ("case_id", "pair_id", "backend")}
    header = {"case_id": schedule["case_id"],
              "pair_id": schedule["pair_id"], "backend": "cpp"}
    logical = abc._record_with_header_identity(record, header)
    assert ge.record_key(logical) == ge.record_key(expected)
    with pytest.raises(gd.G33Corruption, match="conflicts with header"):
        abc._record_with_header_identity({**record, "backend": "fortran"}, header)


def test_schedule_declares_one_substep_and_the_actual_cpp_overlay_scope():
    for algorithm in abc.ALGORITHMS:
        for case_name, (B, K) in abc.CASES.items():
            sched = abc._schedule(algorithm, case_name)
            assert (sched["B"], sched["K"], sched["loops"]) == (B, K, 1)
            assert sched["mstepmax_main"] == [1]
            assert sched["mstepmax_ice"] == [1]
            assert sched["instrumented_stages"] == list(ge.CPP_OVERLAY_STAGES)
            index = ge.run_index(sched)
            assert {c["container_id"] for c in index["containers"]} == {
                "L1_outer_pre", "L1_main_n1", "L1_surface",
                "L1_outer_post_sed", "L1_outer_post_micro",
            }


def test_first_diff_identifies_the_first_changed_output_line():
    a = _valid_output()
    b = a.replace(b"FIELD qr", b"FIELD qx", 1)
    msg = abc._first_diff(a, b)
    assert "line" in msg and "FIELD qr" in msg and "FIELD qx" in msg
