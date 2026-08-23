

"""The v2 manifest schema as a CLOSED tagged union (owner §8)."""
import copy
import hashlib
import inspect
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_refine_manifest as rm  # noqa: E402


#: Every field and every role the v7 provenance contract requires. A fixture
#: carrying a subset describes a build that could not have happened.
def _v7_provenance():
    """A record that describes a build that could have happened.

    The module row is the OVERLAY, as in every published bundle: gfortran
    never opens `module_mp_kdm6.F`, it opens the overlay generated from it,
    so `module_path` and the module row name two different files by design.
    v7 joins the two records of one file -- `compiled_module_sha256` to the
    module row, `fixture_path`/`fixture_sha256` to the fixture row -- so a
    synthetic record that states them independently contradicts itself
    before any mutation is applied.
    """
    import g33_build_provenance as bp
    roles = (("module", "module_mp_ovl.F"),
             ("fixture", "harness/g33_fortran/g33_fixture_x_v1.f90"),
             ("driver", "harness/g33_fortran/g33_refine_driver.f90"),
             ("stub", "harness/g33_fortran/stub_wrf_error.f90"),
             ("libmassv", "host/KIM-meso_v1.0/frame/libmassv.F"),
             ("model_constants",
              "host/KIM-meso_v1.0/share/module_model_constants.F"),
             ("radar", "host/KIM-meso_v1.0/phys/module_mp_radar.F"))
    sources = [{"path": path, "role": role,
                "sha256": hashlib.sha256(role.encode()).hexdigest()}
               for role, path in roles]
    by_role = {r["role"]: r for r in sources}
    return {
        "schema": bp.BUILD_PROVENANCE_SCHEMA,
        "compiler_version": "gfortran (fake) 1.0",
        "compiler_sha256": "1" * 64,
        "compiler_f951_sha256": "5" * 64,
        "module_path": "host/KIM-meso_v1.0/phys/module_mp_kdm6.F",
        "module_sha256": "8" * 64,
        "compiled_module_path": by_role["module"]["path"],
        "compiled_module_sha256": by_role["module"]["sha256"],
        "fixture_path": by_role["fixture"]["path"],
        "fixture_sha256": by_role["fixture"]["sha256"],
        "build_script_sha256": "7" * 64,
        "executable_sha256": "a" * 64,
        "sources": sources,
        "compile_commands": ["gfortran -c " + path for _r, path in roles],
        "repo_commit": "0" * 40,
        "tree_dirty": False,
        # WHERE THE BUILD RAN, in full: `verify()` normalises the published
        # logs by all three roots, so a one-key stand-in described a build
        # whose record could not be re-derived -- and v7 holds this to an
        # exact key set for that reason.
        "diagnostic": {
            "outdir": "/build",
            "tmpdir": "/tmp",
            "repo_root": "/repo",
            "compiler_path": "/usr/bin/gfortran",
            "compiler_f951_path": "/usr/libexec/f951",
            "executable_path": "/build/g33_refine_driver",
            "compile_commands_literal": ["gfortran -c fake"],
        },
    }


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

    # the overlay the compiler read, published as a build artifact
    _OVL = w("module_mp_ovl.F", "   real, parameter, private :: dtcldcr = 120.\n")
    pin = {"path": "harness/p.py", "content_sha256": "d" * 64,
           "commit": "e" * 40, "blob_sha": "f" * 40}
    # The role graph has to AGREE with the pins, so both come from one list:
    # a graph that omits a pinned module filters it out of every id, and one
    # that names an unpinned module describes code the archive does not hold.
    _mods = ["p"] + [f"g33_{k}" for k in sorted(set(rm.DERIVED_ANALYSES)
                                                | set(rm.MULTI_RUN_ANALYSES))]
    _pins = [{**pin, "path": f"harness/{m}.py"} for m in _mods]
    man = {
        # rm.SCHEMA, not a literal: pinned to "v2" this fixture went on
        # testing the previous contract after the bump, and every v3
        # check written against it asserted nothing.
        "schema": rm.SCHEMA,
        "artifact_type": "refinement_experiment", "arm": "reference",
        "precision": "f32", "instrumented": True, "decision_eligible": False,
        # FALSE, and recomputed to false: one member cannot halve against
        # anything. The fixture claimed a chain over a single run, which the
        # validator now refuses -- the claim is derived from the members, so
        # a fixture may not state it independently.
        "is_refinement_chain": False,
        # v4: the experiment the bundle claims to be, and the geometry every
        # member's row is recomputed against (fixture 300 s / 12 splits = 25 s)
        "algorithm": "legacy", "rho_profile": "as-is",
        # the invocation the recipe id records, tied to expected_run below
        "runtime_argv": [["12", "rezero"]],
        "fixture_path": "harness/g33_fortran/g33_fixture_multisubcycle_v1.f90",
        "fixture_sha256": "9" * 64,
        "kernel_geometry": {"schema": "kdm6_subcycle_v3", "dtcldcr": 120.0,
                            "dtcldcr_storage": "f32",
                            "dtcldcr_word": "42F00000",
                            "algorithm": "legacy",
                            "compiled_dtcldcr_word": "42F00000",
                            "compiled_source_sha256": _OVL,
                            "source_path":
                                "host/KIM-meso_v1.0/phys/module_mp_kdm6.F",
                            "source_sha256": "8" * 64},
        "expected_run": {"schema": "g33_expected_run_v1",
                         "fixture_id": "g33_fixture_multisubcycle_v1",
                         "fixture_sha256": "9" * 64, "dt_bits": "43960000",
                         "window_seconds": 300.0, "columns": 3, "levels": 4,
                         "tile_sizes": [3], "rho_profile": "as-is",
                         "mode": "rezero", "nsplits": [12],
                         "source_precision": "f32",
                         "algorithm": "legacy", "precision": "f32"},
        "members": [{"file": "n12.rezero.txt", "nsplit": 12,
                     "mode": "rezero",
                     "algorithm": "legacy", "delt": 25.0, "loops": 1,
                     "dtcld": 25.0,
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
                     "rho": "uniform", "levels": 4, "ntile": 1,
                     "tile_sizes": [3], "tile_ranges": [[1, 3]]},
             "runtime_argv": ["12", "rezero", "3", "uniform"]}],
        "build_artifacts": [{"file": "g33_refine_driver",
                             "sha256": w("g33_refine_driver", "#!f\n")},
                            {"file": "module_mp_ovl.F", "sha256": _OVL}],
        # v7: the build's record is an EXACT key set with a ROLE table, so
        # the fixture carries every field and every role a real build writes
        # (owner review §5)
        "build_provenance": dict(_v7_provenance(), **{
            "executable_sha256": rm.sha256(root / "g33_refine_driver"),
            # an instrumented build feeds the compiler the GENERATED overlay
            # -- and v7 joins that statement to the `module` source row, so
            # the overlay's digest has to move in both places at once
            "compiled_module_sha256": _OVL,
            "sources": [dict(r, sha256=_OVL) if r["role"] == "module" else r
                        for r in _v7_provenance()["sources"]]}),
        "module_path": "host/KIM-meso_v1.0/phys/module_mp_kdm6.F",
        "module_sha256": "8" * 64,
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
        # v7: every analyzer an analysis dispatched to says what it EXECUTED
        # as, and the digest has to be the one the bundle pins for it
        # (owner review §8). Filled in below, once the analyses are known.
    }
    seeds = man["identity"]["analysis_seeds"]
    pins = {Path(q["path"]).stem: q["content_sha256"]
            for g in ("producer_modules", "member_parsers") for q in man[g]}
    # Every seed the analyses dispatch to, so coverage holds: a seed in
    # neither list is refused, because that is indistinguishable from a
    # module that never ran (owner review §8).
    ran = sorted({seeds[a["analysis"]] for a in man["analyses"]
                  if a.get("analysis") in seeds})
    man["executed_analyzers"] = [{"module": m, "sha256": pins.get(m, "0" * 64)}
                                 for m in ran]
    return man


def _recover_attestation(man):
    """Re-derive the attestation after a test changes `analyses`."""
    seeds = (man.get("identity") or {}).get("analysis_seeds") or {}
    pins = {Path(q["path"]).stem: q["content_sha256"]
            for g in ("producer_modules", "member_parsers")
            for q in man.get(g) or []}
    ran = sorted({seeds[a["analysis"]] for a in man.get("analyses") or []
                  if isinstance(a, dict) and a.get("analysis") in seeds})
    man["executed_analyzers"] = [{"module": m, "sha256": pins.get(m, "0" * 64)}
                                 for m in ran]
    return man


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
    # a new analysis brings a new seed to account for
    _recover_attestation(m)
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
    # a new analysis brings a new seed to account for
    _recover_attestation(m)
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
    # a new analysis brings a new seed to account for
    _recover_attestation(m)
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


# --- one file, one pin; one module name, one file (owner review §5) ----------
#
# The pin collectors keyed by basename STEM, so a file pinned in two blocks was
# silently last-wins -- and the graph could read one blob while the id digested
# the other pin. Measured: g33_number_transport.py and g33_probe_read.py are
# each pinned in producer_modules AND member_parsers on the real bundle, and a
# divergent duplicate passed validate() clean.


def test_a_DIVERGENT_duplicate_pin_is_refused(tmp_path):
    m = synthetic_manifest(tmp_path)
    m["member_parsers"] = [{**m["producer_modules"][0], "blob_sha": "1" * 40}]
    assert any("two records of one fact" in b for b in rm.validate(m)), \
        rm.validate(m)[:2]


def test_a_CONSISTENT_duplicate_pin_is_fine(tmp_path):
    """Two records of one fact that AGREE are the normal case."""
    m = synthetic_manifest(tmp_path)
    m["member_parsers"] = [dict(m["producer_modules"][0])]
    assert rm.pin_conflicts(m) == []


def test_two_paths_sharing_a_MODULE_NAME_are_refused(tmp_path):
    """The import graph is keyed by module name; two files under one name
    would collide in it, and whichever the resolver kept would answer for
    both."""
    m = synthetic_manifest(tmp_path)
    m["tracked_build_inputs"] = list(m["tracked_build_inputs"]) + [
        {**m["producer_modules"][0], "path": "elsewhere/p.py",
         "blob_sha": "2" * 40}]
    assert any("both import as" in b for b in rm.validate(m)), rm.validate(m)[:2]


def test_the_blob_must_HASH_to_the_pinned_content():
    """`pinned_blobs` reads the blob the pin names; the graph then answers for
    those bytes. If the blob does not hash to content_sha256 the pin names two
    different files, and which one 'ran' is unknowable from the manifest."""
    man = _real_v3_manifest()
    if man is None:
        pytest.skip("no v3 bundle on this host")
    import copy, hashlib
    blobs = rm.pinned_blobs(man)          # the real one resolves clean
    assert blobs
    bad = copy.deepcopy(man)
    for e in bad["producer_modules"]:
        if e["path"].endswith("g33_schema.py"):
            e["content_sha256"] = "9" * 64
    with pytest.raises(rm.BlobUnavailable, match="does not hash"):
        rm.pinned_blobs(bad)


# --- a repeated row in a set-valued block is refused (owner review §10) ------
#
# Canonical sorting made ORDER irrelevant to the ids; [p1, p1, p2] still
# hashed differently from [p1, p2] while recording the same facts. Measured on
# the live manifest: an exact duplicate pin row validated CLEAN and moved
# run_recipe_id. No block gives multiplicity a meaning.


def test_an_exact_duplicate_row_is_refused_not_deduplicated():
    import copy
    man = _real_v3_manifest()
    if man is None:
        pytest.skip("no v3 bundle on this host")
    assert rm.validate(man) == []
    for key in ("producer_modules", "members", "build_artifacts", "analyses"):
        dup = copy.deepcopy(man)
        dup[key].append(copy.deepcopy(dup[key][0]))
        assert any("twice" in v for v in rm.validate(dup)), key


def test_duplicate_analysis_inputs_are_refused():
    import copy
    man = _real_v3_manifest()
    if man is None:
        pytest.skip("no v3 bundle on this host")
    dup = copy.deepcopy(man)
    for a in dup.get("analyses", []):
        if isinstance(a.get("inputs"), list) and a["inputs"]:
            a["inputs"].append(copy.deepcopy(a["inputs"][0]))
            break
    else:
        pytest.skip("no input-carrying analysis in the live manifest")
    assert any("inputs records" in v for v in rm.validate(dup))


def test_the_DECLARED_decomposition_is_bound_to_what_the_arms_ran():
    """expected_run states the tiling the experiment asked for, and nothing
    compared it to what was published: a v4 manifest could declare (1,2),
    carry arms that ran (3,), and validate clean -- and `ncmin` makes those
    two operators, so the document would be describing the other one
    (Codex). The multi-run inputs are deliberately exempt: varying the
    decomposition is what that analysis is FOR."""
    import copy
    man = _real_v3_manifest_here_v4()
    if man is None:
        pytest.skip("no v4 bundle on this host")
    assert rm.validate(man) == []
    lied = copy.deepcopy(man)
    lied["expected_run"]["tile_sizes"] = [1, 2]
    v = rm.validate(lied)
    assert any("expected_run declares [1, 2]" in x for x in v), v[:2]


def _real_v3_manifest_here_v4():
    import json
    from pathlib import Path
    for root in sorted(Path.home().glob("kdm6ad-g33m-*")):
        for link in sorted(root.iterdir()):
            mf = link.resolve() / "manifest.json"
            if link.is_symlink() and mf.is_file():
                man = json.loads(mf.read_text())
                if (man.get("schema") == "refinement_experiment_v4"
                        and any(a.get("analysis") == "arm_stream"
                                for a in man.get("analyses", []))):
                    return man
    return None


def test_a_bundle_may_declare_only_the_decomposition_it_can_SUBSTANTIATE():
    """A declaration answers to a protocol or to nothing (Codex). G33N under
    --nflux records the tiling and so does G33P on the probe/f64 arms; a
    plain reference bundle writes no tile vector at all, so declaring one
    there is a decoration -- and omitting one where it IS recorded leaves
    the operator unstated."""
    import copy
    man = _real_v3_manifest_here_v4()
    if man is None:
        pytest.skip("no v4 bundle on this host")
    plain = copy.deepcopy(man)
    plain["instrumented"] = False
    plain["arm"] = "reference"
    plain["analyses"] = [a for a in plain["analyses"]
                         if a.get("analysis") != "arm_stream"]
    assert any("no protocol in this bundle records" in v
               for v in rm.validate(plain))
    plain["expected_run"].pop("tile_sizes")
    assert not any("tile_sizes" in v for v in rm.validate(plain))
    # ...and where it IS substantiable, the declaration is required
    absent = copy.deepcopy(man)
    absent["expected_run"].pop("tile_sizes")
    assert any("do record the decomposition" in v for v in rm.validate(absent))


@pytest.mark.parametrize("tag,mutate", [
    ("nsplit 0", lambda m: m["members"][0].update({"nsplit": 0})),
    ("horizon enormous",
     lambda m: m["expected_run"].update({"window_seconds": 1e300})),
    # an unbounded Python INT: math.isfinite takes a float and overflows on
    # the way in, so the guard against a nonsense horizon crashed on one
    ("horizon huge int",
     lambda m: m["expected_run"].update({"window_seconds": 10 ** 400})),
    ("horizon huge negative int",
     lambda m: m["expected_run"].update({"window_seconds": -(10 ** 400)})),
    ("horizon is a string",
     lambda m: m["expected_run"].update({"window_seconds": "300"})),
    ("horizon is a bool",
     lambda m: m["expected_run"].update({"window_seconds": True})),
    ("nsplit huge int",
     lambda m: m["members"][0].update({"nsplit": 10 ** 400})),
    ("horizon inf",
     lambda m: m["expected_run"].update({"window_seconds": float("inf")})),
    ("horizon nan",
     lambda m: m["expected_run"].update({"window_seconds": float("nan")})),
    ("delt is a string", lambda m: m["members"][0].update({"delt": "25"})),
    ("delt absent", lambda m: m["members"][0].update({"delt": None})),
    ("dtcld absent", lambda m: m["members"][0].update({"dtcld": None})),
    ("loops absent", lambda m: m["members"][0].update({"loops": None})),
    ("loops is a bool", lambda m: m["members"][0].update({"loops": True})),
    ("ran is a list", lambda m: [a.update({"ran": [1]})
                                 for a in m["analyses"]
                                 if a.get("analysis") == "arm_stream"]),
    ("expected_run is None", lambda m: m.update({"expected_run": None})),
    ("members are ints", lambda m: m.update({"members": [1, 2]})),
])
def test_the_v4_checks_RETURN_violations_on_a_malformed_manifest(tmp_path, tag,
                                                                mutate):
    """`validate` is contracted to RETURN violations, and the v4 arithmetic
    runs on numbers a malformed document supplies: nsplit=0 divided by zero,
    a 1e300 horizon overflowed the f32 pack, a string delt broke the format,
    a list `ran` broke the attribute access -- four crashes measured, each on
    exactly the input the checker exists to describe (Codex). A checker that
    raises there is the defect one level up."""
    # a v5 document: the geometry arithmetic only runs where the bundle
    # records the limit it was held to, and that is what the fuzz exercises
    d = synthetic_manifest(tmp_path)
    d["schema"] = "refinement_experiment_v5"
    assert rm.validate(d) == []
    try:
        mutate(d)
    except Exception:                      # a mutation the shape cannot take
        pytest.skip(f"{tag} not applicable to this manifest")
    got = rm.validate(d)                   # must not raise
    assert isinstance(got, list) and got, f"{tag} produced no violation"


@pytest.mark.parametrize("tag,mutate,needle", [
    ("drop algorithm", lambda e, m: e.pop("algorithm"), "key set"),
    ("drop precision", lambda e, m: e.pop("precision"), "key set"),
    ("drop rho_profile", lambda e, m: e.pop("rho_profile"), "key set"),
    ("an extra key", lambda e, m: e.update({"note": "x"}), "unexpected"),
    ("horizon is not the decode",
     lambda e, m: e.update({"window_seconds": 300.000001}), "decode"),
    ("dt_bits of another fixture",
     lambda e, m: e.update({"dt_bits": "42700000"}), "decode"),
    ("source_precision f64",
     lambda e, m: e.update({"source_precision": "f64"}), "f32, always"),
    ("mode absent from the vocabulary",
     lambda e, m: e.update({"mode": "drift"}), "expected_run.mode"),
    ("nsplits do not match the members",
     lambda e, m: e.update({"nsplits": [7]}), "is not the members'"),
    ("a member on another mode",
     lambda e, m: m["members"][0].update({"mode": "carry"}),
     "one auxiliary-state rule"),
])
def test_the_expected_run_block_is_a_CLOSED_contract(tmp_path, tag, mutate,
                                                    needle):
    """Every field was "compare if present", so deleting one deleted its
    check: a manifest could drop algorithm, precision and rho_profile and
    still validate, `levels` was never read, the horizon was never held to
    the pinned DT_BITS word, and mode/nsplits were absent so a mixed
    carry/rezero bundle passed at the document level (owner review §5).
    Seven gaps measured; the key set is exact now."""
    man = synthetic_manifest(tmp_path)
    man["schema"] = "refinement_experiment_v5"
    assert rm.validate(man) == [], rm.validate(man)[:2]
    mutate(man["expected_run"], man)
    assert any(needle in v for v in rm.validate(man)), rm.validate(man)[:2]


@pytest.mark.parametrize("argv_tiles,ok", [
    ("3", True), ("1,2", False), ("2,1", False), ("1,1,1", False),
    # ...and NO tile argument is a request too: the driver's default of one
    # tile over the whole domain (g33_refine_driver.f90:365-366)
    (None, True),
])
def test_the_argv_TILE_argument_is_the_declared_decomposition(tmp_path,
                                                              argv_tiles, ok):
    """The argv check compared nsplit, mode and rho_profile but skipped the
    TILE argument at position 2 -- the decomposition the command line
    actually requested, and the one the recipe id hashes. `ncmin` is set by
    a tile's last column, so an argv asking for a tiling the bundle does not
    declare puts a different operator into the id than the document states
    (Codex)."""
    man = synthetic_manifest(tmp_path)
    man["schema"] = "refinement_experiment_v5"
    man["runtime_argv"] = ([["12", "rezero"]] if argv_tiles is None
                           else [["12", "rezero", argv_tiles, "as-is"]])
    got = [v for v in rm.validate(man)
           if "decomposition" in v or "tile argument" in v]
    assert (not got) is ok, got
    # the implicit default is bound to the DECLARED tiling, not assumed
    if argv_tiles is None:
        man["expected_run"]["tile_sizes"] = [1, 2]
        assert any("no tile argument" in v for v in rm.validate(man))


@pytest.mark.parametrize("argv,declared,ok", [
    (["12", "rezero", "3", "uniform"], "uniform", True),
    (["12", "rezero", "3"], "as-is", True),
    (["12", "rezero"], "as-is", True),
    # an OMITTED forcing argument is the driver's default, not a silence
    (["12", "rezero", "3"], "uniform", False),
    (["12", "rezero"], "uniform", False),
])
def test_an_OMITTED_argv_position_is_still_a_request(tmp_path, argv, declared,
                                                     ok):
    """The forcing argument defaults to `as-is`
    (g33_refine_driver.f90:320,347), so a line that omits it requested the
    unperturbed profile -- and leaving the omission unbound let a bundle
    declare `uniform` beside an invocation that never asked for one
    (Codex)."""
    man = synthetic_manifest(tmp_path)
    man["schema"] = "refinement_experiment_v5"
    man["runtime_argv"] = [argv]
    man["rho_profile"] = declared
    man["expected_run"]["rho_profile"] = declared
    got = [v for v in rm.validate(man) if "rho_profile" in v]
    assert (not got) is ok, got


@pytest.mark.parametrize("tag,mutate,needle", [
    ("an arbitrary kernel digest",
     lambda m: m["kernel_geometry"].update({"source_sha256": "0" * 64}),
     "is not the manifest's module_sha256"),
    ("module_sha256 deleted", lambda m: m.pop("module_sha256"),
     "required from v6"),
    ("provenance names another module",
     lambda m: m["build_provenance"].update({"module_sha256": "4" * 64}),
     "two records of the module"),
    ("f64 storage on an f32 build",
     lambda m: m["kernel_geometry"].update({"dtcldcr_storage": "f64",
                                            "dtcldcr_word": "405E000000000000"}),
     "this build's real kind"),
    ("provenance reduced to one key",
     lambda m: m.update({"build_provenance": {
         "executable_sha256": m["build_provenance"]["executable_sha256"]}}),
     "required from v6"),
    ("the overlay is not published",
     lambda m: m.update({"build_artifacts": [
         a for a in m["build_artifacts"] if a["file"] != "module_mp_ovl.F"]}),
     "must publish module_mp_ovl.F"),
    ("the published overlay is not the compiled one",
     lambda m: m["build_provenance"].update({"compiled_module_sha256":
                                             "3" * 64}),
     "not the compiled_module_sha256"),
    ("the overlay carries another limit",
     lambda m: m["kernel_geometry"].update({"compiled_dtcldcr_word":
                                            "42480000"}),
     "generated overlay carries a different"),
])
def test_the_geometry_is_PROVENANCED_to_what_was_compiled(tmp_path, tag,
                                                          mutate, needle):
    """The record was length-checked and compared to the checkout's source
    map, so an arbitrary digest passed while claiming to be the provenance
    of the limit -- and an --nflux build feeds the compiler a GENERATED
    overlay, so the pinned module's constant was an assumption about bytes
    nothing checked (owner review §4). Six gaps measured on the live
    manifest before this contract."""
    man = synthetic_manifest(tmp_path)
    man["schema"] = "refinement_experiment_v6"
    assert rm.validate(man) == [], rm.validate(man)[:2]
    mutate(man)
    assert any(needle in v for v in rm.validate(man)), rm.validate(man)[:3]


# ---- owner review §5: build_provenance is an EXACT contract from v7 --------

def _published_manifests():
    """Every published manifest on this host, newest tag first."""
    import json
    from pathlib import Path
    for root in sorted(Path.home().glob("kdm6ad-g33m-*")):
        if not root.is_dir():
            continue
        for link in sorted(root.iterdir()):
            j = link.resolve() / "manifest.json"
            if link.is_symlink() and j.is_file():
                yield json.loads(j.read_text())


def _real_v6_manifest_here():
    """A published bundle on this host, or None on a public checkout.

    Takes v6 or v7: the live bundles were v6 when these tests were written
    and became v7 at the controlled re-production, and what they need is a
    REAL manifest to promote, not a particular tag."""
    import json
    from pathlib import Path
    for root in sorted(Path.home().glob("kdm6ad-g33m-*")):
        if not root.is_dir():
            continue
        for link in sorted(root.iterdir()):
            j = link.resolve() / "manifest.json"
            if link.is_symlink() and j.is_file():
                man = json.loads(j.read_text())
                if man.get("schema") in ("refinement_experiment_v6",
                                         "refinement_experiment_v7"):
                    return man
    return None


def _full_attestation(v7):
    """One row per module the bundle's own analyses dispatched to.

    Every seed has to be covered: a seed named in neither list is refused,
    so a module the bundle pins nowhere gets a placeholder digest rather
    than being dropped -- the point here is coverage, and the digest/pin
    agreement has its own tests."""
    seeds = (v7.get("identity") or {}).get("analysis_seeds") or {}
    names = {a["analysis"] for a in v7["analyses"] if isinstance(a, dict)}
    pins = {Path(p["path"]).stem: p["content_sha256"]
            for g in ("producer_modules", "member_parsers")
            for p in v7.get(g) or []}
    out, missing = [], []
    for m in sorted({seeds[n] for n in names if n in seeds}):
        if m in pins:
            out.append({"module": m, "sha256": pins[m]})
        else:
            missing.append(m)
    if missing:
        v7["unattested_analyzers"] = missing
        v7["decision_eligible"] = False
    return out


def _v7(man):
    """The same manifest, promoted to the v7 provenance contract."""
    import g33_build_provenance as bp
    out = json.loads(json.dumps(man))
    out["schema"] = "refinement_experiment_v7"
    out.pop("unattested_analyzers", None)
    b = out["build_provenance"]
    b["schema"] = bp.BUILD_PROVENANCE_SCHEMA
    for r in b["sources"]:
        r["role"] = bp.role_of(r["path"])
    # v7 also requires the run to say what its analyzers EXECUTED as
    out["executed_analyzers"] = _full_attestation(out)
    return out


@pytest.mark.parametrize("mutate,expect", [
    (lambda b: b.__setitem__("sources", b["sources"][:1]), "missing the"),
    (lambda b: b.__setitem__("sources", b["sources"]
                             + [dict(b["sources"][0], sha256="e" * 64)]),
     "two digests"),
    (lambda b: b.__setitem__("sources", b["sources"]
                             + [{"path": "harness/ghost.f90", "role": None,
                                 "sha256": "f" * 64}]),
     "no compiled source claims"),
    (lambda b: b.pop("compiler_f951_sha256", None), "key set"),
    (lambda b: b.__setitem__("smuggled", 1), "key set"),
    (lambda b: b.pop("schema", None), "build_provenance.schema"),
    # v7 JOINS the two records of one file. Each of these names a different
    # file, or the same file under a different digest, in exactly one of the
    # two places the record states it -- and all three validated CLEAN
    # against a real published bundle before the join existed (Codex).
    (lambda b: b.__setitem__("sources", [
        dict(r, sha256="c" * 64) if r["role"] == "module" else r
        for r in b["sources"]]), "records compiling one file"),
    (lambda b: b.__setitem__("sources", [
        dict(r, path="harness/g33_fortran/g33_fixture_other_v1.f90")
        if r["role"] == "fixture" else r
        for r in b["sources"]]), "records compiling one file"),
    (lambda b: b.__setitem__("sources", [
        dict(r, sha256="d" * 64) if r["role"] == "fixture" else r
        for r in b["sources"]]), "records compiling one file"),
])
def test_the_provenance_block_is_an_exact_contract(mutate, expect):
    """v6 called this a closed contract and checked only that selected fields
    were present and well shaped. Measured against a real published manifest:
    dropping six of seven source rows, repeating one logical path under two
    digests, adding a row nothing compiled, omitting `compiler_f951_sha256`,
    and smuggling an unknown key ALL validated CLEAN (owner review §5)."""
    man = _real_v6_manifest_here()
    if man is None:
        pytest.skip("no v6 bundle on this host")
    v7 = _v7(man)
    assert not rm.validate(v7), "the promoted manifest must start clean"
    mutate(v7["build_provenance"])
    bad = [b for b in rm.validate(v7) if "build_provenance" in b]
    assert bad and any(expect in b for b in bad), (expect, rm.validate(v7))


@pytest.mark.parametrize("mutate,expect", [
    (lambda b: b.__setitem__("sources", [
        dict(r, sha256="c" * 64) if r["role"] == "module" else r
        for r in b["sources"]]), "compiled_module_sha256"),
    (lambda b: b.__setitem__("sources", [
        dict(r, path="harness/g33_fortran/g33_fixture_other_v1.f90")
        if r["role"] == "fixture" else r
        for r in b["sources"]]), "fixture_path"),
    (lambda b: b.__setitem__("sources", [
        dict(r, sha256="d" * 64) if r["role"] == "fixture" else r
        for r in b["sources"]]), "fixture_sha256"),
])
def test_the_record_cannot_pin_one_file_and_compile_another(tmp_path, mutate,
                                                            expect):
    """SYNTHETIC, so a public checkout checks it too.

    The mutation table above needs a published bundle and therefore skips
    everywhere CI runs -- which is where a rule is most likely to regress
    unnoticed. This is a property of the SCHEMA, not of any one bundle.
    """
    man = synthetic_manifest(tmp_path)
    assert rm.validate(man) == [], rm.validate(man)[:2]
    mutate(man["build_provenance"])
    bad = rm.validate(man)
    assert any(expect in v and "records compiling one file" in v
               for v in bad), (expect, bad[:3])


@pytest.mark.parametrize("mutate,expect", [
    (lambda m: m.__setitem__("is_refinement_chain", None), "carries no value"),
    (lambda m: m.__setitem__("is_refinement_chain",
                             not m["is_refinement_chain"]), "disagree"),
])
def test_the_chain_claim_is_recomputed_from_its_own_members(tmp_path, mutate,
                                                            expect):
    """`is_refinement_chain` says the members halve step by step, and nothing
    read it -- not this validator, not the evidence chain, not the overlay.
    The field could say True over members that do nothing of the kind and
    every gate stayed quiet."""
    man = synthetic_manifest(tmp_path)
    assert rm.validate(man) == [], rm.validate(man)[:2]
    mutate(man)
    bad = rm.validate(man)
    assert any("is_refinement_chain" in v and expect in v for v in bad), bad[:3]


@pytest.mark.parametrize("label,value", [
    ("null", None), ("an empty string", ""), ("an empty list", []),
    ("an empty object", {}), ("zero", 0),
])
def test_no_required_provenance_field_may_be_emptied(tmp_path, label, value):
    """Presence satisfies the exact key set; every spelling of EMPTY
    satisfied it too.

    Refusing `null` alone refused one spelling of the same erasure -- `""`,
    `[]` and `{}` went on passing for the same five fields (Codex). Asked of
    every field and every spelling, because a test that named one of each is
    what let this through the first time. Shape, not truthiness:
    `tree_dirty: false` is a claim and must keep passing, which the clean
    baseline asserts.
    """
    man = synthetic_manifest(tmp_path)
    assert rm.validate(man) == [], rm.validate(man)[:2]
    silent = []
    for key in sorted(rm._BUILD_PROVENANCE_KEYS):
        one = json.loads(json.dumps(man))
        one["build_provenance"][key] = value
        if not rm.validate(one):
            silent.append(key)
    assert not silent, f"{label} passes for {silent}"


@pytest.mark.parametrize("label,value", [
    ("null", None), ("an empty string", ""), ("an empty list", []),
    ("an empty object", {}), ("zero", 0),
])
def test_no_top_level_field_may_be_emptied_or_crash_the_checker(tmp_path,
                                                                label, value):
    """The same question, one level up -- and it caught two checkers that
    died on the artifact they were judging (`members` as ints, `algorithm`
    as a list). A validator that raises has not refused anything: the caller
    sees a crash, not a verdict, and a crash is what an unhandled bundle
    looks like too."""
    man = synthetic_manifest(tmp_path)
    assert rm.validate(man) == [], rm.validate(man)[:2]
    silent = []
    for key in sorted(man):
        if key == "build_provenance":
            continue                   # walked field by field above
        one = json.loads(json.dumps(man))
        one[key] = value
        if not rm.validate(one):       # raising here fails the test, as it must
            silent.append(key)
    assert not silent, f"{label} passes for {silent}"


@pytest.mark.parametrize("label,value", [
    ("null", None), ("an empty string", ""), ("a number", 123),
    ("an empty list", []), ("an empty object", {}),
])
def test_no_diagnostic_field_may_be_emptied(tmp_path, label, value):
    """`diagnostic` was held to being a non-empty object and nothing more,
    so nested junk validated and then broke re-derivation (Codex).

    `verify()` reads `outdir` and normalises the published logs by all three
    roots -- and `Path(123)` raises, so an invalid value there did not fail
    the check, it crashed it. Two paths stay optional because the collector
    writes null when no f951 and no executable were found, which the null
    case below asserts rather than assumes.
    """
    man = synthetic_manifest(tmp_path)
    assert rm.validate(man) == [], rm.validate(man)[:2]
    optional_null = {"compiler_f951_path", "executable_path"}
    empty_list_ok = {"compile_commands_literal"}
    silent = []
    for key in sorted(rm._DIAGNOSTIC_KEYS):
        if value is None and key in optional_null:
            continue                   # a real build records null here
        if value == [] and key in empty_list_ok:
            continue                   # no commands is a shape, not a hole
        one = json.loads(json.dumps(man))
        one["build_provenance"]["diagnostic"][key] = value
        if not any("diagnostic" in v for v in rm.validate(one)):
            silent.append(key)
    assert not silent, f"{label} passes for {silent}"


def test_the_diagnostic_is_an_exact_key_set(tmp_path):
    """A key nothing declares is a key nothing checks."""
    man = synthetic_manifest(tmp_path)
    assert rm.validate(man) == [], rm.validate(man)[:2]
    smuggled = json.loads(json.dumps(man))
    smuggled["build_provenance"]["diagnostic"]["where_else"] = "/elsewhere"
    assert any("diagnostic is not the v7 key set" in v
               for v in rm.validate(smuggled))
    dropped = json.loads(json.dumps(man))
    dropped["build_provenance"]["diagnostic"].pop("repo_root")
    assert any("diagnostic is not the v7 key set" in v
               for v in rm.validate(dropped))


def test_the_optional_diagnostic_paths_really_are_optional(tmp_path):
    """The collector writes null for an f951 and an executable it did not
    find, so refusing null there would refuse a build that really happened."""
    man = synthetic_manifest(tmp_path)
    for key in ("compiler_f951_path", "executable_path"):
        man["build_provenance"]["diagnostic"][key] = None
    assert rm.validate(man) == [], rm.validate(man)[:2]


@pytest.mark.parametrize("text", ["[]", "null", '"x"', "42", "true", "{}"])
def test_no_field_of_any_wrong_json_type_can_crash_the_validator(tmp_path,
                                                                 text):
    """Every top-level field against every JSON root -- the CLASS, not the
    case in front of me.

    `x or []` filters the FALSY wrong types and passes `42` and `true`
    straight into a `for` loop, so twelve of these raised out of the
    validation instead of failing it (Codex). A validator that raises has
    not refused anything. Asked as a sweep because fixing the site Codex
    named would have left the other eleven, which is exactly how the
    previous two rounds went.
    """
    man = synthetic_manifest(tmp_path)
    assert rm.validate(man) == [], rm.validate(man)[:2]
    value = json.loads(text)
    silent = []
    for key in sorted(man):
        if man[key] == value:
            continue               # not a mutation
        one = json.loads(json.dumps(man))
        one[key] = value
        if not rm.validate(one):   # raising here fails the test, as it must
            silent.append(key)
    assert not silent, f"{text} passes for {silent}"


@pytest.mark.parametrize("text", [
    "[]", "null", '"x"', "42", "true", "{}", "[42]", "[null]",
    '[{"path":42}]', '{"role_graph":42}',
])
def test_NO_public_reader_crashes_on_a_malformed_manifest(text):
    """Every public function that takes a manifest, found by SIGNATURE.

    The defences went in at `validate()`'s entry, so every entry point that
    does not cross that door stayed exposed -- `graph_violations` and
    `identity_digest` both died on pin containers (Codex). Same structure as
    `verify()` two rounds earlier: a guard on the door is not a guard on the
    code that walks.

    Discovered rather than listed, so a reader added later is covered the
    day it is added instead of the round after someone finds it.
    """
    man = _real_v6_manifest_here()
    if man is None:
        pytest.skip("no bundle on this host")
    readers = []
    for name, fn in vars(rm).items():
        if name.startswith("_") or not inspect.isfunction(fn):
            continue
        if getattr(fn, "__module__", None) != rm.__name__:
            continue
        params = list(inspect.signature(fn).parameters.values())
        if params and params[0].name == "man" and all(
                p.default is not p.empty for p in params[1:]):
            readers.append((name, fn))
    assert len(readers) >= 6, [n for n, _ in readers]
    value, died = json.loads(text), []
    for key in sorted(man):
        broken = json.loads(json.dumps(man))
        broken[key] = value
        for name, fn in readers:
            try:
                fn(broken)
            except rm.BlobUnavailable:
                pass               # a pin this host cannot resolve, not a shape
            except Exception as e:
                died.append(f"{name}({key}={text}) {type(e).__name__}")
    assert not died, died[:5]


#: Filled in for readers that take more than the manifest. Asserted rather
#: than skipped: a reader taking something new must fail the sweep, not
#: quietly leave it -- that was the defect one round after the sweep existed.
_READER_ARGS = {"name": "qr_process_ledger", "blobs": None, "published": ()}


def _public_readers():
    """Every public function whose FIRST argument is a manifest, in both
    modules, found by signature so one added later is covered the day it is
    added."""
    import g33_identity as gi
    import inspect as _i
    out = []
    for mod in (rm, gi):
        for name, fn in vars(mod).items():
            if name.startswith("_") or not _i.isfunction(fn):
                continue
            if getattr(fn, "__module__", None) != mod.__name__:
                continue
            params = list(_i.signature(fn).parameters.values())
            if not params or params[0].name != "man":
                continue
            required = [p for p in params[1:] if p.default is p.empty]
            missing = [p.name for p in required if p.name not in _READER_ARGS]
            assert not missing, (
                f"{mod.__name__}.{name} takes {missing}, which the sweep "
                f"cannot supply -- add it to _READER_ARGS rather than "
                f"letting the reader go unswept")
            out.append((f"{mod.__name__}.{name}", fn,
                        tuple(_READER_ARGS[p.name] for p in required)))
    assert len(out) >= 15, [n for n, _, _ in out]
    return out


def _paths(doc, prefix=(), depth=2):
    """Every location in the document, to `depth` levels.

    Replacing a TOP-LEVEL field wholesale never leaves one entry of a nested
    map malformed, which is where `analysis_reach[name] = 42` lived (Codex).
    """
    if depth < 0:
        return
    items = (doc.items() if isinstance(doc, dict)
             else enumerate(doc[:2]) if isinstance(doc, list) else ())
    for key, value in items:
        yield prefix + (key,)
        yield from _paths(value, prefix + (key,), depth - 1)


#: The three readers that re-read every pinned blob, ~1 s per call. The sweep
#: is quadratic in reader x location, so they are covered at the top level --
#: where the pin blocks they walk actually live -- and left out of the deeper
#: passes rather than turning one test into a ten-minute one.
_SLOW_READERS = ("pinned_blobs", "pinned_imports", "graph_violations")


def _sweep_public_readers(man, value, depth=0, skip_slow=False):
    """`man` with each location replaced by `value`, through every reader.

    `report()` prints, so stdout is swallowed. Only two escapes are allowed,
    and they are NARROW on purpose: `BlobUnavailable` is a pin this host
    cannot resolve, and `ValueError` is what these readers raise to REFUSE a
    record they will not recompute from. A blanket `except KeyError,
    ValueError` had been hiding whatever else landed in those classes, which
    is how a sweep reports zero while a crash is still there.
    """
    import contextlib
    import io
    died = []
    locations = ([()] if not isinstance(man, dict)
                 else sorted(set(_paths(man, depth=depth))))
    for location in locations:
        broken = value if not location else json.loads(json.dumps(man))
        target = broken
        for key in location[:-1]:
            target = target[key]
        if location:
            target[location[-1]] = value
        for label, fn, args in _public_readers():
            if skip_slow and label.split(".")[-1] in _SLOW_READERS:
                continue
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    fn(broken, *args)
            except (rm.BlobUnavailable, rm.PinConflict, ValueError, KeyError):
                # NARROW, and by KIND rather than by message. `ValueError` and
                # `KeyError` are how these readers REFUSE a record they will
                # not recompute from -- `analysis_id` raises `KeyError("no
                # derived analysis named ...")`, a sentence, not a key -- so
                # matching on the text was reading an error message as an
                # interface. What is under test is that a malformed document
                # produces the SAME refusal an empty one does, never a
                # `TypeError` or an `AttributeError` that depends on which
                # wrong shape arrived.
                pass
            except Exception as e:
                died.append(f"{label}({'.'.join(map(str, location))}="
                            f"{value!r}) {type(e).__name__}")
    assert not died, died[:5]


@pytest.mark.parametrize("text", [
    "[42]", "[null]", '[{"path":42}]', '[[1]]', '[{"inputs":42}]',
    '{"analysis_reach":42}', '{"role_graph":"x"}', '{"analysis_seeds":42}',
])
def test_the_GATE_never_crashes_on_a_malformed_manifest(text):
    """`validate()` decides whether a bundle is admissible evidence, so it
    is the one reader that must always ANSWER.

    A validator that raises is indistinguishable from a bundle nothing
    handled -- the caller sees a crash either way, and the difference
    between "refused" and "never examined" is the difference between
    evidence and no evidence. That is why this axis is worth a test here and
    is not chased through every reader: the other readers compute addresses
    for documents the gate has already accepted.

    Measured before this was true: 2260 gate calls over every location in a
    real manifest to depth two, five crash sites, now none.
    """
    man = _real_v6_manifest_here()
    if man is None:
        pytest.skip("no bundle on this host")
    value = json.loads(text)
    for location in sorted(set(_paths(man, depth=2))):
        broken = json.loads(json.dumps(man))
        target = broken
        for key in location[:-1]:
            target = target[key]
        target[location[-1]] = value
        rm.validate(broken)            # raising here fails the test, as it must


@pytest.mark.parametrize("value", [42, "x", {}, [42], [None], True, [""], []])
def test_a_RECORDED_reach_entry_that_is_not_module_names_is_refused(value):
    """One level below the shape sweep, which replaces `identity` WHOLESALE
    and so never leaves a single entry malformed.

    The map was checked and the entry was not, so
    `analysis_reach: {"qr_process_ledger": 42}` reached `set(42)` (Codex).
    An entry that is not a non-empty collection of module names records no
    closure, and recomputing one here would walk the READER's imports rather
    than the producer's -- which is exactly what the recorded block exists
    to prevent, so this refuses rather than falling through.
    """
    import g33_identity as gi
    man = _real_v6_manifest_here()
    if man is None or not (man.get("identity") or {}).get("analysis_reach"):
        pytest.skip("no bundle with a recorded reach on this host")
    name = sorted(man["identity"]["analysis_reach"])[0]
    broken = json.loads(json.dumps(man))
    broken["identity"]["analysis_reach"][name] = value
    with pytest.raises(ValueError):
        gi.analysis_reach(broken, name)
    # ...and the healthy record still answers
    assert gi.analysis_reach(man, name)


@pytest.mark.parametrize("value", [[], None, "x", 42, True, (), 0.5])
def test_NO_public_reader_crashes_on_a_manifest_that_is_not_one(value):
    """THE ARGUMENT ITSELF is an axis, and no field coverage reaches it.

    The field sweep varies a real manifest's fields, so `man` was a dict in
    every one of its calls -- and seven of eight readers died the moment
    `man` was the wrong thing (Codex, on `identity_digest([])`), with six
    more in `g33_identity` that naming the site would have left.
    """
    _sweep_public_readers(value, value)


def test_every_container_the_rules_walk_is_judged_at_the_entry():
    """A container added to the manifest without an entry here is one a
    later rule can die on."""
    named = {k for k, _, _ in rm._TOP_LEVEL_CONTAINERS}
    assert "analyses" in named and "build_provenance" in named
    assert all(kind in (list, dict) for _, kind, _ in rm._TOP_LEVEL_CONTAINERS)


def test_the_shape_table_covers_the_whole_contract():
    """A field added to the key set with no shape beside it is a field that
    can be emptied -- which is the defect above, one release later."""
    named = {k for k, _, _ in rm._BUILD_PROVENANCE_SHAPES}
    assert named == rm._BUILD_PROVENANCE_KEYS, named ^ rm._BUILD_PROVENANCE_KEYS


@pytest.mark.parametrize("declare,clean", [
    (lambda seeds: sorted(seeds), True),
    (lambda seeds: sorted(seeds)[:3], False),
    (lambda seeds: None, False),
])
def test_a_bundle_that_attested_NOTHING_may_say_so(tmp_path, declare, clean):
    """Absence of `executed_analyzers` is an omission unless the bundle
    already named every seed it dispatched to as unattested.

    Refusing that case meant a producer sharing an interpreter -- the suite,
    where an earlier module has already imported the analyzers -- could not
    publish at all: the same shape as refusing at import, a production
    invariant applied to a process that is not the production one. A bundle
    carrying `unattested_analyzers` can never be decision evidence, which is
    what makes the confession safe to accept.
    """
    man = synthetic_manifest(tmp_path)
    man.pop("executed_analyzers", None)
    named = declare(rm.dispatched_seeds(man))
    if named is not None:
        man["unattested_analyzers"] = named
        man["decision_eligible"] = False
    bad = rm.validate(man)
    if clean:
        assert bad == [], bad[:2]
    else:
        assert any("omitting the record" in v for v in bad), bad[:3]


def test_a_v6_bundle_answers_for_the_v6_contract():
    """A stricter key set is a NEW TAG, never a new demand on history."""
    man = next((m for m in _published_manifests()
                if m.get("schema") == "refinement_experiment_v6"), None)
    if man is None:
        pytest.skip("no v6 bundle on this host -- the live ones are v7 now")
    assert "schema" not in man["build_provenance"]
    assert rm.validate(man) == []


# ---- owner review §8: what RAN is held to what the bundle PINS -------------

@pytest.mark.parametrize("rows,expect", [
    ([{"module": "g33_matched_closure", "sha256": "d" * 64}],
     "describes bytes that did not run"),
    ([{"module": 123}], "not a module/digest row"),
    ([{"module": "g33_nowhere", "sha256": "e" * 64}], "pins nowhere"),
])
def test_executed_analyzers_is_consumed_not_just_recorded(rows, expect):
    """The block is the digest each analyzer had when its first statement
    executed; the pins beside it are re-read from the working tree when the
    manifest is assembled, at the END of a run that takes the better part of
    an hour. Recorded and never consumed it was decoration -- a mismatched
    digest, a malformed row and a module pinned nowhere all validated CLEAN
    (measured, Codex)."""
    man = _real_v6_manifest_here()
    if man is None:
        pytest.skip("no v6 bundle on this host")
    v7 = _v7(man)
    assert not rm.validate(v7)
    v7["executed_analyzers"] = rows
    bad = rm.validate(v7)
    assert bad and any(expect in b for b in bad), bad


def test_an_analyzer_that_ran_as_its_pin_says_is_accepted():
    man = _real_v6_manifest_here()
    if man is None:
        pytest.skip("no v6 bundle on this host")
    v7 = _v7(man)
    pin = next(p for p in v7["producer_modules"]
               if p["path"].endswith("g33_matched_closure.py"))
    # the row under test, with the other seeds still accounted for
    v7["executed_analyzers"] = [
        e for e in v7["executed_analyzers"] if e["module"] != "g33_matched_closure"
    ] + [{"module": "g33_matched_closure", "sha256": pin["content_sha256"]}]
    assert rm.validate(v7) == []
    # ...and one import gets one attestation
    v7["executed_analyzers"].append({"module": "g33_matched_closure",
                                     "sha256": "b" * 64})
    assert any("twice" in b for b in rm.validate(v7))




def test_omitting_the_attestation_is_not_how_a_bundle_avoids_it():
    """Absence was legal so that a run dispatching no analyzer had nothing to
    attest -- which made OMITTING the block a way to skip the check entirely,
    while `analyses` proved analyzers had run (Codex). The manifest's own
    `analysis_seeds` names which module each analysis dispatched to, so the
    expected set is not a guess."""
    man = _real_v6_manifest_here()
    if man is None:
        pytest.skip("no v6 bundle on this host")
    v7 = _v7(man)
    assert v7.get("analyses"), "this fixture must carry analyses"
    v7.pop("executed_analyzers")          # the omission under test
    bad = rm.validate(v7)
    assert bad and any("is absent" in b for b in bad), bad

    v7["executed_analyzers"] = _full_attestation(v7)
    assert rm.validate(v7) == []


def test_a_bundle_with_no_analyses_owes_no_attestation():
    """An instrumented bundle must carry the analyses that make it
    instrumented, so emptying `analyses` alone is a different violation --
    the point here is only that the attestation is not demanded of a run that
    dispatched nothing."""
    man = _real_v6_manifest_here()
    if man is None:
        pytest.skip("no v6 bundle on this host")
    v7 = _v7(man)
    v7["analyses"] = []
    assert not [b for b in rm.validate(v7)
                if "executed_analyzers" in b or "nothing attests" in b]


# ---- owner review §8: a bundle says what it could NOT attest ---------------

def _with_unattested(v7):
    out = json.loads(json.dumps(v7))
    out["unattested_analyzers"] = ["g33_number_transport"]
    out["executed_analyzers"] = [e for e in out["executed_analyzers"]
                                 if e["module"] != "g33_number_transport"]
    out["decision_eligible"] = False
    return out


def test_a_bundle_that_cannot_attest_everything_says_so():
    """Dropping the modules it could not attest published a record a reader
    cannot tell apart from a complete one: measured, 20 analyses with seven
    modules named and `g33_number_transport` simply absent (Codex)."""
    man = _real_v6_manifest_here()
    if man is None:
        pytest.skip("no v6 bundle on this host")
    v7 = _with_unattested(_v7(man))
    assert rm.validate(v7) == []


@pytest.mark.parametrize("mutate,expect", [
    (lambda m: m.__setitem__("decision_eligible", True), "decision_eligible"),
    (lambda m: m["executed_analyzers"].append(
        {"module": "g33_number_transport", "sha256": "a" * 64}),
     "BOTH attested and unattested"),
    (lambda m: m.__setitem__("unattested_analyzers", []), "non-empty list"),
    (lambda m: m.__setitem__("unattested_analyzers", [123]), "non-empty list"),
])
def test_the_unattested_record_cannot_be_smoothed_over(mutate, expect):
    """Saying it is incompatible with being decision evidence, a module may
    not be claimed on both sides, and an empty or malformed list is not a way
    to say nothing."""
    man = _real_v6_manifest_here()
    if man is None:
        pytest.skip("no v6 bundle on this host")
    v7 = _with_unattested(_v7(man))
    mutate(v7)
    bad = rm.validate(v7)
    assert bad and any(expect in b for b in bad), bad


def test_every_seed_is_attested_or_declared(monkeypatch):
    """`unattested_analyzers` gave a bundle a way to explain an absence, and
    with no coverage rule it also became a way to HIDE one: a seed named in
    neither list is indistinguishable from a module that never ran (Codex).

    Enforceable now that the multi-run analyzers reach their module through
    the seam -- a real CLI run attests nine modules and covers all eight
    seeds, measured."""
    man = _real_v6_manifest_here()
    if man is None:
        pytest.skip("no bundle on this host")
    v7 = _v7(man)
    seeds = (v7.get("identity") or {}).get("analysis_seeds") or {}
    victim = next((seeds[a["analysis"]] for a in v7["analyses"]
                   if a.get("analysis") in seeds
                   and any(e["module"] == seeds[a["analysis"]]
                           for e in v7["executed_analyzers"])), None)
    if victim is None:
        pytest.skip("this bundle attests no seed to drop")

    dropped = json.loads(json.dumps(v7))
    dropped["executed_analyzers"] = [e for e in dropped["executed_analyzers"]
                                     if e["module"] != victim]
    bad = rm.validate(dropped)
    assert bad and any("does not account for" in b for b in bad), bad

    # ...and DECLARING it is the honest way out, at the cost of eligibility
    declared = json.loads(json.dumps(dropped))
    declared["unattested_analyzers"] = [victim]
    declared["decision_eligible"] = False
    assert rm.validate(declared) == []


@pytest.mark.parametrize("name", ["g33_nowhere", "KNOWN_BUT_UNRELATED"])
def test_the_declaration_may_only_name_analyzers_that_actually_RAN(name):
    """A confession about work that did not happen is not a limitation, it is
    noise in the provenance. Checking against the whole seed registry let a
    bundle declare a module whose analysis it never ran -- measured,
    `g33_qr_process_ledger` declared unattested by a bundle carrying no such
    analysis, CLEAN (Codex). The set is the seeds this bundle's own analyses
    dispatched to."""
    man = _real_v6_manifest_here()
    if man is None:
        pytest.skip("no bundle on this host")
    v7 = _v7(man)
    seeds = (v7.get("identity") or {}).get("analysis_seeds") or {}
    ran = {seeds[a["analysis"]] for a in v7["analyses"]
           if isinstance(a, dict) and a.get("analysis") in seeds}
    if name == "KNOWN_BUT_UNRELATED":
        name = next((s for s in sorted(set(seeds.values()) - ran)), None)
        if name is None:
            pytest.skip("this bundle's analyses cover every known seed")
    v7["unattested_analyzers"] = [name]
    v7["decision_eligible"] = False
    bad = rm.validate(v7)
    assert bad and any("no analysis in this bundle dispatches to" in b
                       for b in bad), bad


def test_a_bundle_that_ran_nothing_can_declare_nothing():
    """`expected` is empty when no analysis ran, and the stray check was
    guarded on it being non-empty -- so a manifest with `analyses: []` could
    declare any name at all, measured CLEAN (Codex). An empty expected set
    means EVERY name is unrelated: nothing ran, so nothing can be
    unattested."""
    man = _real_v6_manifest_here()
    if man is None:
        pytest.skip("no bundle on this host")
    v7 = _v7(man)
    v7["analyses"] = []
    v7["executed_analyzers"] = []
    v7["decision_eligible"] = False

    # ...saying nothing is fine
    assert not [b for b in rm.validate(v7)
                if "unattested" in b or "dispatches to" in b]

    # ...saying anything is not
    v7["unattested_analyzers"] = ["made_up"]
    bad = rm.validate(v7)
    assert bad and any("no analysis in this bundle dispatches to" in b
                       for b in bad), bad


def test_the_manifest_algorithm_vocabulary_tracks_the_driver_cascade():
    """`_ALGOS` says it is the driver's own `ALGOTAG` vocabulary, and a manifest
    naming anything else is rejected as a run that could not have happened. So a
    driver arm missing from it makes a REAL run unpublishable -- which is what
    happened to `nmass_dry` and `nmass_dry_window` for a week.

    Pinned in both directions, like the transfer-metric table it repeats.
    """
    import re
    driver = (Path(__file__).resolve().parents[1]
              / "g33_fortran" / "g33_refine_driver.f90").read_text()
    emitted = set(re.findall(r"ALGOTAG = '([a-z_0-9]+)'", driver))
    assert emitted, "no ALGOTAG assignments found; the cascade moved"
    assert emitted == set(rm._ALGOS), (
        f"only the driver knows: {sorted(emitted - set(rm._ALGOS))}; "
        f"only the manifest knows: {sorted(set(rm._ALGOS) - emitted)}")
