"""The chain from a claim to the run behind it (owner §9.2).

Fixture bundles rather than the real ones: the published bundles live outside the
repo and are absent in CI, so a test written against them would assert the host.
"""
import hashlib
import inspect
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_evidence_chain as ec  # noqa: E402
import g33_refine_manifest as rm  # noqa: E402


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
        ["matches"] + ["modules-unpinned"] * 3
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

def _pinned(bundle, write, commit, blob, path="harness/g33_matched_closure.py",
            content="0" * 64):
    body = b'{"x": 1}\n'
    (bundle / "a.json").write_bytes(body)
    write({"members": [], "findings": [],
           "analyses": [{"file": "a.json", "analysis": "matched_closure",
                         "sha256": _sha(body), "analyzer": path,
                         "analyzer_sha256": content,
                         "analyzer_commit": commit, "analyzer_blob_sha": blob}]})


def _head_blob(path):
    import subprocess
    r = subprocess.run(["git", "rev-parse", f"HEAD:{path}"], cwd=ec.REPO,
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def test_a_resolvable_commit_and_blob_PASSES_whatever_the_working_tree_holds(
        world):
    """The point of the change: the question is no longer "does today's file
    match" but "can the bytes this bundle ran be recovered" (owner §16-6). What
    proves the working tree is irrelevant is that the check reads the BLOB and
    never the file on disk.

    The pin must still be CONSISTENT -- `content_sha256` is the digest of the
    pinned blob (owner P0-2). An inconsistent one is the next test."""
    bundle, write = world
    path = "harness/g33_matched_closure.py"
    content = hashlib.sha256((ec.REPO / path).read_bytes()).hexdigest()
    _pinned(bundle, write, _head(), _head_blob(path), path, content)
    states = {m["state"] for a in ec.chain()[0]["artifacts"] for m in a["members"]}
    # `modules-unpinned` rides along: this fixture pins no producer modules.
    assert "matches" in states and not (states - {"matches", "modules-unpinned"})
    assert ec.check() == 0


def test_a_pin_whose_CONTENT_and_BLOB_disagree_FAILS(world):
    """`content_sha256` records what RAN and `blob_sha` names what is
    RECOVERABLE. Resolving the blob alone cannot tell them apart, so a bundle
    built from an uncommitted file passed while its own manifest recorded the
    disagreement (owner P0-2)."""
    bundle, write = world
    path = "harness/g33_matched_closure.py"
    _pinned(bundle, write, _head(), _head_blob(path), path, "0" * 64)
    states = {m["state"] for a in ec.chain()[0]["artifacts"] for m in a["members"]}
    assert "PIN-INCONSISTENT" in states
    assert ec.check() == 1


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
        ["modules-unpinned"] * 3   # one per pin block


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
    """A CONSISTENT pin: content_sha256 must be the digest of the pinned blob.
    `0`*64 was fine while the checker only resolved the blob; it is now the
    inconsistency the checker exists to catch (owner P0-2)."""
    path = f"harness/{mod}.py"
    return {"path": path, "content_sha256": hashlib.sha256(
                (ec.REPO / path).read_bytes()).hexdigest(),
            "commit": _head(), "blob_sha": ec._blob_at("HEAD", path)}


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
    for block in ("member_parsers", "producer_modules", "tracked_build_inputs"):
        assert (f"<{block}>", "modules-unpinned") in _module_rows(write)

    # Each block, alone: the others must still be reported missing.
    blocks = ("member_parsers", "producer_modules", "tracked_build_inputs")
    for one in blocks:
        rows = _module_rows(write, **{one: [_pin("g33_matched_closure")]})
        assert (f"<{one}>", "modules-unpinned") not in rows
        for other in blocks:
            if other != one:
                assert (f"<{other}>", "modules-unpinned") in rows

    every = _module_rows(write, **{b: [_pin("g33_matched_closure")] for b in blocks})
    assert not [f for f, st in every if st == "modules-unpinned"]


def test_an_unpinned_block_is_REPORTED_not_failed(world):
    """Old bundles legitimately predate these pins."""
    _, write = world
    _module_rows(write)
    assert ec.check() == 0


# ---- owner P0-E2: a new bundle cannot downgrade to the legacy contract -------

def _head() -> str:
    """The resolved HEAD sha. `"HEAD"` is a MOVING reference, so it cannot be a
    pin -- the validator rejects it, correctly, and the fixture used it for
    convenience."""
    import subprocess
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ec.REPO,
                          capture_output=True, text=True).stdout.strip()


def _man(**kw):
    pin = _pin("g33_matched_closure")
    base = {"artifact_type": "refinement_experiment",
            "schema": "refinement_experiment_v2",
            "members": [{"file": "n3.rezero.txt", "output_sha256": "0" * 64}],
            "member_parsers": [pin], "producer_modules": [pin],
            "tracked_build_inputs": [pin],
            "build_provenance": {"repo_commit": "x"}, "arm": "reference",
            "precision": "f32", "analyses": [], "instrumented": False,
            "decision_eligible": False,
            "build_artifacts": [{"file": "g33_refine_driver",
                                 "sha256": "0" * 64}]}
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


# ---- owner P0-2: one typed validator, not truthiness ------------------------

def test_the_checker_uses_the_SCHEMAS_OWN_validator():
    """It carried its own copy, which tested only truthiness. One validator,
    called by the producer before publishing and by this checker before
    believing anything, is what stops a bundle being valid to one and invalid to
    the other."""
    import g33_refine_manifest as rm

    assert ec._schema_violations({"x": 1}) == rm.validate({"x": 1})


@pytest.mark.parametrize("name,patch", [
    # `[{}]` is a non-empty list, so truthiness accepted it; the entries then
    # became `analyzer-unpinned`, a PASSING state kept for legacy bundles.
    ("empty-dict pins", {"member_parsers": [{}], "producer_modules": [{}]}),
    # Deleting the key deleted the `analyses` requirement with it.
    ("no instrumented", {"instrumented": None}),
    ("decision_eligible true", {"decision_eligible": True}),
    ("bogus arm", {"arm": "made-up"}),
    ("bogus precision", {"precision": "f128"}),
    # This raised KeyError out of `--check`. A crash is not a verdict.
    ("malformed member", {"members": [{}]}),
    ("short blob sha", {"member_parsers": [{"path": "x", "content_sha256": "0" * 64,
                                            "commit": "0" * 40, "blob_sha": "0" * 12}]}),
])
def test_a_v2_manifest_that_LOOKS_complete_but_is_not_FAILS(tmp_path, name, patch):
    man = _man()
    for k, v in patch.items():
        if v is None:
            man.pop(k, None)
        else:
            man[k] = v
    assert _first_state(tmp_path, man) == "MANIFEST-SCHEMA-MISMATCH", name


def test_a_COMPLETE_v2_manifest_passes(tmp_path):
    """A validator that refused everything would also pass the tests above."""
    import g33_refine_manifest as rm

    assert rm.validate(_man()) == []


# ---- closeout mode: absence must not read as a pass (owner priority 6) ------

def test_ABSENCE_passes_a_routine_check_and_FAILS_a_closeout():
    """The two questions are different. CI cannot demand bundles that live
    outside the repo by design; a closeout cannot record "we could not check
    this" as "we checked and it is fine"."""
    for state in ec.EXCUSED_BY_ABSENCE:
        assert ec.verdict(state) is False, f"{state} must pass a routine check"
        assert ec.verdict(state, require_available=True) is True, \
            f"{state} must fail a closeout"


def test_the_STRICT_mode_does_not_weaken_anything():
    """It only ever adds failures: every state that fails routinely must still
    fail, or a closeout could pass something CI rejects."""
    for state in ec.FAILING_STATES | {"not-a-real-state"}:
        assert ec.verdict(state) is True
        assert ec.verdict(state, require_available=True) is True


def test_a_claim_with_NO_artifacts_is_INVISIBLE_to_the_artifact_walk():
    """The largest absence there is -- a measurement whose run was never pinned
    -- yields NO rows to walk, so the artifact loop alone could never see it.
    The claim declares it, and in a closeout the declaration is the finding."""
    rows = ec.chain()
    unpinned = [r for r in rows
                if r["artifact_status"] == "historical_unavailable"]
    assert unpinned, "expected claims still declaring their run unreachable"
    assert all(not r["artifacts"] for r in unpinned), (
        "these carry no artifacts, which is exactly why the walk cannot fail "
        "them and the claim-level check is needed")


def test_the_ROUTINE_check_still_PASSES(capsys):
    """The strict mode is opt-in. Turning absence into a failure by default
    would break every CI run on evidence that is unavailable by design."""
    assert ec.check() == 0


def test_the_CLOSEOUT_check_FAILS_today_and_says_why(capsys):
    """C4 is on hold for exactly this reason, so the tool must say so rather
    than reporting a clean closeout."""
    assert ec.check(require_available=True) == 1
    out = capsys.readouterr().out
    assert "historical_unavailable" in out
    assert "blocker(s) under --require-available" in out
    assert "the right answer for CI and the wrong one" in out


def test_SOURCE_only_claims_are_NOT_failed_by_the_closeout():
    """`not_applicable` means no run artifact APPLIES, not that one is missing.
    Failing those would make the closeout unsatisfiable by construction."""
    source = [r for r in ec.chain() if r["evidence_kind"] == "source"]
    assert source, "no source-only claims -- this check would be vacuous"
    assert all(r["artifact_status"] != "historical_unavailable" for r in source)


# ---- claim figures vs the pinned artifact (owner priority 7) ----------------

_LEG = ("kdm6ad-g33m-migrate/number-003.bundles/"
        "ae6234bf4ce333e124cacae1a28d236a11ed7fa03cb79fdcf4a1c3a4fd93c34e")
_TRUTH = {"file": f"{_LEG}/n12.rezero.defect_magnitude.json",
          "path": "rows.main/nr/1.of_surface_flux",
          "value": 0.150035513206531, "tolerance": 0.0}
_COVERED = {_TRUTH["file"]}
_HERE = {_LEG: "matches"}


def _bundles_present():
    return (ec.HOME / _TRUTH["file"]).is_file()


needs_bundle = pytest.mark.skipif(not _bundles_present(),
                                  reason="decision-grade bundle not on this host")


@needs_bundle
def test_the_PUBLISHED_figures_are_IN_the_pinned_artifact():
    """The claim's prose said 15.0036/13.3377/11.8402% and nothing checked that
    the pinned run actually produced them. A figure quoted in a claim and a
    figure a run emitted were two unrelated facts."""
    states = [v["state"] for r in ec.chain() for v in r["values"]]
    assert states, "no claim declares a figure -- the check would be vacuous"
    assert set(states) == {"value-matches"}, [
        (r["id"], v["path"], v["state"]) for r in ec.chain() for v in r["values"]
        if v["state"] != "value-matches"]


@needs_bundle
def test_a_LAST_DIGIT_change_is_caught():
    """Exact by default. The claim asserts these reproduced EXACTLY, so an
    approximate check would not be testing what the claim says."""
    assert ec.resolve_value(_TRUTH, _COVERED, _HERE)["state"] == "value-matches"
    off = {**_TRUTH, "value": 0.150035513206532}
    assert ec.resolve_value(off, _COVERED, _HERE)["state"] == "VALUE-MISMATCH"
    assert ec.resolve_value({**off, "tolerance": 1e-15},
                            _COVERED, _HERE)["state"] == "value-matches"


@needs_bundle
@pytest.mark.parametrize("mutation,expected", [
    ({"path": "rows.main/nr/1.of_surface_fluxx"}, "VALUE-PATH-ABSENT"),
    ({"file": f"{_LEG}/nope.json"}, "VALUE-FILE-ABSENT"),
    ({"path": "note"}, "VALUE-NOT-NUMERIC"),
])
def test_every_way_a_BINDING_can_be_WRONG_is_a_FAILURE(mutation, expected):
    """A typo in the path must not read as agreement, and a missing file must
    not read as one either."""
    w = {**_TRUTH, **mutation}
    r = ec.resolve_value(w, _COVERED | {w["file"]}, _HERE)
    assert r["state"] == expected
    assert ec.verdict(r["state"]) is True


def test_a_figure_may_only_be_bound_to_a_DIGEST_VERIFIED_file():
    """The check that makes the others mean anything, and the seam that was
    still open: requiring the file to sit in a pinned bundle DIRECTORY is not
    the same as requiring a digest to cover it. A JSON planted beside the
    manifest resolved and reported `value-matches` (Codex). Beside the evidence
    is not the evidence."""
    loose = {**_TRUTH, "file": "kdm6ad-g33m-migrate/elsewhere/x.json"}
    assert ec.resolve_value(loose, _COVERED, _HERE)["state"] == \
        "VALUE-UNPINNED-FILE"
    assert ec.verdict("VALUE-UNPINNED-FILE") is True


@needs_bundle
def test_a_file_PLANTED_in_a_pinned_bundle_is_not_covered_by_it():
    """The attack, run for real: write a JSON into the pinned bundle directory
    carrying the number a claim wants, and bind to it."""
    rogue = ec.HOME / _LEG / "rogue_test_only.json"
    rogue.write_text(json.dumps({"rows": {"main/nr/1":
                                          {"of_surface_flux": 0.999}}}))
    try:
        covered = {f"{Path(a['path']).parent}/{m['file']}"
                   for r in ec.chain() for a in r["artifacts"]
                   if a["state"] == "matches"
                   for m in a["members"] if m["state"] == "matches"}
        assert str(rogue.relative_to(ec.HOME)) not in covered
        r = ec.resolve_value({"file": str(rogue.relative_to(ec.HOME)),
                              "path": "rows.main/nr/1.of_surface_flux",
                              "value": 0.999, "tolerance": 0.0},
                             covered, _HERE)
        assert r["state"] == "VALUE-UNPINNED-FILE"
    finally:
        rogue.unlink()


@pytest.mark.parametrize("manifest_state,member_state", [
    ("MISMATCH", "matches"),      # the manifest itself was tampered with
    ("matches", "MISMATCH"),      # the analysis file was
])
def test_a_BROKEN_digest_anywhere_on_the_link_breaks_the_binding(
        manifest_state, member_state):
    """`covered` is built only from a manifest that MATCHED and members that
    MATCHED, so the figure cannot outlive a break anywhere on that chain."""
    arts = [{"path": f"{_LEG}/manifest.json", "state": manifest_state,
             "members": [{"file": "n12.rezero.defect_magnitude.json",
                          "state": member_state}]}]
    covered = {f"{Path(a['path']).parent}/{m['file']}"
               for a in arts if a["state"] == "matches"
               for m in a["members"] if m["state"] == "matches"}
    r = ec.resolve_value(_TRUTH, covered, {_LEG: manifest_state})
    assert r["state"] == "VALUE-UNPINNED-FILE"


def test_a_bundle_ABSENT_from_this_host_stays_EXCUSED_routinely():
    """On a host without the private bundles NOTHING is covered. Failing there
    would fail the routine check everywhere the evidence legitimately is not --
    the very thing --require-available exists to keep separate."""
    r = ec.resolve_value(_TRUTH, set(), {_LEG: "unavailable"})
    assert r["state"] == "value-unavailable"
    assert ec.verdict(r["state"]) is False
    assert ec.verdict(r["state"], require_available=True) is True


def test_the_binding_is_DECLARED_not_DISCOVERED():
    """Searching the artifacts for a number equal to the published one would
    bind to whatever sat near it. On this fixture 1.0 appears at five unrelated
    paths across two files, so "100.00%" would have matched all five."""
    src = (ec.__file__ and open(ec.__file__).read())
    assert "Declared, never discovered" in src
    for c in ec.claims():
        for w in c["expected_values"]:
            assert w["file"] and w["path"], "both must be named explicitly"


def test_a_key_containing_a_DOT_makes_the_path_AMBIGUOUS():
    """The flattened path joins keys with ".", so a key that contains one could
    resolve two different structures to the same string. Refuse rather than
    pick."""
    assert ec.flatten({"a": {"b": 1}}) == {"a.b": 1}
    assert "." in str(list({"a.b": {"c": 1}})[0])
    assert ec._keys_of({"a.b": {"c": 1}}) == ["a.b", "c"]


def test_TOLERANCE_defaults_to_EXACT_when_unstated():
    for c in ec.claims():
        for w in c["expected_values"]:
            assert w["tolerance"] == 0.0, \
                f"{c['id']}: a tolerance was introduced -- state why in the claim"


def test_every_member_row_says_WHERE_its_digest_was_verified():
    """Two namespaces meet in this list: files hashed at <bundle>/<file>, and
    provenance resolved from a pinned commit in the SOURCE TREE. Without
    `scope` they are indistinguishable, and any consumer joining a path under
    the bundle silently mixes them."""
    for r in ec.chain():
        for a in r["artifacts"]:
            for m in a["members"]:
                assert m.get("scope") in ("bundle", "repo"), \
                    f"{a['path']} -> {m.get('file')}: unscoped row"


@needs_bundle
def test_covered_contains_NO_repo_paths():
    """A repo path joined under the bundle names a location NOTHING hashed.
    Through `covered_files`, so this checks the shipped filter."""
    covered = {c for r in ec.chain() for c in ec.covered_files(r["artifacts"])}
    assert covered
    assert not [c for c in covered if "/harness/" in c]


def _artifact_rows():
    """One pinned manifest carrying both kinds of row, as `members_of` returns
    them: an analysis hashed IN the bundle, and provenance resolved from the
    source tree. No private bundle needed, so this runs in public CI -- where
    the first version of this regression was skipped entirely (Codex)."""
    return [{"path": f"{_LEG}/manifest.json", "state": "matches", "members": [
        {"file": "n12.rezero.defect_magnitude.json", "state": "matches",
         "scope": "bundle"},
        {"file": "harness/g33_defect_magnitude.py", "state": "matches",
         "scope": "repo"},
    ]}]


def test_a_PROVENANCE_PATH_COLLISION_cannot_cover_a_file():
    """The exploit, against the PRODUCTION filter.

    Provenance rows verify `harness/*.py` in the repo. Joining those under the
    bundle produced entries like <bundle>/harness/g33_defect_magnitude.py, and a
    JSON written at exactly that path made a claim's figure resolve against a
    file whose digest was never taken there -- the guarantee belonged to the
    repo file of the same name (Codex).

    Asserts the collision is still DEMONSTRABLE on the unscoped join before
    checking the real filter rejects it, so this cannot pass by the exploit
    quietly ceasing to exist.
    """
    arts = _artifact_rows()
    rogue = f"{_LEG}/harness/g33_defect_magnitude.py"

    unscoped = {f"{Path(a['path']).parent}/{m['file']}"
                for a in arts if a["state"] == "matches"
                for m in a["members"] if m["state"] == "matches"}
    assert rogue in unscoped, "the collision must still be demonstrable"

    covered = ec.covered_files(arts)          # the PRODUCTION filter
    assert rogue not in covered
    assert f"{_LEG}/n12.rezero.defect_magnitude.json" in covered, \
        "the legitimate member must survive the filter"

    r = ec.resolve_value({"file": rogue, "path": "rows.main/nr/1.of_surface_flux",
                          "value": 0.999, "tolerance": 0.0},
                         covered, {_LEG: "matches"})
    assert r["state"] == "VALUE-UNPINNED-FILE"
    assert ec.verdict(r["state"]) is True


def test_the_collision_test_uses_the_PRODUCTION_filter():
    """A guard on the guard. The first version re-derived its own filter, on
    the repo-path prefix, and would have passed with `covered_files` deleted --
    testing a rule that existed only in the test."""
    assert "def covered_files(" in Path(ec.__file__).read_text()
    # Every OTHER test's source -- excluding this one by construction, since a
    # guard that greps the whole file matches the literal it is grepping for.
    me = "test_the_collision_test_uses_the_PRODUCTION_filter"
    others = "\n".join(
        inspect.getsource(f) for n, f in list(globals().items())
        if n.startswith("test_") and n != me and callable(f))
    assert "ec.covered_files(arts)" in others, \
        "the collision regression must exercise the production filter"
    # No test may BUILD a covered set by hand; they must call the real one.
    assert 'scope") == "bundle"' not in others, \
        "a hand-rolled stand-in for the production filter came back"


@needs_bundle
def test_the_REAL_bundle_agrees_with_the_synthetic_rows():
    """The synthetic rows above must describe the real thing, or the CI test
    guards a shape that does not occur."""
    scopes = {m.get("scope") for r in ec.chain() for a in r["artifacts"]
              for m in a["members"]}
    assert scopes == {"bundle", "repo"}, scopes
    assert any("/harness/" in f"{Path(a['path']).parent}/{m['file']}"
               for r in ec.chain() for a in r["artifacts"]
               if a["state"] == "matches"
               for m in a["members"]
               if m["state"] == "matches" and m.get("scope") == "repo"), \
        "no repo-scoped row would collide -- the exploit shape is gone"


def test_every_member_row_says_WHERE_its_digest_was_verified():
    """Two namespaces meet in this list: files hashed at <bundle>/<file>, and
    provenance resolved from a pinned commit in the SOURCE TREE. Without
    `scope` they are indistinguishable, and any consumer joining a path under
    the bundle silently mixes them."""
    for r in ec.chain():
        for a in r["artifacts"]:
            for m in a["members"]:
                assert m.get("scope") in ("bundle", "repo"), \
                    f"{a['path']} -> {m.get('file')}: unscoped row"


@needs_bundle
def test_covered_contains_NO_repo_paths():
    """A repo path joined under the bundle names a location NOTHING hashed.
    Through `covered_files`, so this checks the shipped filter."""
    covered = {c for r in ec.chain() for c in ec.covered_files(r["artifacts"])}
    assert covered
    assert not [c for c in covered if "/harness/" in c]


def test_the_CHAIN_production_path_applies_the_scope_filter(tmp_path,
                                                             monkeypatch):
    """The wiring, not the filter in isolation.

    Calling `covered_files` and `resolve_value` directly proves the filter
    works; it does NOT prove `chain()` uses it. Reverting `chain()` to an
    unscoped comprehension would leave those tests green (Codex). This drives
    the real `chain()` over a real bundle on disk and reads the states it
    produced.

    Only `members_of` is stubbed -- the collision is about how `chain()`
    CONSUMES member rows, and the two shapes it returns are asserted against the
    real bundles by test_the_REAL_bundle_agrees_with_the_synthetic_rows.
    """
    bundle = tmp_path / "bundle"
    (bundle / "harness").mkdir(parents=True)
    manifest = bundle / "manifest.json"
    manifest.write_text('{"members": []}')
    (bundle / "a.json").write_text(json.dumps({"v": 1.5}))
    # A file at exactly the path a repo-scoped provenance row would produce.
    (bundle / "harness" / "p.py").write_text(json.dumps({"v": 0.999}))

    claim = {
        "id": "T-1", "evidence": [], "status": "active",
        "artifact_status": "pinned", "evidence_kind": "measurement",
        "artifacts": {"bundle/manifest.json": ec.sha256(manifest)},
        "expected_values": [
            {"file": "bundle/a.json", "path": "v",
             "value": 1.5, "tolerance": 0.0},
            {"file": "bundle/harness/p.py", "path": "v",
             "value": 0.999, "tolerance": 0.0},
        ],
    }
    monkeypatch.setattr(ec, "HOME", tmp_path)
    monkeypatch.setattr(ec, "claims", lambda: [claim])
    monkeypatch.setattr(ec, "bundles", lambda: {})
    monkeypatch.setattr(ec, "members_of", lambda p: [
        {"file": "a.json", "state": "matches", "scope": "bundle"},
        {"file": "harness/p.py", "state": "matches", "scope": "repo"},
    ])

    states = {v["file"]: v["state"] for v in ec.chain()[0]["values"]}
    assert states["bundle/a.json"] == "value-matches", \
        "a genuinely covered figure must still resolve through chain()"
    assert states["bundle/harness/p.py"] == "VALUE-UNPINNED-FILE", \
        "chain() let a provenance-path collision cover a file"
    assert ec.check() == 1, "and the collision must fail the routine check"


def test_an_UNRECOVERABLE_legacy_analyzer_blocks_a_CLOSEOUT():
    """`legacy-analyzer-changed` means no commit pin, only a content digest,
    and the working-tree file no longer matches it -- so the exact analyzer
    bytes that produced the analysis cannot be recovered from anywhere.

    Routine: reportable, because old bundles legitimately predate the pin.
    Closeout: a blocker, like every other unrecoverable entry (owner §10)."""
    assert ec.verdict("legacy-analyzer-changed") is False
    assert ec.verdict("legacy-analyzer-changed", require_available=True) is True
    assert "legacy-analyzer-changed" in ec.EXCUSED_BY_ABSENCE


def test_the_legacy_analyzer_blocker_is_currently_UNEXERCISED():
    """Stated, not assumed. No bundle in the registry carries this state today,
    so the guard is correct and inert: it protects a case that does not yet
    occur. If one appears, the closeout count moves and that is the point."""
    live = {m["state"] for r in ec.chain() for a in r["artifacts"]
            for m in a["members"]}
    assert "legacy-analyzer-changed" not in live, (
        "a bundle now carries an unrecoverable legacy analyzer -- the closeout "
        "blocker count should have risen; update this test deliberately")


@needs_bundle
def test_an_ARM_STREAM_is_not_asked_for_an_ANALYZER_it_cannot_have():
    """`members_of` ran `_analyzer_state` over EVERY analysis entry, including
    `arm_stream`s -- which are raw driver runs with no analyzer by design, as
    the schema's own tagged union says. Every one reported "no analyzer
    recorded", and --require-available turned each into a closeout blocker
    demanding something that must not exist.

    30 of the 58 blockers were that. A blocker with no possible resolution is
    not a blocker; it is noise hiding the real ones."""
    rows = [m for r in ec.chain() for a in r["artifacts"] for m in a["members"]]
    assert rows, "no members walked -- the check would be vacuous"
    assert not [m for m in rows if m.get("file") == "<no analyzer recorded>"]


@needs_bundle
def test_DERIVED_analyses_are_still_analyzer_checked():
    """The other direction, so the fix cannot have silenced the real check."""
    import json
    man = ec.HOME / _LEG / "manifest.json"
    kinds = {a.get("analysis") for a in json.loads(man.read_text())["analyses"]}
    assert kinds - {"arm_stream"}, "this bundle must carry derived analyses"
    states = {m["state"] for m in ec.members_of(man) if m.get("scope") == "repo"}
    assert states, "derived analyses must still produce analyzer rows"


@needs_bundle
def test_the_CLOSEOUT_blockers_are_now_only_REAL_ones(capsys):
    """What is left is the actual migration debt, not an artefact of the
    walker: claims with no reachable run, and bundles that predate the module
    pins."""
    assert ec.check(require_available=True) == 1
    out = capsys.readouterr().out
    # `id: path -> file: STATE  [note]` -- the state follows the LAST colon
    # before the bracket, not the first token after the arrow, which is the
    # file placeholder.
    kinds = {ln.split("[")[0].rsplit(":", 1)[-1].strip()
             for ln in out.splitlines() if " -> " in ln}
    assert kinds, "no member blocker lines parsed -- this check would be vacuous"
    assert kinds == {"modules-unpinned"}, (
        f"unexpected member blocker kinds {sorted(kinds)}")
    claim_level = [ln for ln in out.splitlines()
                   if " -> " not in ln and ln.startswith("G33")]
    assert len(claim_level) == 22, (
        f"{len(claim_level)} claim-level blockers, expected 22 -- if a claim "
        f"was migrated this moves, and that is the point")
    assert "analyzer-unpinned" not in out, \
        "the unresolvable arm_stream blockers must stay gone"
    assert "historical_unavailable" in out, "the real migration debt must show"


def _synthetic_bundle(root):
    """A schema-valid v2 bundle carrying one derived analysis and one
    arm_stream. No private data, so this runs on a public clone -- where the
    bundle-backed version of this check produces zero member rows and its
    non-empty guard fails (Codex)."""
    def w(name, text):
        p = root / name
        p.write_text(text)
        return rm.sha256(p)

    pin = {"path": "p", "content_sha256": "d" * 64, "commit": "e" * 40,
           "blob_sha": "f" * 40}
    man = {
        "schema": "refinement_experiment_v2",
        "artifact_type": "refinement_experiment", "arm": "reference",
        "precision": "f32", "instrumented": False, "decision_eligible": False,
        "is_refinement_chain": True,
        "members": [{"file": "n12.rezero.txt", "nsplit": 12,
                     "output_sha256": w("n12.rezero.txt", "x\n")}],
        "analyses": [
            {"file": "n12.rezero.matched_closure.json",
             "analysis": "matched_closure", "nsplit": 12,
             "sha256": w("n12.rezero.matched_closure.json", "{}\n"),
             "analyzer": "harness/g33_matched_closure.py",
             "analyzer_sha256": "a" * 64, "analyzer_commit": "b" * 40,
             "analyzer_blob_sha": "c" * 40},
            {"file": "n12.rezero.uniform.txt", "analysis": "arm_stream",
             "nsplit": 12, "sha256": w("n12.rezero.uniform.txt", "y\n"),
             "arm": "uniform",
             "runtime_argv": ["12", "rezero", "3", "uniform"]}],
        "build_artifacts": [{"file": "g33_refine_driver",
                             "sha256": w("g33_refine_driver", "#!f\n")}],
        "build_provenance": {"executable_sha256": rm.sha256(
            root / "g33_refine_driver")},
        "member_parsers": [pin], "producer_modules": [pin],
        "tracked_build_inputs": [pin],
    }
    (root / "manifest.json").write_text(json.dumps(man))
    return root / "manifest.json"


def test_the_synthetic_bundle_is_SCHEMA_VALID(tmp_path):
    """Or the check below would be testing the schema's rejection path."""
    manifest = _synthetic_bundle(tmp_path)
    assert rm.validate(json.loads(manifest.read_text())) == []


def test_ARM_STREAMS_produce_no_analyzer_row_WITHOUT_private_data(tmp_path):
    """The rule, on a public clone. An `arm_stream` is a raw driver run with no
    analyzer by design, so it must contribute no analyzer row -- while a
    DERIVED analysis still does, or the fix would have silenced the real
    check."""
    rows = ec.members_of(_synthetic_bundle(tmp_path))
    assert rows, "no rows walked -- this check would be vacuous"
    assert not [r for r in rows if r.get("file") == "<no analyzer recorded>"]
    repo_rows = [r for r in rows if r.get("scope") == "repo"]
    assert repo_rows, "the derived analysis must still be analyzer-checked"
