"""The verifier digest must cover what a verdict actually depends on.

The first version enumerated eleven modules by hand and described that as
"explicit rather than a glob". Neither framing was the issue: a hand list is not
the DEPENDENCY CLOSURE, and it missed `g33_expectation`, `g33_derived`,
`g33_dump`, `g33_abc_protocol`, `g33_schedule_probe`, `g33_fixture_v1` and the two
Fortran parser modules. Any of those changes how the same bundle parses, whether
it is admissible, or which records are expected — with the digest unmoved, and so
with a stale artifact still marked current.

So the set is derived and the list is a frozen copy of it, asserted equal in both
directions.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_verifier_identity as vid  # noqa: E402


def test_the_declared_list_IS_the_import_closure():
    closure, listed = set(vid.closure()), set(vid.DECISION_LOGIC)
    assert closure - listed == set(), (
        f"reachable from the decision roots but not digested: "
        f"{sorted(closure - listed)} — a change there would move the verdict and "
        f"leave the artifact marked current")
    assert listed - closure == set(), (
        f"digested but nothing imports it: {sorted(listed - closure)} — the digest "
        f"would then go stale for a file no verdict depends on")


def test_the_closure_reaches_the_modules_the_review_named():
    """These were the concrete misses. Naming them keeps the regression pinned to
    the actual failure rather than to the count."""
    closure = set(vid.closure())
    for name in ("g33_expectation.py", "g33_derived.py", "g33_dump.py",
                 "g33_abc_protocol.py", "g33_schedule_probe.py",
                 "g33_fixture_v1.py", "g33_fortran/g33_fortran_dump.py",
                 "g33_fortran/g33_fortran_semantics.py"):
        assert name in closure, f"{name} is not reachable from the decision roots"


def test_every_declared_file_exists():
    assert vid.missing() == (), f"declared but absent: {vid.missing()}"


@pytest.mark.parametrize("name", sorted(vid.DECISION_LOGIC))
def test_one_byte_in_ANY_covered_file_moves_the_PRODUCTION_digest(name):
    """The mutation goes through the real hasher, not a copy of it.

    The first version built its own hash beside the production one and compared
    the two. That can pass while the production hasher SKIPS a file entirely: the
    baseline would then be a digest over 19 files and the test's hash over 20, so
    they differ for every parametrisation regardless of the mutation. It proved
    nothing about which files the shipped code reads.

    Same shape this repository was already burned by — a manifest replayed into
    the writer in manifest order, passing while the real overlay differed in k,
    shape, count and field set. So `semantics_sha256` now takes the reader, and
    this perturbs exactly one file through it.
    """
    real = {n: (vid.HARNESS / n).read_bytes() for n in vid.DECISION_LOGIC}
    baseline = vid.semantics_sha256(real.__getitem__)
    assert baseline == vid.semantics_sha256(), (
        "the injected reader must reproduce the default digest, or this test is "
        "measuring a different function than production uses")
    mutated = dict(real, **{name: real[name] + b"\n# mutation\n"})
    assert vid.semantics_sha256(mutated.__getitem__) != baseline, (
        f"editing {name} does not move the digest the verifier actually computes")


def test_a_hasher_that_SKIPPED_a_file_would_be_caught():
    """The failure the previous test could not see, made explicit.

    A digest over a subset must not equal the digest over the whole set — if it
    did, dropping a file from DECISION_LOGIC would be invisible.
    """
    real = {n: (vid.HARNESS / n).read_bytes() for n in vid.DECISION_LOGIC}
    full = vid.semantics_sha256(real.__getitem__)
    for drop in vid.DECISION_LOGIC[:3]:
        short = dict(real, **{drop: b""})
        assert vid.semantics_sha256(short.__getitem__) != full


def test_the_digest_is_domain_separated_and_length_prefixed():
    """Without lengths, a rename shifting a byte boundary between two files could
    leave the concatenation — and the digest — unchanged."""
    assert vid._DOMAIN.startswith(b"KDM6AD-G33-VERIFIER")
    src = (ROOT / "g33_verifier_identity.py").read_text()
    assert "to_bytes(4" in src and "to_bytes(8" in src


def test_the_digest_can_be_computed_at_a_COMMIT():
    """This is what binds the two provenance fields: a recorded commit and a
    recorded digest are each merely plausible until checked against each other."""
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT.parent,
                          capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "harness"],
                           cwd=ROOT.parent, capture_output=True, text=True).stdout
    at_head = vid.semantics_sha256_at(head)
    assert at_head is not None, "cannot read the decision logic at HEAD"
    if not dirty:
        assert at_head == vid.semantics_sha256()


def test_an_unknown_commit_returns_None_rather_than_raising():
    assert vid.semantics_sha256_at("0" * 40) is None


# ── the closure's own blind spots, made loud (owner review §6) ────────────────

def test_no_DYNAMIC_import_hides_a_dependency():
    """The AST walk resolves `import g33_x` and `from g33_x import …`. A module
    named at runtime is outside what it can follow, so the closure would stop
    being complete SILENTLY and the digest would keep reporting a set that no
    longer matches what runs.

    Failing is the right response, not making the parser cleverer: this project
    has already learned on the C++ side that each round of teaching a static
    checker one more construct produced another fail-open.
    """
    found = vid.dynamic_imports_in_closure()
    assert not found, (
        "dynamic import inside the decision closure — the digest can no longer be "
        "trusted to cover what runs:\n"
        + "\n".join(f"  {f}:{ln} {call}(…)" for f, ln, call in found))


def test_the_tripwire_would_actually_FIRE():
    """A tripwire that has never been shown to trip is a comment."""
    import ast as _ast
    tree = _ast.parse("import importlib\nx = importlib.import_module('g33_schema')\n")
    calls = [n for n in _ast.walk(tree) if isinstance(n, _ast.Call)]
    names = [n.func.attr for n in calls if isinstance(n.func, _ast.Attribute)]
    assert set(names) & set(vid._DYNAMIC_IMPORT_CALLS), (
        "the call the detector looks for is not the call this construct makes")


def test_no_module_stem_is_resolvable_in_TWO_search_directories():
    """`_resolve` returns the first hit, so a shadowed second file would never be
    digested while an import of that name might load it."""
    dup = vid.duplicate_module_stems()
    assert not dup, (
        f"module stem(s) present in both harness/ and harness/g33_fortran/: "
        f"{list(dup)} — one of them is shadowed and unhashed")


def test_the_module_that_DEFINES_coverage_is_itself_covered():
    """It was excluded on the grounds that "it digests, it does not decide".

    That is wrong. DECISION_LOGIC, NOT_DECISION_LOGIC and `_digest` between them
    determine what is covered at all, so a change here changes what the digest
    MEANS — and the one thing coverage did not include was the module defining
    coverage. There is no circularity: the digest reads bytes off disk, it does not
    depend on its own value.
    """
    assert "g33_verifier_identity.py" in vid.DECISION_LOGIC
    assert vid.NOT_DECISION_LOGIC == frozenset(), (
        "an exception needs a reason recorded next to it; an empty set is the "
        "default because every exception is a hole in the coverage claim")


def test_editing_the_DECISION_LOGIC_LIST_moves_the_digest():
    """The list is inside a covered file, so shortening it is visible — which is
    what stops a future edit from quietly narrowing what a verdict depends on."""
    real = {n: (vid.HARNESS / n).read_bytes() for n in vid.DECISION_LOGIC}
    baseline = vid.semantics_sha256(real.__getitem__)
    edited = dict(real)
    edited["g33_verifier_identity.py"] = real["g33_verifier_identity.py"].replace(
        b'"g33_schema.py",', b"")
    assert vid.semantics_sha256(edited.__getitem__) != baseline
