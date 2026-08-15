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
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
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
    """The CURRENT bundles -- what each store symlink points at.

    Not every directory under `*.bundles/`. A bundle is immutable and a
    re-production leaves the old one in place on purpose, so globbing the store
    walks superseded bundles too -- and a superseded bundle can never satisfy a
    contract added after it, because nothing may edit it. Requiring that would
    mean no contract could ever be added without rewriting history.

    A claim pinning a superseded bundle is still checked: the evidence chain
    resolves the PATH the claim names, and `rm.validate` refuses a v3 manifest
    whose identity block is incomplete wherever it is reached from
    (Codex stop-time review).
    """
    out = []
    for root in sorted(Path.home().glob("kdm6ad-g33m-*")):
        for link in sorted(root.iterdir()):
            if link.is_symlink() and (link.resolve() / "manifest.json").is_file():
                out.append(link.resolve() / "manifest.json")
    return out


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


# --- the anchors (owner priority 4-5) ---------------------------------------
#
# The layering was measured on synthetic MUTATIONS -- change one analyzer's
# content hash, watch which id moves -- and passed. What it never reproduced is
# the path a producer actually takes: rebuild the same bundle from the same
# bytes at a new HEAD. Every pin carries `commit` beside `content_sha256` and
# `repo_commit` sits at the top of the manifest, so an id over the pins moved on
# EVERY commit, including the analysis-only and documentation-only ones the
# layers exist to be stable across.


def _reanchor(man, commit="e" * 40):
    """The same run, published from a different commit. Nothing about the bytes
    changes: only where they can be fetched from, and the prose beside them."""
    out = copy.deepcopy(man)
    out["repo_commit"] = commit
    out["build_provenance"]["repo_commit"] = commit
    for block in ("producer_modules", "member_parsers", "tracked_build_inputs"):
        for e in out[block]:
            e["commit"] = commit
    for a in out["analyses"]:
        if a.get("analyzer"):
            a["analyzer_commit"] = commit
    out["findings"] = [{"path": "harness/evidence/FINDING_x.md",
                        "sha256": "8" * 64}]
    return out


def test_a_commit_that_moved_no_bytes_moves_NO_run_id():
    """The regression the synthetic mutations could not express."""
    man = _manifest()
    man["repo_commit"] = "c" * 40
    assert gi.run_recipe_id(man) == gi.run_recipe_id(_reanchor(man))
    assert gi.run_content_id(man) == gi.run_content_id(_reanchor(man))
    for name in ("dual_ledger", "substep_schedule"):
        assert gi.analysis_id(man, name) == gi.analysis_id(_reanchor(man), name)


def test_the_BUNDLE_ADDRESS_still_moves_and_that_is_the_point():
    """The contrast is the whole argument for the layers: today's one address
    cannot tell a re-publication from a re-run, and the layers can."""
    man = _manifest()
    man["repo_commit"] = "c" * 40
    assert rm.identity_digest(man) != rm.identity_digest(_reanchor(man))


def test_a_finding_correction_does_not_re_address_the_raw_stream():
    """`findings` is prose attached to the run at publish time, not output of
    it. Editing a sentence used to move the run's content id."""
    man, other = _mutate(lambda m: m.update(
        findings=[{"path": "harness/evidence/FINDING_x.md", "sha256": "8" * 64}]))
    assert gi.run_content_id(man) == gi.run_content_id(other)


def test_the_BYTES_still_move_every_id_they_should():
    """The anchors are dropped; nothing else is. A run-role module whose CONTENT
    moved must still move the recipe -- otherwise this stopped answering the
    question it exists for."""
    man, other = _mutate(lambda m: m["producer_modules"][4].update(
        content_sha256="9" * 64, blob_sha="9" * 40))
    assert gi.run_recipe_id(man) != gi.run_recipe_id(other)
    man, other = _mutate(lambda m: m["analyses"][0].update(
        analyzer_sha256="e" * 64))
    assert gi.run_recipe_id(man) == gi.run_recipe_id(other)
    assert gi.run_content_id(man) == gi.run_content_id(other)
    assert gi.analysis_id(man, "dual_ledger") != gi.analysis_id(other, "dual_ledger")
    assert gi.analysis_id(man, "substep_schedule") == \
        gi.analysis_id(other, "substep_schedule")


# --- and the same thing against REAL commits of this repository -------------

def _blob_at(commit, path):
    r = subprocess.run(["git", "rev-parse", f"{commit}:{path}"],
                       cwd=REPO, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def _two_commits_sharing_a_blob(path):
    """Two REAL commits of this repository whose blob for `path` is identical.

    Almost every commit qualifies -- that is the point: a run-role file is
    unchanged by most commits, and those are exactly the commits that were
    moving its run id.
    """
    log = subprocess.run(["git", "rev-list", "-n", "60", "HEAD"],
                         cwd=REPO, capture_output=True, text=True).stdout.split()
    seen = {}
    for c in log:
        b = _blob_at(c, path)
        if b and b in seen:
            return seen[b], c, b
        if b:
            seen[b] = c
    return None, None, None


def _real_pins(commit, paths):
    out = []
    for p in paths:
        blob = _blob_at(commit, p)
        raw = subprocess.run(["git", "cat-file", "blob", blob], cwd=REPO,
                             capture_output=True).stdout
        out.append({"path": p, "content_sha256": hashlib.sha256(raw).hexdigest(),
                    "commit": commit, "blob_sha": blob})
    return out


#: Run-role modules, so `_by_role` keeps them in the recipe.
_RUN_ROLE_PATHS = ["harness/g33_number_transport.py",
                   "harness/g33_refine_analyze.py"]


def test_TWO_REAL_COMMITS_that_left_the_run_code_alone_give_ONE_recipe_id():
    """Not a mutated manifest: two commits that exist in this repository's
    history, their real blob ids, and the real bytes behind them."""
    a, b, _blob = _two_commits_sharing_a_blob(_RUN_ROLE_PATHS[0])
    if a is None:
        pytest.skip("shallow clone: no two commits share a blob for this path")
    assert a != b
    man = _manifest()
    ma, mb = copy.deepcopy(man), copy.deepcopy(man)
    ma["producer_modules"] = _real_pins(a, _RUN_ROLE_PATHS)
    mb["producer_modules"] = _real_pins(b, _RUN_ROLE_PATHS)
    assert ma["producer_modules"] != mb["producer_modules"], \
        "the two pin blocks must differ, or this proves nothing"
    assert gi.run_recipe_id(ma) == gi.run_recipe_id(mb)
    assert gi.run_content_id(ma) == gi.run_content_id(mb)


def test_and_a_REAL_commit_that_DID_change_the_run_code_moves_it():
    """The other direction, so the test above is not passing by ignoring the
    block entirely."""
    path = _RUN_ROLE_PATHS[0]
    log = subprocess.run(["git", "rev-list", "-n", "200", "HEAD", "--", path],
                         cwd=REPO, capture_output=True, text=True).stdout.split()
    if len(log) < 2:
        pytest.skip(f"shallow clone: fewer than two commits touch {path}")
    a, b = log[0], log[1]
    assert _blob_at(a, path) != _blob_at(b, path)
    man = _manifest()
    ma, mb = copy.deepcopy(man), copy.deepcopy(man)
    ma["producer_modules"] = _real_pins(a, [path])
    mb["producer_modules"] = _real_pins(b, [path])
    assert gi.run_recipe_id(ma) != gi.run_recipe_id(mb)


# --- an id must be a function of the MANIFEST (owner priority 8) -------------
#
# `roles()` and `analysis_reach()` read the registries and the import graph of
# whatever tree is present. So a refactor that moves a module from run+analysis
# to analysis-only -- touching no bundle byte -- changes `_by_role`'s filter and
# moves a HISTORICAL manifest's run_content_id. That is the coupling the layers
# exist to remove, one level further out, and it is what Phase B was waiting on:
# an id written into an archive has to be reproducible from the archive.


def _with_identity(man):
    out = copy.deepcopy(man)
    out["identity"] = gi.identity_block()
    return out


def test_a_recorded_role_graph_makes_the_ids_SELF_CONTAINED():
    man = _with_identity(_manifest())
    assert gi.identity_is_self_contained(man)
    assert not gi.identity_is_self_contained(_manifest())


def test_a_REFACTOR_of_the_role_graph_does_not_move_a_RECORDED_id(monkeypatch):
    """The regression. `g33_number_transport` carries both roles today; move it
    to analysis-only and a manifest that RECORDS the old graph must not notice.
    """
    plain, recorded = _manifest(), _with_identity(_manifest())
    before = (gi.run_recipe_id(recorded), gi.run_content_id(recorded))
    before_plain = (gi.run_recipe_id(plain), gi.run_content_id(plain))

    moved = {m: (r - {"run"} if m == "g33_number_transport" else r)
             for m, r in gi.roles().items()}
    monkeypatch.setattr(gi, "roles", lambda: moved)

    assert (gi.run_recipe_id(recorded), gi.run_content_id(recorded)) == before, \
        "a recorded graph must be read with, whatever the checkout looks like"
    assert (gi.run_recipe_id(plain), gi.run_content_id(plain)) != before_plain, \
        "...and without one the id DOES follow the tree -- or this proves nothing"


def test_a_recorded_analysis_reach_does_not_follow_the_import_graph(monkeypatch):
    """The same thing one layer down: an analyzer that grows an import would
    widen a historical analysis's id."""
    recorded = _with_identity(_manifest())
    before = gi.analysis_id(recorded, "dual_ledger")
    monkeypatch.setattr(gi, "_closure",
                        lambda *a, **k: {"g33_dual_ledger", "g33_something_new"})
    assert gi.analysis_id(recorded, "dual_ledger") == before


def test_the_recorded_block_COVERS_every_analysis_the_producer_runs():
    """A reach map missing an analysis silently falls back to recomputing it,
    which is the behaviour the block exists to replace."""
    import g33_refine_manifest as rm
    block = gi.identity_block()
    # EVERY analysis a bundle can carry, which is the manifest module's
    # vocabulary -- not the producer's two dispatch registries.
    # `metric_trajectory` is written by `_driver_analyses` directly, so it is in
    # neither registry and it is in every instrumented as-is bundle. This test
    # asserted the registries and therefore agreed with the gap (Codex
    # stop-time review).
    # The registries, plus whatever the bundle published. Recording every
    # producible analysis left keys answerable to nothing: an invented key names
    # any module the dispatcher imports and widens the cut to cover it (Codex
    # stop-time review). `metric_trajectory` is the one outside the registries,
    # so it is recorded only where it is published -- and the CUT still covers
    # it, because the cut is derived from the pinned code and not from here.
    registries = set(rx.ANALYSES) | set(rx.MULTI_RUN)
    assert set(block["analysis_reach"]) == registries
    assert "metric_trajectory" not in block["analysis_reach"]
    with_mt = gi.identity_block({"metric_trajectory"})
    assert set(with_mt["analysis_reach"]) == registries | {"metric_trajectory"}
    assert set(gi.producible()) == (set(rm.DERIVED_ANALYSES)
                                    | set(rm.MULTI_RUN_ANALYSES))
    assert set(block["role_graph"]) == set(gi.roles())
    for name, mods in block["analysis_reach"].items():
        assert mods, name


def test_a_v3_manifest_may_NOT_opt_out_of_the_identity_block(tmp_path):
    """The fallback was unconditional, so a v3 manifest could omit the block
    and quietly get checkout-dependent ids anyway -- opt-out-by-omission, which
    is the defect the schema bump before it was for (Codex stop-time review)."""
    import g33_refine_manifest as rm
    man = _with_identity(_manifest())
    man["schema"] = rm.SCHEMA
    assert gi.run_recipe_id(man)
    del man["identity"]
    for call in (lambda: gi.run_recipe_id(man),
                 lambda: gi.run_content_id(man),
                 lambda: gi.analysis_id(man, "dual_ledger")):
        with pytest.raises(ValueError, match="requires an `identity"):
            call()
    # ...and a pre-v3 manifest still falls back, because it has nothing else.
    man["schema"] = "refinement_experiment_v2"
    assert gi.run_recipe_id(man)


def test_a_v3_manifest_may_not_omit_ONE_analysis_from_the_reach_map(tmp_path):
    """The partial case, which is the one that actually happened: a bundle
    carrying `metric_trajectory` with no reach entry for it had that analysis's
    id fall back while every other one was recorded."""
    import g33_refine_manifest as rm
    man = _with_identity(_manifest())
    man["schema"] = rm.SCHEMA
    del man["identity"]["analysis_reach"]["dual_ledger"]
    with pytest.raises(ValueError, match="analysis_reach"):
        gi.analysis_id(man, "dual_ledger")
    # the OTHER analysis is unaffected -- the refusal is per entry
    assert gi.analysis_id(man, "substep_schedule")


# --- the SLICES, not the declarations (Codex stop-time review, round 3) ------
#
# Three rounds of identity checking validated the declarations and left the
# slices open, which is the same mistake three times. `_by_role` and `_pins_for`
# both filter `producer_modules`, and a module can be pinned as a tracked BUILD
# INPUT instead -- so a graph giving the `run` role only to `make_fortran_overlay`
# satisfied "somebody is in the run role" and left the run slice EMPTY. Measured:
# run-slice 0 with a clean validate, the same end state as the forgery the round
# before closed, through a different door.


def _real_v3():
    import json
    for root in sorted(Path.home().glob("kdm6ad-g33m-*")):
        for link in sorted(root.iterdir()):
            mf = link.resolve() / "manifest.json"
            if link.is_symlink() and mf.is_file():
                man = json.loads(mf.read_text())
                if (man.get("identity") or {}).get("role_graph"):
                    return man
    return None


def test_the_SCHEMA_rule_and_the_ID_functions_agree_about_the_slice():
    """The check lives in the manifest module and the slice is computed in this
    one, so they can drift -- which is exactly how the run-slice hole survived a
    round that was looking for it. This ties them together on real data: what
    the schema calls a non-empty slice is what `_by_role` and `_pins_for`
    actually return.
    """
    import g33_refine_manifest as rm
    man = _real_v3()
    if man is None:
        pytest.skip("no v3 bundle on this host")
    assert rm.validate(man) == [], rm.validate(man)[:2]
    assert gi._by_role(man, "run"), "the schema passed a run slice that is empty"
    for a in man["analyses"]:
        if a.get("analysis") == "arm_stream":
            continue
        mods = gi.analysis_reach(man, a["analysis"])
        assert gi._pins_for(man, mods), (a["analysis"], sorted(mods))
        own = Path(a["analyzer"]).stem
        assert any(Path(p["path"]).stem == own for p in gi._pins_for(man, mods)), (
            f"{a['analysis']}: its id does not cover {own}, the analyzer that "
            f"produced it")


@pytest.mark.parametrize("what,mutate", [
    ("the run slice emptied through build-input pins",
     lambda m: m["identity"].update(role_graph={
         k: (["run"] if k in ("make_fortran_overlay", "g33_fortran_bindings")
             else ["analysis"]) for k in m["identity"]["role_graph"]})),
    ("an analysis slice emptied the same way",
     lambda m: m["identity"]["analysis_reach"].update(
         dual_ledger=["make_fortran_overlay"])),
    ("an analysis slice that omits its own analyzer",
     lambda m: m["identity"]["analysis_reach"].update(dual_ledger=["g33_schema"])),
])
def test_an_EMPTY_or_INCOMPLETE_slice_is_refused(what, mutate):
    """Each of these validated clean before, and each produces an id over
    modules that cannot answer for the thing it identifies."""
    import g33_refine_manifest as rm
    man = _real_v3()
    if man is None:
        pytest.skip("no v3 bundle on this host")
    bad = copy.deepcopy(man)
    mutate(bad)
    assert rm.validate(bad), what


def test_NO_single_edit_leaves_a_validating_manifest_with_a_BROKEN_slice():
    """The check the last three rounds needed and did not have.

    Hand-picked attacks find the holes you thought of; this drops each element
    of the recorded graph and each module of each reach entry in turn, and
    requires that whatever still VALIDATES still has slices the ids can stand
    on. Three rounds of spot-checking declarations missed a run slice that
    filtered to empty, so the property is asserted over the search rather than
    over three examples.
    """
    import g33_refine_manifest as rm
    man = _real_v3()
    if man is None:
        pytest.skip("no v3 bundle on this host")
    broken, checked = [], 0

    def slices_ok(d, why):
        nonlocal checked
        if rm.validate(d) != []:
            return                                   # refused: nothing to check
        checked += 1
        if not gi._by_role(d, "run"):
            broken.append((why, "empty run slice"))
        for a in d["analyses"]:
            if a.get("analysis") == "arm_stream":
                continue
            pins = gi._pins_for(d, gi.analysis_reach(d, a["analysis"]))
            own = Path(a["analyzer"]).stem
            if not pins:
                broken.append((why, f"{a['analysis']}: empty analysis slice"))
            elif not any(Path(p["path"]).stem == own for p in pins):
                broken.append((why, f"{a['analysis']}: slice lost {own}"))

    for m in sorted(man["identity"]["role_graph"]):
        d = copy.deepcopy(man)
        d["identity"]["role_graph"].pop(m)
        slices_ok(d, f"role_graph drops {m}")
    for name, mods in sorted(man["identity"]["analysis_reach"].items()):
        for mod in sorted(mods):
            rest = [x for x in mods if x != mod]
            if not rest:
                continue
            d = copy.deepcopy(man)
            d["identity"]["analysis_reach"][name] = rest
            slices_ok(d, f"reach[{name}] drops {mod}")

    assert checked, "every mutation was refused -- the search proves nothing"
    assert not broken, broken[:5]


# --- identity v2: the block itself is not run content (owner review §3) ------
#
# Under v1 the whole `identity` block -- role graph, seeds, every reach entry --
# rode into `run_content_id`, so an ANALYSIS-ONLY change that regenerated the
# block moved the run's content id. Measured on the real f64 manifest: growing
# one reach entry moved it with no run byte changed. The earlier regression
# missed it because its synthetic manifest is v2 and carries no block, and the
# real-manifest test mutated `analyses` without regenerating the block the way
# the producer does.


def test_regenerating_the_block_after_an_ANALYSIS_change_moves_NO_run_id():
    """The PRODUCER PATH, not a synthetic mutation: the block is regenerated by
    `identity_block()` on both sides, with the analysis surface changed in
    between -- one more published analysis, which is exactly what re-running a
    bundle with a new analyzer does."""
    man = _with_identity(_manifest())
    man["identity"] = gi.identity_block()
    man["schema"] = rm.SCHEMA
    before = (gi.run_recipe_id(man), gi.run_content_id(man),
              gi.analysis_id(man, "dual_ledger"))

    after = copy.deepcopy(man)
    after["identity"] = gi.identity_block({"metric_trajectory"})
    assert after["identity"] != man["identity"], \
        "the block must actually differ, or this proves nothing"
    assert gi.run_recipe_id(after) == before[0]
    assert gi.run_content_id(after) == before[1]
    assert gi.analysis_id(after, "dual_ledger") == before[2]


def test_a_reach_or_rolegraph_edit_alone_moves_NO_content_id():
    """The two mutations measured moving it under v1."""
    man = _with_identity(_manifest())
    man["identity"]["schema"] = gi.IDENTITY_SCHEMA
    before = gi.run_content_id(man)
    d = copy.deepcopy(man)
    d["identity"]["analysis_reach"]["dual_ledger"] = sorted(
        set(d["identity"]["analysis_reach"]["dual_ledger"]) | {"extra_mod"})
    assert gi.run_content_id(d) == before
    d2 = copy.deepcopy(man)
    d2["identity"]["role_graph"]["analysis_only_newcomer"] = ["analysis"]
    assert gi.run_content_id(d2) == before


def test_a_RUN_ROLE_reassignment_still_moves_the_content_id():
    """The reduction must not have thrown the baby out: the run-role half of
    the graph reaches the id through `_by_role`'s filtered pin list, so
    reassigning a run module to analysis-only changes which pins are digested."""
    man = _with_identity(_manifest())
    man["identity"]["schema"] = gi.IDENTITY_SCHEMA
    before = gi.run_content_id(man)
    d = copy.deepcopy(man)
    d["identity"]["role_graph"] = {
        m: (["analysis"] if r == ["run"] else r)
        for m, r in d["identity"]["role_graph"].items()}
    assert gi.run_content_id(d) != before


def test_the_schema_TAG_still_moves_the_content_id():
    """Two manifests canonicalised under different rules are not comparable
    ids, so the tag is the one part of the block that stays."""
    man = _with_identity(_manifest())
    man["identity"]["schema"] = gi.IDENTITY_SCHEMA
    d = copy.deepcopy(man)
    d["identity"]["schema"] = "g33_layered_identity_v1"
    assert gi.run_content_id(d) != gi.run_content_id(man)


def test_LIST_ORDER_does_not_move_an_id():
    """Four of the manifest's lists are semantically sets; JSON hashes their
    order. Two valid manifests recording the same rows differently ordered
    carried different ids -- harmless while ids are derived-only, fatal once
    Phase B stores them (owner review §7.3)."""
    man = _with_identity(_manifest())
    man["identity"]["schema"] = gi.IDENTITY_SCHEMA
    before = (gi.run_recipe_id(man), gi.run_content_id(man))
    d = copy.deepcopy(man)
    d["producer_modules"] = list(reversed(d["producer_modules"]))
    d["members"] = list(reversed(d["members"]))
    d["member_parsers"] = list(reversed(d["member_parsers"]))
    d["build_artifacts"] = list(reversed(d["build_artifacts"]))
    assert (gi.run_recipe_id(d), gi.run_content_id(d)) == before
    # ...and an ORDER-BEARING list still moves it: argv is a command line.
    d2 = copy.deepcopy(man)
    d2["runtime_argv"] = [list(reversed(a)) for a in d2["runtime_argv"]]
    assert gi.run_recipe_id(d2) != before[0]


def test_INPUT_order_does_not_move_an_analysis_id():
    """analyses[].inputs are a set of digested files: the chain reads them
    per-file and nothing reads their order, so a differently-ordered but
    otherwise identical entry must address as the same analysis (§10.2).
    Measured on the live f64 manifest before the fix: reversing one
    multi-run analysis's inputs moved its analysis_id."""
    a = {"analyses": [{"analysis": "x",
                       "inputs": [{"file": "b", "sha256": "2"},
                                  {"file": "a", "sha256": "1"}]}]}
    b = {"analyses": [{"analysis": "x",
                       "inputs": [{"file": "a", "sha256": "1"},
                                  {"file": "b", "sha256": "2"}]}]}
    assert gi._canonical_lists(a) == gi._canonical_lists(b)
