

"""The v2 manifest schema as a CLOSED tagged union (owner §8)."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_refine_manifest as rm  # noqa: E402


def synthetic_manifest(root):
    """A schema-valid v2 manifest built from nothing.

    The mutation tests below ran ONLY against the real bundle, so on a public
    clone every one of them skipped and the six rules were unchecked exactly
    where they are most likely to regress (Codex, generalized from the evidence
    chain). The rules are properties of the SCHEMA, not of any particular
    bundle, so they can and should be tested without private data.
    """
    def w(name, text):
        f = root / name
        f.write_text(text)
        return rm.sha256(f)

    pin = {"path": "p", "content_sha256": "d" * 64, "commit": "e" * 40,
           "blob_sha": "f" * 40}
    return {
        "schema": "refinement_experiment_v2",
        "artifact_type": "refinement_experiment", "arm": "reference",
        "precision": "f32", "instrumented": True, "decision_eligible": False,
        "is_refinement_chain": True,
        "members": [{"file": "n12.rezero.txt", "nsplit": 12,
                     "output_sha256": w("n12.rezero.txt", "x\n")}],
        "analyses": [
            {"file": f"n12.rezero.{k}.json", "analysis": k, "nsplit": 12,
             "sha256": w(f"n12.rezero.{k}.json", "{}\n"),
             "analyzer": f"harness/g33_{k}.py", "analyzer_sha256": "a" * 64,
             "analyzer_commit": "b" * 40, "analyzer_blob_sha": "c" * 40}
            for k in rm.REQUIRED_WHEN_INSTRUMENTED
        ] + [
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


def _real_manifest():
    store = Path.home() / "kdm6ad-g33m-migrate/number-003.bundles"
    m = next(store.glob("*/manifest.json"), None)
    if m is None:
        pytest.skip("decision-grade bundle not on this host")
    return json.loads(m.read_text())


def _arm(m):
    return next(a for a in m["analyses"] if a.get("analysis") == "arm_stream")


def test_the_REAL_bundles_still_validate():
    assert rm.validate(_real_manifest()) == []


@pytest.mark.parametrize("mutate,expect", [
    (lambda m: _arm(m).update(arm="anything"), "is not one of"),
    (lambda m: _arm(m).update(runtime_argv="not-a-list"), "must be a list of str"),
    (lambda m: _arm(m).update(runtime_argv=["9", "rezero", "3", "inverted"]),
     "contradicts nsplit"),
    (lambda m: _arm(m).update(runtime_argv=["12", "rezero", "3", "x2"]),
     "contradicts arm"),
])
def test_an_ARM_STREAM_entry_must_MATCH_the_run_it_names(mutate, expect,
                                                        tmp_path):
    """`arm` was any truthy string and `runtime_argv` any truthy value. The
    argv is what RAN and the fields are what the manifest SAYS: recording both
    without comparing them lets an entry describe a different run than the one
    it names (owner §8.1)."""
    m = synthetic_manifest(tmp_path)
    assert rm.validate(m) == [], "the base manifest must be valid first"
    mutate(m)
    bad = rm.validate(m)
    assert any(expect in b for b in bad), bad


def test_an_UNKNOWN_derived_analysis_kind_is_REFUSED(tmp_path):
    """Anything not "arm_stream" was accepted as a derived analysis, so a typo
    shipped as a new kind (owner §8.2). Added rather than renamed, so the
    minimum-set rule is not what catches it."""
    m = synthetic_manifest(tmp_path)
    extra = copy.deepcopy(next(a for a in m["analyses"]
                               if a.get("analysis") == "matched_closure"))
    extra["analysis"] = "matched_clsoure"
    extra["file"] = "n12.rezero.typo.json"
    m["analyses"].append(extra)
    assert any("unknown derived analysis" in b for b in rm.validate(m))


def test_an_INSTRUMENTED_bundle_must_carry_the_instrumented_analyses(tmp_path):
    """`instrumented: true` needed only a non-empty `analyses`, which a single
    arm_stream satisfies while carrying none of them (owner §8.3)."""
    m = synthetic_manifest(tmp_path)
    m["analyses"] = [a for a in m["analyses"] if a.get("analysis") == "arm_stream"]
    assert any("missing the analyses that make it instrumented" in b
               for b in rm.validate(m))


def test_the_TWO_statements_about_the_BINARY_must_agree(tmp_path):
    """The executable digest is recorded in build_artifacts AND inside
    build_provenance, and nothing compared them. Two statements about the same
    binary that are never checked against each other are one statement and one
    decoration (owner §8.4)."""
    m = synthetic_manifest(tmp_path)
    for a in m["build_artifacts"]:
        if a["file"] == "g33_refine_driver":
            a["sha256"] = "f" * 64
    assert any("names two different binaries" in b for b in rm.validate(m))


def test_DERIVED_ANALYSES_matches_the_PRODUCER_registry():
    """Declared in the manifest module because the producer imports it, so
    drift has to be a test failure rather than a silently widened union."""
    import g33_refine_experiment as xp
    assert set(rm.DERIVED_ANALYSES) == set(xp.ANALYSES) | {"metric_trajectory"}
    assert set(rm.REQUIRED_WHEN_INSTRUMENTED) == set(xp.ANALYSES)


# ---- the third union variant: analyses that run the DRIVER ------------------

def _multi(m):
    return next(a for a in m["analyses"]
                if a["analysis"] in rm.MULTI_RUN_ANALYSES)


def _with_multi(root):
    m = synthetic_manifest(root)
    m["analyses"].append({
        "file": "fx.ncmin_locality.json", "analysis": "ncmin_locality",
        "sha256": "e" * 64, "fixture": "fx",
        "decompositions": [[3], [1, 2], [2, 1], [1, 1, 1]],
        "ran": {"nsplit": 1, "carry": "rezero", "rho": "as-is", "width": 3,
                "decompositions": [[3], [1, 2], [2, 1], [1, 1, 1]]},
        # The RAW streams the analysis consumed. A multi_run entry without
        # them leaves the chain unable to reach the stdout its numbers came
        # from (owner P0-EVIDENCE-1).
        "inputs": [{"file": f"mr.n1.rezero.as-is.tiles-{'-'.join(map(str, d))}.txt",
                    "sha256": "f" * 64,
                    "runtime_argv": ["1", "rezero", ",".join(map(str, d)), "as-is"]}
                   for d in ([3], [1, 2], [2, 1], [1, 1, 1])],
        "analyzer": "harness/g33_ncmin_locality.py",
        "analyzer_sha256": "a" * 64, "analyzer_commit": "b" * 40,
        "analyzer_blob_sha": "c" * 40})
    return m


def test_a_MULTI_RUN_analysis_is_a_THIRD_variant(tmp_path):
    """It reads no member stream, so the derived contract's `nsplit` cannot
    describe it: `g33_ncmin_locality` is (driver, fixture) and runs the driver
    once per decomposition, while derived analyses are (stream, basis) per
    member. Keyed on the FIXTURE and the decompositions instead."""
    assert rm.validate(_with_multi(tmp_path)) == []
    assert "ncmin_locality" not in rm.DERIVED_ANALYSES, \
        "it must not be accepted as a per-member derived analysis"


@pytest.mark.parametrize("mutate,expect", [
    (lambda a: a.pop("fixture"), "needs the `fixture` it ran"),
    (lambda a: a.update(decompositions=[]), "non-empty list"),
    (lambda a: a.update(decompositions=[[1, 2], [1, 2]]), "repeats a decomposition"),
    (lambda a: a.update(decompositions=[[0, 3]]), "positive-int"),
    (lambda a: a.pop("analyzer_sha256"), "is missing analyzer_sha256"),
])
def test_a_MULTI_RUN_entry_must_say_WHAT_IT_RAN(tmp_path, mutate, expect):
    """A table with no record of which decompositions produced it cannot be
    re-derived, and an unpinned analyzer means the code that concluded it is
    unrecoverable."""
    m = _with_multi(tmp_path)
    assert rm.validate(m) == [], "the base must be valid first"
    mutate(_multi(m))
    assert any(expect in b for b in rm.validate(m)), rm.validate(m)


def test_a_MULTI_RUN_analysis_needs_NO_member_nsplit(tmp_path):
    """The member-nsplit check would reject it for having no nsplit -- it
    analyses no member."""
    m = _with_multi(tmp_path)
    assert "nsplit" not in _multi(m)
    assert rm.validate(m) == []


def test_a_MULTI_RUN_entry_records_the_CONFIG_IT_DROVE(tmp_path):
    """The analysis chooses its own nsplit/mode/rho -- `g33_ncmin_locality`
    drives the binary at nsplit=1/rezero/as-is regardless of what the bundle
    was produced with. Recording only the fixture let the entry read as though
    it shared the bundle's configuration, which it does not (Codex)."""
    m = _with_multi(tmp_path)
    e = _multi(m)
    e["ran"] = {"nsplit": 1, "carry": "rezero", "rho": "as-is", "width": 3,
                "decompositions": e["decompositions"]}
    assert rm.validate(m) == []

    e.pop("ran")
    assert any("needs `ran`" in b for b in rm.validate(m))


def test_the_DECOMPOSITIONS_must_agree_with_what_RAN(tmp_path):
    """Two records of the same fact, so they must be checked against each
    other -- the entry's list was derived from the FIXTURE while `ran` comes
    from the analysis output."""
    m = _with_multi(tmp_path)
    e = _multi(m)
    e["ran"] = {"nsplit": 1, "carry": "rezero", "rho": "as-is", "width": 3,
                "decompositions": [[3]]}
    assert any("decompositions disagree" in b for b in rm.validate(m))


@pytest.mark.parametrize("field,value,expect", [
    ("nsplit", "twelve", "not a positive integer"),
    ("nsplit", 0, "not a positive integer"),
    ("nsplit", None, "not a positive integer"),
    ("nsplit", True, "not a positive integer"),
    ("nsplit", 2 ** 31, "1..2147483647"),
    ("nsplit", 10 ** 30, "1..2147483647"),
    ("carry", "banana", "is not one of"),
    ("rho", "purple", "is not one of"),
])
def test_the_RUN_IDENTITY_is_TYPED_not_merely_present(tmp_path, field, value,
                                                       expect):
    """Checking only that the keys exist accepted nsplit="twelve", nsplit=0,
    carry="banana" and rho="purple" -- a run identity that cannot describe any
    run the driver would accept, since it error-stops on each (Codex).

    `nsplit=True` is included because a bool IS an int in Python, so a plain
    isinstance check would let it through."""
    m = _with_multi(tmp_path)
    assert rm.validate(m) == [], "the base must be valid first"
    _multi(m)["ran"][field] = value
    assert any(expect in b for b in rm.validate(m)), rm.validate(m)


def test_the_RUN_IDENTITY_vocabularies_are_the_DRIVERS():
    """Not a second list that can drift from what the binary accepts."""
    assert rm._CARRY_MODES == ("carry", "rezero")
    assert set(rm._RHO_ARMS) == {"as-is", "uniform", "inverted", "x2",
                                 "offset+", "offset-"}
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import g33_ncmin_locality as nl
    assert set(nl.RHO_MODES) == set(rm._RHO_ARMS), \
        "the analyzer and the schema disagree about the density arms"


def test_the_NSPLIT_BOUND_is_the_DRIVERS_int32_limit(tmp_path):
    """MEASURED against the real binary, not inferred:

      2147483647  accepted
      2147483648  ERROR STOP NSPLIT must be a positive integer

    The driver reads NSPLIT into a Fortran default INTEGER, so the read fails
    above int32. "Positive integer" alone admits identities it rejects, because
    Python ints are unbounded and the run being described is not (Codex)."""
    assert rm._MAX_NSPLIT == 2 ** 31 - 1

    m = _with_multi(tmp_path)
    _multi(m)["ran"]["nsplit"] = rm._MAX_NSPLIT
    assert rm.validate(m) == [], "the boundary value itself must be accepted"

    _multi(m)["ran"]["nsplit"] = rm._MAX_NSPLIT + 1
    assert any("1..2147483647" in b for b in rm.validate(m))


@pytest.mark.parametrize("dec,note", [
    ([[1, 1]], "sums to 2"),
    ([[5, 7]], "sums to 12"),
    ([[4]], "sums to 4"),
    ([[3], [1, 1]], "two decompositions of different domains"),
])
def test_a_decomposition_must_COVER_the_domain(tmp_path, dec, note):
    """The driver error-stops with "tile sizes must sum to B", so a
    decomposition summing to anything else names a run that could not have
    happened -- and a SET of them summing to different totals cannot all
    describe one domain (Codex). Measured against the real binary: 1,1 / 5,7 /
    4 all ERROR STOP on a 3-column fixture."""
    m = _with_multi(tmp_path)
    assert rm.validate(m) == [], "the base must be valid first"
    e = _multi(m)
    e["decompositions"] = dec
    e["ran"]["decompositions"] = dec
    assert any("do not sum to the domain width" in b
               for b in rm.validate(m)), f"{note}: {rm.validate(m)}"


def test_the_WIDTH_is_recorded_because_the_manifest_has_no_other_source(tmp_path):
    """`fixture` is only a name here; nothing in the manifest resolves it to a
    column count, and the schema cannot import the producer (which imports it).
    So the entry states the domain it ran over and is checked against itself."""
    m = _with_multi(tmp_path)
    assert "width" in _multi(m)["ran"]
    _multi(m)["ran"].pop("width")
    assert any("needs `ran` with" in b for b in rm.validate(m))


@pytest.mark.parametrize("dec", ["abc", [["a", "b"]], [None], [[1, 2], "x"], 3,
                                 [[True, True]]])
def test_a_malformed_decomposition_is_REJECTED_not_a_CRASH(tmp_path, dec):
    """`validate()` is contracted to RETURN violations, so raising on bad input
    is worse than missing it: the caller gets a traceback instead of a list.
    The width check reached `sum(d)` even when the shape check had already
    failed (Codex). `[[True, True]]` is included because bool subclasses int."""
    m = _with_multi(tmp_path)
    e = _multi(m)
    e["decompositions"] = dec
    e["ran"]["decompositions"] = dec
    assert rm.validate(m), "must be rejected"


def test_the_FOUR_analysis_registries_agree():
    """One name has to reach four places, in three files:

      ANALYSES                    what the producer RUNS
      DERIVED_ANALYSES            what the manifest ACCEPTS
      REQUIRED_WHEN_INSTRUMENTED  what an instrumented bundle MUST carry
      FINDING_bundle_analyses_v1  what the record SAYS a bundle carries

    `substep_schedule` reached them one at a time, each gap found separately:
    publication failed on the second, an instrumented manifest could silently
    omit the analysis on the third, and the finding disagreed with the code on
    the fourth. Checking them together is what stops the next analysis
    repeating it. They cannot be derived from one another -- the experiment
    imports the manifest, so the dependency runs one way only.
    """
    import g33_refine_experiment as rx
    runs = set(rx.ANALYSES)
    assert set(rm.REQUIRED_WHEN_INSTRUMENTED) == runs, (
        f"run but not required: {sorted(runs - set(rm.REQUIRED_WHEN_INSTRUMENTED))}; "
        f"required but never run: {sorted(set(rm.REQUIRED_WHEN_INSTRUMENTED) - runs)}")
    declared = set(rm.DERIVED_ANALYSES)
    assert declared == runs | {"metric_trajectory"}, (
        f"produced but not declared: {sorted(runs - declared)}; "
        f"declared but never produced: "
        f"{sorted(declared - runs - {'metric_trajectory'})}")


def test_a_multi_run_analysis_must_KEEP_its_raw_streams(tmp_path):
    """The chain reached the derived JSON, the analyzer and the binary, but
    never the stdout the numbers were computed from. Reproducible and retained
    are different contracts, and the density arms had always been kept this way
    (owner P0-EVIDENCE-1)."""
    m = _with_multi(tmp_path)
    assert rm.validate(m) == [], "the base manifest must be valid first"
    e = next(a for a in m["analyses"] if a.get("analysis") == "ncmin_locality")
    del e["inputs"]
    assert any("records no `inputs`" in b for b in rm.validate(m))


def test_a_kept_stream_must_be_PINNED_and_identifiable(tmp_path):
    """A filename alone does not bind bytes, and without runtime_argv nothing
    says WHICH decomposition the stream is."""
    for damage, probe in (
            (lambda s: s.pop("sha256"), "not pinned by a 64-hex sha"),
            (lambda s: s.pop("runtime_argv"), "records no 4-element runtime_argv"),
            (lambda s: s.__setitem__("runtime_argv", ["1", "rezero"]),
             "records no 4-element runtime_argv")):
        m = _with_multi(tmp_path)
        e = next(a for a in m["analyses"] if a.get("analysis") == "ncmin_locality")
        damage(e["inputs"][0])
        assert any(probe in b for b in rm.validate(m)), probe


def test_a_DECOMPOSITION_the_analysis_ran_must_have_a_kept_stream(tmp_path):
    """`ran` says which decompositions drove the binary. If one of them kept no
    stream, the entry describes a run the bundle cannot show."""
    m = _with_multi(tmp_path)
    e = next(a for a in m["analyses"] if a.get("analysis") == "ncmin_locality")
    e["inputs"] = [s for s in e["inputs"] if "1-1-1" not in s["file"]]
    assert any("kept no stream for it" in b for b in rm.validate(m))


def test_the_same_stream_listed_TWICE_is_refused(tmp_path):
    """Two analyses share a stream and both list it; one analysis listing it
    twice is a different thing, and it would double-count coverage."""
    m = _with_multi(tmp_path)
    e = next(a for a in m["analyses"] if a.get("analysis") == "ncmin_locality")
    e["inputs"].append(dict(e["inputs"][0]))
    assert any("twice" in b for b in rm.validate(m))


# ---- the run/analysis split: name the half that does not move (owner §12) ---

@pytest.mark.parametrize("mutate,label", [
    (lambda m: m.__setitem__("analyses", m["analyses"][:-1]), "drop an analysis"),
    (lambda m: m.pop("analyzer_sha256", None), "drop analyzer_sha256"),
    (lambda m: m.__setitem__("producer_modules", m["producer_modules"][:-1]),
     "drop a producer module"),
])
def test_the_RUN_identity_does_not_move_when_the_ANALYSES_do(tmp_path, mutate, label):
    """Adding an analyzer currently moves every bundle's address, so the whole
    archive is re-produced and every binding re-pointed -- paid five times in
    one day and growing with the archive (owner §12).

    `run_identity` names the half that does not change. Nothing stores it yet:
    recording it would move every manifest and force exactly the re-production
    it exists to retire, so the invariant is guarded before anything relies
    on it.
    """
    m = synthetic_manifest(tmp_path)
    before, before_addr = rm.run_identity(m), rm.identity_digest(m)
    mutate(m)
    if rm.identity_digest(m) == before_addr:
        # The mutation did not change this fixture -- it carries no such key --
        # so it cannot demonstrate anything. Skipping is honest; asserting
        # "the address moved" would fail on a no-op rather than on a defect.
        pytest.skip(f"the synthetic manifest has nothing to {label}")
    assert rm.run_identity(m) == before, f"{label} moved the run identity"
    # ...and it is a DIFFERENT question from the bundle address, which DID move.
    assert rm.identity_digest(m) != before_addr


@pytest.mark.parametrize("mutate,label", [
    (lambda m: m["build_artifacts"][0].__setitem__("sha256", "0" * 64),
     "the binary"),
    (lambda m: m.__setitem__("arm", "probe"), "the arm"),
    (lambda m: m.__setitem__("precision", "f64"), "the precision"),
    (lambda m: m["member_parsers"][0].__setitem__("content_sha256", "0" * 64),
     "the member parser"),
    (lambda m: m["tracked_build_inputs"][0].__setitem__("content_sha256", "0" * 64),
     "a tracked build input"),
])
def test_the_RUN_identity_MOVES_when_the_run_does(tmp_path, mutate, label):
    """The complement, so "stable" cannot degenerate into "constant".

    Mutates keys the SYNTHETIC manifest actually carries. The first version
    used module_sha256/fixture_sha256/repo_commit, which it does not, so every
    case skipped -- a sensitivity check that never ran, in the commit that
    fixed a regression for exactly that reason.
    """
    m = synthetic_manifest(tmp_path)
    before = rm.run_identity(m)
    mutate(m)
    assert rm.run_identity(m) != before, f"changing {label} left the run identity"


def test_a_member_digest_is_part_of_the_RUN(tmp_path):
    """The raw streams ARE the run. A member changing under a stable identity
    would make the name useless for the thing it is supposed to name."""
    m = synthetic_manifest(tmp_path)
    before = rm.run_identity(m)
    m["members"][0]["output_sha256"] = "0" * 64
    assert rm.run_identity(m) != before


def test_the_two_bundles_that_share_a_RUN_are_recognised(tmp_path):
    """number-003-cons and number-009-ice were produced from identical
    arguments and collapsed to one content address. The run identity says so
    independently, which is the property the split would rest on."""
    import g33_evidence_chain as ec
    have = ec.bundles()
    if not have:
        pytest.skip("no bundle store on this host")
    groups = {}
    for name, man in have.items():
        groups.setdefault(rm.run_identity(man), []).append(name.split("/")[1])
    shared = [sorted(v) for v in groups.values() if len(v) > 1]
    assert ["number-003-cons", "number-009-ice"] in shared, groups
