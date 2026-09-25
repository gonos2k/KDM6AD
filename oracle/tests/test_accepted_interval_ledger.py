"""Rejected attempts and duplicate delivery cannot contaminate accepted Q."""

from dataclasses import replace
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from accepted_interval_ledger import (  # noqa: E402
    TrialEvent, accept_trial, initial_ledger, reject_trial, restore_ledger,
)
from interval_exchange_contract import (  # noqa: E402
    IntegrationPlan, PlannedInterval, RateRecord, integrate_rate_plan,
)


REVISIONS = (("state", "s1"), ("geometry", "g1"))


def _plan():
    return IntegrationPlan(
        "exchange-1", 0.,
        (PlannedInterval("a", 0., .2, REVISIONS),
         PlannedInterval("b", .2, 1., REVISIONS)),
        ("state", "geometry"), "W/m2", "J/m2",
    )


def _trial(interval, trial_id, amount, *, revisions=REVISIONS, unit="J/m2"):
    return TrialEvent(interval, trial_id, amount, unit, revisions)


def test_rejected_trial_never_enters_accepted_variable_interval_total():
    plan = _plan()
    integrated = integrate_rate_plan(plan, (
        RateRecord("a", 2., "W/m2", 0., 0., .2, REVISIONS),
        RateRecord("b", 8., "W/m2", 0., 0., 1., REVISIONS),
    ))
    assert integrated.contributions == (("a", .4), ("b", 6.4))
    ledger = initial_ledger(plan)
    rejected = reject_trial(plan, ledger, _trial("a", "try-a1", 10.))
    assert rejected.cumulative_amount == 0.
    assert rejected.completed_ids == ()
    assert rejected.as_of_s == 0.
    first = accept_trial(plan, rejected, _trial("a", "try-a2", integrated.contributions[0][1]),
                         acceptance_id="A")
    assert first.cumulative_amount == .4
    assert first.completed_ids == ("a",)
    assert first.as_of_s == .2
    final = accept_trial(plan, first, _trial("b", "try-b1", integrated.contributions[1][1]),
                         acceptance_id="B")
    assert final.cumulative_amount == pytest.approx(6.8)
    assert final.completed_ids == ("a", "b")
    assert final.as_of_s == 1.


def test_duplicate_acceptance_is_idempotent_and_conflict_is_rejected():
    plan = _plan()
    trial = _trial("a", "try-a", .4)
    first = accept_trial(plan, initial_ledger(plan), trial, acceptance_id="A")
    after_second_interval = accept_trial(
        plan, first, _trial("b", "try-b", 6.4), acceptance_id="B")
    assert accept_trial(plan, after_second_interval, trial, acceptance_id="A") is after_second_interval
    with pytest.raises(ValueError, match="conflicting content"):
        accept_trial(plan, after_second_interval, _trial("a", "try-a", .5),
                     acceptance_id="A")
    with pytest.raises(ValueError, match="already accepted or rejected"):
        accept_trial(plan, first, trial, acceptance_id="another-id")
    with pytest.raises(ValueError, match="all planned intervals"):
        accept_trial(plan, after_second_interval, _trial("b", "new-try", 6.4),
                     acceptance_id="C")


def test_rejected_trial_id_cannot_be_reaccepted_or_changed():
    plan = _plan()
    trial = _trial("a", "failed-attempt", 10.)
    rejected = reject_trial(plan, initial_ledger(plan), trial)
    assert reject_trial(plan, rejected, trial) is rejected
    with pytest.raises(ValueError, match="conflicting content"):
        reject_trial(plan, rejected, _trial("a", "failed-attempt", 9.))
    with pytest.raises(ValueError, match="already accepted or rejected"):
        accept_trial(plan, rejected, trial, acceptance_id="A")


def test_restart_accepts_exact_prefix_and_never_reapplies_it():
    plan = _plan()
    first = accept_trial(plan, initial_ledger(plan), _trial("a", "try-a", .4),
                         acceptance_id="A")
    restored = restore_ledger(plan, first)
    assert restored is first
    final = accept_trial(plan, restored, _trial("b", "try-b", 6.4), acceptance_id="B")
    assert final.cumulative_amount == pytest.approx(6.8)
    for damaged, message in (
        (replace(first, plan_sha256="0" * 64), "independent interval plan"),
        (replace(first, completed_ids=()), "exact plan prefix"),
        (replace(first, as_of_s=0.), "ledger time"),
        (replace(first, cumulative_amount=.8), "cumulative amount"),
        (replace(first, accepted=(replace(first.accepted[0], payload_sha256="0" * 64),)),
         "payload changed"),
        (replace(first, accepted=(replace(first.accepted[0], acceptance_id="changed"),)),
         "payload changed"),
    ):
        with pytest.raises(ValueError, match=message):
            restore_ledger(plan, damaged)
    changed_plan = replace(plan, intervals=(replace(plan.intervals[0], end_s=.25),
                                            replace(plan.intervals[1], start_s=.25)))
    with pytest.raises(ValueError, match="independent interval plan"):
        restore_ledger(changed_plan, first)
    future_rejection = replace(first, rejected=(
        reject_trial(plan, first, _trial("b", "failed-b", 9.)).rejected[0],
    ))
    with pytest.raises(ValueError, match="beyond the reached"):
        restore_ledger(plan, replace(initial_ledger(plan),
                                     rejected=future_rejection.rejected))


def test_signed_amount_and_invalid_unit_revision_or_payload():
    plan = _plan()
    accepted = accept_trial(plan, initial_ledger(plan), _trial("a", "return", -2.),
                            acceptance_id="signed-A")
    assert accepted.cumulative_amount == -2.
    with pytest.raises(ValueError, match="planned amount unit"):
        accept_trial(plan, initial_ledger(plan), _trial("a", "wrong-unit", 1., unit="W/m2"),
                     acceptance_id="A")
    with pytest.raises(ValueError, match="stale"):
        accept_trial(plan, initial_ledger(plan),
                     _trial("a", "wrong-state", 1., revisions=(("state", "s2"),
                                                              ("geometry", "g1"))),
                     acceptance_id="A")
    for bad in (math.nan, True):
        with pytest.raises(ValueError, match="finite real"):
            accept_trial(plan, initial_ledger(plan), _trial("a", "bad", bad),
                         acceptance_id="A")
    with pytest.raises(ValueError, match="not in the independent plan"):
        accept_trial(plan, initial_ledger(plan), _trial("missing", "bad", 1.),
                     acceptance_id="A")
