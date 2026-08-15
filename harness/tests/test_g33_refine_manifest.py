

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

    pin = {"path": "harness/p.py", "content_sha256": "d" * 64,
           "commit": "e" * 40, "blob_sha": "f" * 40}
    # The role graph has to AGREE with the pins, so both come from one list:
    # a graph that omits a pinned module filters it out of every id, and one
    # that names an unpinned module describes code the archive does not hold.
    _mods = ["p"] + [f"g33_{k}" for k in sorted(set(rm.DERIVED_ANALYSES)
                                                | set(rm.MULTI_RUN_ANALYSES))]
    _pins = [{**pin, "path": f"harness/{m}.py"} for m in _mods]
    return {
        # rm.SCHEMA, not a literal: pinned to "v2" this fixture went on
        # testing the previous contract after the bump, and every v3
        # check written against it asserted nothing.
        "schema": rm.SCHEMA,
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
             # TYPED beside the literal command line (owner priority 5): the
             # argv is four strings and only two positions were ever compared.
             "ran": {"nsplit": 12, "carry": "rezero", "width": 3,
                     "rho": "uniform"},
             "runtime_argv": ["12", "rezero", "3", "uniform"]}],
        "build_artifacts": [{"file": "g33_refine_driver",
                             "sha256": w("g33_refine_driver", "#!f\n")}],
        "build_provenance": {"executable_sha256": rm.sha256(
            root / "g33_refine_driver")},
        "member_parsers": [pin], "producer_modules": _pins,
        "tracked_build_inputs": [pin],
        # The role graph the layered ids are derived under. Required from v3:
        # without it they follow whichever checkout reads the manifest, which
        # is the coupling the block exists to remove (owner priority 8).
        "identity": {
            # rm.IDENTITY_SCHEMA, not a literal -- a fixture pinned to the
            # old tag tests the previous contract after a bump.
            "schema": rm.IDENTITY_SCHEMA,
            "role_graph": {m: (["run"] if m == "p" else ["analysis"])
                           for m in _mods},
            # The seed of each reach entry, which is also the dispatch cut.
            "analysis_seeds": {k: f"g33_{k}" for k in
                               set(rm.DERIVED_ANALYSES)
                               | set(rm.MULTI_RUN_ANALYSES)},
            "analysis_reach": {k: [f"g33_{k}"] for k in
                               set(rm.DERIVED_ANALYSES)
                               | set(rm.MULTI_RUN_ANALYSES)},
        },
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
    # EVERY position, which is what v3 adds. Under v2 only [0] and [3] were
    # compared, so a bundle could record `carry` and a domain width nobody
    # read -- half the run identity (owner priority 5).
    (lambda m: _arm(m).update(runtime_argv=["9", "rezero", "3", "uniform"]),
     "runtime_argv[0]"),
    (lambda m: _arm(m).update(runtime_argv=["12", "carry", "3", "uniform"]),
     "runtime_argv[1]"),
    (lambda m: _arm(m).update(runtime_argv=["12", "rezero", "5", "uniform"]),
     "runtime_argv[2]"),
    (lambda m: _arm(m).update(runtime_argv=["12", "rezero", "3", "x2"]),
     "runtime_argv[3]"),
    # ...and the typed block must agree with the entry's own fields, or it is
    # a third statement nobody compares.
    (lambda m: _arm(m).update(nsplit=9), "contradicts nsplit"),
    (lambda m: _arm(m).update(arm="x2"), "contradicts arm"),
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


@pytest.mark.parametrize("mutate,expect", [
    (lambda r: r.pop("carry"), "needs `ran` with"),
    (lambda r: r.pop("width"), "needs `ran` with"),
    (lambda r: r.update(nsplit="twelve"), "not a positive integer"),
    (lambda r: r.update(nsplit=0), "not a positive integer"),
    (lambda r: r.update(nsplit=True), "not a positive integer"),
    (lambda r: r.update(carry="banana"), "ran.carry"),
    (lambda r: r.update(rho="purple"), "ran.rho"),
    (lambda r: r.update(width=0), "ran.width"),
    (lambda r: r.update(width="three"), "ran.width"),
])
def test_an_ARM_RUN_IDENTITY_is_TYPED_not_merely_present(mutate, expect,
                                                        tmp_path):
    """The same rule the multi-run block already had, on the same vocabularies.
    They are the DRIVER's: it error-stops on anything else, so a manifest
    declaring anything else names a run that could not have happened."""
    m = synthetic_manifest(tmp_path)
    assert rm.validate(m) == []
    mutate(_arm(m)["ran"])
    assert any(expect in b for b in rm.validate(m)), rm.validate(m)


def test_a_v2_arm_stream_is_GRANDFATHERED_not_broken(tmp_path):
    """Five published bundles carry v2 arm streams with no `ran`. A new
    required field on v2 would either invalidate them or have to be
    opt-out-by-omission -- which is the defect the v2 bump itself was for. So
    the requirement is a VERSION, and the old contract still validates the old
    bundles."""
    m = synthetic_manifest(tmp_path)
    del _arm(m)["ran"]
    assert any("needs `ran` with" in b for b in rm.validate(m)),         "v3 must require it"
    m["schema"] = "refinement_experiment_v2"
    assert not any("ran" in b for b in rm.validate(m)),         "v2 predates the block and must not be failed for lacking it"


def test_the_TWO_ran_blocks_use_ONE_spelling(tmp_path):
    """An arm stream and a multi-run analysis both carry `ran`, and the first
    draft of the arm block said `mode` where the multi-run block says `carry`
    -- two words for the driver's one argument, in one manifest."""
    m = _with_multi(tmp_path)
    assert set(rm._RAN_CORE) <= set(_multi(m)["ran"]),         "the multi-run block must carry the shared core under the same names"
    assert set(rm._RAN_CORE) <= set(_arm(m)["ran"])
    assert [f for _pos, f in rm._ARGV_TO_RAN] == list(rm._RAN_CORE),         "the argv mapping and the core field list must not drift apart"


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


# ---- applicability: an analysis is not valid on every stream (priority 6) ----

def test_EVERY_analysis_the_producer_runs_declares_its_PRECISIONS():
    """The fifth place a name has to reach. Without it a new analysis is valid
    at every precision by the act of not being listed, which is the fail-open
    shape the other four registries exist to close."""
    import g33_refine_experiment as xp
    runs = set(xp.ANALYSES) | set(xp.MULTI_RUN) | {"metric_trajectory"}
    assert set(rm.ANALYSIS_PRECISIONS) == runs, (
        f"run but unclassified: {sorted(runs - set(rm.ANALYSIS_PRECISIONS))}; "
        f"classified but never run: {sorted(set(rm.ANALYSIS_PRECISIONS) - runs)}")
    for name, precisions in rm.ANALYSIS_PRECISIONS.items():
        assert "f32" in precisions, (
            f"{name} is not defined at the REFERENCE precision, which is the "
            f"only one that produces decision evidence")


def test_an_unclassified_analysis_is_refused_rather_than_assumed_valid():
    with pytest.raises(KeyError, match="no declared precision applicability"):
        rm.applicable("something_new", "f32")


def test_the_f32_only_analyses_are_the_ones_that_replay_or_read_G33R():
    """Named, so a later reader can check the reason rather than the list."""
    only32 = {n for n, p in rm.ANALYSIS_PRECISIONS.items() if p == ("f32",)}
    assert only32 == {"qr_process_ledger", "ncmin_locality", "metric_trajectory"}
    assert not rm.applicable("qr_process_ledger", "f64")
    assert rm.applicable("dual_ledger", "f64")


def test_an_f64_bundle_carrying_an_f32_only_analysis_is_REFUSED(tmp_path):
    """The direction a manifest cannot talk its way out of: the precision it is
    checked against is the precision it declares about itself."""
    m = synthetic_manifest(tmp_path)
    m["arm"], m["precision"] = "f64", "f64"
    m["analyses"].append({
        "file": "n12.rezero.qr_process_ledger.json",
        "analysis": "qr_process_ledger", "sha256": "e" * 64, "fixture": "fx",
        "decompositions": [[3], [1, 1, 1]],
        "ran": {"nsplit": 1, "carry": "rezero", "rho": "as-is", "width": 3,
                "decompositions": [[3], [1, 1, 1]]},
        "inputs": [{"file": "mr.n1.rezero.as-is.tiles-3.txt", "sha256": "f" * 64,
                    "runtime_argv": ["1", "rezero", "3", "as-is"]},
                   {"file": "mr.n1.rezero.as-is.tiles-1-1-1.txt",
                    "sha256": "f" * 64,
                    "runtime_argv": ["1", "rezero", "1,1,1", "as-is"]}],
        "analyzer": "harness/g33_qr_process_ledger.py",
        "analyzer_sha256": "a" * 64, "analyzer_commit": "b" * 40,
        "analyzer_blob_sha": "c" * 40})
    assert any("defined only at" in b for b in rm.validate(m))
    # ...and the same entry on an f32 bundle is fine, so the refusal is about
    # the precision and not about the analysis.
    m["arm"], m["precision"] = "reference", "f32"
    assert not any("defined only at" in b for b in rm.validate(m))


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

    def set_nsplit(n):
        """BOTH sides. `ran` and each kept stream's argv must agree, so moving
        one alone now makes the manifest inconsistent -- which is a different
        violation from the bound this test is about."""
        _multi(m)["ran"]["nsplit"] = n
        for src in _multi(m)["inputs"]:
            src["runtime_argv"][0] = str(n)

    set_nsplit(rm._MAX_NSPLIT)
    assert rm.validate(m) == [], "the boundary value itself must be accepted"

    set_nsplit(rm._MAX_NSPLIT + 1)
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


@pytest.mark.parametrize("argv,probe", [
    ([1, 2, 3, 4], "not all strings"),
    (["1", "rezero", 3, "as-is"], "not all strings"),
    (["99", "rezero", "3", "as-is"], "nsplit"),
    (["1", "carry", "3", "as-is"], "carry"),
    (["1", "rezero", "3", "x2"], "rho"),
    (["1", "rezero", "0", "as-is"], "positive integers"),
    (["1", "rezero", "-1", "as-is"], "positive integers"),
])
def test_a_multirun_input_must_DESCRIBE_the_run_it_came_from(tmp_path, argv, probe):
    """`runtime_argv` was length-checked and then `.split(",")` was applied to
    argv[2], so `[1, 2, 3, 4]` raised AttributeError out of a function whose
    contract is to RETURN violations -- a crash is not fail-close (owner §6).

    And it was never compared with `ran`, so an entry could name an nsplit,
    carry, rho or decomposition the analysis never used and the bundle still
    validated.
    """
    m = _with_multi(tmp_path)
    assert rm.validate(m) == [], "the base manifest must be valid first"
    e = next(a for a in m["analyses"] if a.get("analysis") == "ncmin_locality")
    e["inputs"][0]["runtime_argv"] = argv
    bad = rm.validate(m)                       # must not raise
    assert any(probe in b for b in bad), (probe, bad)


@pytest.mark.parametrize("name", ["../escape/mr.txt", "sub/mr.txt", ".."])
def test_a_multirun_input_file_must_be_a_PLAIN_BASENAME(tmp_path, name):
    """The file is resolved inside the bundle directory, so a path with a
    separator names something the bundle never published -- and the digest
    would then be checked against whatever sits there."""
    m = _with_multi(tmp_path)
    e = next(a for a in m["analyses"] if a.get("analysis") == "ncmin_locality")
    e["inputs"][0]["file"] = name
    assert any("plain basename" in b for b in rm.validate(m))


# --- the recorded role graph must be TRUE, not merely shaped (stop-time) -----
#
# Requiring the block and checking only its shape is fail-open, and not mildly.
# `_by_role` filters the bundle's own module pins THROUGH this graph, so a
# manifest declaring a thin one gets a recipe id over a subset of its pins, and
# one declaring every module `analysis`-only gets a recipe id over NOTHING.
# Measured on a real manifest: 19 pins, and a fabricated graph brought 0 of them
# into `run_recipe_id` -- after which no run-role module's bytes could move it.
# Strictly worse than the coupling the block was added to remove, because it is
# forgeable.

def _ident(m):
    return m["identity"]


@pytest.mark.parametrize("what,mutate,expect", [
    ("a thin graph", lambda i: i.update(role_graph={"g33_refine_experiment": ["run"]}),
     "omits pinned modules"),
    ("nobody in the run role",
     lambda i: i.update(role_graph={m: ["analysis"] for m in i["role_graph"]}),
     "no module the `run` role"),
    ("a module the bundle pins nowhere",
     lambda i: i["role_graph"].update(totally_made_up=["run"]), "pins nowhere"),
    ("a role nothing filters on",
     lambda i: i["role_graph"].update(g33_refine_experiment=["banana"]),
     "not in ('run', 'analysis')"),
    ("a reach entry naming unpinned code",
     lambda i: i["analysis_reach"].update(dual_ledger=["not_a_module"]),
     "pins nowhere"),
    ("one pin quietly dropped from the graph",
     lambda i: i["role_graph"].pop("g33_refine_analyze", None) or
               i["role_graph"].pop(sorted(i["role_graph"])[0]),
     "omits pinned modules"),
])
def test_a_FABRICATED_identity_graph_is_REFUSED(what, mutate, expect, tmp_path):
    m = synthetic_manifest(tmp_path)
    assert rm.validate(m) == [], "the base manifest must be valid first"
    mutate(_ident(m))
    bad = rm.validate(m)
    assert any(expect in b for b in bad), (what, bad)


def test_every_PYTHON_pin_carries_a_role_and_no_OTHER_pin_is_asked_for(tmp_path):
    """The role graph is about modules. The build inputs also pin
    `refine_build.sh`, the driver and the fixture `.f90` -- real, pinned, and
    not things an import closure has a role for. Demanding a role for every
    pinned FILE would get one invented."""
    m = synthetic_manifest(tmp_path)
    m["tracked_build_inputs"] = list(m["tracked_build_inputs"]) + [
        {**m["tracked_build_inputs"][0], "path": "harness/g33_fortran/refine_build.sh"}]
    assert rm.validate(m) == [], rm.validate(m)
    assert "refine_build" not in rm._pinned_modules(m)


def test_the_REAL_bundles_satisfy_the_graph_contract():
    """It states a property the produced bundles HAVE. If it did not, the
    contract would be describing something nobody makes."""
    import json
    from pathlib import Path
    seen = 0
    for root in sorted(Path.home().glob("kdm6ad-g33m-*")):
        for link in sorted(root.iterdir()):
            mf = link.resolve() / "manifest.json"
            if not (link.is_symlink() and mf.is_file()):
                continue
            man = json.loads(mf.read_text())
            if not rm.at_least(str(man.get("schema", "")),
                               "refinement_experiment_v3"):
                continue
            assert rm._identity_violations(man) == [], (link.name,
                                                        rm._identity_violations(man))
            seen += 1
    if not seen:
        pytest.skip("no v3 bundle on this host")


# --- the dispatch cut is DERIVED, and scoped to the dispatcher (round 5) -----
#
# It was DECLARED, and a declaration for an analysis the bundle did not publish
# was unconstrained -- so a seed could be repointed to widen the set of edges
# the closure check excuses. And the cut was excused from EVERY module: 11 of
# them import something in the dispatch set, while the producer cuts out of
# exactly one.

def _real_v3_manifest():
    import json
    from pathlib import Path
    for root in sorted(Path.home().glob("kdm6ad-g33m-*")):
        for link in sorted(root.iterdir()):
            mf = link.resolve() / "manifest.json"
            if link.is_symlink() and mf.is_file():
                man = json.loads(mf.read_text())
                if (man.get("identity") or {}).get("analysis_seeds"):
                    return man
    return None


@pytest.mark.parametrize("victim", ["g33_identity", "g33_probe_read",
                                    "g33_refine_manifest"])
def test_an_INVENTED_seed_key_cannot_widen_the_cut(victim):
    """The last thing the manifest still contributed to the cut.

    A key that was neither in the pinned registries nor published by this
    bundle was answerable to nothing: it could name any module the dispatcher
    imports, and the module it named could then be dropped from the run role.
    Measured before the fix: a bogus key naming `g33_identity` -- the module
    that COMPUTES the identity -- passed the schema and the graph check clean
    and took the run slice from 9 pins to 8.

    The key set is now exactly the registries plus what the bundle published,
    and the dispatch set is derived from the pinned dispatcher entirely, so the
    manifest contributes nothing to it.
    """
    import copy
    man = _real_v3_manifest()
    if man is None:
        pytest.skip("no v3 bundle with recorded seeds on this host")
    edges = rm.pinned_imports(man)
    bad = copy.deepcopy(man)
    bad["identity"]["analysis_seeds"]["not_an_analysis"] = victim
    bad["identity"]["analysis_reach"]["not_an_analysis"] = sorted(
        rm._blob_closure(edges, victim))
    bad["identity"]["role_graph"][victim] = ["analysis"]
    got = rm.validate(bad) or rm.graph_violations(bad)
    assert got, victim
    assert any("analysis_seeds keys" in g for g in got), got[:1]


def test_the_DISPATCH_SET_comes_from_the_CODE_and_not_the_manifest():
    """Both halves of it. The registries name nine modules; the tenth and
    eleventh are named by the literal `_analyzer_pin` arguments, which is how
    the producer records the analyzer of an analysis it writes outside a
    registry. Together they are exactly what the producer dispatches to -- and
    the manifest is not consulted, so it cannot widen them."""
    man = _real_v3_manifest()
    if man is None:
        pytest.skip("no v3 bundle with recorded seeds on this host")
    blobs = rm.pinned_blobs(man)
    _who, registry, dispatch = rm._dispatch_from_blobs(blobs)
    assert set(registry.values()) < dispatch, \
        "the literal-argument half contributes nothing -- it should"
    assert "g33_metric_trajectory" in dispatch and \
        "g33_metric_trajectory" not in set(registry.values())
    # Nothing the manifest says can move it.
    import copy
    tampered = copy.deepcopy(man)
    tampered["identity"]["analysis_seeds"] = {"x": "g33_identity"}
    _w, _r, same = rm._dispatch_from_blobs(rm.pinned_blobs(tampered))
    assert same == dispatch


def test_the_DISPATCHER_is_derived_from_the_pinned_code_not_named():
    """Naming `g33_refine_experiment` in the checker would be a second place to
    keep in step with the producer. The module that DECLARES both registries is
    the dispatcher, and there must be exactly one."""
    man = _real_v3_manifest()
    if man is None:
        pytest.skip("no v3 bundle with recorded seeds on this host")
    blobs = rm.pinned_blobs(man)
    who, registry, _dispatch = rm._dispatch_from_blobs(blobs)
    assert who == "g33_refine_experiment", who
    assert registry, "the registries parsed to nothing"
    assert set(registry) <= set(man["identity"]["analysis_seeds"])


@pytest.mark.parametrize("what,name,seed", [
    ("a seed for an UNPUBLISHED analysis", "ncmin_locality", "g33_refine_manifest"),
    ("a seed for a PUBLISHED analysis", "dual_ledger", "g33_schema"),
    ("a seed outside the registry", "metric_trajectory", "g33_expectation"),
])
def test_a_FORGED_seed_cannot_widen_the_cut(what, name, seed):
    """The forgery has to be COMPETENT or the test measures the wrong check.

    Repointing a seed and leaving `analysis_reach` alone trips the
    reach-equals-closure rule, which would fail on the previous module too --
    so the reach is recomputed to match the forged seed, leaving the cut as the
    only thing under test. What the widened cut would buy is then taken: the
    module the seed now names is dropped from the run role, and the leak it
    creates is exactly what the cut would excuse.
    """
    # ANY v3 bundle recording this key, not the first v3 bundle. The f64
    # bundle legitimately stopped recording `metric_trajectory` when the key
    # set narrowed, and taking the first bundle made this case silently skip
    # while the ncmin bundle -- which records it -- sat right beside it.
    import json
    man = None
    for root in sorted(Path.home().glob("kdm6ad-g33m-*")):
        for link in sorted(root.iterdir()):
            mf = link.resolve() / "manifest.json"
            if link.is_symlink() and mf.is_file():
                cand = json.loads(mf.read_text())
                if name in (cand.get("identity") or {}).get("analysis_seeds", {}):
                    man = cand
                    break
        if man:
            break
    if man is None:
        pytest.skip(f"no v3 bundle records {name} on this host")
    import copy
    bad = copy.deepcopy(man)
    edges = rm.pinned_imports(bad)
    bad["identity"]["analysis_seeds"][name] = seed
    bad["identity"]["analysis_reach"][name] = sorted(
        rm._blob_closure(edges, seed))
    roles = bad["identity"]["role_graph"]
    if "run" in roles.get(seed, []):
        roles[seed] = [r for r in roles[seed] if r != "run"] or ["analysis"]
    got = rm.graph_violations(bad)
    assert got, what
    assert any("analysis_seeds" in g for g in got), (
        f"{what}: refused, but not for the seed -- {got[:1]}")


def test_a_NON_DISPATCHER_cannot_use_the_cut_to_escape_closure():
    """The overbroad half. Excusing dispatch edges from every module let any
    module import an analyzer and drop it from its role."""
    man = _real_v3_manifest()
    if man is None:
        pytest.skip("no v3 bundle with recorded seeds on this host")
    import copy
    blobs = rm.pinned_blobs(man)
    dispatcher, _reg, _d = rm._dispatch_from_blobs(blobs)
    edges = rm.pinned_imports(man, blobs)
    seeds = set(man["identity"]["analysis_seeds"].values())
    others = sorted(m for m in man["identity"]["role_graph"]
                    if m != dispatcher and edges.get(m, set()) & seeds)
    assert others, "no non-dispatcher imports the cut set -- vacuous"
    bad = copy.deepcopy(man)
    victim = sorted(edges[others[0]] & seeds)[0]
    bad["identity"]["role_graph"][victim] = [
        r for r in bad["identity"]["role_graph"][victim] if r != "analysis"] or ["run"]
    assert rm.graph_violations(bad), (others[0], victim)
