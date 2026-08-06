"""The chain from a claim to the run behind it (owner §9.2).

Fixture bundles rather than the real ones: the published bundles live outside the
repo and are absent in CI, so a test written against them would assert the host.
"""
import hashlib
import json
import re
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
    # A realistic LEGACY manifest: every archived bundle declares its schema and
    # artifact_type, so a fixture without them was testing a shape that does not
    # exist -- and one the checker now rejects as unidentifiable.
    man = {"schema": "refinement_experiment_v1",
           "artifact_type": "refinement_experiment",
           "members": [{"file": "n3.rezero.txt", "output_sha256": _sha(stream)}],
           "findings": []}

    def write(manifest=None, pin=None, claim_extra=""):
        manifest = {"schema": "refinement_experiment_v1",
                    "artifact_type": "refinement_experiment",
                    **(man if manifest is None else manifest)}
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
    # `modules-unpinned` rides along: this fixture pins no producer modules.
    assert [m["state"] for m in ec.chain()[0]["artifacts"][0]["members"]] == \
        ["matches", "modules-unpinned", "modules-unpinned"]
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


def test_a_LEGACY_bundle_with_only_a_content_digest_is_REPORTED_not_failed(world):
    """Bundles published before the commit+blob pin existed recorded only the
    analyzer's content digest, checkable solely against the working tree. A
    moved-on analyzer makes those unverifiable rather than corrupt."""
    bundle, write = world
    body = b'{"x": 1}\n'
    (bundle / "a.json").write_bytes(body)
    write({"members": [], "findings": [],
           "analyses": [{"file": "a.json", "analysis": "matched_closure",
                         "sha256": _sha(body),
                         "analyzer": "harness/g33_matched_closure.py",
                         "analyzer_sha256": "0" * 64}]})
    states = {m["state"] for a in ec.chain()[0]["artifacts"] for m in a["members"]}
    assert "legacy-analyzer-changed" in states
    assert ec.check() == 0, "a moved-on analyzer is information, not corruption"


# ---- owner §16-6: the analyzer is RECOVERED, not compared ---------------------

def _pinned(bundle, write, commit, blob, path="harness/g33_matched_closure.py"):
    body = b'{"x": 1}\n'
    (bundle / "a.json").write_bytes(body)
    write({"members": [], "findings": [],
           "analyses": [{"file": "a.json", "analysis": "matched_closure",
                         "sha256": _sha(body), "analyzer": path,
                         "analyzer_sha256": "0" * 64,
                         "analyzer_commit": commit, "analyzer_blob_sha": blob}]})


def _head_blob(path):
    import subprocess
    r = subprocess.run(["git", "rev-parse", f"HEAD:{path}"], cwd=ec.REPO,
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def test_a_resolvable_commit_and_blob_PASSES_whatever_the_working_tree_holds(
        world):
    """The point of the change. `analyzer_sha256` here is deliberately wrong --
    it is `0`*64 -- and the check still passes, because the question is no longer
    "does today's file match" but "can the bytes this bundle ran be recovered"
    (owner §16-6)."""
    bundle, write = world
    path = "harness/g33_matched_closure.py"
    _pinned(bundle, write, "HEAD", _head_blob(path), path)
    states = {m["state"] for a in ec.chain()[0]["artifacts"] for m in a["members"]}
    # `modules-unpinned` rides along: this fixture pins no producer modules.
    assert "matches" in states and not (states - {"matches", "modules-unpinned"})
    assert ec.check() == 0


def test_a_blob_that_does_not_match_the_pinned_commit_FAILS(world):
    """Pin and commit must agree, or the manifest names bytes that commit never
    held."""
    bundle, write = world
    _pinned(bundle, write, "HEAD", "0" * 40)
    states = {m["state"] for a in ec.chain()[0]["artifacts"] for m in a["members"]}
    assert "ANALYZER-BLOB-MISMATCH" in states
    assert ec.check() == 1


def test_a_pin_that_cannot_be_RESOLVED_fails_rather_than_being_reported(world):
    """A rewritten commit, a path deleted from history, or a wrong pin. The old
    check could only say "the file on disk differs", which is a different and
    much weaker statement."""
    bundle, write = world
    _pinned(bundle, write, "0" * 40, "0" * 40)
    states = {m["state"] for a in ec.chain()[0]["artifacts"] for m in a["members"]}
    assert "ANALYZER-UNRESOLVABLE" in states
    assert ec.check() == 1


def test_an_analysis_naming_NO_analyzer_is_flagged_not_silently_skipped(world):
    """An entry with no analyzer at all used to fall through the `if` and vanish
    from the report, so a bundle that pinned nothing looked like one that
    checked out."""
    bundle, write = world
    body = b'{"x": 1}\n'
    (bundle / "a.json").write_bytes(body)
    write({"members": [], "findings": [],
           "analyses": [{"file": "a.json", "analysis": "matched_closure",
                         "sha256": _sha(body)}]})
    states = {m["state"] for a in ec.chain()[0]["artifacts"] for m in a["members"]}
    assert "analyzer-unpinned" in states


# ---- owner P0-5: a manifest that will not parse is corruption ---------------

def test_an_unreadable_manifest_is_not_an_artifact_with_no_children(world):
    """It returned an empty child list, which reads as an artifact with nothing
    to check -- indistinguishable from a clean one, even though its own digest
    matched."""
    bundle, write = world
    write()
    (bundle / "manifest.json").write_bytes(b"{not json")
    assert [m["state"] for m in ec.members_of(bundle / "manifest.json")] == \
        ["MANIFEST-UNREADABLE"]


def test_a_manifest_that_is_not_an_object_is_refused(world):
    bundle, write = world
    write()
    (bundle / "manifest.json").write_bytes(b"[]")
    assert ec.members_of(bundle / "manifest.json")[0]["state"] == \
        "MANIFEST-SCHEMA-MISMATCH"


def test_a_manifest_with_no_members_KEY_is_refused_but_an_empty_list_is_not(
        world):
    """Absence of the key and an empty list are different statements: only the
    second is a bundle that legitimately published no members."""
    bundle, write = world
    write()
    p = bundle / "manifest.json"
    head = '"schema": "refinement_experiment_v1", ' \
           '"artifact_type": "refinement_experiment"'
    p.write_text("{" + head + ', "analyses": []}')
    assert ec.members_of(p)[0]["state"] == "MANIFEST-MISSING-MEMBERS"
    p.write_text("{" + head + ', "members": [], "analyses": []}')
    assert [m["state"] for m in ec.members_of(p)] == \
        ["modules-unpinned", "modules-unpinned"]   # one per pin block


def test_a_manifest_that_declares_NO_schema_is_unidentifiable(world):
    """Every archived bundle declares one, so a manifest without it cannot be
    matched to a contract and must not be validated against a guessed one."""
    bundle, write = world
    write()
    p = bundle / "manifest.json"
    p.write_bytes(b'{"members": []}')
    assert ec.members_of(p)[0]["state"] == "MANIFEST-SCHEMA-MISMATCH"


def test_a_corrupt_manifest_FAILS_the_check_not_merely_reports(world):
    bundle, write = world
    write()
    (bundle / "manifest.json").write_bytes(b"{not json")
    assert ec.check() == 1


# ---- owner P0-2: parsers and producer modules ride the same chain -----------

def test_member_parsers_are_followed_by_commit_and_blob(world):
    """Recorded by content digest alone, they were checkable against today's
    working tree and nothing else -- the defect §16-6 fixed for analyzers."""
    bundle, write = world
    write({"members": [], "analyses": [],
           "member_parsers": [{"path": "harness/g33_refine_analyze.py",
                               "content_sha256": "0" * 64,
                               "commit": "0" * 40, "blob_sha": "0" * 40}]})
    states = {m["state"] for a in ec.chain()[0]["artifacts"] for m in a["members"]}
    assert "ANALYZER-UNRESOLVABLE" in states
    assert ec.check() == 1


def test_producer_modules_are_followed_too(world):
    bundle, write = world
    write({"members": [], "analyses": [],
           "producer_modules": [{"path": "harness/g33_matched_closure.py",
                                 "content_sha256": "0" * 64,
                                 "commit": "HEAD", "blob_sha": "0" * 40}]})
    states = {m["state"] for a in ec.chain()[0]["artifacts"] for m in a["members"]}
    assert "ANALYZER-BLOB-MISMATCH" in states
    assert ec.check() == 1


# ---- the verdict must classify every state it can be handed ------------------

def test_an_UNCLASSIFIED_state_fails_rather_than_passing():
    """Both fail-open holes here were the same shape: a state was added to a
    producer and never wired into the `if/elif` verdict, so it fell through and
    passed. `unavailable` and `divergent` were reachable and unclassified."""
    assert ec.verdict("SOME-STATE-NOBODY-CLASSIFIED") is True
    assert ec.verdict("") is True
    assert ec.verdict("matches") is False


def test_the_two_classifications_do_not_overlap():
    assert not (ec.PASSING_STATES & ec.FAILING_STATES)


def test_EVERY_state_the_module_can_emit_is_classified():
    """The completeness check that closes the class. A state literal added to
    the producer without a verdict entry fails here rather than silently
    passing `--check` -- which is exactly how the last two got in."""
    src = (ec.REPO / "harness" / "g33_evidence_chain.py").read_text()
    emitted = set(re.findall(r'"state": "([A-Za-z-]+)"', src))
    emitted |= set(re.findall(r'else "([A-Za-z-]+)"[,\)\n]', src))
    known = ec.PASSING_STATES | ec.FAILING_STATES
    assert emitted <= known, f"unclassified: {sorted(emitted - known)}"
    assert emitted, "the scan found no states -- it has stopped checking anything"


def _pin(mod):
    path = f"harness/{mod}.py"
    return {"path": path, "content_sha256": "0" * 64, "commit": "HEAD",
            "blob_sha": ec._blob_at("HEAD", path)}


def _module_rows(world_write, **blocks):
    world_write({"members": [], "analyses": [], **blocks})
    return {(m["file"], m["state"])
            for a in ec.chain()[0]["artifacts"] for m in a["members"]}


def test_EACH_pin_block_is_checked_SEPARATELY(world):
    """An `any()` across both blocks let a bundle carrying parsers but no
    producer_modules satisfy the combined check, and the missing block vanished
    from the report entirely (Codex). Every combination is exercised, because
    the hole was in exactly the two mixed ones."""
    _, write = world
    assert ("<member_parsers>", "modules-unpinned") in _module_rows(write)
    assert ("<producer_modules>", "modules-unpinned") in _module_rows(write)

    only_parsers = _module_rows(write, member_parsers=[_pin("g33_refine_analyze")])
    assert ("<producer_modules>", "modules-unpinned") in only_parsers
    assert ("<member_parsers>", "modules-unpinned") not in only_parsers

    only_prod = _module_rows(write, producer_modules=[_pin("g33_matched_closure")])
    assert ("<member_parsers>", "modules-unpinned") in only_prod
    assert ("<producer_modules>", "modules-unpinned") not in only_prod

    both = _module_rows(write, member_parsers=[_pin("g33_refine_analyze")],
                        producer_modules=[_pin("g33_matched_closure")])
    assert not [f for f, st in both if st == "modules-unpinned"]


def test_an_unpinned_block_is_REPORTED_not_failed(world):
    """Old bundles legitimately predate these pins."""
    _, write = world
    _module_rows(write)
    assert ec.check() == 0


# ---- owner P0-E2: a new bundle cannot downgrade to the legacy contract -------

def _man(**kw):
    pin = {"path": "harness/g33_matched_closure.py", "content_sha256": "0" * 64,
           "commit": "HEAD",
           "blob_sha": ec._blob_at("HEAD", "harness/g33_matched_closure.py")}
    base = {"artifact_type": "refinement_experiment",
            "schema": "refinement_experiment_v2",
            "members": [{"file": "n3.rezero.txt", "output_sha256": "0" * 64}],
            "member_parsers": [pin], "producer_modules": [pin],
            "build_provenance": {"repo_commit": "x"}, "arm": "reference",
            "precision": "f32", "analyses": []}
    return {**base, **kw}


def _first_state(tmp_path, man):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(man))
    return ec.members_of(p)[0]["state"]


def test_a_v2_bundle_that_DELETES_its_pin_blocks_FAILS(tmp_path):
    """Under v1 the blocks were optional metadata, so a new bundle could shed
    them and be read as an old one -- a contract you can opt out of by omission
    is not a contract (owner P0-E2)."""
    assert _first_state(tmp_path, _man(member_parsers=[], producer_modules=[])) \
        == "MANIFEST-SCHEMA-MISMATCH"


def test_a_v1_bundle_WITHOUT_the_pin_blocks_is_only_reported(tmp_path):
    """They did not exist then. Failing would make every archived bundle red."""
    st = _first_state(tmp_path, _man(schema="refinement_experiment_v1",
                                     member_parsers=[], producer_modules=[]))
    assert st != "MANIFEST-SCHEMA-MISMATCH"


def test_a_ZERO_MEMBER_experiment_is_refused(tmp_path):
    """`members: []` still passes the generic reader -- a bundle may publish
    none -- but a refinement experiment with no members is not a small
    experiment (owner P0-E3)."""
    assert _first_state(tmp_path, _man(members=[])) == "MANIFEST-SCHEMA-MISMATCH"


def test_an_UNKNOWN_schema_is_refused(tmp_path):
    """The old check only rejected a top-level that was not an object, so
    `"schema": "completely-unknown"` went straight through."""
    assert _first_state(tmp_path, _man(schema="made-up-v9")) == \
        "MANIFEST-SCHEMA-MISMATCH"
    assert _first_state(tmp_path, _man(artifact_type="something-else")) == \
        "MANIFEST-SCHEMA-MISMATCH"


def test_an_instrumented_v2_bundle_must_carry_analyses(tmp_path):
    assert _first_state(tmp_path, _man(instrumented=True, analyses=[])) == \
        "MANIFEST-SCHEMA-MISMATCH"


def test_GARBAGE_in_a_pin_block_fails_rather_than_crashing(tmp_path):
    """It raised AttributeError out of `--check`. A crash is not a verdict."""
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(_man(member_parsers=[42])))
    assert "MANIFEST-SCHEMA-MISMATCH" in [m["state"] for m in ec.members_of(p)]
