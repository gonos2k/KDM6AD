"""Internal RK states and physical consumer inputs have different gates."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from stage_validity_contract import (  # noqa: E402
    StageRole, QuantityDomain, StageSpec, StagePlan, StageRecord, validate_stages,
)


NUMBER = QuantityDomain("number", "declared_internal_number", 0., 1e9)
INTERNAL = StageRole.SOLVER_INTERNAL
CONSUMER = StageRole.PHYSICAL_CONSUMER_INPUT
ACCEPTED = StageRole.ACCEPTED_STATE
DIAG = StageRole.DIAGNOSTIC_ONLY


def _plan(with_repair=False):
    stages = [
        StageSpec("rk", INTERNAL, ("number",), ()),
        StageSpec("boundary_copy", INTERNAL, ("number",), ("rk",)),
    ]
    predecessor = "boundary_copy"
    if with_repair:
        stages.append(StageSpec("declared_repair", INTERNAL, ("number",), (predecessor,)))
        predecessor = "declared_repair"
    stages.extend((
        StageSpec("consumer", CONSUMER, ("number",), (predecessor,)),
        StageSpec("accepted", ACCEPTED, ("number",), ("consumer",)),
        StageSpec("diagnostic", DIAG, ("number",), ("accepted",)),
    ))
    return StagePlan("rk_number_synthetic", (NUMBER,), tuple(stages))


class Unreadable:
    def __float__(self):
        raise AssertionError("diagnostic-only value was inspected")


def _records(*, repaired=False, consumer_value=0.):
    events = [
        StageRecord("rk", INTERNAL, {"number": -0.028539743}, ()),
        StageRecord("boundary_copy", INTERNAL, {"number": -0.028539743}, ("rk",)),
    ]
    predecessor = "boundary_copy"
    if repaired:
        events.append(StageRecord("declared_repair", INTERNAL, {"number": 0.},
                                  (predecessor,)))
        predecessor = "declared_repair"
    events.extend((
        StageRecord("consumer", CONSUMER, {"number": consumer_value}, (predecessor,)),
        StageRecord("accepted", ACCEPTED, {"number": 0.}, ("consumer",)),
        StageRecord("diagnostic", DIAG, {"number": Unreadable()}, ("accepted",)),
    ))
    return tuple(events)


def test_negative_solver_internal_is_reported_but_corrected_consumer_may_pass():
    audit = validate_stages(_plan(with_repair=True), _records(repaired=True))
    assert audit.internal_outside_accepted_domain == (("rk", "number"),
                                                     ("boundary_copy", "number"))
    assert audit.checked_ids == tuple(s.stage_id for s in _plan(True).stages)


def test_negative_actual_physical_consumer_input_is_not_excused_as_internal():
    with pytest.raises(ValueError, match="consumer.number.*inadmissible"):
        validate_stages(_plan(), _records(consumer_value=-0.028539743))


def test_negative_accepted_state_is_rejected_even_after_valid_consumer():
    records = list(_records(repaired=True))
    records[-2] = StageRecord("accepted", ACCEPTED, {"number": -1e-3}, ("consumer",))
    with pytest.raises(ValueError, match="accepted.number.*inadmissible"):
        validate_stages(_plan(True), tuple(records))


def test_unreadable_diagnostic_output_is_not_a_physical_zero():
    audit = validate_stages(_plan(True), _records(repaired=True))
    assert "diagnostic" in audit.checked_ids
    stages = _plan(True).stages
    bad_plan = StagePlan(
        "rk_number_synthetic", (NUMBER,),
        stages[:-2] + (StageSpec("diagnostic", DIAG, ("number",), ("consumer",)),
                       StageSpec("accepted", ACCEPTED, ("number",), ("diagnostic",))),
    )
    records = _records(repaired=True)
    reordered = records[:-2] + (StageRecord("diagnostic", DIAG,
                                           {"number": Unreadable()}, ("consumer",)),
                                StageRecord("accepted", ACCEPTED,
                                            {"number": 0.}, ("diagnostic",)))
    with pytest.raises(ValueError, match="diagnostic-only"):
        validate_stages(bad_plan, reordered)


def test_expected_plan_refuses_missing_swapped_or_relabelled_records():
    plan = _plan(True)
    records = list(_records(repaired=True))
    with pytest.raises(ValueError, match="missing or unexpected"):
        validate_stages(plan, tuple(records[:-1]))
    records[2] = StageRecord("declared_repair", ACCEPTED, {"number": 0.},
                             ("boundary_copy",))
    with pytest.raises(ValueError, match="differs from plan"):
        validate_stages(plan, tuple(records))


def test_quantity_domain_is_stage_specific_not_universal_nonnegativity():
    signed = QuantityDomain("temperature_anomaly", "K", None, None)
    plan = StagePlan("signed_control", (signed,),
                     (StageSpec("consumer", CONSUMER, ("temperature_anomaly",), ()),))
    audit = validate_stages(plan,
                            (StageRecord("consumer", CONSUMER,
                                         {"temperature_anomaly": -2.}, ()),))
    assert audit.internal_outside_accepted_domain == ()


@pytest.mark.parametrize("bad", [float("nan"), True, "0"])
def test_physical_consumer_rejects_nonreal_or_nonfinite_values(bad):
    with pytest.raises(ValueError, match="finite real"):
        validate_stages(_plan(), _records(consumer_value=bad))
