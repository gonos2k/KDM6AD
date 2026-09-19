"""Selected, cap-aware named-process attribution checks.

These tests use only the existing ProcessControls groups.  They intentionally
do not perturb one raw mass or number rate independently, because that can
violate paired donor budgets.
"""
from __future__ import annotations

import pytest
import torch

import kdm6.process_attribution as pa
from kdm6.process_attribution import (
    PROCESS_CONTROL_FIELDS,
    PROCESS_STATE_FIELDS,
    attribute_process,
    cold_fixture,
    coverage_matrix,
    warm_fixture,
)
from kdm6.runtime import kdm6_step, make_parameters
from kdm6.sensitivity_diagnostics import SensitivityTrace


def test_autoconv_alpha_reaches_paired_limited_rates_and_state_fd():
    result = attribute_process(*warm_fixture(), "autoconv", regime="warm")

    assert result.status == "verified_selected_direction"
    assert result.active and result.nonzero_state_effect
    assert result.paired_mass_number
    assert result.tapped_topology_fixed
    assert result.state_effect["qc"] > 0.0
    assert result.state_effect["qr"] > 0.0
    assert result.rate_max_relative_error < 1.0e-6
    assert result.selected_state_max_relative_error < 1.0e-6
    assert result.rate_ad["praut"] > 0.0
    assert result.rate_fd["praut"] == pytest.approx(result.rate_ad["praut"], rel=1.0e-6)
    assert result.rate_fd["nraut"] == pytest.approx(result.rate_ad["nraut"], rel=1.0e-6)


def test_cold_deposition_has_mass_and_latent_coupled_effect_without_number_claim():
    result = attribute_process(*cold_fixture(), "deposition", regime="cold")

    assert result.status == "verified_selected_direction"
    assert result.active and result.nonzero_state_effect
    # Deposition is explicitly mass-only in the current control contract.
    assert not result.paired_mass_number
    assert set(result.baseline_rates) == {"pidep", "psdep", "pgdep"}
    assert result.state_effect["qs"] > 0.0
    assert result.state_effect["qg"] > 0.0
    assert result.state_effect["bg"] > 0.0
    assert abs(result.temperature_effect) > 0.0
    assert result.rate_max_relative_error < 1.0e-6
    assert result.selected_state_max_relative_error < 1.0e-4
    # Water is conserved to the precision of this singleton selected case;
    # this does not certify the unresolved project-wide number/enthalpy units.
    assert abs(result.water_effect) < 1.0e-9


def test_cold_riming_intervention_keeps_paired_rates_and_temperature_effect():
    result = attribute_process(*cold_fixture(), "riming", regime="cold")

    assert result.status == "verified_selected_direction"
    assert result.paired_mass_number
    assert result.baseline_rates["psacw"] > 0.0
    assert result.baseline_rates["nsacw"] > 0.0
    assert result.state_effect["qs"] > 0.0
    assert result.state_effect["qg"] > 0.0
    assert abs(result.temperature_effect) > 0.0
    assert result.rate_max_relative_error < 1.0e-6
    assert result.selected_state_max_relative_error < 1.0e-4


def test_full_cold_prevp_links_are_structural_but_zero_in_selected_regime():
    state, forcing = cold_fixture()
    state = state._replace(**{
        name: getattr(state, name).clone().requires_grad_(True)
        for name in state._fields
    })
    trace = SensitivityTrace()
    _, handle = kdm6_step(
        state, forcing, make_parameters(), 20.0, diagnostic_trace=trace)
    warm_prevp = trace.by_name("warm")[0].rates.prevp
    cold = trace.by_name("cold")[0].rates
    assert float(warm_prevp.detach().abs().max()) > 0.0
    for name in ("pinud", "pidep"):
        value = getattr(cold, name)
        grad = torch.autograd.grad(
            value.sum(), warm_prevp, retain_graph=True, allow_unused=True
        )[0]
        assert grad is not None
        assert float(grad.detach().abs().max()) == 0.0
    handle.close()


def test_freeze_case_reports_output_resolution_limit():
    result = attribute_process(*cold_fixture(), "freeze", regime="cold")

    assert result.active
    assert result.paired_mass_number
    assert result.baseline_rates["pinuc"] >= 0.0
    assert result.baseline_rates["ninuc"] >= 0.0
    # The existing freeze transfer is physically applied, but the selected
    # central FD includes fields whose signal is below the output-ULP bound.
    assert result.status == "unresolved_output_resolution"
    assert "th" in result.output_resolution_fields
    assert "output-ULP" in (result.reason or "")


@pytest.mark.parametrize(
    ("process", "expected_zero_fields"),
    [
        ("deposition", ("qi",)),
        ("riming", ("qc", "qi", "nc", "ni")),
        ("freeze", ("qc", "qi", "nc", "ni")),
    ],
)
def test_cold_gate_field_metadata_distinguishes_zero_and_resolution(
        process, expected_zero_fields):
    state, forcing = cold_fixture()
    result = attribute_process(state, forcing, process, regime="cold")

    expected_checked = PROCESS_STATE_FIELDS[process]
    assert result.checked_state_fields == expected_checked
    assert set(result.unchecked_state_fields) == set(state._fields) - set(expected_checked)
    assert set(result.state_field_status) == set(expected_checked)

    # These newly selected gate fields have AD=FD=0 in this fixture.  Record
    # that as a selected zero response, without calling it independence.
    for name in expected_zero_fields:
        assert result.state_fd[name] == 0.0
        assert result.state_ad[name] == 0.0
        assert result.state_field_status[name] == "zero_response"

    if process == "freeze":
        assert result.state_field_status["th"] == "output_resolution_unresolved"
        assert "th" in result.output_resolution_fields
    else:
        assert result.state_field_status["th"] == "resolved_nonzero"


@pytest.mark.parametrize("target_call", [3, 5], ids=["plus", "graph_ad"])
def test_changed_tapped_topology_blocks_resolved_nonzero_label(monkeypatch, target_call):
    original_run = pa._run
    calls = 0

    def run_with_changed_plus(*args, **kwargs):
        nonlocal calls
        calls += 1
        output, trace, handle = original_run(*args, **kwargs)
        if calls == target_call:
            for record in trace.records:
                if record.branch is not None:
                    record.branch = ~record.branch.to(torch.bool)
                    break
        return output, trace, handle

    monkeypatch.setattr(pa, "_run", run_with_changed_plus)
    result = attribute_process(*cold_fixture(), "riming", regime="cold")

    assert not result.tapped_topology_fixed
    assert result.state_field_status["th"] == "topology_unresolved"
    assert result.state_field_status["qc"] == "zero_response"


@pytest.mark.parametrize("target", ["controlled", "plus", "minus", "graph"])
def test_nonfinite_rate_at_each_product_boundary_is_unresolved(monkeypatch, target):
    original_run = pa._run
    calls = 0
    target_call = {"controlled": 2, "plus": 3, "minus": 4, "graph": 5}[target]

    def run_with_nonfinite_rate(*args, **kwargs):
        nonlocal calls
        calls += 1
        output, trace, handle = original_run(*args, **kwargs)
        if calls == target_call:
            record = trace.by_name("cold_limited")[0]
            record.rates = record.rates._replace(
                psacw=torch.full_like(record.rates.psacw, float("nan")))
        return output, trace, handle

    monkeypatch.setattr(pa, "_run", run_with_nonfinite_rate)
    result = attribute_process(*cold_fixture(), "riming", regime="cold")

    assert result.status == "nonfinite_unresolved"
    assert result.reason == "nonfinite process rate, state, or derivative product"
    assert all(status != "resolved_nonzero"
               for status in result.state_field_status.values())


def test_coverage_matrix_makes_inactive_and_unresolved_pairs_explicit():
    matrix = coverage_matrix()

    assert set(matrix) == {"warm", "cold", "melt"}
    assert set(matrix["warm"]) == set(PROCESS_CONTROL_FIELDS)
    assert matrix["warm"]["autoconv"].status == "verified_selected_direction"
    assert matrix["cold"]["deposition"].status == "verified_selected_direction"
    assert matrix["cold"]["freeze"].status == "unresolved_output_resolution"
    assert not matrix["warm"]["deposition"].active
    assert matrix["warm"]["deposition"].status == "zero_inactive_or_unresolved"
