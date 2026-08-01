"""Exactly one result artifact is decision-valid, and every artifact says so.

`attested: true` is a claim about the BUNDLES a run consumed — that their
manifests, commits and fixture matched their anchors. It says nothing about
whether the run's CONCLUSION still stands. Two artifacts in this repo had
`attested: true` alongside a conclusion that had been withdrawn in a markdown
finding: the v10 result asserts that Picons and the saturation adjustment are
excluded, which its own records could not support because the Fortran stage was
injected after the wrong ProgB call. A human reading the findings sees the
retraction; a script reading artifacts does not.

So decision validity is its own machine-readable field, and this test is what
makes it a contract rather than a convention.
"""
import json
import pathlib

import pytest

EVIDENCE = pathlib.Path(__file__).resolve().parents[1] / "evidence"
INDEX = EVIDENCE / "RESULT_INDEX.json"

STATUSES = {"current", "superseded", "withdrawn"}


def _results():
    return sorted(EVIDENCE.rglob("*result*.json"))


def _index():
    return json.loads(INDEX.read_text())


def test_every_result_declares_its_decision_validity():
    missing = []
    for p in _results():
        sup = json.loads(p.read_text()).get("supersession")
        if not isinstance(sup, dict) or "valid_for_decision" not in sup:
            missing.append(p.relative_to(EVIDENCE).as_posix())
    assert not missing, (
        f"result artifact(s) with no machine-readable decision validity: {missing}. "
        f"A reader that takes `attested` for validity would treat a withdrawn "
        f"conclusion as evidence.")


@pytest.mark.parametrize("path", _results(), ids=lambda p: p.name)
def test_status_and_validity_agree(path):
    sup = json.loads(path.read_text())["supersession"]
    assert sup["status"] in STATUSES, f"unknown status {sup['status']!r}"
    assert sup["valid_for_decision"] is (sup["status"] == "current"), (
        "only a `current` artifact may be decision-valid")
    if sup["status"] == "withdrawn":
        assert sup.get("withdrawal_reason"), (
            "a withdrawn artifact must say WHY, in the artifact — the reason is "
            "what a later reader needs and it is not in the file otherwise")
    # SUPERSEDED and WITHDRAWN are different claims and carry different duties.
    # "Superseded" means something replaced it, so the successor must exist and be
    # named. "Withdrawn" means this artifact should not be relied on — which stands
    # on its own, and may well have no replacement yet. Requiring a successor for
    # both would force a withdrawal to wait for a regeneration, i.e. would leave a
    # known-bad artifact marked current in the meantime.
    if sup["status"] == "superseded":
        assert sup.get("superseded_by"), "a superseded artifact must name its successor"
    if sup["status"] == "withdrawn" and not sup.get("superseded_by"):
        assert "pending" in sup["withdrawal_reason"].lower() or \
               "no replacement" in sup["withdrawal_reason"].lower(), (
            "a withdrawn artifact with no successor must say so in its reason, so "
            "the gap is stated rather than inferred from a null")


def test_at_most_one_result_is_current_and_the_index_declares_which():
    """Two current results is always wrong. ZERO is a real state — every artifact
    withdrawn and none regenerated yet — but it may not be silent: the index has to
    say `current_decision_result: null`, so a reader cannot mistake absence for
    "the tests did not cover it"."""
    current = [p.name for p in _results()
               if json.loads(p.read_text())["supersession"]["status"] == "current"]
    assert len(current) <= 1, f"more than one current result: {current}"
    declared = _index()["current_decision_result"]
    if current:
        assert declared == current[0]
    else:
        assert declared is None, (
            "no artifact is current, so the index must declare "
            "current_decision_result: null rather than naming one")


def test_the_index_agrees_with_the_artifacts():
    idx = _index()
    on_disk = {p.name: json.loads(p.read_text())["supersession"]["status"]
               for p in _results()}
    if idx["current_decision_result"] is not None:
        assert idx["current_decision_result"] in on_disk
        assert on_disk[idx["current_decision_result"]] == "current"

    listed = {pathlib.Path(e["file"]).name: e["status"] for e in idx["superseded"]}
    non_current = {n: s for n, s in on_disk.items() if s != "current"}
    assert listed == non_current, (
        f"index and artifacts disagree; index says {listed}, disk says {non_current}")


def test_named_successors_exist():
    names = {p.name for p in _results()}
    for p in _results():
        succ = json.loads(p.read_text())["supersession"].get("superseded_by")
        if succ:
            assert succ in names, f"{p.name} names a successor that is not here: {succ}"


# ── the CURRENT artifact must be reproducible, not merely well-formed ─────────
#
# Exactly-one-current and a consistent supersession graph say nothing about
# whether the one current result can be reproduced. The v14 artifact satisfied
# both while recording `verifier_tree_dirty: true` — a verifier commit the run was
# not made from, so checking it out does not give that result. These are the
# properties that make `current` mean something.

REQUIRED_DIGESTS = (
    "cpp_root_manifest_sha256", "fortran_legacy_manifest_sha256",
    "fortran_conservative_manifest_sha256", "gate_a_report_sha256",
    "fixture_manifest_sha256",
)


def _current():
    """The current artifact, or skip. Skipping is correct only because
    test_at_most_one_result_is_current_and_the_index_declares_which already
    requires the absence to be declared — without that these would go quietly
    vacuous the moment an artifact was withdrawn."""
    for p in _results():
        d = json.loads(p.read_text())
        if d["supersession"]["status"] == "current":
            return p, d
    pytest.skip("no current decision result (declared null in RESULT_INDEX)")


def test_the_current_artifact_was_produced_from_a_CLEAN_tree():
    p, d = _current()
    prov = d.get("provenance")
    assert prov, f"{p.name}: no provenance block"
    assert prov["verifier_tree_dirty"] is False, (
        f"{p.name} was produced from a dirty working tree, so its recorded "
        f"verifier_commit does not reproduce it. It cannot be the decision result.")


def test_the_current_artifact_is_at_the_decision_protocol_version():
    import sys
    sys.path.insert(0, str(EVIDENCE.parent))
    import g33_fortran_bundle_io as bio
    p, d = _current()
    assert d["provenance"]["decision_protocol_version"] == bio.DECISION_PROTOCOL_VERSION, (
        f"{p.name} is at protocol v{d['provenance']['decision_protocol_version']} "
        f"while the decision path is at v{bio.DECISION_PROTOCOL_VERSION}")


@pytest.mark.parametrize("field", ["producer_commit", "verifier_commit"])
def test_the_recorded_commits_are_real_git_objects(field):
    """A commit that is not in this repository is a string, not a lineage."""
    import subprocess
    p, d = _current()
    sha = d["provenance"][field]
    r = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                       cwd=EVIDENCE.parent.parent, capture_output=True)
    assert r.returncode == 0, f"{p.name}: {field}={sha} is not a commit in this repo"


def test_every_required_digest_is_present():
    p, d = _current()
    missing = [k for k in REQUIRED_DIGESTS if not d["provenance"].get(k)]
    assert not missing, f"{p.name}: provenance is missing {missing}"


def test_a_debug_only_artifact_can_never_be_current():
    for p in _results():
        d = json.loads(p.read_text())
        if d.get("debug_only"):
            assert d["supersession"]["status"] != "current", (
                f"{p.name} is debug_only and cannot be the decision result")
