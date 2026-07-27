"""CLI contract for the G3.3-M decision gate (public CI — no build, no bundle).

Covers the parts that must hold regardless of evidence: the external-anchor usage
guard, the exit-code mapping, and that every reader failure lands as
INVALID_EVIDENCE with a deterministic result file rather than a traceback.
"""
import json

import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import gateb_g33m_check as gate  # noqa: E402


def _args(tmp_path, out, **over):
    a = ["--cpp-bundle", str(tmp_path / "nope"),
         "--fortran-legacy", str(tmp_path / "l.g33f"),
         "--fortran-conservative", str(tmp_path / "c.g33f"),
         "--out", str(out)]
    for k, v in over.items():
        a += [f"--{k}", v] if v is not True else [f"--{k}"]
    return a


def test_exit_code_contract_is_the_documented_one():
    # PASS_MECHANISM, not PASS: the protocol's PASS needs historical causality
    # and downstream propagation, which no synthetic fixture can supply
    assert gate.EXIT == {"PASS_MECHANISM": 0, "FAIL": 1,
                         "INCONCLUSIVE": 2, "INVALID_EVIDENCE": 3,
                         # a debug run must not share exit 0 with a decision
                         "UNATTESTED_MECHANISM_CANDIDATE": 5}
    assert gate.EXIT_USAGE == 4


def test_refuses_to_run_without_external_anchors(tmp_path, capsys):
    out = tmp_path / "r.json"
    assert gate.main(_args(tmp_path, out)) == gate.EXIT_USAGE
    assert "refusing to run" in capsys.readouterr().err
    assert not out.exists()          # no result is written for a usage error


# All four legs. The C++ side was externally anchored long before the Fortran side
# had a bundle to anchor, and "attested" meant only the former.
_ANCHORS = {"expected-manifest-sha256": "a" * 64,
            "expected-repo-commit": "b" * 40,
            "expected-fixture-id": "arithmetic_synthetic_v1",
            "expected-fixture-manifest-sha256": "e" * 64,
            "expected-fortran-legacy-manifest-sha256": "c" * 64,
            "expected-fortran-conservative-manifest-sha256": "d" * 64}


def test_missing_evidence_is_invalid_not_a_traceback(tmp_path):
    out = tmp_path / "r.json"
    rc = gate.main(_args(tmp_path, out, **_ANCHORS))
    assert rc == gate.EXIT["INVALID_EVIDENCE"]
    r = json.loads(out.read_text())
    # attested is what the LEGS reported; verification failed, so nothing attested
    assert r["verdict"] == "INVALID_EVIDENCE" and r["attested"] is False
    assert r["inputs"]["expected_fixture_id"] == "arithmetic_synthetic_v1"


@pytest.mark.parametrize("drop", sorted(_ANCHORS))
def test_every_external_anchor_is_required(tmp_path, capsys, drop):
    # the fixture id is an anchor like the other two: a bundle checked against the
    # fixture it declares attests nothing
    out = tmp_path / "r.json"
    partial = {k: v for k, v in _ANCHORS.items() if k != drop}
    assert gate.main(_args(tmp_path, out, **partial)) == gate.EXIT_USAGE
    assert "refusing to run" in capsys.readouterr().err
    assert not out.exists()


def test_debug_mode_is_stamped_unattested(tmp_path):
    out = tmp_path / "r.json"
    rc = gate.main(_args(tmp_path, out, **{"allow-unattested": True}))
    assert rc == gate.EXIT["INVALID_EVIDENCE"]       # the paths still do not exist
    assert json.loads(out.read_text())["attested"] is False


def test_result_json_is_deterministic(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    for out in (a, b):
        gate.main(_args(tmp_path, out, **{"allow-unattested": True}))
    assert a.read_text() == b.read_text() and a.read_text().endswith("\n")
