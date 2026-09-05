"""Focused regressions for the audited runtime helper boundaries."""
from __future__ import annotations

import pytest
import torch

from kdm6 import coordinator as _coord
from kdm6.coordinator import WarmPhaseOutputs
from kdm6.process_controls import ProcessControls, apply_warm_controls
from kdm6.runtime import _kdm6_pure
from kdm6.state import Forcing, State


def _rates(value: float = 1.0) -> WarmPhaseOutputs:
    z = torch.full((1, 1), value, dtype=torch.float64)
    return WarmPhaseOutputs(
        praut=z, nraut=z, pracw=z, nracw=z, nccol=z, nrcol=z,
        prevp=z, rain_complete_evap=torch.zeros_like(z, dtype=torch.bool),
    )


def test_process_control_exp_factor_keeps_a_valid_gradient():
    """A valid finite alpha keeps the factor in the autograd graph."""
    alpha = torch.tensor(0.25, dtype=torch.float64, requires_grad=True)
    out = apply_warm_controls(
        _rates(), ProcessControls(alpha_autoconv=alpha))
    grad, = torch.autograd.grad(out.praut.sum(), alpha)
    assert torch.isfinite(grad).all()
    assert grad.item() > 0.0
    assert torch.allclose(out.praut, torch.exp(alpha).expand_as(out.praut))


@pytest.mark.parametrize("alpha", [1000.0, -1000.0])
def test_process_control_rejects_exp_overflow_and_underflow(alpha):
    """Finite alpha values whose dtype exp is inf or zero fail at the boundary."""
    with pytest.raises(ValueError, match="positive and finite|finite"):
        apply_warm_controls(
            _rates(), ProcessControls(
                alpha_autoconv=torch.tensor(alpha, dtype=torch.float64)))


@pytest.mark.parametrize(
    "delt, dtcldcr, match",
    [
        (float("nan"), 120.0, "delt must be finite"),
        (60.0, float("inf"), "dtcldcr must be finite"),
        (60.0, 0.0, "dtcldcr must be finite"),
        (60.0, -120.0, "dtcldcr must be finite"),
        (float("1e308"), float("1e-308"), "representable subcycle range"),
    ],
)
def test_compute_loops_max_rejects_invalid_public_inputs(delt, dtcldcr, match):
    with pytest.raises(ValueError, match=match):
        _coord.compute_loops_max(delt, dtcldcr)


def _mixed_rce_fixture() -> tuple[State, Forcing]:
    """Cold complete-evap cells with valid ice/snow/graupel moments.

    The graupel pair has qg/bg=200 kg m^-3, inside the [100,900] ProgB
    interval.  The cold cell is dry enough to consume all rain; the warm cell
    provides the complementary arm in the same K-order column.
    """
    def f(values):
        return torch.tensor([values], dtype=torch.float64)

    state = State(
        th=f([260.0, 300.0]), qv=f([1.0e-4, 2.0e-3]),
        qc=f([1.0e-4, 1.0e-4]), qr=f([5.0e-6, 5.0e-6]),
        qi=f([1.0e-3, 1.0e-3]), qs=f([1.0e-3, 1.0e-3]),
        qg=f([1.0e-3, 1.0e-3]), nccn=f([1.0e9, 1.0e9]),
        nc=f([1.0e8, 1.0e8]), ni=f([1.0e8, 1.0e8]),
        nr=f([1.0e4, 1.0e4]), bg=f([5.0e-6, 5.0e-6]),
    )
    forcing = Forcing(
        rho=f([1.0, 1.0]), pii=f([0.97, 0.97]),
        p=f([9.0e4, 9.0e4]), delz=f([500.0, 500.0]),
    )
    return state, forcing


def test_complete_rain_evap_transfers_pair_before_cold_rates(monkeypatch):
    """Fortran's B4 NR→CCN statement owns the cold-phase input boundary.

    The independent expectation is the source statement itself: on a
    complete-evap mask, ``nrs=0`` before C1-C6; elsewhere the paired number is
    unchanged.  The counterfactual cold call with the old number demonstrates
    that this boundary changes number collection for a valid mixed-phase
    fixture, rather than merely observing a dormant branch.
    """
    state, forcing = _mixed_rce_fixture()
    seen = {}
    warm_impl = _coord.warm_phase_torch
    cold_impl = _coord.cold_phase_torch
    sat_impl = _coord.apply_satadj_step_torch

    def warm_probe(*args, **kwargs):
        seen["warm_nr"] = args[0].nr.detach().clone()
        out = warm_impl(*args, **kwargs)
        seen["rce"] = out.rain_complete_evap.detach().clone()
        return out

    def cold_probe(*args, **kwargs):
        seen["cold_args"] = args
        seen["cold_kwargs"] = kwargs
        seen["cold_nr"] = args[0].nr.detach().clone()
        out = cold_impl(*args, **kwargs)
        seen["cold_out"] = out
        return out

    def sat_probe(*args, **kwargs):
        seen["sat_nccn"] = kwargs["nccn"].detach().clone()
        return sat_impl(*args, **kwargs)

    monkeypatch.setattr(_coord, "warm_phase_torch", warm_probe)
    monkeypatch.setattr(_coord, "cold_phase_torch", cold_probe)
    monkeypatch.setattr(_coord, "apply_satadj_step_torch", sat_probe)
    out = _kdm6_pure(state, forcing, None, 120.0)

    rce = seen["rce"]
    assert bool(rce[0, 0]) and bool(rce[0, 1])
    expected_nr = torch.where(rce, torch.zeros_like(seen["warm_nr"]),
                              seen["warm_nr"])
    assert torch.equal(seen["cold_nr"], expected_nr)

    # The paired transfer is made before the deferred satadj/activation call;
    # entry clamping is a no-op for this in-range nccn fixture.
    expected_nccn = state.nccn + seen["warm_nr"] * rce.to(state.nccn.dtype)
    assert torch.equal(seen["sat_nccn"], expected_nccn)

    # Re-run only the captured cold producer with the pre-transfer NR.  This
    # is the old consumer boundary and is independently expected to differ.
    old_state = seen["cold_args"][0]._replace(nr=seen["warm_nr"])
    old_cold = cold_impl(
        old_state, *seen["cold_args"][1:], **seen["cold_kwargs"])
    assert seen["cold_out"].nraci[0, 0].item() == 0.0
    assert old_cold.nraci[0, 0].item() > 0.0
    assert old_cold.nsacr[0, 0].item() > seen["cold_out"].nsacr[0, 0].item()
    assert old_cold.ngacr[0, 0].item() > seen["cold_out"].ngacr[0, 0].item()
    assert torch.isfinite(torch.stack(tuple(out))).all()
