#!/usr/bin/env python3
"""The gate and the artifact generator must not drift apart again — public CI, no build.

They had two independent loaders, and the generator's was the weaker one: it read the
C++ bundle without external anchors, parsed the Fortran C-lane stdout directly with no
bundle verification, copied the verdict out of a previous run's result.json, and
recomputed the first divergence from `stages` alone.

The last is the one that matters. The comparator's first divergence ranges over the op
ladder as well as the snapshots, so once the earliest difference moves INTO the ladder
the two answers separate — the gate names an op, the artifact names a later stage — and
the artifact is the document a reader trusts.

These are structural tests over the source. They cannot check that a real run agrees
(that needs a build), but they can check that no SECOND path exists to disagree with.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_fourcase_load as fcl        # noqa: E402

GATE = ROOT / "gateb_g33m_check.py"
GENERATOR = ROOT / "make_g33m_evidence_artifact.py"


def _calls(path):
    """Every function/attribute name called in the module."""
    tree = ast.parse(path.read_text())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
    return out


def test_both_consumers_load_through_the_shared_entry():
    for path in (GATE, GENERATOR):
        assert "load_verified_fourcase" in _calls(path), (
            f"{path.name} does not use the shared loader")


def test_neither_consumer_verifies_a_bundle_itself():
    """Verification belongs to the loader. A consumer calling verify_* again would be
    a second path, free to pass different anchors than the loader does."""
    for path in (GATE, GENERATOR):
        called = _calls(path)
        for banned in ("verify_cpp_bundle", "verify_cpp_evidence",
                       "verify_fortran_bundle", "parse_fortran_run"):
            assert banned not in called, (
                f"{path.name} calls {banned} directly instead of the shared loader")


def test_the_generator_does_not_compute_its_own_first_divergence():
    """It must publish the comparator's, which sees the op ladder."""
    src = GENERATOR.read_text()
    assert "legacy_first_divergence" in src, (
        "the artifact must carry the comparator's own first divergence")
    assert "STAGE_ORDER.index" not in src, (
        "a stages-only ordering here is a second first-divergence algorithm")


def _code_strings(path):
    """Every string LITERAL in executable position — comments and docstrings excluded,
    so prose describing the old behaviour cannot fail the test."""
    tree = ast.parse(path.read_text())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            d = ast.get_docstring(node, clean=False)
            if d is not None:
                docstrings.add(d)
    return {n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and n.value not in docstrings}


def test_the_generator_does_not_copy_a_previous_verdict():
    assert not [s for s in _code_strings(GENERATOR) if s.endswith("result.json")], (
        "reading a previous run's result.json lets the artifact assert a verdict "
        "nothing in this process established")


def test_an_unanchored_load_cannot_build_the_decision_type():
    """`evidence` is the promotable object. Present on an unanchored load it would
    name more than was checked."""
    src = Path(fcl.__file__).read_text()
    tree = ast.parse(src)
    assigns = [n for n in ast.walk(tree)
               if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "evidence" for t in n.targets)]
    assert assigns, "no `evidence` assignment found — has the loader been renamed?"
    # the VerifiedFourCase.of() call must sit under `if anchored`
    guarded = [n for n in ast.walk(tree)
               if isinstance(n, ast.If)
               and isinstance(n.test, ast.Name) and n.test.id == "anchored"
               and "VerifiedFourCase" in ast.dump(n)]
    assert guarded, "VerifiedFourCase.of() is not guarded by `anchored`"


def test_the_verdict_path_follows_what_was_attested():
    """An anchored load adjudicates the verified type; an unanchored one takes the
    path that cannot promote. Selecting on a CALLER FLAG rather than on what the load
    actually produced is how a debug run comes to publish a decision verdict."""
    src = Path(fcl.__file__).read_text()
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "verdict")
    dumped = ast.dump(fn)
    assert "adjudicate_verified" in dumped and "adjudicate_unattested" in dumped
    tested = [ast.dump(n.test) for n in ast.walk(fn) if isinstance(n, ast.If)]
    assert any("'evidence'" in t and "'self'" in t for t in tested), (
        f"the branch must test the loaded evidence, not a flag the caller "
        f"passed; branches were {tested}")


def test_evidence_errors_excludes_programming_errors():
    """A TypeError or AttributeError here is a defect in the harness. Catching it as
    an evidence error reports it as 'the bundle is bad'."""
    for bad in (TypeError, AttributeError, NameError, ZeroDivisionError):
        assert bad not in fcl.EVIDENCE_ERRORS, f"{bad.__name__} is not an evidence error"
    assert fcl.EVIDENCE_ERRORS, "no evidence errors declared"
