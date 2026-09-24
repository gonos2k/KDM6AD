"""Variable-interval radiative-exchange arithmetic and cache contracts."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from interval_exchange_contract import (  # noqa: E402
    PlannedInterval, IntegrationPlan, RateRecord, AccumulationCheckpoint,
    integrate_rate_plan, plan_sha256,
)


DEPS = (("state", "s1"), ("geometry", "g1"), ("parameters", "p1"),
        ("optics", "o1"), ("units", "W_per_m2"))
KEYS = tuple(key for key, _ in DEPS)


def _plan(deps_a=DEPS, deps_b=DEPS):
    return IntegrationPlan(
        "radiative_exchange_case", 0.,
        (PlannedInterval("a", 0., .2, deps_a),
         PlannedInterval("b", .2, 1., deps_b)),
        KEYS, "W/m2", "J/m2",
    )


def _record(name, rate, *, deps=DEPS, produced=0., start=0., until=1.):
    return RateRecord(name, rate, "W/m2", produced, start, until, deps)


def test_each_rate_is_integrated_over_its_own_interval():
    result = integrate_rate_plan(_plan(),
                                 (_record("a", 2.), _record("b", 8., produced=.2)))
    assert result.contributions == (("a", pytest.approx(.4)),
                                    ("b", pytest.approx(6.4)))
    assert result.checkpoint.cumulative_amount == pytest.approx(6.8)
    assert result.checkpoint.amount_unit == "J/m2"
    assert result.checkpoint.completed_ids == ("a", "b")
    assert result.checkpoint.cumulative_amount != pytest.approx((2. + 8.) * .8)


def test_restart_uses_completed_prefix_once_and_rejects_duplicate_record():
    checkpoint = AccumulationCheckpoint("radiative_exchange_case", plan_sha256(_plan()), .2, .4,
                                        "J/m2", ("a",))
    after = integrate_rate_plan(_plan(), (_record("b", 8., produced=.2),),
                                checkpoint=checkpoint)
    assert after.contributions == (("b", pytest.approx(6.4)),)
    assert after.checkpoint.cumulative_amount == pytest.approx(6.8)
    with pytest.raises(ValueError, match="missing, duplicate, completed"):
        integrate_rate_plan(_plan(), (_record("a", 2.), _record("b", 8.)),
                            checkpoint=checkpoint)
    with pytest.raises(ValueError, match="origin time"):
        integrate_rate_plan(_plan(), (_record("b", 8.),), checkpoint=
                            AccumulationCheckpoint("radiative_exchange_case", plan_sha256(_plan()), 0., .4,
                                                   "J/m2", ("a",)))
    with pytest.raises(ValueError, match="finite real"):
        integrate_rate_plan(_plan(), (_record("b", 8.),), checkpoint=
                            AccumulationCheckpoint("radiative_exchange_case", plan_sha256(_plan()), True, .4,
                                                   "J/m2", ("a",)))
    with pytest.raises(ValueError, match="empty completed prefix"):
        integrate_rate_plan(
            _plan(), (_record("a", 2.), _record("b", 8.)),
            checkpoint=AccumulationCheckpoint("radiative_exchange_case",
                                              plan_sha256(_plan()), 0., .4,
                                              "J/m2", ()),
        )


def test_restart_rejects_same_name_and_clock_with_changed_completed_dependency():
    old = _plan()
    checkpoint = AccumulationCheckpoint(old.plan_id, plan_sha256(old), .2,
                                        .4, "J/m2", ("a",))
    changed_a = tuple((key, "new" if key == "optics" else value) for key, value in DEPS)
    with pytest.raises(ValueError, match="completed plan prefix"):
        integrate_rate_plan(_plan(deps_a=changed_a), (_record("b", 8.),),
                            checkpoint=checkpoint)


def test_intentional_cached_rate_can_span_two_intervals_when_dependencies_match():
    record_a = _record("a", 3., produced=-1., start=0., until=1.)
    record_b = _record("b", 3., produced=-1., start=0., until=1.)
    result = integrate_rate_plan(_plan(), (record_b, record_a))
    assert result.checkpoint.cumulative_amount == pytest.approx(3.)
    assert result.contributions == (("a", pytest.approx(.6)),
                                    ("b", pytest.approx(2.4)))


@pytest.mark.parametrize("changed", ["state", "geometry", "parameters", "optics", "units"])
def test_changed_consumer_dependency_rejects_stale_cached_rate(changed):
    updated = tuple((key, "new" if key == changed else value) for key, value in DEPS)
    with pytest.raises(ValueError, match="stale"):
        integrate_rate_plan(_plan(deps_b=updated),
                            (_record("a", 2.), _record("b", 8., produced=.2)))


def test_validity_horizon_not_generation_count_controls_intended_reuse():
    with pytest.raises(ValueError, match="outside"):
        integrate_rate_plan(_plan(),
                            (_record("a", 2.), _record("b", 8., until=.7)))
    with pytest.raises(ValueError, match="outside"):
        integrate_rate_plan(_plan(),
                            (_record("a", 2.), _record("b", 8., produced=.3)))


def test_plan_not_received_records_defines_expected_interval_set():
    with pytest.raises(ValueError, match="missing, duplicate"):
        integrate_rate_plan(_plan(), (_record("a", 2.),))
    with pytest.raises(ValueError, match="missing, duplicate"):
        integrate_rate_plan(_plan(), (_record("a", 2.), _record("a", 8.)))
    with pytest.raises(ValueError, match="missing, duplicate"):
        integrate_rate_plan(_plan(), (_record("a", 2.), _record("b", 8.),
                                      _record("extra", 1.)))
    with pytest.raises(ValueError, match="tile time"):
        bad = IntegrationPlan("radiative_exchange_case", 0.,
                              (PlannedInterval("a", 0., .2, DEPS),
                               PlannedInterval("b", .3, 1., DEPS)),
                              KEYS, "W/m2", "J/m2")
        integrate_rate_plan(bad, (_record("a", 2.), _record("b", 8.)))


def test_rate_unit_and_nonfinite_or_boolean_payloads_are_refused():
    with pytest.raises(ValueError, match="rate unit"):
        integrate_rate_plan(_plan(), (_record("a", 2.),
                                      RateRecord("b", 8., "K/s", .2, .2, 1., DEPS)))
    with pytest.raises(ValueError, match="finite real"):
        integrate_rate_plan(_plan(), (_record("a", 2.), _record("b", True)))
    with pytest.raises(ValueError, match="finite real"):
        integrate_rate_plan(_plan(), (_record("a", 2.), _record("b", float("nan"))))


def test_signed_exchange_and_overflow_are_not_silently_clipped():
    signed = integrate_rate_plan(_plan(), (_record("a", 2.), _record("b", -8.)))
    assert signed.checkpoint.cumulative_amount == pytest.approx(-6.)
    with pytest.raises(ValueError, match="overflowed"):
        integrate_rate_plan(
            _plan(), (_record("b", 1e308),),
            checkpoint=AccumulationCheckpoint("radiative_exchange_case", plan_sha256(_plan()), .2,
                                              1e308, "J/m2", ("a",)),
        )
