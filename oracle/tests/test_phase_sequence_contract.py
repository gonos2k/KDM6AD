"""Ordered-stage properties extend X1 without changing its shared-draw rule."""

from dataclasses import replace
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from phase_transfer_contract import PhaseTransfer, check_phase_budget  # noqa: E402
from phase_sequence_contract import (  # noqa: E402
    AppliedStage, PhaseState, PlannedStage, check_phase_sequence,
)


def _a(value):
    return np.asarray([value], dtype=np.float64)


def _state(vapour, liquid, ice, temperature):
    return PhaseState(
        {"vapour": _a(vapour), "liquid": _a(liquid), "ice": _a(ice)},
        _a(temperature),
    )


def _transfer(name, source, destination, requested, applied, heat):
    return PhaseTransfer(name, source, destination, _a(requested), _a(applied), heat)


def _case():
    initial = _state(.001, 0., 0., 270.)
    condensed = _state(0., .001, 0., 272.5)
    final = _state(0., 0., .001, 272.834)
    plan = (PlannedStage("condense", "saturation",
                         (("v_to_l", "vapour", "liquid"),)),
            PlannedStage("freeze", "microphysics",
                         (("l_to_i", "liquid", "ice"),)))
    stages = (
        AppliedStage("condense", "saturation", initial, condensed, _a(1000.),
                     (_transfer("v_to_l", "vapour", "liquid", .001, .001, 2.5e6),)),
        AppliedStage("freeze", "microphysics", condensed, final, _a(1000.),
                     (_transfer("l_to_i", "liquid", "ice", .001, .001, 334000.),)),
    )
    return plan, stages, initial, final


def test_ordered_condensation_then_freeze_consumes_new_liquid():
    plan, stages, initial, final = _case()
    result = check_phase_sequence(plan, stages, initial, final)
    assert result.stage_ids == ("condense", "freeze")
    assert all(max(abs(x).max() for x in b.mass_residual.values()) == 0
               for _, b in result.stage_budgets)
    with pytest.raises(ValueError, match="combined applied draw"):
        check_phase_budget(
            initial.reservoirs, final.reservoirs,
            initial.temperature, final.temperature, _a(1000.),
            stages[0].transfers + stages[1].transfers,
        )


def test_same_stage_competitors_share_available_storage():
    plan, stages, initial, _ = _case()
    plan = (plan[0], PlannedStage("freeze", "microphysics",
                                  (("contact", "liquid", "ice"),
                                   ("immersion", "liquid", "ice"))))
    after = _state(0., 0., .001, 272.834)
    split = replace(stages[1], after=after, transfers=(
        _transfer("contact", "liquid", "ice", .0008, .0005, 334000.),
        _transfer("immersion", "liquid", "ice", .0008, .0005, 334000.),
    ))
    assert check_phase_sequence(plan, (stages[0], split), initial, after).stage_ids == (
        "condense", "freeze")
    excessive = replace(split, transfers=(
        _transfer("contact", "liquid", "ice", .0008, .0007, 334000.),
        _transfer("immersion", "liquid", "ice", .0008, .0007, 334000.),
    ))
    with pytest.raises(ValueError, match="combined applied draw"):
        check_phase_sequence(plan, (stages[0], excessive), initial, after)


def test_intermediate_overdraw_cannot_be_repaired_by_final_stage():
    initial = _state(0., .1, 0., 270.)
    invalid_middle = _state(0., -.1, .2, 270.2)
    final = _state(0., 0., .1, 270.1)
    plan = (PlannedStage("freeze", "microphysics",
                         (("freeze", "liquid", "ice"),)),
            PlannedStage("melt", "microphysics",
                         (("melt", "ice", "liquid"),)))
    stages = (
        AppliedStage("freeze", "microphysics", initial, invalid_middle, _a(1000.),
                     (_transfer("freeze", "liquid", "ice", .2, .2, 1000.),)),
        AppliedStage("melt", "microphysics", invalid_middle, final, _a(1000.),
                     (_transfer("melt", "ice", "liquid", .1, .1, -1000.),)),
    )
    with pytest.raises(ValueError, match="nonnegative accepted state|combined applied draw"):
        check_phase_sequence(plan, stages, initial, final)


def test_stage_handoff_rejects_missing_mass_and_temperature():
    plan, stages, initial, final = _case()
    wrong_mass = _state(0., .001000000001, 0., 272.5)
    with pytest.raises(ValueError, match="handoff changed reservoir liquid"):
        check_phase_sequence(plan, (stages[0], replace(stages[1], before=wrong_mass)),
                             initial, final)
    wrong_temp = _state(0., .001, 0., 272.500000001)
    with pytest.raises(ValueError, match="handoff changed temperature"):
        check_phase_sequence(plan, (stages[0], replace(stages[1], before=wrong_temp)),
                             initial, final)


def test_independent_schedule_rejects_omission_reordering_and_owner_change():
    plan, stages, initial, final = _case()
    with pytest.raises(ValueError, match="exactly match"):
        check_phase_sequence(plan, stages[:1], initial, final)
    with pytest.raises(ValueError, match="order or owning"):
        check_phase_sequence(plan, stages[::-1], initial, final)
    with pytest.raises(ValueError, match="order or owning"):
        check_phase_sequence(plan, (stages[0], replace(stages[1], owner="saturation")),
                             initial, final)
    with pytest.raises(ValueError, match="unique"):
        check_phase_sequence((plan[0], plan[0]), stages, initial, final)
    with pytest.raises(ValueError, match="transfer set"):
        check_phase_sequence(
            plan,
            (stages[0], replace(stages[1], transfers=(
                _transfer("wrong_event", "liquid", "ice", .001, .001, 334000.),))),
            initial, final,
        )


def test_per_stage_heat_cannot_cancel_across_stages():
    plan, stages, initial, final = _case()
    overheated = replace(stages[0], after=_state(0., .001, 0., 272.501))
    with pytest.raises(ValueError, match="latent-temperature"):
        check_phase_sequence(plan, (overheated, stages[1]), initial, final)


def test_masked_or_boolean_amount_and_final_gap_are_rejected():
    plan, stages, initial, final = _case()
    masked = np.ma.array([.001], mask=[True])
    bad_transfer = replace(stages[0].transfers[0], applied=masked)
    with pytest.raises(ValueError, match="masked"):
        check_phase_sequence(plan, (replace(stages[0], transfers=(bad_transfer,)), stages[1]),
                             initial, final)
    with pytest.raises(TypeError, match="mass_atol"):
        check_phase_sequence(plan, stages, initial, final, mass_atol=1e308)
    with pytest.raises(ValueError, match="final handoff changed reservoir ice"):
        check_phase_sequence(plan, stages, initial, _state(0., 0., .0009, 272.834))


def test_raw_mixed_boolean_numeric_amount_cannot_promote_to_float():
    initial = PhaseState(
        {"vapour": np.array([1., .001]), "liquid": np.zeros(2),
         "ice": np.zeros(2)}, np.array([270., 270.]),
    )
    final = PhaseState(
        {"vapour": np.zeros(2), "liquid": np.array([1., .001]),
         "ice": np.zeros(2)}, np.array([270., 270.]),
    )
    transfer = PhaseTransfer("condense", "vapour", "liquid",
                             [True, .001], [True, .001], 0.)
    stage = AppliedStage("condense", "saturation", initial, final,
                         np.array([1000., 1000.]), (transfer,))
    with pytest.raises(ValueError, match="boolean masks"):
        check_phase_sequence((PlannedStage("condense", "saturation",
                                           (("condense", "vapour", "liquid"),)),),
                             (stage,), initial, final)
