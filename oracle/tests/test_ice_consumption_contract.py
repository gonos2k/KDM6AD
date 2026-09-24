"""Synthetic common properties; the fixed 39-layer regression remains unchanged."""

import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from ice_consumption_contract import (
    VelocitySample,
    normalize,
    consume,
    check_geometry,
    select_msteps,
    schedule,
    audit_events,
    generation_for,
)


@pytest.mark.parametrize("layers", [1, 2, 4])
def test_normalize_once_with_consistent_length_conversion(layers):
    dz = torch.arange(1, layers + 1, dtype=torch.float64).reshape(1, -1) * 25
    v = torch.arange(1, layers + 1, dtype=torch.float64).reshape(1, -1)
    check_geometry(dz)
    raw = VelocitySample((1, "selection", 0), v, v * 0.25)
    rate = normalize(raw, dz)
    cm = normalize(VelocitySample(raw.generation, v * 100, v * 25), dz * 100)
    torch.testing.assert_close(
        rate.mass, cm.mass, rtol=4 * torch.finfo(v.dtype).eps, atol=0
    )
    torch.testing.assert_close(
        rate.number, cm.number, rtol=4 * torch.finfo(v.dtype).eps, atol=0
    )
    with pytest.raises(TypeError):
        normalize(rate, dz)
    with pytest.raises(TypeError):
        consume(raw, raw.generation)
    with pytest.raises(ValueError, match="stale"):
        consume(rate, (2, "selection", 0))


def test_changed_velocity_exposes_insufficient_frozen_selection():
    dz = torch.tensor([[25.0]], dtype=torch.float64)
    initial = normalize(
        VelocitySample((1, "selection", 0), torch.ones_like(dz), torch.ones_like(dz)),
        dz,
    )
    later = normalize(
        VelocitySample(
            generation_for(1, 1), 3 * torch.ones_like(dz), 3 * torch.ones_like(dz)
        ),
        dz,
    )
    selected = select_msteps(initial, 20.0)
    assert selected.tolist() == [1] and select_msteps(later, 20.0).tolist() == [3]
    assert (20 * later.mass / selected[:, None]).item() == pytest.approx(2.4)
    assert selected.tolist() == [1]  # Detection is not an adaptive-policy change.


def test_schedule_completeness_and_generation_ignore_record_declarations():
    expected = schedule(((1, 3), (1, 2)))
    events = [
        dict(
            cycle=c,
            n=n,
            column=b,
            producer_generation=generation_for(c, n),
            expected_generation=generation_for(c, n),
            selected_mstep=((1, 3), (1, 2))[c - 1][b],
            consumed_mstep=((1, 3), (1, 2))[c - 1][b],
        )
        for c, n, b in sorted(expected)
    ]
    assert audit_events(events, expected) == 7
    shortened = [dict(e, declared_event_count=6) for e in events[:-1]]
    with pytest.raises(ValueError, match="missing"):
        audit_events(shortened, expected)
    with pytest.raises(ValueError, match="duplicate"):
        audit_events(events + [events[-1]], expected)
    altered_counts = [dict(e) for e in events]
    altered_counts[-1]["selected_mstep"] = altered_counts[-1]["consumed_mstep"] = 3
    with pytest.raises(ValueError, match="substep count"):
        audit_events(altered_counts, expected)
    stale = [dict(e) for e in events]
    stale[-1]["producer_generation"] = stale[-1]["expected_generation"] = (
        1,
        "ice_velocity",
        1,
    )
    with pytest.raises(ValueError, match="stale"):
        audit_events(stale, expected)


def test_normalization_derivative_includes_velocity_and_geometry():
    v = torch.tensor([[1.0, 3.0]], dtype=torch.float64)
    dz = torch.tensor([[25.0, 60.0]], dtype=torch.float64)
    dv = torch.tensor([[0.3, -0.2]], dtype=v.dtype)
    ddz = torch.tensor([[0.5, -0.4]], dtype=v.dtype)

    def f(v, dz):
        return normalize(VelocitySample((1, "test", 0), v, v * 0.25), dz).mass

    y, jvp = torch.func.jvp(f, (v, dz), (dv, ddz))
    expected = dv / dz - v * ddz / dz.square()
    torch.testing.assert_close(jvp, expected, rtol=1e-14, atol=1e-16)
    h = 1e-5
    fd = (f(v + h * dv, dz + h * ddz) - f(v - h * dv, dz - h * ddz)) / (2 * h)
    torch.testing.assert_close(jvp, fd, rtol=1e-9, atol=1e-12)
    seed = torch.tensor([[0.7, -0.4]], dtype=v.dtype)
    _, pb = torch.func.vjp(f, v, dz)
    gv, gd = pb(seed)
    torch.testing.assert_close(
        (jvp * seed).sum(), (dv * gv).sum() + (ddz * gd).sum(), rtol=1e-14, atol=1e-16
    )


def test_invalid_geometry_is_rejected_before_differentiation():
    for v in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            check_geometry(torch.tensor([[v]], dtype=torch.float64))


def test_integer_selection_obeys_executed_binary64_rounding_at_boundary():
    from ice_consumption_contract import RateSample

    c = torch.tensor(
        [[1 - 2**-52], [1 - 2**-53], [1.0], [1 + 2**-52]], dtype=torch.float64
    )
    # C+1 rounds the immediate predecessor of 1 to 2 before floor is taken.
    assert select_msteps(RateSample((0,), c, c), 1.0).tolist() == [1, 2, 2, 2]
