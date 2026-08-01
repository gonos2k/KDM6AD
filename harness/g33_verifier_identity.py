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
#:
#: EMPTY, and this module is deliberately not in it. It was, on the grounds that
#: "it digests, it does not decide" — which is wrong: DECISION_LOGIC, this
#: exception set and `_digest` between them determine WHAT IS COVERED, so a change
#: here changes what the digest means. The module that defines coverage was the one
#: thing coverage did not include. There is no circularity: the digest reads bytes
#: off disk, it does not depend on its own value.
NOT_DECISION_LOGIC = frozenset()

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


#: How a local module can be pulled in without an `import` statement the AST walk
#: above can see. None of these appear in the closure today; the point is that if
#: one arrives, the closure stops being complete SILENTLY — the digest would keep
#: reporting a set that no longer matches what runs.
_DYNAMIC_IMPORT_CALLS = ("import_module", "__import__", "load_module", "exec_module")


def dynamic_imports_in_closure() -> tuple:
    """(file, line, call) for every dynamic-import call inside the closure.

    Not a digest input — a tripwire. The AST walk resolves `import g33_x` and
    `from g33_x import ...`; anything that names a module at runtime is outside
    what it can follow, so the honest response is to fail rather than to widen the
    parser and hope. This project has already learned that lesson on the C++ side,
    where each round of making a static expression checker cleverer produced
    another fail-open.
    """
    found = []
    for rel in closure():
        path = HARNESS / rel
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = (fn.attr if isinstance(fn, ast.Attribute)
                    else fn.id if isinstance(fn, ast.Name) else None)
            if name in _DYNAMIC_IMPORT_CALLS:
                found.append((rel, node.lineno, name))
    return tuple(sorted(found))


def duplicate_module_stems() -> tuple:
    """Module stems resolvable in more than one search directory.

    `_resolve` returns the first hit, so a second file with the same stem would be
    shadowed and never digested while an import of that name might well load it.
    """
    seen, dup = {}, set()
    for d in _SEARCH:
        if not d.is_dir():
            continue
        for f in d.glob("g33*.py"):
            if f.stem in seen and seen[f.stem] != f:
                dup.add(f.stem)
            seen.setdefault(f.stem, f)
    return tuple(sorted(dup))


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
    "g33_verifier_identity.py",
    "gateb_g33m_check.py",
)

#: Domain separator + version, so this digest can never collide with another
#: SHA256 over the same bytes computed for a different purpose.
_DOMAIN = b"KDM6AD-G33-VERIFIER\0V2\0"


def _digest(read_bytes) -> str:
    """The one hashing routine. Every caller goes through it, including the tests.

    `read_bytes(name) -> bytes` is injected so a test can perturb ONE file and
    exercise THIS function. The previous mutation test built its own hash instead
    and compared that to the production digest — so it could pass while the
    production hasher skipped a file entirely, which is the circular shape this
    repository has already been burned by once (a manifest replayed into the
    writer in manifest order, passing while the real overlay differed in k, shape,
    count and field set).
    """
    h = hashlib.sha256()
    h.update(_DOMAIN)
    for name in DECISION_LOGIC:
        nb = name.encode()
        body = read_bytes(name)
        h.update(len(nb).to_bytes(4, "big"))
        h.update(nb)
        h.update(len(body).to_bytes(8, "big"))
        h.update(body)
    return h.hexdigest()


def semantics_sha256(read_bytes=None) -> str:
    """SHA256 over the decision-logic sources, in the declared order.

    Length-prefixed and domain-separated: without explicit lengths, a rename that
    shifts a byte boundary between two files could leave the concatenation — and
    therefore the digest — unchanged.
    """
    return _digest(read_bytes or (lambda n: (HARNESS / n).read_bytes()))


def semantics_sha256_at(commit: str) -> str | None:
    """The same digest over the tree at `commit`, or None if it cannot be read.

    This is what binds the two provenance fields together: an artifact records a
    `verifier_commit` AND a digest, and until they are checked against each other
    both are merely plausible.
    """
    import subprocess
    root = HARNESS.parent
    blobs = {}
    for name in DECISION_LOGIC:
        r = subprocess.run(["git", "show", f"{commit}:harness/{name}"],
                           cwd=root, capture_output=True)
        if r.returncode != 0:
            return None
        blobs[name] = r.stdout
    # THE SAME routine as the working-tree digest. Two hashing implementations
    # would be two things to keep in step, and the one that drifted would be the
    # one nothing exercised.
    return _digest(blobs.__getitem__)


def missing() -> tuple:
    """Declared files that are not present — a rename must fail loudly."""
    return tuple(n for n in DECISION_LOGIC if not (HARNESS / n).is_file())


#: The runtime a DECISION artifact must be produced on — the one public CI pins
#: (.github/workflows/g33-harness-ci.yml).
#:
#: Not decoration. The replay is NumPy f32/f64 arithmetic and this decision turns
#: on an f32 storage boundary: the analytic coefficient effect is ~0.46 ULP and the
#: stored result is 1 ULP. Identical sources on a different runtime are not
#: self-evidently the same verifier, and recording the runtime without requiring
#: it left a decision-valid artifact produced on NumPy 1.23.5 while CI ran 2.4.6.
#:
#: The patch level is deliberately not pinned for Python: CI resolves 3.11.x and
#: pinning it would fail on a runner image update for a reason unrelated to the
#: arithmetic. NumPy IS pinned exactly, because it is the arithmetic.
VERIFIER_RUNTIME = {
    "python_implementation": "CPython",
    "python_major_minor": "3.11",
    "numpy_version": "2.4.6",
    "byteorder": "little",
}


def runtime_matches(recorded: dict) -> tuple:
    """Fields of `recorded` that disagree with the required runtime, as (k, want, got)."""
    bad = []
    for k, want in VERIFIER_RUNTIME.items():
        got = (".".join(recorded.get("python_version", "").split(".")[:2])
               if k == "python_major_minor" else recorded.get(k))
        if got != want:
            bad.append((k, want, got))
    return tuple(bad)
