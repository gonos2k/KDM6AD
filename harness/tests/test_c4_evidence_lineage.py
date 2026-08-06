"""The C4 closeout package is frozen, and the freeze is checked (owner §16-5).

Declaring a file immutable in prose does not make it so. The lineage sidecar pins
the snapshot's full digest, so any edit to the snapshot -- including the
well-meant "just refresh producer_commit" -- fails here.
"""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "docs" / "c4_evidence_manifest.json"
LINEAGE = REPO / "docs" / "c4_evidence_lineage.json"
STATUS = REPO / "docs" / "STATUS.md"


@pytest.fixture(scope="module")
def lineage():
    return json.loads(LINEAGE.read_text())


def test_the_snapshot_digest_still_matches(lineage):
    """The whole point of the freeze."""
    got = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    assert got == lineage["historical_snapshot"]["manifest_sha256"], (
        "docs/c4_evidence_manifest.json has changed. It is an immutable "
        "historical snapshot (owner §16-5): a successor goes in a SEPARATE "
        "addendum carrying this digest as its parent, never by editing this file.")


def test_the_pinned_commits_are_the_snapshot_s_OWN(lineage):
    """A lineage that named some other run's commits would freeze nothing."""
    repo = json.loads(MANIFEST.read_text())["public_repo"]
    snap = lineage["historical_snapshot"]
    assert snap["producer_commit"] == repo["producer_commit"]
    assert snap["main_commit"] == repo["main_commit"]


def test_the_lineage_does_not_try_to_NAME_the_current_head(lineage):
    """A static file cannot: the commit that edits it cannot know its own hash,
    and every later commit makes the value stale the moment it lands. The first
    version recorded the PR's own base and was already wrong when merged (owner
    P0-3). It also made the test vacuous -- `historical != current` passes for
    any old commit at all."""
    assert "current_harness" not in lineage
    assert lineage["current_authority"]["current_head"] == \
        "resolved dynamically at check time"


def test_the_authority_anchor_is_an_ANCESTOR_of_the_current_head(lineage):
    """What IS stable: where the authority was introduced. If HEAD does not
    descend from it, this lineage describes a different history."""
    anchor = lineage["current_authority"]["authority_introduced_at"]
    r = subprocess.run(["git", "merge-base", "--is-ancestor", anchor, "HEAD"],
                       cwd=REPO, capture_output=True)
    if r.returncode == 128:
        pytest.skip("the anchor commit is not present in this clone")
    assert r.returncode == 0, f"HEAD does not descend from {anchor[:12]}"


def test_the_authority_files_EXIST_at_the_anchor(lineage):
    """An anchor naming a commit that never carried these files would pin
    nothing."""
    anchor = lineage["current_authority"]["authority_introduced_at"]
    for path in ("docs/c4_evidence_lineage.json", "harness/evidence/CLAIMS.yaml"):
        r = subprocess.run(["git", "rev-parse", f"{anchor}:{path}"],
                           cwd=REPO, capture_output=True, text=True)
        if r.returncode == 128:
            pytest.skip("the anchor commit is not present in this clone")
        assert r.returncode == 0, f"{path} absent at {anchor[:12]}"


def test_the_addendum_gate_names_what_is_ACTUALLY_outstanding(lineage):
    """It said the addendum was gated on §16-6 and two correctness items -- all
    implemented here. A gate that names finished work reads as blocked when it
    is not (owner P0-3)."""
    note = lineage["note"]
    assert "RE-RUN" in note and "independent closeout" in note


def test_authoritative_pins_are_FULL_digests(lineage):
    """A 16-hex prefix is for display. An authority pin is 64 hex (owner §16-6)."""
    d = lineage["historical_snapshot"]["manifest_sha256"]
    assert len(d) == 64 and all(c in "0123456789abcdef" for c in d)


def test_STATUS_no_longer_calls_the_snapshot_a_LIVE_authority():
    """It said the manifest was "updated per closeout, not a frozen historical
    tag" while the file it described had not moved in many closeouts -- the
    contradiction owner §16-5 named."""
    text = STATUS.read_text()
    assert "updated per closeout" not in text
    assert "IMMUTABLE HISTORICAL SNAPSHOT" in text
    assert "harness/evidence/CLAIMS.yaml" in text, \
        "STATUS must name where current authority actually lives"
