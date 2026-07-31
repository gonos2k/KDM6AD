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


def test_every_semantic_stage_field_has_a_dtype():
    """The dtype map used to name each stage in turn, so adding a stage to the field
    lists left it absent here and the comparator reported `unknown <stage> field 'qv'`
    — a structural error about evidence that was correct. It is derived now; this pins
    that no stage can be half-declared again."""
    import g33_schema as schema
    for stage in schema._SEMANTIC_STAGE_FIELDS:
        for field in schema.semantic_stage_fields(stage):
            dt = schema.semantic_stage_field_dtype(stage, field)
            assert dt in ("f32", "f64", "i32", "u8"), f"{stage}.{field} -> {dt!r}"


def test_no_module_level_name_is_defined_twice_in_the_parser():
    """A second assignment silently shadows the first, and the two stay equal only until
    someone edits one — which is how eight names came to be defined twice consecutively
    while every test passed (owner P0-10)."""
    import ast
    from collections import Counter
    src = (ROOT / "g33_fortran" / "g33_fortran_dump.py").read_text()
    tree = ast.parse(src)
    names = Counter(
        t.id for node in tree.body if isinstance(node, ast.Assign)
        for t in node.targets if isinstance(t, ast.Name))
    dupes = {n: c for n, c in names.items() if c > 1}
    assert not dupes, f"module-level names assigned more than once: {dupes}"


def test_every_comparator_stage_has_a_classifier_branch():
    """A stage with no branch of its own falls through to "pairs diverge differently",
    which names the phase and says nothing about what it means. micro_call_progb_aux did
    exactly that until it got one (owner P0-4)."""
    import ast
    import g33_fourcase_comparator as cmp
    src = (ROOT / "g33_fourcase_comparator.py").read_text()
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "classify")
    handled = {c.value for c in ast.walk(fn)
               if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    # phases the comparator can report as a first divergence, minus the ones deliberately
    # grouped: substep_pre and outer_pre_sed share the _PRESED branch, ops are the
    # promotable path, final_output/surface share the whole-step handling
    grouped = {"substep_pre", "outer_pre_sed", "op", "surface", "final_output"}
    for stage in cmp._STAGES:
        if stage in grouped:
            continue
        assert stage in handled, (
            f"{stage} has no branch in classify(); a first divergence there would fall "
            f"through to the generic reason")
