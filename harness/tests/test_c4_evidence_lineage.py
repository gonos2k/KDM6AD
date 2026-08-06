"""The C4 closeout package is frozen, and the freeze is checked (owner §16-5).

Declaring a file immutable in prose does not make it so. The lineage sidecar pins
the snapshot's full digest, so any edit to the snapshot -- including the
well-meant "just refresh producer_commit" -- fails here.
"""
import hashlib
import json
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


def test_the_snapshot_producer_is_NOT_the_current_main(lineage):
    """If these ever coincide the distinction has quietly collapsed -- which is
    exactly the in-place update this structure exists to prevent."""
    assert lineage["historical_snapshot"]["producer_commit"] != \
        lineage["current_harness"]["main_commit"]


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
