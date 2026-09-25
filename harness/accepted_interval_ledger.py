"""Immutable trial/accept/restart ledger on X5's independent interval plan.

Amounts here are already integrated over their planned intervals. X5 checks
rate×duration and cached producer validity; this pilot checks which trial was
actually accepted. It is not a host checkpoint or distributed transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from numbers import Real

from interval_exchange_contract import IntegrationPlan, PlannedInterval, plan_sha256


@dataclass(frozen=True)
class TrialEvent:
    interval_id: str
    trial_id: str
    amount: float
    amount_unit: str
    producer_revisions: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class AcceptedEvent:
    acceptance_id: str
    trial: TrialEvent
    payload_sha256: str


@dataclass(frozen=True)
class RejectedEvent:
    trial: TrialEvent
    payload_sha256: str


@dataclass(frozen=True)
class AcceptedLedger:
    plan_id: str
    plan_sha256: str
    amount_unit: str
    as_of_s: float
    completed_ids: tuple[str, ...]
    cumulative_amount: float
    accepted: tuple[AcceptedEvent, ...]
    rejected: tuple[RejectedEvent, ...]


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite real")
    return float(value)


def _interval_by_id(plan: IntegrationPlan, interval_id: str) -> PlannedInterval:
    found = [i for i in plan.intervals if i.interval_id == interval_id]
    if len(found) != 1:
        raise ValueError("trial interval is not in the independent plan")
    return found[0]


def _revisions(value: object) -> dict[str, str]:
    if not isinstance(value, tuple):
        raise ValueError("producer revisions must be immutable pairs")
    result: dict[str, str] = {}
    for pair in value:
        if (not isinstance(pair, tuple) or len(pair) != 2
                or any(not isinstance(x, str) or not x for x in pair)
                or pair[0] in result):
            raise ValueError("producer revisions must have unique nonempty keys")
        result[pair[0]] = pair[1]
    return result


def _trial_payload(plan: IntegrationPlan, trial: TrialEvent) -> str:
    if (not isinstance(trial, TrialEvent)
            or not isinstance(trial.interval_id, str) or not trial.interval_id
            or not isinstance(trial.trial_id, str) or not trial.trial_id
            or trial.amount_unit != plan.amount_unit):
        raise ValueError("trial needs a named interval/ID and planned amount unit")
    amount = _finite(trial.amount, "trial integrated amount")
    interval = _interval_by_id(plan, trial.interval_id)
    producer = _revisions(trial.producer_revisions)
    if producer != _revisions(interval.consumer_revisions):
        raise ValueError("trial used stale state, geometry or other plan dependency")
    encoded = json.dumps({
        "interval_id": trial.interval_id,
        "trial_id": trial.trial_id,
        "amount_hex": amount.hex(),
        "amount_unit": trial.amount_unit,
        "producer_revisions": sorted(producer.items()),
    }, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _accepted_payload(acceptance_id: str, trial_sha256: str) -> str:
    if not isinstance(acceptance_id, str) or not acceptance_id:
        raise ValueError("accepted event needs a nonempty ID")
    encoded = json.dumps({"acceptance_id": acceptance_id,
                          "trial_sha256": trial_sha256},
                         sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _sum_amounts(events: tuple[AcceptedEvent, ...]) -> float:
    try:
        total = math.fsum(_finite(event.trial.amount, "accepted amount")
                          for event in events)
    except OverflowError as exc:
        raise ValueError("accepted amount accumulation overflowed") from exc
    return _finite(total, "accepted cumulative amount")


def validate_ledger(plan: IntegrationPlan, ledger: AcceptedLedger) -> None:
    """Recheck the full accepted prefix and rejected-trial records at restart."""
    digest = plan_sha256(plan)
    if (not isinstance(ledger, AcceptedLedger)
            or ledger.plan_id != plan.plan_id
            or ledger.plan_sha256 != digest
            or ledger.amount_unit != plan.amount_unit
            or not isinstance(ledger.accepted, tuple)
            or not isinstance(ledger.rejected, tuple)
            or not isinstance(ledger.completed_ids, tuple)):
        raise ValueError("ledger does not match independent interval plan")
    if len(ledger.accepted) > len(plan.intervals):
        raise ValueError("ledger has more accepted events than planned intervals")
    prefix = tuple(i.interval_id for i in plan.intervals[:len(ledger.accepted)])
    if ledger.completed_ids != prefix:
        raise ValueError("accepted intervals are not an exact plan prefix")
    expected_as_of = (plan.intervals[len(prefix) - 1].end_s
                      if prefix else plan.epoch_s)
    if _finite(ledger.as_of_s, "ledger time") != expected_as_of:
        raise ValueError("ledger time differs from completed interval boundary")
    accepted_ids: set[str] = set()
    all_trial_ids: set[str] = set()
    for interval, event in zip(plan.intervals, ledger.accepted):
        if (not isinstance(event, AcceptedEvent)
                or not isinstance(event.acceptance_id, str)
                or not event.acceptance_id
                or event.acceptance_id in accepted_ids
                or not isinstance(event.trial, TrialEvent)
                or event.trial.interval_id != interval.interval_id):
            raise ValueError("accepted event ID or interval is missing/duplicated")
        accepted_ids.add(event.acceptance_id)
        if event.trial.trial_id in all_trial_ids:
            raise ValueError("trial ID was reused across accepted/rejected events")
        all_trial_ids.add(event.trial.trial_id)
        if event.payload_sha256 != _accepted_payload(
                event.acceptance_id, _trial_payload(plan, event.trial)):
            raise ValueError("accepted event payload changed")
    for event in ledger.rejected:
        if not isinstance(event, RejectedEvent) or not isinstance(event.trial, TrialEvent):
            raise ValueError("rejected trial record has wrong type")
        interval_index = next((index for index, interval in enumerate(plan.intervals)
                               if interval.interval_id == event.trial.interval_id), None)
        if interval_index is None or interval_index > len(ledger.accepted):
            raise ValueError("rejected trial lies beyond the reached plan interval")
        if event.trial.trial_id in all_trial_ids:
            raise ValueError("trial ID was reused across accepted/rejected events")
        all_trial_ids.add(event.trial.trial_id)
        if event.payload_sha256 != _trial_payload(plan, event.trial):
            raise ValueError("rejected trial payload changed")
    if _finite(ledger.cumulative_amount, "ledger amount") != _sum_amounts(ledger.accepted):
        raise ValueError("ledger cumulative amount differs from accepted events")


def initial_ledger(plan: IntegrationPlan) -> AcceptedLedger:
    digest = plan_sha256(plan)
    state = AcceptedLedger(plan.plan_id, digest, plan.amount_unit,
                           plan.epoch_s, (), 0.0, (), ())
    validate_ledger(plan, state)
    return state


def restore_ledger(plan: IntegrationPlan, checkpoint: AcceptedLedger) -> AcceptedLedger:
    """Read an immutable accepted prefix once; do not reapply its events."""
    validate_ledger(plan, checkpoint)
    return checkpoint


def _next_interval(plan: IntegrationPlan, ledger: AcceptedLedger) -> str:
    if len(ledger.completed_ids) == len(plan.intervals):
        raise ValueError("all planned intervals have already been accepted")
    return plan.intervals[len(ledger.completed_ids)].interval_id


def reject_trial(plan: IntegrationPlan, ledger: AcceptedLedger,
                 trial: TrialEvent) -> AcceptedLedger:
    """Record a rejected attempt without changing cumulative physical amount."""
    validate_ledger(plan, ledger)
    payload = _trial_payload(plan, trial)
    if any(event.trial.trial_id == trial.trial_id for event in ledger.accepted):
        raise ValueError("accepted trial cannot later be rejected")
    for event in ledger.rejected:
        if event.trial.trial_id == trial.trial_id:
            if event.payload_sha256 != payload:
                raise ValueError("same rejected trial ID has conflicting content")
            return ledger
    if trial.interval_id != _next_interval(plan, ledger):
        raise ValueError("rejected trial is outside the current planned interval")
    next_state = AcceptedLedger(
        ledger.plan_id, ledger.plan_sha256, ledger.amount_unit,
        ledger.as_of_s, ledger.completed_ids, ledger.cumulative_amount,
        ledger.accepted, ledger.rejected + (RejectedEvent(trial, payload),),
    )
    validate_ledger(plan, next_state)
    return next_state


def accept_trial(plan: IntegrationPlan, ledger: AcceptedLedger,
                 trial: TrialEvent, *, acceptance_id: str) -> AcceptedLedger:
    """Apply a newly accepted interval once; duplicate exact delivery is inert."""
    validate_ledger(plan, ledger)
    payload = _accepted_payload(acceptance_id, _trial_payload(plan, trial))
    for event in ledger.accepted:
        if event.acceptance_id == acceptance_id:
            if event.payload_sha256 != payload:
                raise ValueError("same accepted event ID has conflicting content")
            return ledger
    if any(event.trial.trial_id == trial.trial_id
           for event in (*ledger.accepted, *ledger.rejected)):
        raise ValueError("trial was already accepted or rejected")
    if trial.interval_id != _next_interval(plan, ledger):
        raise ValueError("accepted trial is outside the next planned interval")
    accepted = ledger.accepted + (AcceptedEvent(acceptance_id, trial, payload),)
    interval = plan.intervals[len(ledger.completed_ids)]
    next_state = AcceptedLedger(
        ledger.plan_id, ledger.plan_sha256, ledger.amount_unit,
        interval.end_s, ledger.completed_ids + (trial.interval_id,),
        _sum_amounts(accepted), accepted, ledger.rejected,
    )
    validate_ledger(plan, next_state)
    return next_state
