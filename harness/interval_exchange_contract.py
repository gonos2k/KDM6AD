"""Declared variable-interval rate integration and dependency-validity pilot.

No radiation or land-surface solver is implemented here. The independent plan
defines expected intervals and consumer dependencies; producer records may be
reused only across their declared validity horizon with matching revisions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from numbers import Real


RevisionPairs = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PlannedInterval:
    interval_id: str
    start_s: float
    end_s: float
    consumer_revisions: RevisionPairs


@dataclass(frozen=True)
class IntegrationPlan:
    plan_id: str
    epoch_s: float
    intervals: tuple[PlannedInterval, ...]
    required_dependencies: tuple[str, ...]
    rate_unit: str
    amount_unit: str


@dataclass(frozen=True)
class RateRecord:
    interval_id: str
    rate: float
    rate_unit: str
    produced_at_s: float
    valid_from_s: float
    valid_until_s: float
    producer_revisions: RevisionPairs


@dataclass(frozen=True)
class AccumulationCheckpoint:
    plan_id: str
    plan_sha256: str
    as_of_s: float
    cumulative_amount: float
    amount_unit: str
    completed_ids: tuple[str, ...]


@dataclass(frozen=True)
class IntegrationResult:
    checkpoint: AccumulationCheckpoint
    contributions: tuple[tuple[str, float], ...]


def _finite_real(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite real, not a mask")
    return float(value)


def _revisions(pairs: RevisionPairs, required: tuple[str, ...]) -> dict[str, str]:
    if not isinstance(pairs, tuple):
        raise ValueError("dependency revisions must be immutable pairs")
    result: dict[str, str] = {}
    for pair in pairs:
        if (not isinstance(pair, tuple) or len(pair) != 2
                or not all(isinstance(x, str) and x for x in pair)):
            raise ValueError("dependency keys and revisions must be nonempty strings")
        key, value = pair
        if key in result:
            raise ValueError("duplicate dependency revision")
        result[key] = value
    if set(result) != set(required):
        raise ValueError("dependency set differs from the independent plan")
    return result


def _validated_plan(plan: IntegrationPlan) -> None:
    if (not isinstance(plan.plan_id, str) or not plan.plan_id
            or not isinstance(plan.rate_unit, str) or not plan.rate_unit
            or not isinstance(plan.amount_unit, str) or not plan.amount_unit
            or not isinstance(plan.intervals, tuple) or not plan.intervals
            or not isinstance(plan.required_dependencies, tuple)
            or not plan.required_dependencies
            or any(not isinstance(k, str) or not k for k in plan.required_dependencies)
            or len(set(plan.required_dependencies)) != len(plan.required_dependencies)):
        raise ValueError("declare plan ID, units, nonempty intervals and unique dependencies")
    expected_start = _finite_real(plan.epoch_s, "plan epoch")
    seen: set[str] = set()
    for interval in plan.intervals:
        if (not isinstance(interval.interval_id, str) or not interval.interval_id
                or interval.interval_id in seen):
            raise ValueError("interval IDs must be nonempty and unique")
        seen.add(interval.interval_id)
        start = _finite_real(interval.start_s, "interval start")
        end = _finite_real(interval.end_s, "interval end")
        if start != expected_start or end <= start:
            raise ValueError("declared intervals must tile time in order without gaps")
        _revisions(interval.consumer_revisions, plan.required_dependencies)
        expected_start = end


def plan_sha256(plan: IntegrationPlan) -> str:
    """Stable identity for the entire independent interval/dependency plan."""
    _validated_plan(plan)
    encoded = json.dumps(asdict(plan), sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def integrate_rate_plan(plan: IntegrationPlan, records: tuple[RateRecord, ...],
                        *, checkpoint: AccumulationCheckpoint | None = None) -> IntegrationResult:
    """Integrate each signed rate over its own planned interval, once.

    A checkpoint must name an exact completed prefix of the independent plan.
    This prevents a restart from double-counting an earlier exchange. A
    producer may intentionally hold a rate across intervals if its validity
    window and declared dependencies cover every consumer interval.
    """
    digest = plan_sha256(plan)
    if checkpoint is None:
        completed: tuple[str, ...] = ()
        total = 0.0
        as_of = plan.epoch_s
    else:
        completed = checkpoint.completed_ids
        if (checkpoint.plan_id != plan.plan_id
                or checkpoint.plan_sha256 != digest
                or checkpoint.amount_unit != plan.amount_unit
                or not isinstance(completed, tuple)
                or completed != tuple(i.interval_id for i in plan.intervals[:len(completed)])):
            raise ValueError("restart checkpoint does not match a completed plan prefix")
        as_of = plan.intervals[len(completed) - 1].end_s if completed else plan.epoch_s
        if _finite_real(checkpoint.as_of_s, "restart time") != as_of:
            raise ValueError("restart cumulative origin time changed")
        total = _finite_real(checkpoint.cumulative_amount, "restart amount")
        if not completed and total != 0:
            raise ValueError("empty completed prefix cannot carry prior exchange")
    remaining = plan.intervals[len(completed):]
    if not isinstance(records, tuple):
        raise ValueError("rate records must be an explicit immutable collection")
    if any(not isinstance(record, RateRecord) for record in records):
        raise ValueError("rate records must use the declared record type")
    by_id = {record.interval_id: record for record in records}
    if (len(by_id) != len(records)
            or set(by_id) != {interval.interval_id for interval in remaining}):
        raise ValueError("missing, duplicate, completed or unexpected interval record")
    contributions = []
    for interval in remaining:
        record = by_id[interval.interval_id]
        if record.rate_unit != plan.rate_unit:
            raise ValueError("rate unit differs from independent plan")
        producer = _revisions(record.producer_revisions, plan.required_dependencies)
        consumer = _revisions(interval.consumer_revisions, plan.required_dependencies)
        if producer != consumer:
            raise ValueError("stale state, geometry, parameter, optical or unit dependency")
        produced = _finite_real(record.produced_at_s, "production time")
        valid_from = _finite_real(record.valid_from_s, "validity start")
        valid_until = _finite_real(record.valid_until_s, "validity end")
        if (produced > interval.start_s or valid_from > interval.start_s
                or valid_until < interval.end_s or valid_until <= valid_from):
            raise ValueError("cached rate is outside its declared consumer interval")
        rate = _finite_real(record.rate, "rate")
        amount = rate * (interval.end_s - interval.start_s)
        total += amount
        if not math.isfinite(amount) or not math.isfinite(total):
            raise ValueError("integrated exchange overflowed")
        contributions.append((interval.interval_id, amount))
    return IntegrationResult(
        AccumulationCheckpoint(plan.plan_id, digest,
                               plan.intervals[-1].end_s if remaining else as_of,
                               total, plan.amount_unit,
                               tuple(i.interval_id for i in plan.intervals)),
        tuple(contributions),
    )
