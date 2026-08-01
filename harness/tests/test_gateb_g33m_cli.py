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
    # --debug-only on every CLI test: these ARE debug runs, written from a working
    # tree that is dirty by definition during development, and the gate refuses to
    # write a DECISION artifact from one. Marking them is honest and keeps the
    # refusal strict rather than making it skippable.
    a = ["--cpp-bundle", str(tmp_path / "nope"),
         "--fortran-legacy", str(tmp_path / "l.g33f"),
         "--fortran-conservative", str(tmp_path / "c.g33f"),
         "--debug-only", "--out", str(out)]
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


# ── a defect here is not a bad bundle, and a decision is not overwritten (P1) ──

def test_an_internal_defect_has_its_own_exit_code():
    """A blanket `except Exception` turned a TypeError in this harness into
    INVALID_EVIDENCE, which reads as "the bundle is bad" and sends an operator to
    audit evidence that is fine."""
    assert gate.EXIT_INTERNAL == 6
    assert gate.EXIT_INTERNAL not in gate.EXIT.values()
    assert gate.EXIT_INTERNAL != gate.EXIT_USAGE


def test_only_evidence_errors_are_converted_to_a_verdict():
    import inspect, re
    caught = re.search(r"except \((.*?)\) as e", inspect.getsource(gate.main), re.S)
    names = {n.strip() for n in caught.group(1).split(",")}
    assert "Exception" not in names, (
        "a blanket except hides programming defects as evidence errors")
    for suspicious in ("TypeError", "AttributeError", "NameError"):
        assert suspicious not in names, suspicious


def test_a_decision_artifact_is_not_silently_overwritten(tmp_path):
    out = tmp_path / "result.json"
    out.write_text('{"verdict": "PASS_MECHANISM"}')
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        gate._write(out, {"verdict": "FAIL"})
    assert json.loads(out.read_text())["verdict"] == "PASS_MECHANISM", (
        "the earlier verdict must survive the refusal")
    gate._write(out, {"verdict": "FAIL"}, force=True)     # deliberate replacement
    assert json.loads(out.read_text())["verdict"] == "FAIL"


def test_the_writer_is_atomic(tmp_path):
    # a partial write leaves a file that parses but describes nothing that happened
    out = tmp_path / "result.json"
    gate._write(out, {"verdict": "INCONCLUSIVE"})
    assert json.loads(out.read_text())["verdict"] == "INCONCLUSIVE"
    assert not list(tmp_path.glob("*.tmp")), "the temp file must not survive"


def test_a_dirty_tree_cannot_write_a_DECISION_artifact(tmp_path, monkeypatch):
    """The v14 artifact was written from a dirty tree AND marked decision-valid.

    Its recorded verifier_commit does not reproduce it, which is the whole content
    of the provenance block, so the refusal has to be in the producer — a field a
    tool does not enforce is a field a reader cannot rely on.
    """
    out = tmp_path / "r.json"
    monkeypatch.setattr(gate, "_git",
                        lambda *a: "M x" if a[0] == "status" else "0" * 40)
    args = [x for x in _args(tmp_path, out, **_ANCHORS) if x != "--debug-only"]
    with pytest.raises(SystemExit, match="DIRTY working tree"):
        gate.main(args)
    assert not out.exists(), "nothing may be written when the refusal fires"


def test_a_dirty_tree_MAY_write_a_debug_artifact_and_it_says_so(tmp_path, monkeypatch):
    out = tmp_path / "r.json"
    monkeypatch.setattr(gate, "_git",
                        lambda *a: "M x" if a[0] == "status" else "0" * 40)
    gate.main(_args(tmp_path, out, **_ANCHORS))
    r = json.loads(out.read_text())
    assert r["debug_only"] is True and r["provenance"]["verifier_tree_dirty"] is True


def test_the_provenance_block_is_produced_by_the_TOOL(tmp_path):
    """It used to be attached by hand afterwards, which is why it could record a
    dirty tree on an artifact simultaneously marked decision-valid."""
    out = tmp_path / "r.json"
    gate.main(_args(tmp_path, out, **_ANCHORS))
    prov = json.loads(out.read_text())["provenance"]
    for k in ("result_schema_version", "decision_protocol_version",
              "producer_commit", "verifier_commit", "verifier_tree_dirty",
              "cpp_root_manifest_sha256", "gate_a_report_sha256",
              "fixture_manifest_sha256"):
        assert k in prov, f"provenance is missing {k}"
