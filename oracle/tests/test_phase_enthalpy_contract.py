"""Synthetic state-function checks are separate from KDM's local cpm update."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from phase_enthalpy_contract import (  # noqa: E402
    EnthalpyModel, LatentEdge, PhaseThermoState, SpeciesEnthalpy,
    check_closed_cycle, check_enthalpy_budget, latent_coefficient,
)
from phase_transfer_contract import PhaseTransfer, check_phase_budget  # noqa: E402


def _model(*, ice_cp=2100.):
    return EnthalpyModel(
        reference_temperature_k=273.15,
        dry_heat_capacity_j_per_kg_k=1000.,
        phases={
            "vapour": SpeciesEnthalpy(2.5e6, 1850.),
            "liquid": SpeciesEnthalpy(0., 4200.),
            "ice": SpeciesEnthalpy(-334000., ice_cp),
        },
    )


def _state(temperature, vapour=0., liquid=0., ice=0.):
    return PhaseThermoState(temperature, {
        "vapour": vapour, "liquid": liquid, "ice": ice,
    })


def _budget(model, before, after, *, heat=0., work=0., mass_energy=0.):
    return check_enthalpy_budget(
        model, before, after,
        external_heat_j_per_kg_dry=heat,
        declared_work_j_per_kg_dry=work,
        mass_exchange_energy_j_per_kg_dry=mass_energy,
    )


def test_reference_latent_cycle_closes_and_inconsistent_path_fails():
    model = _model()
    edges = (
        LatentEdge("vapour", "liquid", 2.5e6),
        LatentEdge("liquid", "ice", 334000.),
        LatentEdge("ice", "vapour", -2.834e6),
    )
    assert check_closed_cycle(model, edges) == 0.
    assert latent_coefficient(model, "liquid", "ice", 283.15) == pytest.approx(355000.)
    with pytest.raises(ValueError, match="conflicts"):
        check_closed_cycle(model, edges[:-1] + (LatentEdge("ice", "vapour", -2.8e6),))
    # Each edge stays within its own absolute tolerance, but their three
    # signed errors cannot be allowed to accumulate past the fixed cycle gate.
    shifted = tuple(LatentEdge(e.source, e.destination,
                               e.coefficient_j_per_kg_at_reference + 9e-9)
                    for e in edges)
    with pytest.raises(ValueError, match="nonzero work"):
        check_closed_cycle(model, shifted)
    with pytest.raises(ValueError, match="closed ordered cycle"):
        check_closed_cycle(model, (edges[0], edges[2], edges[1]))


def test_x1_fixed_cpm_local_heat_can_pass_while_total_enthalpy_fails():
    model = _model()
    t0 = 283.15
    amount = .01
    latent = latent_coefficient(model, "liquid", "ice", t0)
    cpm_initial = 1000. + amount * 4200.
    t_local = t0 + latent * amount / cpm_initial
    before = _state(t0, liquid=amount)
    after_local = _state(t_local, ice=amount)
    check_phase_budget(
        {"liquid": np.array([amount]), "ice": np.array([0.])},
        {"liquid": np.array([0.]), "ice": np.array([amount])},
        np.array([t0]), np.array([t_local]), np.array([cpm_initial]),
        (PhaseTransfer("freeze", "liquid", "ice", np.array([amount]),
                       np.array([amount]), latent),),
    )
    with pytest.raises(ValueError, match="does not close"):
        _budget(model, before, after_local)
    # The changing composition has a different final heat capacity. Solve the
    # stated H(T,q) equation, rather than altering X1's local-temperature rule.
    h_before = cpm_initial * (t0 - model.reference_temperature_k)
    final_theta = (h_before + amount * 334000.) / (1000. + amount * 2100.)
    after_closed = _state(model.reference_temperature_k + final_theta, ice=amount)
    assert abs(_budget(model, before, after_closed).residual_j_per_kg_dry) < 1e-8


def test_external_heat_work_and_mass_energy_are_separate_ledger_terms():
    model = _model()
    before = _state(model.reference_temperature_k)
    warmer = _state(model.reference_temperature_k + 1.)
    assert abs(_budget(model, before, warmer, heat=700., work=300.).residual_j_per_kg_dry) < 1e-8
    with pytest.raises(ValueError, match="does not close"):
        _budget(model, before, warmer, heat=700.)
    vapour_added = _state(model.reference_temperature_k, vapour=.001)
    assert abs(_budget(model, before, vapour_added, mass_energy=2500.).residual_j_per_kg_dry) < 1e-8
    with pytest.raises(ValueError, match="does not close"):
        _budget(model, before, vapour_added)


def test_equal_phase_heat_capacities_make_local_and_total_rules_agree():
    model = _model(ice_cp=4200.)
    amount = .01
    t0 = 283.15
    latent = latent_coefficient(model, "liquid", "ice", t0)
    t1 = t0 + amount * latent / (1000. + amount * 4200.)
    assert abs(_budget(model, _state(t0, liquid=amount),
                       _state(t1, ice=amount)).residual_j_per_kg_dry) < 1e-8


def test_invalid_model_state_and_external_budget_are_rejected():
    model = _model()
    before = _state(273.15)
    with pytest.raises(ValueError, match="positive K"):
        _budget(EnthalpyModel(0., 1000., model.phases), before, before)
    with pytest.raises(ValueError, match="nonnegative"):
        _budget(model, before, _state(273.15, liquid=-.001))
    with pytest.raises(ValueError, match="finite real"):
        _budget(model, before, before, heat=math.nan)
    with pytest.raises(ValueError, match="every model phase"):
        _budget(model, before, PhaseThermoState(273.15, {"liquid": 0.}))
