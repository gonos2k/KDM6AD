"""A first cross-phenomenon pilot: applied phase transfer and latent work.

The synthetic cases test the contract itself. The KDM cases seed phase amounts
and run the real freeze cap and inline applier; they do not regenerate rates.
"""

import math
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from phase_transfer_contract import PhaseTransfer, check_phase_budget  # noqa: E402

from kdm6.coordinator import (
    CoordinatorState, MeltFreezePhaseOutputs, PreambleOutputs,
    apply_melt_freeze_inline_torch,
)
from kdm6.process_controls import ProcessControls, apply_freeze_controls
from kdm6.melt_freeze import DEFAULT_XLF


def _check(before, after, t0, t1, transfers, *, cpm=1000.0):
    return check_phase_budget(
        {k: np.asarray([v]) for k, v in before.items()},
        {k: np.asarray([v]) for k, v in after.items()},
        np.asarray([t0]), np.asarray([t1]), np.asarray([cpm]), transfers,
    )


def _transfer(name, source, destination, request, applied, latent):
    return PhaseTransfer(name, source, destination, np.asarray([request]),
                         np.asarray([applied]), latent)


def test_two_competing_freezes_use_one_shared_reservoir_and_applied_heat():
    transfers = (
        _transfer("contact", "liquid", "ice", 0.7, 0.5, 1000.0),
        _transfer("immersion", "liquid", "ice", 0.7, 0.5, 1000.0),
    )
    budget = _check({"liquid": 1.0, "ice": 0.0},
                    {"liquid": 0.0, "ice": 1.0}, 270.0, 271.0, transfers)
    assert max(abs(x).max() for x in budget.mass_residual.values()) == 0.0
    assert budget.heat_residual_j_per_kg[0] == 0.0
    with pytest.raises(ValueError, match="combined applied draw"):
        _check({"liquid": 1.0, "ice": 0.0}, {"liquid": 0.0, "ice": 1.0},
               270.0, 271.0,
               tuple(_transfer(t.name, t.source, t.destination, .7, .7, 1000.)
                     for t in transfers))
    with pytest.raises(ValueError, match="latent-temperature"):
        _check({"liquid": 1.0, "ice": 0.0},
               {"liquid": 0.0, "ice": 1.0}, 270.0, 271.4, transfers)


def test_phase_budget_rejects_state_and_request_mismatches():
    tr = (_transfer("freeze", "liquid", "ice", .5, .5, 1000.),)
    with pytest.raises(ValueError, match="reservoir changes"):
        _check({"liquid": 1., "ice": 0.}, {"liquid": .6, "ice": .4},
               270., 270.5, tr)
    with pytest.raises(ValueError, match="exceeds request"):
        _check({"liquid": 1., "ice": 0.}, {"liquid": .5, "ice": .5},
               270., 270.5,
               (_transfer("freeze", "liquid", "ice", .4, .5, 1000.),))


def test_phase_budget_rejects_overflow_and_empty_grid():
    huge = (_transfer("freeze", "liquid", "ice", 1e308, 1e308, 2.),)
    with np.errstate(over="ignore", invalid="ignore"):
        with pytest.raises(ValueError, match="overflowed|nonfinite"):
            _check({"liquid": 1e308, "ice": 0.},
                   {"liquid": 0., "ice": 1e308}, 0., 2., huge, cpm=1e308)
    empty = np.asarray([], dtype=np.float64)
    with pytest.raises(ValueError, match="nonempty grid"):
        check_phase_budget(
            {"liquid": empty, "ice": empty},
            {"liquid": empty, "ice": empty}, empty, empty, empty,
            (PhaseTransfer("freeze", "liquid", "ice", empty, empty, 1.),),
        )


def _tensor(value):
    return torch.tensor([[value]], dtype=torch.float64)


def _isolated_state(*, cold):
    z = _tensor(0.0)
    state = CoordinatorState(*(z for _ in CoordinatorState._fields))._replace(
        qc=_tensor(.001) if cold else z,
        qi=z if cold else _tensor(.001),
        qs=z if cold else _tensor(.001),
        nc=_tensor(1e6), t=_tensor(263.0 if cold else 283.0),
    )
    pre = PreambleOutputs(*(z for _ in PreambleOutputs._fields))._replace(
        cpm=_tensor(1005.0), xl=_tensor(2.50e6),
        supcol=_tensor(10.0 if cold else -10.0),
    )
    mf = MeltFreezePhaseOutputs(*(z for _ in MeltFreezePhaseOutputs._fields))
    return state, pre, mf


def test_kdm_controlled_freeze_reuses_capped_mass_for_latent_work():
    state, pre, mf = _isolated_state(cold=True)
    mf = mf._replace(pinuc=_tensor(.0004), pfrzdtc=_tensor(.0004))
    applied = apply_freeze_controls(
        mf, ProcessControls(alpha_freeze=_tensor(math.log(2))), state.qc, state.nc,
    )
    out = apply_melt_freeze_inline_torch(state, applied, pre, dtcld=20., xls=2.85e6)
    amount1, amount2 = applied.pinuc.item(), applied.pfrzdtc.item()
    assert amount1 + amount2 == pytest.approx(.001)
    budget = _check(
        {"qc": state.qc.item(), "qi": state.qi.item()},
        {"qc": out.qc.item(), "qi": out.qi.item()},
        state.t.item(), out.t.item(),
        (_transfer("contact", "qc", "qi", .0008, amount1, 350000.),
         _transfer("immersion", "qc", "qi", .0008, amount2, 350000.)),
        cpm=pre.cpm.item(),
    )
    assert abs(budget.heat_residual_j_per_kg[0]) < 1e-8


def test_kdm_melt_rate_becomes_amount_and_cools_with_same_amount():
    state, pre, mf = _isolated_state(cold=False)
    mf = mf._replace(psmlt=_tensor(-1e-5))
    out = apply_melt_freeze_inline_torch(state, mf, pre, dtcld=20., xls=2.85e6)
    amount = 20. * -mf.psmlt.item()
    budget = _check(
        {"qs": state.qs.item(), "qr": state.qr.item()},
        {"qs": out.qs.item(), "qr": out.qr.item()},
        state.t.item(), out.t.item(),
        (_transfer("snow_melt", "qs", "qr", amount, amount, -DEFAULT_XLF),),
        cpm=pre.cpm.item(),
    )
    assert abs(budget.heat_residual_j_per_kg[0]) < 1e-8
