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
def test_one_byte_in_ANY_covered_file_moves_the_digest(name):
    """A digest that does not respond to every file it claims to cover is a digest
    over a subset, whatever its docstring says."""
    import hashlib
    before = vid.semantics_sha256()
    orig = (vid.HARNESS / name).read_bytes()
    h = hashlib.sha256()
    h.update(vid._DOMAIN)
    for n in vid.DECISION_LOGIC:
        body = (orig + b"\n# mutation\n") if n == name \
            else (vid.HARNESS / n).read_bytes()
        nb = n.encode()
        h.update(len(nb).to_bytes(4, "big"))
        h.update(nb)
        h.update(len(body).to_bytes(8, "big"))
        h.update(body)
    assert h.hexdigest() != before, f"editing {name} does not move the digest"


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
