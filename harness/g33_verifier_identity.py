#!/usr/bin/env python3
"""A digest of the DECISION LOGIC, so an artifact goes stale when it changes.

`decision_protocol_version` covers the EVIDENCE contract — which stages exist,
what fields they carry. It does not cover the code that turns that evidence into
a verdict. A change to the comparator's ordering, to the activity filter's rule,
or to the replay's association changes the answer without touching the protocol
version, and the artifact produced before it stays `current` while no longer
describing what the current tree would conclude.

So the artifact records what it was decided BY, and the index test compares that
against the tree it is being read in. Editing a test or a document does not
invalidate a result; editing the verdict logic does.

THE FILE SET IS DERIVED, NOT LISTED. The first version enumerated eleven modules
by hand and called that "explicit rather than a glob". It was neither the right
set nor the wrong kind of set — it was not the DEPENDENCY CLOSURE, and it missed
`g33_expectation` (the expected record universe), `g33_derived`, `g33_dump`,
`g33_abc_protocol`, `g33_schedule_probe`, `g33_fixture_v1` and the two Fortran
parser modules. Any of those can change how the same bundle parses, whether it is
admissible, or which records are expected — with the digest unmoved. The claim
"decision logic changes ⇒ artifact stale" simply did not hold.

It is now computed from the roots by following local imports, and the checked-in
list is asserted equal to that closure in both directions: a dependency missing
from the list fails, and a listed file that nothing imports fails too.
"""
from __future__ import annotations

import ast
import hashlib
import pathlib

HARNESS = pathlib.Path(__file__).resolve().parent

#: Where a verdict starts. Everything reachable from these by local import is part
#: of the decision logic by construction.
DECISION_ROOTS = (
    "gateb_g33m_check.py",
    "g33_fourcase_load.py",
    "g33_fourcase_comparator.py",
)

#: Local modules that are NOT decision logic even though a root imports them.
#: Each needs a reason; the point of the exception list is that it is short and
#: read, not that it exists.
NOT_DECISION_LOGIC = frozenset({
    "g33_verifier_identity",   # this module: it digests, it does not decide
})

_SEARCH = (HARNESS, HARNESS / "g33_fortran")


def _resolve(module: str) -> pathlib.Path | None:
    for d in _SEARCH:
        p = d / f"{module}.py"
        if p.is_file():
            return p
    return None


def _local_imports(path: pathlib.Path) -> set[str]:
    """Every `import g33_x` / `from g33_x import …` that resolves to a local file."""
    out = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module] if node.module and node.level == 0 else []
        else:
            continue
        for n in names:
            head = (n or "").split(".")[0]
            if head.startswith("g33") and _resolve(head):
                out.add(head)
    return out


def closure() -> tuple[str, ...]:
    """The transitive local-import closure of the roots, as repo-relative paths."""
    seen, stack = set(), [r[:-3] for r in DECISION_ROOTS]
    while stack:
        m = stack.pop()
        if m in seen or m in NOT_DECISION_LOGIC:
            continue
        seen.add(m)
        p = _resolve(m)
        if p is not None:
            stack.extend(_local_imports(p) - seen)
    rel = []
    for m in seen:
        p = _resolve(m)
        if p is not None:
            rel.append(p.relative_to(HARNESS).as_posix())
    return tuple(sorted(rel))


#: The closure, frozen into the repository so a change to it is a reviewed diff
#: rather than a silent recomputation. test_g33_verifier_identity asserts the two
#: agree in BOTH directions.
DECISION_LOGIC = (
    "g33_abc_protocol.py",
    "g33_activity.py",
    "g33_bundle_io.py",
    "g33_derived.py",
    "g33_dump.py",
    "g33_evidence_validate.py",
    "g33_expectation.py",
    "g33_fixture_v1.py",
    "g33_fortran/g33_fortran_dump.py",
    "g33_fortran/g33_fortran_semantics.py",
    "g33_fortran_bundle_io.py",
    "g33_fourcase_comparator.py",
    "g33_fourcase_load.py",
    "g33_mechanism.py",
    "g33_normalize.py",
    "g33_replay.py",
    "g33_schedule_probe.py",
    "g33_schema.py",
    "g33_update_replay.py",
    "gateb_g33m_check.py",
)

#: Domain separator + version, so this digest can never collide with another
#: SHA256 over the same bytes computed for a different purpose.
_DOMAIN = b"KDM6AD-G33-VERIFIER\0V2\0"


def semantics_sha256() -> str:
    """SHA256 over the decision-logic sources, in the declared order.

    Length-prefixed and domain-separated: without explicit lengths, a rename that
    shifts a byte boundary between two files could leave the concatenation — and
    therefore the digest — unchanged.
    """
    h = hashlib.sha256()
    h.update(_DOMAIN)
    for name in DECISION_LOGIC:
        nb = name.encode()
        body = (HARNESS / name).read_bytes()
        h.update(len(nb).to_bytes(4, "big"))
        h.update(nb)
        h.update(len(body).to_bytes(8, "big"))
        h.update(body)
    return h.hexdigest()


def semantics_sha256_at(commit: str) -> str | None:
    """The same digest over the tree at `commit`, or None if it cannot be read.

    This is what binds the two provenance fields together: an artifact records a
    `verifier_commit` AND a digest, and until they are checked against each other
    both are merely plausible.
    """
    import subprocess
    root = HARNESS.parent
    h = hashlib.sha256()
    h.update(_DOMAIN)
    for name in DECISION_LOGIC:
        r = subprocess.run(["git", "show", f"{commit}:harness/{name}"],
                           cwd=root, capture_output=True)
        if r.returncode != 0:
            return None
        nb, body = name.encode(), r.stdout
        h.update(len(nb).to_bytes(4, "big"))
        h.update(nb)
        h.update(len(body).to_bytes(8, "big"))
        h.update(body)
    return h.hexdigest()


def missing() -> tuple:
    """Declared files that are not present — a rename must fail loudly."""
    return tuple(n for n in DECISION_LOGIC if not (HARNESS / n).is_file())
