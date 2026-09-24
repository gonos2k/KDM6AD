"""Bounded dynamic ice probes using the real KDM6 slope and ice kernel."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from dynamic_ice_probe import make_fixture, make_plan, probe_case, run_with_plan  # noqa: E402


def _single_column(fixture: dict, column: int) -> dict:
    batch = fixture["qi"].shape[0]
    return {
        key: (
            value[column : column + 1].clone()
            if isinstance(value, torch.Tensor)
            and value.ndim == 2
            and value.shape[0] == batch
            else value
        )
        for key, value in fixture.items()
    }


def _expected_consumers(plan):
    # Independently construct the event set from the frozen plan; do not derive
    # it from trace records or a record-side event declaration.
    return {
        (cycle, n, column)
        for cycle, counts in enumerate(plan, 1)
        for column, count in enumerate(counts)
        for n in range(1, count + 1)
    }


@pytest.mark.parametrize("layers", [1, 2, 4])
def test_real_slope_plan_has_heterogeneous_complete_consumers(layers):
    fixture = make_fixture(layers)
    plan = make_plan(fixture["qi"], fixture["ni"], fixture, cycles=2)
    assert len(plan) == 2
    assert plan[0][0] == 1 < plan[0][1]

    outputs, events = run_with_plan(
        fixture["qi"], fixture["ni"], fixture, plan, trace=True
    )
    keys = [(event["cycle"], event["n"], event["column"]) for event in events]
    expected = _expected_consumers(plan)
    assert len(keys) == len(set(keys))
    assert set(keys) == expected

    for event in events:
        cycle, n, column = event["cycle"], event["n"], event["column"]
        assert event["selected_mstep"] == plan[cycle - 1][column]
        assert event["consumed_mstep"] == plan[cycle - 1][column]
        assert event["producer_generation"] == event["expected_generation"]
        torch.testing.assert_close(
            event["mass_rate"],
            event["mass_velocity"] / fixture["dz"][column],
            rtol=0.0,
            atol=0.0,
        )
        torch.testing.assert_close(
            event["number_rate"],
            event["number_velocity"] / fixture["dz"][column],
            rtol=0.0,
            atol=0.0,
        )
        assert n <= plan[cycle - 1][column]

    assert len(outputs) == 4
    assert all(value.shape == fixture["qi"].shape for value in outputs)
    assert all(bool(torch.isfinite(value).all()) for value in outputs)
    assert bool((outputs[0] >= 0).all() and (outputs[1] >= 0).all())


def test_batch_and_isolated_columns_match_and_inactive_gates_are_noops():
    fixture = make_fixture(4)
    batch_plan = make_plan(fixture["qi"], fixture["ni"], fixture, cycles=2)
    batch_out, events = run_with_plan(
        fixture["qi"], fixture["ni"], fixture, batch_plan, trace=True
    )

    # The thick column has one scheduled update while the thin column has four
    # in cycle 1. It still enters the batched kernel under the max loop bound;
    # the per-column gate must leave its full state and accumulated fall alone.
    inactive_checks = 0
    for event in events:
        for column, count in enumerate(batch_plan[event["cycle"] - 1]):
            if event["n"] > count:
                for before, after in zip(event["before_state"], event["after_state"]):
                    assert torch.equal(
                        before[column].contiguous().view(torch.uint8),
                        after[column].contiguous().view(torch.uint8),
                    )
                inactive_checks += 1
    assert inactive_checks > 0

    for column in range(fixture["qi"].shape[0]):
        one = _single_column(fixture, column)
        one_plan = make_plan(one["qi"], one["ni"], one, cycles=2)
        assert tuple(row[column] for row in batch_plan) == tuple(
            row[0] for row in one_plan
        )
        one_out, _ = run_with_plan(one["qi"], one["ni"], one, one_plan, trace=True)
        for batched, isolated in zip(batch_out, one_out):
            # Transcendental slope kernels may use different vector widths.
            # This is not the legacy host bitwise gate; inactive snapshots above
            # still require exact bytes within one execution.
            torch.testing.assert_close(
                batched[column : column + 1],
                isolated,
                rtol=64 * torch.finfo(torch.float64).eps,
                atol=0,
            )


def test_each_consumer_uses_velocity_resloped_from_updated_ice_state():
    fixture = make_fixture(4)
    plan = make_plan(fixture["qi"], fixture["ni"], fixture, cycles=2)
    _, events = run_with_plan(fixture["qi"], fixture["ni"], fixture, plan, trace=True)
    first = next(e for e in events if (e["cycle"], e["n"], e["column"]) == (1, 1, 1))
    second = next(e for e in events if (e["cycle"], e["n"], e["column"]) == (1, 2, 1))
    assert first["producer_generation"] == (1, "ice_velocity", 1)
    assert second["producer_generation"] == (1, "ice_velocity", 2)
    torch.testing.assert_close(
        second["delta_v_mass"],
        second["mass_velocity"] - first["mass_velocity"],
        rtol=0.0,
        atol=0.0,
    )
    torch.testing.assert_close(
        second["delta_v_number"],
        second["number_velocity"] - first["number_velocity"],
        rtol=0.0,
        atol=0.0,
    )
    assert bool(((second["delta_v_mass"] != 0) | (second["delta_v_number"] != 0)).any())

    # The reslope callback reads the supplied physical slope parameters, while
    # the value-only plan remains the one selected before this run.
    changed = dict(fixture)
    params = fixture["slope_params"]
    changed["slope_params"] = params._replace(
        pvti=params.pvti * 1.001,
        pvtin=params.pvtin * 1.001,
    )
    _, changed_events = run_with_plan(
        fixture["qi"], fixture["ni"], changed, plan, trace=True
    )
    assert [(e["cycle"], e["n"], e["column"]) for e in changed_events] == [
        (e["cycle"], e["n"], e["column"]) for e in events
    ]
    assert any(
        not torch.equal(a["mass_velocity"], b["mass_velocity"])
        or not torch.equal(a["number_velocity"], b["number_velocity"])
        for a, b in zip(events, changed_events)
    )
    assert all(
        e["consumed_mstep"] == plan[e["cycle"] - 1][e["column"]] for e in changed_events
    )


def test_completed_multicycle_column_budgets_include_accumulated_surface_fall():
    fixture = make_fixture(4)
    plan = make_plan(fixture["qi"], fixture["ni"], fixture, cycles=2)
    qi_out, ni_out, fall_qi, fall_ni = run_with_plan(
        fixture["qi"], fixture["ni"], fixture, plan, trace=False
    )[0]

    # Conditional kernel-coordinate inventories only: mass uses rho*dz, and
    # number uses dz. This makes no claim about a resolved physical number unit.
    initial_mass = (fixture["rho"] * fixture["dz"] * fixture["qi"]).sum(dim=1)
    final_mass = (fixture["rho"] * fixture["dz"] * qi_out).sum(dim=1)
    mass_surface = fall_qi[:, -1] * fixture["dt"] * fixture["dz"][:, -1]
    initial_number = (fixture["dz"] * fixture["ni"]).sum(dim=1)
    final_number = (fixture["dz"] * ni_out).sum(dim=1)
    number_surface = fall_ni[:, -1] * fixture["dt"] * fixture["dz"][:, -1]

    assert bool((mass_surface > 0).all() and (number_surface > 0).all())
    torch.testing.assert_close(
        initial_mass,
        final_mass + mass_surface,
        rtol=32 * torch.finfo(torch.float64).eps,
        atol=0,
    )
    torch.testing.assert_close(
        initial_number,
        final_number + number_surface,
        rtol=32 * torch.finfo(torch.float64).eps,
        atol=0,
    )


def test_fixed_plan_jvp_vjp_and_fd_include_dynamic_slope_changes():
    result = probe_case(4)
    deriv = result["derivatives"]
    assert result["plan_mstep_ice_by_cycle_column"] == [[1, 4], [1, 2]]
    assert result["scheduled_consumer_events"] == 8
    assert deriv["plus_minus_plan_stable"]
    assert deriv["plus_minus_branch_signatures_stable"]
    assert deriv["max_fd_relative_error_including_velocity_trace"] < 1.0e-6
    assert deriv["jvp_vjp_relative_residual"] < 1.0e-12
    assert deriv["mass_rate_tangent_norm"] > 0
    assert deriv["number_rate_tangent_norm"] > 0
    assert deriv["delta_v_mass_tangent_norm"] > 0
    assert deriv["delta_v_number_tangent_norm"] > 0
