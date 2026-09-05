"""Focused regressions for the Python state-update arm routing.

The phase producers intentionally compute several collision rates in every
temperature cell because D5 consumes their adjusted values.  F1e must select
the complete cold or warm state/number/latent budget at the update boundary.
"""
from __future__ import annotations

from types import SimpleNamespace

import torch

import kdm6.coordinator as coord
from kdm6.runtime import kdm6_fn, make_parameters
from kdm6.state import Forcing, State


DTYPE = torch.float64


def _col(values, *, requires_grad: bool = False):
    value = torch.as_tensor(values, dtype=DTYPE).reshape(1, -1)
    return value.clone().requires_grad_(requires_grad)


def _runtime_fixture(*, requires_grad: bool = False):
    state = State(
        th=_col([260.0, 280.0, 260.0], requires_grad=requires_grad),
        qv=_col([5.0e-3] * 3, requires_grad=requires_grad),
        qc=_col([1.0e-3] * 3, requires_grad=requires_grad),
        qr=_col([1.0e-2] * 3, requires_grad=requires_grad),
        qi=_col([1.0e-3] * 3, requires_grad=requires_grad),
        qs=_col([1.0e-2] * 3, requires_grad=requires_grad),
        qg=_col([1.0e-2] * 3, requires_grad=requires_grad),
        nccn=_col([1.0e9] * 3, requires_grad=requires_grad),
        nc=_col([1.0e8] * 3, requires_grad=requires_grad),
        ni=_col([1.0e8] * 3, requires_grad=requires_grad),
        nr=_col([1.0e8] * 3, requires_grad=requires_grad),
        # qg/bg = 200 is inside the valid [100, 900] graupel density range.
        bg=_col([5.0e-5] * 3, requires_grad=requires_grad),
    )
    forcing = Forcing(
        rho=_col([1.1] * 3),
        pii=_col([1.0] * 3),
        p=_col([8.0e4] * 3),
        delz=_col([500.0] * 3),
    )
    return state, forcing


def _cold_fields_that_are_cold_only():
    # Every floating-point ColdPhaseOutputs field consumed only by the cold
    # state-update arm.  paacw_adj/naacw are intentionally absent: they are
    # common inputs whose destinations are selected separately in F1e.  psevp
    # and pgevp are warm-arm evaporation terms despite living in ColdOutputs.
    return (
        "praci", "piacr", "psaci", "pgaci",
        "nraci", "niacr", "nsaci", "ngaci",
        "piacw", "niacw",
        "pracs", "psacr_adj", "nsacr", "pgacr_adj", "ngacr",
        "pmulcs", "pmulrs", "pmulcg", "pmulrg",
        "nmulcs", "nmulrs", "nmulcg", "nmulrg",
        "pinud", "ninud", "pidep", "psdep", "pgdep",
        "psaut", "nsaut",
    )


def test_actual_runtime_routes_valid_warm_counterexample_by_arm():
    """A reachable qg/bg=200 mixed column omits cold residuals in its warm cell.

    The producer rates are captured from the full public runtime.  The expected
    result is independently formed by masking only cold-arm fields at F1e; the
    adjusted collision producers remain available to the warm D5 producer.
    """
    state, forcing = _runtime_fixture()
    assert torch.equal(state.qg / state.bg, torch.full_like(state.qg, 200.0))
    original = coord.state_update_torch
    observed = {}

    def wrapped(state_c, pre, warm, cold, mf, *args, **kwargs):
        actual = original(state_c, pre, warm, cold, mf, *args, **kwargs)
        cold_mask = (pre.supcol >= 0).to(state_c.qc.dtype)
        cold_masked = cold._replace(**{
            name: getattr(cold, name) * cold_mask
            for name in _cold_fields_that_are_cold_only()
        })
        expected = original(state_c, pre, warm, cold_masked, mf, *args, **kwargs)
        observed.update(
            base=state_c, pre=pre, warm=warm, cold=cold, mf=mf,
            args=args, kwargs=kwargs,
            actual=actual, expected=expected,
        )
        return actual

    coord.state_update_torch = wrapped
    try:
        result = kdm6_fn(
            state, forcing, make_parameters(), 20.0,
            None, 0.0, 0.0, None,
        )
    finally:
        coord.state_update_torch = original

    assert observed, "the full runtime did not reach state_update_torch"
    pre = observed["pre"]
    cold = observed["cold"]
    actual = observed["actual"]
    expected = observed["expected"]
    warm_col = 1
    assert float(pre.supcol[0, warm_col]) < 0.0
    # The actual producers still reach the warm layer; routing owns the mask.
    assert float(cold.psacr_adj[0, warm_col]) != 0.0
    assert float(cold.pgacr_adj[0, warm_col]) != 0.0

    # Every returned state field must match the branch-masked counterfactual.
    for name in actual._fields:
        assert torch.equal(getattr(actual, name), getattr(expected, name)), name

    # The old unmasked path is a real counterexample in this same valid
    # qg/bg=200 fixture. It differs at the warm cell because psacr/pgacr are
    # intentionally nonzero there, while the fixed path equals `expected`.
    base, warm_in, cold_in, mf_in = (
        observed["base"], observed["warm"], observed["cold"], observed["mf"])
    legacy_dqr = observed["kwargs"]["dtcld"] * (
        warm_in.praut + warm_in.pracw + warm_in.prevp
        - cold_in.piacr - cold_in.pgacr_adj - cold_in.psacr_adj
        - cold_in.pmulrs - cold_in.pmulrg
        + 2.0 * cold_in.paacw_adj * ((observed["pre"].supcol < 0).to(base.qr.dtype))
        - mf_in.pseml - mf_in.pgeml
        - (mf_in.psmlt + mf_in.pgmlt)
            * ((observed["pre"].supcol < 0).to(base.qr.dtype))
    ) - mf_in.pfrzdtr
    legacy_qr = torch.clamp(base.qr + legacy_dqr, min=0.0)
    assert not torch.equal(legacy_qr[0, warm_col], expected.qr[0, warm_col])
    del result


def test_state_update_arm_routing_preserves_ad_graph():
    """Cold/warm selection leaves finite gradients through the owning update."""
    from kdm6.coordinator import (
        ColdPhaseOutputs,
        CoordinatorState,
        MeltFreezePhaseOutputs,
        PreambleOutputs,
        WarmPhaseOutputs,
        state_update_torch,
    )

    shape = (1, 2)
    z = lambda: torch.zeros(shape, dtype=DTYPE)
    state = CoordinatorState(
        qv=torch.full(shape, 5.0e-3, dtype=DTYPE, requires_grad=True),
        qc=torch.full(shape, 1.0e-2, dtype=DTYPE, requires_grad=True),
        qr=torch.full(shape, 1.0e-2, dtype=DTYPE, requires_grad=True),
        qs=torch.full(shape, 1.0e-2, dtype=DTYPE, requires_grad=True),
        qg=torch.full(shape, 1.0e-2, dtype=DTYPE, requires_grad=True),
        qi=torch.full(shape, 1.0e-2, dtype=DTYPE, requires_grad=True),
        nc=torch.full(shape, 1.0e8, dtype=DTYPE, requires_grad=True),
        nr=torch.full(shape, 1.0e8, dtype=DTYPE, requires_grad=True),
        ni=torch.full(shape, 1.0e8, dtype=DTYPE, requires_grad=True),
        brs=torch.full(shape, 1.0, dtype=DTYPE, requires_grad=True),
        t=torch.full(shape, 280.0, dtype=DTYPE, requires_grad=True),
    )
    pre = PreambleOutputs(
        cpm=torch.full(shape, 1005.0, dtype=DTYPE),
        xl=torch.full(shape, 2.476e6, dtype=DTYPE),
        supcol=torch.tensor([[10.0, -10.0]], dtype=DTYPE),
        qs1=z(), qs2=z(), rh_w=z(), rh_ice=z(), supsat=z(), supsat_ice=z(),
        denfac=z(), work2=z(), rslopec=z(), avedia_c=z(), avedia_r=z(),
        sigma_c=z(), lencon=z(), lenconcr=z(),
        progb=SimpleNamespace(rhox=torch.ones(shape, dtype=DTYPE)), slope=None,
    )
    warm = WarmPhaseOutputs(*(torch.full(shape, 1.0e-8, dtype=DTYPE)
                              for _ in WarmPhaseOutputs._fields))
    cold_values = {name: torch.full(shape, 1.0e-8, dtype=DTYPE)
                   for name in ColdPhaseOutputs._fields}
    cold_values["ifsat"] = torch.zeros(shape, dtype=torch.bool)
    cold_values["ice_complete_sublim"] = torch.zeros(shape, dtype=torch.bool)
    cold = ColdPhaseOutputs(**cold_values)
    mf_values = {name: z() for name in MeltFreezePhaseOutputs._fields}
    mf = MeltFreezePhaseOutputs(**mf_values)

    out = state_update_torch(state, pre, warm, cold, mf, dtcld=1.0)

    # Keep the routing assertion independent of a duplicated state-update
    # formula: removing all cold-only producer inputs is the counterfactual
    # definition of the warm arm. Every returned field must be unchanged in
    # the warm column; at least one field must respond in the cold column.
    cold_zero = cold._replace(**{
        name: torch.zeros_like(getattr(cold, name))
        for name in _cold_fields_that_are_cold_only()
    })
    without_cold = state_update_torch(state, pre, warm, cold_zero, mf, dtcld=1.0)
    for name in out._fields:
        assert torch.equal(getattr(out, name)[0, 1],
                           getattr(without_cold, name)[0, 1]), name
    assert any(
        not torch.equal(getattr(out, name)[0, 0],
                        getattr(without_cold, name)[0, 0])
        for name in out._fields
    ), "all cold-only inputs were inert in the cold arm"

    loss = sum(value.sum() for value in out)
    loss.backward()
    for name in ("qv", "qc", "qr", "t"):
        grad = getattr(state, name).grad
        assert grad is not None and torch.isfinite(grad).all(), name
