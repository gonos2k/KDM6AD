#!/usr/bin/env python3
"""A digest of the DECISION LOGIC, so an artifact goes stale when it changes.

`decision_protocol_version` covers the EVIDENCE contract — which stages exist,
what fields they carry. It does not cover the code that turns that evidence into
a verdict. A change to the comparator's ordering, to the activity filter's rule,
or to the replay's association changes the answer without touching the protocol
version, and the artifact produced before it stays `current` while no longer
describing what the current tree would conclude (owner review §3).

So the artifact records what it was decided BY, and the index test compares that
against the tree it is being read in. Editing a test or a document does not
invalidate a result; editing the verdict logic does.

The file list is explicit rather than a glob: a glob would silently start
including whatever lands in the directory, and the point is to state which code
the verdict depends on.
"""
from __future__ import annotations

import hashlib
import pathlib

HARNESS = pathlib.Path(__file__).resolve().parent

#: Every module whose behaviour can change a verdict from the same evidence.
DECISION_LOGIC = (
    "g33_fourcase_comparator.py",   # ordering, first divergence, classification
    "g33_activity.py",              # which records are verdict-eligible
    "g33_update_replay.py",         # the replay arithmetic and branch rule
    "g33_replay.py",                # op-ladder replay
    "g33_evidence_validate.py",     # gate semantics, record identity
    "g33_schema.py",                # stage/field vocabulary and ordering
    "g33_normalize.py",             # projection of both backends onto it
    "g33_bundle_io.py",             # C++ leg verification
    "g33_fortran_bundle_io.py",     # Fortran leg verification, protocol version
    "g33_fourcase_load.py",         # anchoring and Gate A wiring
    "g33_mechanism.py",             # the closed-world mechanism vocabulary
)


def semantics_sha256() -> str:
    """SHA256 over the decision-logic sources, in the declared order.

    Each file contributes its name and length as well as its bytes, so a rename or
    a boundary shift between two files cannot leave the digest unchanged.
    """
    h = hashlib.sha256()
    for name in DECISION_LOGIC:
        b = (HARNESS / name).read_bytes()
        h.update(name.encode())
        h.update(str(len(b)).encode())
        h.update(b)
    return h.hexdigest()


def missing() -> tuple:
    """Declared files that are not present — a rename must fail loudly."""
    return tuple(n for n in DECISION_LOGIC if not (HARNESS / n).is_file())
