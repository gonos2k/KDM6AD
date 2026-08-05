"""The chain from a claim to the run behind it (owner §9.2).

Fixture bundles rather than the real ones: the published bundles live outside the
repo and are absent in CI, so a test written against them would assert the host.
"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_evidence_chain as ec  # noqa: E402


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A home with one bundle, and a registry pinning its manifest.

    Returns (home, bundle_dir, write_registry) so each test can vary one thing.
    """
    home = tmp_path / "home"
    bundle = home / "kdm6ad-g33m-refine" / "run-a"
    bundle.mkdir(parents=True)
    stream = b"G33R STATE 1 1 1 th 3F800000\n"
    (bundle / "n3.rezero.txt").write_bytes(stream)
    man = {"members": [{"file": "n3.rezero.txt", "output_sha256": _sha(stream)}],
           "findings": []}

    def write(manifest=man, pin=None, claim_extra=""):
        mb = json.dumps(manifest, indent=2, sort_keys=True).encode()
        (bundle / "manifest.json").write_bytes(mb)
        digest = pin if pin is not None else _sha(mb)[:16]
        reg = tmp_path / "CLAIMS.yaml"
        reg.write_text(
            "schema: 1\n\nclaims:\n"
            "  - id: G33-TEST-001\n"
            "    status: active\n"
            "    artifacts:\n"
            f"      - kdm6ad-g33m-refine/run-a/manifest.json: {digest}\n"
            "    evidence: [FINDING_x.md]\n" + claim_extra)
        monkeypatch.setattr(ec, "REGISTRY", reg)
        monkeypatch.setattr(ec, "HOME", home)

    return bundle, write


def test_a_claim_can_pin_the_run_not_only_the_document(world):
    """The gap §9.2 names: the registry pinned the finding's digest and nothing
    about the run whose numbers the finding quotes."""
    _, write = world
    write()
    row = ec.chain()[0]
    assert row["id"] == "G33-TEST-001"
    assert row["artifacts"][0]["state"] == "matches"
    assert ec.check() == 0


def test_a_tampered_artifact_fails(world):
    _, write = world
    write(pin="0" * 16)
    assert ec.chain()[0]["artifacts"][0]["state"] == "MISMATCH"
    assert ec.check() == 1


def test_an_absent_bundle_is_unavailable_not_a_failure(world):
    """Bundles are outside the repo and absent in CI. Failing on absence would
    make this uncheckable everywhere it matters and red everywhere else."""
    bundle, write = world
    write()
    (bundle / "manifest.json").unlink()
    assert ec.chain()[0]["artifacts"][0]["state"] == "unavailable"
    assert ec.check() == 0


def test_pinning_the_manifest_reaches_the_RAW_STREAMS_through_it(world):
    """Otherwise the pin proves only that a JSON file did not change, while the
    outputs it describes could be anything."""
    bundle, write = world
    write()
    assert [m["state"] for m in ec.chain()[0]["artifacts"][0]["members"]] == \
        ["matches"]
    (bundle / "n3.rezero.txt").write_bytes(b"G33R STATE 1 1 1 th DEADBEEF\n")
    assert ec.chain()[0]["artifacts"][0]["members"][0]["state"] == "MISMATCH"
    assert ec.check() == 1, "a tampered raw stream must fail even when the " \
                            "manifest still matches its own pin"


def test_a_missing_member_inside_a_PRESENT_bundle_FAILS(world):
    """An absent top-level manifest is `unavailable` and must not fail -- bundles
    live outside the repo. But once the manifest is present AND matches, the
    bundle has declared these files exist, so one of them missing is a corrupt or
    incomplete bundle. Treating both cases as "absent, not a failure" let a
    bundle whose raw streams had all been deleted pass --check cleanly
    (owner P0-4)."""
    bundle, write = world
    write()
    (bundle / "n3.rezero.txt").unlink()
    assert ec.chain()[0]["artifacts"][0]["members"][0]["state"] == "absent"
    assert ec.check() == 1, "a declared-but-missing member must fail"


def test_the_two_kinds_of_absence_are_distinguished(world):
    """Parent absent -> unavailable, no failure. Child absent -> failure."""
    bundle, write = world
    write()
    assert ec.check() == 0
    (bundle / "manifest.json").unlink()          # parent gone
    assert ec.check() == 0, "an absent bundle is unavailable, not a failure"


def test_a_finding_revised_after_its_run_is_history_not_failure(world):
    """A published bundle is content-addressed and IMMUTABLE, so the finding
    digest inside it can never be updated. Treating divergence as failure would
    make every legitimate correction -- including the claim-status stamper's own
    block -- break the build permanently."""
    _, write = world
    write({"members": [],
           "findings": [{"path": "harness/evidence/FINDING_x.md",
                         "sha256": "0" * 64}]})
    (ec.REPO / "harness/evidence").mkdir(parents=True, exist_ok=True)
    states = {s["state"] for s in ec.snapshots()}
    assert states <= {"divergent", "absent", "matches"}
    assert ec.check() == 0


def test_the_registry_parser_reads_the_artifacts_block(world):
    """A silently-unparsed block would report `no artifacts pinned` for a claim
    that pins them -- the failure mode that looks like success."""
    bundle, write = world
    write(claim_extra="    scope: a scope\n")
    got = ec.claims()[0]["artifacts"]
    assert list(got) == ["kdm6ad-g33m-refine/run-a/manifest.json"]
    assert got["kdm6ad-g33m-refine/run-a/manifest.json"] == \
        _sha((bundle / "manifest.json").read_bytes())[:16]


def test_a_key_after_the_artifacts_block_ends_it(world):
    """`in_art` must clear on the next key, or a later `evidence:` line would be
    swallowed as an artifact and the claim would lose its findings."""
    _, write = world
    write(claim_extra="    scope: a scope\n")
    c = ec.claims()[0]
    assert c["evidence"] == ["FINDING_x.md"], "evidence survived the artifacts block"


# ---- the real registry --------------------------------------------------------

def test_the_real_registry_parses_and_its_pins_hold():
    """Runs against whatever bundles this host has; on a host with none, every
    artifact is `unavailable` and this asserts the parse alone."""
    assert len(ec.claims()) >= 10
    assert ec.check() == 0


# ---- owner §4 / §8.2: arm streams and the analyzer digest -------------------

def test_an_arm_stream_the_manifest_declares_is_followed(world):
    """The multi-arm decomposition is computed from six raw runs. Previously
    they existed only inside the analysis function, so the chain stopped at a
    derived JSON and nothing downstream could re-derive the table (owner §4)."""
    bundle, write = world
    arm = b"G33N STREAM_BEGIN 4 1 1 1 legacy rezero mstep uniform\n"
    (bundle / "n3.rezero.uniform.txt").write_bytes(arm)
    write({"members": [], "findings": [],
           "analyses": [{"file": "n3.rezero.uniform.txt", "analysis": "arm_stream",
                         "arm": "uniform", "sha256": _sha(arm)}]})
    assert ec.check() == 0
    (bundle / "n3.rezero.uniform.txt").write_bytes(b"tampered\n")
    assert ec.check() == 1, "a tampered arm stream must fail"


def test_a_missing_arm_stream_fails(world):
    bundle, write = world
    arm = b"G33N STREAM_BEGIN 4 1 1 1 legacy rezero mstep x2\n"
    (bundle / "n3.rezero.x2.txt").write_bytes(arm)
    write({"members": [], "findings": [],
           "analyses": [{"file": "n3.rezero.x2.txt", "analysis": "arm_stream",
                         "arm": "x2", "sha256": _sha(arm)}]})
    (bundle / "n3.rezero.x2.txt").unlink()
    assert ec.check() == 1


def test_a_CHANGED_analyzer_is_reported_but_does_not_fail(world):
    """The analyzer digest was recorded and never checked (owner §8.2). It is
    followed now — but reported rather than failed: the analysis JSON is still
    the artifact the claim cites, and the source moving on is ordinary. What the
    report means is that re-running would not necessarily reproduce it."""
    bundle, write = world
    body = b'{"x": 1}\n'
    (bundle / "a.json").write_bytes(body)
    write({"members": [], "findings": [],
           "analyses": [{"file": "a.json", "analysis": "matched_closure",
                         "sha256": _sha(body),
                         "analyzer": "harness/g33_matched_closure.py",
                         "analyzer_sha256": "0" * 64}]})
    states = {m["state"] for a in ec.chain()[0]["artifacts"] for m in a["members"]}
    assert "ANALYZER-CHANGED" in states
    assert ec.check() == 0, "a moved-on analyzer is information, not corruption"
