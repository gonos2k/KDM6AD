"""Small reusable evidence-manifest check; external truth is not inferred.

The caller supplies an independently fixed expected event set. Measured,
derived and synthetic records have different required provenance. This
checks manifest completeness and labels, not native-file authenticity or a
scientific acceptance gate by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
EventKey = tuple[str | int, ...]


class EvidenceTier(str, Enum):
    MEASURED = "measured"
    DERIVED = "derived"
    SYNTHETIC = "synthetic"


@dataclass(frozen=True)
class ExpectedEvidence:
    key: EventKey
    tier: EvidenceTier
    source_sha256: str | None = None
    payload_sha256: str | None = None
    generator_id: str | None = None
    parents: tuple[EventKey, ...] = ()


@dataclass(frozen=True)
class EvidenceRecord:
    key: EventKey
    tier: EvidenceTier
    source_sha256: str | None = None
    payload_sha256: str | None = None
    generator_id: str | None = None
    parents: tuple[EventKey, ...] = ()


@dataclass(frozen=True)
class EvidencePlan:
    case_id: str
    expected: tuple[ExpectedEvidence, ...]


@dataclass(frozen=True)
class EvidenceAudit:
    case_id: str
    measured: int
    derived: int
    synthetic: int
    scope: str = "manifest_consistency_only"


def _key(key: EventKey) -> None:
    if (not isinstance(key, tuple) or not key
            or any(isinstance(x, bool) or not isinstance(x, (str, int))
                   or (isinstance(x, str) and not x) for x in key)):
        raise ValueError("event identity must be a nonempty tuple of strings/integers")


def _validate_expected(item: ExpectedEvidence, prior: set[EventKey]) -> None:
    _key(item.key)
    if not isinstance(item.tier, EvidenceTier):
        raise ValueError("evidence tier must be declared")
    if (item.payload_sha256 is not None
            and (not isinstance(item.payload_sha256, str)
                 or not _SHA256.fullmatch(item.payload_sha256))):
        raise ValueError("declared payload SHA256 is malformed")
    if not isinstance(item.parents, tuple):
        raise ValueError("derived parent identities must be immutable")
    if item.tier is EvidenceTier.MEASURED:
        if (not isinstance(item.source_sha256, str)
                or not _SHA256.fullmatch(item.source_sha256)
                or item.generator_id is not None or item.parents):
            raise ValueError("measured event needs a source digest, not a generator/parent")
    elif item.tier is EvidenceTier.SYNTHETIC:
        if (item.source_sha256 is not None or not isinstance(item.generator_id, str)
                or not item.generator_id or item.parents):
            raise ValueError("synthetic event needs a generator, not a measured source")
    else:
        for parent in item.parents:
            _key(parent)
        if (item.source_sha256 is not None or item.generator_id is not None
                or not item.parents or len(set(item.parents)) != len(item.parents)):
            raise ValueError("derived event needs unique declared parent events")
        for parent in item.parents:
            if parent not in prior:
                raise ValueError("derived event parent must precede it in the plan")


def audit_evidence(plan: EvidencePlan, records: tuple[EvidenceRecord, ...]) -> EvidenceAudit:
    """Reject absent, extra, relabelled or wrongly attributed planned events."""
    if (not isinstance(plan.case_id, str) or not plan.case_id
            or not isinstance(plan.expected, tuple) or not plan.expected
            or not isinstance(records, tuple)):
        raise ValueError("independent nonempty evidence plan and record tuple required")
    expected = {}
    for item in plan.expected:
        if not isinstance(item, ExpectedEvidence):
            raise ValueError("expected events must use the declared schema")
        _validate_expected(item, set(expected))
        if item.key in expected:
            raise ValueError("duplicate expected event")
        expected[item.key] = item
    actual = {}
    for item in records:
        if not isinstance(item, EvidenceRecord):
            raise ValueError("actual events must use the declared schema")
        _key(item.key)
        if item.key in actual:
            raise ValueError("duplicate observed event")
        actual[item.key] = item
    if set(actual) != set(expected):
        raise ValueError("missing or unexpected evidence event")
    counts = {tier: 0 for tier in EvidenceTier}
    for key, declared in expected.items():
        observed = actual[key]
        if (observed.tier is not declared.tier
                or observed.source_sha256 != declared.source_sha256
                or observed.generator_id != declared.generator_id
                or observed.parents != declared.parents
                or (declared.payload_sha256 is not None
                    and observed.payload_sha256 != declared.payload_sha256)):
            raise ValueError("evidence tier, ancestry, source or pinned payload changed")
        if (observed.payload_sha256 is not None
                and (not isinstance(observed.payload_sha256, str)
                     or not _SHA256.fullmatch(observed.payload_sha256))):
            raise ValueError("observed payload SHA256 is malformed")
        counts[declared.tier] += 1
    return EvidenceAudit(plan.case_id, counts[EvidenceTier.MEASURED],
                         counts[EvidenceTier.DERIVED], counts[EvidenceTier.SYNTHETIC])
