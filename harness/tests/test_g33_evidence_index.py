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
    "fixture_manifest_sha256", "verifier_semantics_sha256",
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
    """A commit that is not in this repository is a string, not a lineage.

    The existence half needs a complete clone to answer. CI checks out with the
    `actions/checkout` default `fetch-depth: 1`, where `git cat-file` cannot see a
    commit that is genuinely present in the repository — the first version of this
    test failed there on two perfectly good SHAs, asserting a property of the
    LOCAL CLONE rather than of the artifact.

    So the SHAPE is checked always (that IS a property of the artifact), and
    existence only where the clone can answer. The skip is conditioned on the repo
    actually being shallow, not on the lookup failing — conditioning it on failure
    is how such a check goes quietly vacuous.
    """
    import re as _re
    import subprocess
    p, d = _current()
    sha = d["provenance"][field]
    assert _re.fullmatch(r"[0-9a-f]{40}", sha or ""), (
        f"{p.name}: {field}={sha!r} is not a full 40-hex commit id")

    root = EVIDENCE.parent.parent
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"],
                             cwd=root, capture_output=True, text=True).stdout.strip()
    if shallow != "false":
        pytest.skip(f"shallow clone: cannot resolve {field}; shape checked")
    r = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                       cwd=root, capture_output=True)
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


def test_the_current_artifact_was_decided_by_THIS_verifier():
    """Stale-by-logic, not only stale-by-protocol (owner review §3).

    `decision_protocol_version` covers the evidence contract. It does not cover the
    code that turns evidence into a verdict: a change to the comparator's ordering,
    the activity rule or the replay's association moves the answer with the protocol
    version untouched, and the artifact would stay `current` while no longer
    describing what this tree concludes.

    Editing a test or a document does not trip this — only the declared decision
    logic does.
    """
    import sys
    sys.path.insert(0, str(EVIDENCE.parent))
    import g33_verifier_identity as vid
    assert not vid.missing(), f"declared decision-logic files are missing: {vid.missing()}"
    p, d = _current()
    recorded = d["provenance"].get("verifier_semantics_sha256")
    assert recorded == vid.semantics_sha256(), (
        f"{p.name} was decided by different logic than this tree carries "
        f"(recorded {recorded[:12] if recorded else None}…, tree "
        f"{vid.semantics_sha256()[:12]}…). Regenerate it, or supersede it.")


def test_the_recorded_digest_MATCHES_the_recorded_commit():
    """The two provenance fields must point at the SAME tree (owner review §2).

    An artifact records a `verifier_commit` and a `verifier_semantics_sha256`.
    Checked separately, each is merely plausible — one is a real commit, the other
    matches this tree — and nothing says they describe each other. That is the same
    shape as the hand-attached provenance block: fields that look right beside a
    run they do not describe.

    Needs the commit's tree, so it skips on a shallow clone. The evidence CI job
    checks out with fetch-depth: 0 precisely so it runs there.
    """
    import subprocess
    import sys
    sys.path.insert(0, str(EVIDENCE.parent))
    import g33_verifier_identity as vid
    p, d = _current()
    sha = d["provenance"]["verifier_commit"]
    root = EVIDENCE.parent.parent
    if subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=root,
                      capture_output=True, text=True).stdout.strip() != "false":
        pytest.skip("shallow clone: cannot read the tree at verifier_commit")
    at = vid.semantics_sha256_at(sha)
    assert at is not None, f"{p.name}: cannot read the decision logic at {sha}"
    assert at == d["provenance"]["verifier_semantics_sha256"], (
        f"{p.name}: the recorded digest is not the digest of the recorded commit "
        f"— the two provenance fields describe different trees")


def test_the_verifier_commit_is_an_ANCESTOR_of_HEAD():
    """"A commit in this repository" is weaker than "a commit that got here".

    A result decided on a branch that was never merged is not a result this tree
    stands behind. Skips on a shallow clone for the same reason as above.
    """
    import subprocess
    p, d = _current()
    sha = d["provenance"]["verifier_commit"]
    root = EVIDENCE.parent.parent
    if subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=root,
                      capture_output=True, text=True).stdout.strip() != "false":
        pytest.skip("shallow clone: cannot walk history")
    r = subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"],
                       cwd=root, capture_output=True)
    assert r.returncode == 0, (
        f"{p.name}: verifier_commit {sha[:12]} is not an ancestor of HEAD — the "
        f"result was decided on a line this tree does not contain")


def test_the_current_artifact_records_its_RUNTIME():
    """The replay is NumPy f32/f64 arithmetic; the same sources on a different
    runtime are not self-evidently the same verifier."""
    p, d = _current()
    rt = d["provenance"].get("verifier_runtime")
    assert rt, f"{p.name}: no verifier_runtime"
    for k in ("python_implementation", "python_version", "numpy_version",
              "byteorder"):
        assert rt.get(k), f"{p.name}: verifier_runtime is missing {k}"


def test_the_current_artifact_is_at_result_schema_v3_or_later():
    p, d = _current()
    assert d["provenance"]["result_schema_version"] >= 3, (
        "verifier_semantics_sha256 and the operand-group counterfactual became "
        "required, so a current artifact is at least schema v3")
