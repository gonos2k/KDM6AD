"""The identity layering (owner §16-8 / D2).

A bundle has one address over its whole manifest, so adding one analysis
re-addresses the raw stream it was derived from -- which did not move -- and
every claim binding into that bundle has to be re-pointed. This checks the
three narrower questions that address answers together, and the module
labelling that makes them separable.

Synthetic manifests throughout, so the whole file runs where the bundles are
not: the layering is a property of the manifest shape, not of this host.
"""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import g33_identity as gi          # noqa: E402
import g33_refine_experiment as rx  # noqa: E402
import g33_refine_manifest as rm   # noqa: E402


def _pin(mod, sha="a" * 64):
    return {"path": f"harness/{mod}.py", "content_sha256": sha,
            "commit": "c" * 40, "blob_sha": "b" * 40}


def _manifest():
    """A run with two INDEPENDENT analyzers and one raw arm stream."""
    return {
        "schema": "refinement_experiment_v2",
        "artifact_type": "refinement_experiment",
        "arm": "reference", "precision": "f32", "rho_profile": "as-is",
        "instrumented": True,
        "fixture_path": "harness/g33_fortran/fix.f90",
        "fixture_sha256": "f" * 64,
        "module_path": "host/phys/module_mp_kdm6.F", "module_sha256": "d" * 64,
        "runtime_argv": [["12", "rezero"]],
        "members": [{"file": "n12.rezero.txt", "output_sha256": "1" * 64,
                     "nsplit": 12, "mode": "rezero"}],
        "build_artifacts": [{"file": "g33_refine_driver", "sha256": "2" * 64}],
        "build_provenance": {"repo_commit": "c" * 40, "tree_dirty": False},
        "member_parsers": [_pin("g33_refine_analyze")],
        "tracked_build_inputs": [_pin("g33_fortran/refine_build")],
        "producer_modules": [_pin("g33_schema"), _pin("g33_refine_analyze"),
                             _pin("g33_dual_ledger"), _pin("g33_substep_schedule"),
                             _pin("g33_number_transport")],
        "analyzer_sha256": "9" * 64,
        "analyses": [
            {"analysis": "dual_ledger", "analyzer": "harness/g33_dual_ledger.py",
             "analyzer_sha256": "3" * 64, "file": "n12.rezero.dual_ledger.json",
             "sha256": "4" * 64},
            {"analysis": "substep_schedule",
             "analyzer": "harness/g33_substep_schedule.py",
             "analyzer_sha256": "5" * 64, "file": "n12.rezero.substep.json",
             "sha256": "6" * 64},
            {"analysis": "arm_stream", "arm": "inverted",
             "file": "n12.rezero.inverted.txt", "nsplit": 12,
             "runtime_argv": ["12", "rezero", "3", "inverted"],
             "sha256": "7" * 64},
        ],
    }


def _moved(before, after):
    return {name for name, fn in (("recipe", gi.run_recipe_id),
                                  ("content", gi.run_content_id),
                                  ("address", rm.identity_digest))
            if fn(before) != fn(after)}


def _mutate(fn):
    man = _manifest()
    other = copy.deepcopy(man)
    fn(other)
    return man, other


# --- the labelling ---------------------------------------------------------

def test_EVERY_reachable_module_carries_a_role():
    """A module in neither role is one nothing here describes, and its bytes
    would be outside every id while still deciding what a bundle contains."""
    assert gi.unlabelled() == set()
    assert set(gi.roles()) == rx.reachable_modules()


def test_the_roles_are_a_LABELLING_not_a_partition():
    """The first design was a split, and the measurement refused it.

    An import closure cannot separate run from analysis, because the producer
    DISPATCHES every analysis -- analysis-only comes out empty. Cutting exactly
    the dispatch edges works, and then five modules carry both roles, which is
    correct rather than a defect: `g33_probe_read` imports
    `g33_number_transport`, so it really does decide what a run admits AND it
    really is an analysis of its own.
    """
    both = {m for m, r in gi.roles().items() if len(r) == 2}
    assert "g33_number_transport" in both
    assert "g33_number_transport" in rx._local_imports("g33_probe_read")
    naive = gi.analysis_modules() - gi._closure(
        {"g33_refine_experiment"} | rx._build_script_modules())
    assert naive == set(), "an analysis-only set would make a split possible"


def test_a_RUN_module_is_not_reachable_only_through_an_analysis():
    """The cut is what defines the run role, so the run seeds must reach every
    run module without passing through a dispatched analysis."""
    seeds = {"g33_refine_experiment"} | rx._build_script_modules()
    assert gi.run_modules() == gi._closure(
        seeds, cut_from="g33_refine_experiment", cut=gi.analysis_seeds())


# --- the layering ----------------------------------------------------------

def test_ADDING_an_analysis_does_not_move_the_run():
    """The cost this exists to remove: a derived JSON re-addressed the raw
    stream it was derived from, and every binding into the bundle with it."""
    man, other = _mutate(lambda m: m["analyses"].append(
        {"analysis": "new_one", "analyzer": "harness/g33_cap_interface.py",
         "analyzer_sha256": "8" * 64, "file": "x.json", "sha256": "8" * 64}))
    assert _moved(man, other) == {"address"}


def test_an_ANALYSIS_module_moving_does_not_move_the_run():
    """`producer_modules` is ONE flat block holding both roles, so an
    unfiltered content id moved when an analyzer's bytes moved. Measured on a
    real manifest before it was filtered."""
    def bump(m):
        for e in m["producer_modules"]:
            if e["path"].endswith("g33_dual_ledger.py"):
                e["content_sha256"] = "0" * 64
    assert _moved(*_mutate(bump)) == {"address"}


@pytest.mark.parametrize("what,mutate,expect", [
    ("a run module's bytes",
     lambda m: [e.update(content_sha256="0" * 64) for e in m["producer_modules"]
                if e["path"].endswith("g33_schema.py")],
     {"recipe", "content", "address"}),
    ("the fixture", lambda m: m.update(fixture_sha256="0" * 64),
     {"recipe", "content", "address"}),
    ("the module under test", lambda m: m.update(module_sha256="0" * 64),
     {"recipe", "content", "address"}),
    ("the argv", lambda m: m.update(runtime_argv=[["24", "carry"]]),
     {"recipe", "content", "address"}),
    ("a raw member", lambda m: m["members"][0].update(output_sha256="0" * 64),
     {"content", "address"}),
    ("the build", lambda m: m["build_artifacts"][0].update(sha256="0" * 64),
     {"content", "address"}),
])
def test_what_each_LAYER_is_sensitive_to(what, mutate, expect):
    assert _moved(*_mutate(mutate)) == expect, what


def test_a_RAW_ARM_STREAM_is_content_not_analysis():
    """The `analyses` block does double duty: most entries are a derived JSON
    with a pinned analyzer, and `arm_stream` is a RAW stream from a perturbed
    run with no analyzer at all. Stripping the block wholesale dropped raw
    content out of the content id, and two runs differing only in their arm
    streams addressed as the same run."""
    def bump(m):
        for a in m["analyses"]:
            if a["analysis"] == "arm_stream":
                a["sha256"] = "0" * 64
    assert _moved(*_mutate(bump)) == {"content", "address"}


def test_an_UNCLASSIFIABLE_analyses_entry_is_REFUSED():
    """Neither an analyzer nor a raw stream. Landing it on either side by
    default puts it in one id and out of the other, silently."""
    man = _manifest()
    man["analyses"].append({"analysis": "mystery", "file": "x"})
    with pytest.raises(ValueError, match="neither derived"):
        gi.split_analyses(man)
    man["analyses"][-1] = "not-an-object"
    with pytest.raises(ValueError, match="neither derived"):
        gi.split_analyses(man)


# --- the per-analysis id ---------------------------------------------------

def test_an_analysis_id_moves_with_ITS_OWN_code_only():
    """An id over the whole analysis ROLE would move every analysis whenever
    any analyzer changed -- the same coupling, one layer down."""
    man = _manifest()
    before = {n: gi.analysis_id(man, n) for n in ("dual_ledger", "substep_schedule")}
    other = copy.deepcopy(man)
    for e in other["producer_modules"]:
        if e["path"].endswith("g33_dual_ledger.py"):
            e["content_sha256"] = "0" * 64
    assert gi.analysis_id(other, "dual_ledger") != before["dual_ledger"]
    assert gi.analysis_id(other, "substep_schedule") == before["substep_schedule"]


def test_an_analysis_id_moves_when_the_RUN_under_it_moves():
    """It is an analysis OF something. An id that survived the stream changing
    would say two different readings were the same reading."""
    man = _manifest()
    other = copy.deepcopy(man)
    other["members"][0]["output_sha256"] = "0" * 64
    assert gi.analysis_id(other, "dual_ledger") != gi.analysis_id(man, "dual_ledger")


def test_asking_for_the_analysis_id_of_a_RAW_stream_is_REFUSED():
    """`arm_stream` names no analyzer, so its reach is empty and an id over an
    empty module set never moves. Refused rather than answered."""
    man = _manifest()
    with pytest.raises(KeyError):
        gi.analysis_id(man, "arm_stream")
    with pytest.raises(KeyError):
        gi.analysis_reach(man, "arm_stream")


def test_an_UNRESOLVABLE_analyzer_is_refused_not_treated_as_reaching_nothing():
    man = _manifest()
    man["analyses"][0]["analyzer"] = "harness/g33_not_a_module.py"
    with pytest.raises(KeyError, match="no resolvable analyzer"):
        gi.analysis_reach(man, "dual_ledger")


# --- what is NOT separated yet ---------------------------------------------

def test_two_analyses_are_COUPLED_to_the_whole_layer_by_one_import():
    """`g33_ncmin_locality` does `from g33_refine_experiment import
    fixture_dims`. That one convenience import pulls in the producer, and the
    producer dispatches everything, so its reach is the entire analysis layer
    -- and `g33_qr_process_ledger` inherits it through ncmin.

    Recorded as a MEASUREMENT, not accepted: when `fixture_dims` moves to a
    leaf, this fails and says so. Nine of the eleven published analyses reach
    between one and five modules; these two reach fifteen.
    """
    collapsed = {m for m in gi.analysis_seeds()
                 if "g33_refine_experiment" in gi._closure({m})}
    assert collapsed == {"g33_ncmin_locality", "g33_qr_process_ledger"}, collapsed
    assert "g33_refine_experiment" in rx._local_imports("g33_ncmin_locality")
    for m in collapsed:
        assert len(gi._closure({m})) >= 15


# --- the same contract, on the real archive --------------------------------

def _published():
    return sorted(Path.home().glob("kdm6ad-g33m-*/*.bundles/*/manifest.json"))


needs_bundles = pytest.mark.skipif(not _published(),
                                   reason="no bundle store on this host")


@needs_bundles
def test_EVERY_published_manifest_CLASSIFIES_its_analyses():
    """Real manifests carry shapes a synthetic one does not invent. If any
    entry were neither derived nor raw, the layering would be guessing on the
    archive it is meant to describe."""
    import json
    for p in _published():
        derived, raw = gi.split_analyses(json.loads(p.read_text()))
        assert derived or raw or True   # a bundle may publish no analyses
        for a in derived:
            assert gi.analysis_reach(json.loads(p.read_text()), a["analysis"])


@needs_bundles
def test_the_LAYERING_holds_on_a_real_manifest():
    """The matrix above, on the bundle the density-matrix claims bind into."""
    import json
    p = next((q for q in _published() if "number-003-cons" in str(q)), None)
    if p is None:
        pytest.skip("number-003-cons is not on this host")
    man = json.loads(p.read_text())
    other = copy.deepcopy(man)
    other["analyses"] = [a for a in other["analyses"]
                         if a.get("analysis") != "dual_ledger"]
    assert _moved(man, other) == {"address"}
    other = copy.deepcopy(man)
    other["members"][0]["output_sha256"] = "0" * 64
    assert _moved(man, other) == {"content", "address"}
