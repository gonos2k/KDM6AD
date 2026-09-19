"""Regression for a reachable ProcessControls warm-to-cold link."""
from __future__ import annotations

import torch

from kdm6.process_attribution import cold_fixture
from kdm6.process_controls import ProcessControls
from kdm6.runtime import kdm6_step, make_parameters
from kdm6.sensitivity_diagnostics import SensitivityTrace


def _run(alpha, *, graph):
    state, forcing = cold_fixture()
    state = state._replace(qr=torch.full_like(state.qr, 3.0e-4))
    a = torch.tensor(alpha, dtype=torch.float64, requires_grad=graph)
    trace = SensitivityTrace()
    out, handle = kdm6_step(
        state, forcing, make_parameters(), 300.0, value_only=not graph,
        controls=ProcessControls(alpha_autoconv=a), diagnostic_trace=trace,
    )
    warm = next(r for r in trace.records if r.name == "warm" and r.step == 0)
    cold = next(r for r in trace.records if r.name == "cold" and r.step == 1)
    return a, warm, cold, trace, handle


def test_autoconv_control_reaches_later_cold_pgdep_with_jvp_vjp_fd():
    alpha, warm, cold, base_trace, base_handle = _run(0.0, graph=True)
    try:
        target = cold.rates.pgdep.sum()
        vjp = torch.autograd.grad(target, alpha, retain_graph=True)[0]
        with torch.autograd.forward_ad.dual_level():
            dual = torch.autograd.forward_ad.make_dual(
                torch.tensor(0.0, dtype=torch.float64), torch.tensor(1.0, dtype=torch.float64))
            state, forcing = cold_fixture()
            state = state._replace(qr=torch.full_like(state.qr, 3.0e-4))
            trace = SensitivityTrace()
            _, h = kdm6_step(
                state, forcing, make_parameters(), 300.0,
                controls=ProcessControls(alpha_autoconv=dual),
                diagnostic_trace=trace,
            )
            fwd_target = next(r for r in trace.records
                              if r.name == "cold" and r.step == 1).rates.pgdep.sum()
            primal, jvp = torch.autograd.forward_ad.unpack_dual(fwd_target)
            h.close()
        assert torch.equal(primal, target.detach())
        assert torch.isfinite(vjp) and torch.isfinite(jvp)
        assert float(warm.rates.praut.detach().abs().max()) > 0.0
        assert float(vjp.abs()) > 0.0 and float(jvp.abs()) > 0.0
        assert float((jvp - vjp).abs()) <= 1.0e-12 * max(
            float(vjp.abs()), float(jvp.abs()))
        for eps in (1.0e-4, 3.0e-5):
            _, _, cp, tp, hp = _run(eps, graph=False)
            _, _, cm, tm, hm = _run(-eps, graph=False)
            try:
                fd = (cp.rates.pgdep.sum() - cm.rates.pgdep.sum()) / (2.0 * eps)
                assert torch.isfinite(fd)
                assert float((fd - vjp).abs() / vjp.abs()) < 5.0e-2
                assert tp.signature() == base_trace.signature() == tm.signature()
                assert tp.subcycles == base_trace.subcycles == tm.subcycles
                inf = torch.full_like(cp.rates.pgdep, float("inf"))
                bound = torch.maximum(
                    (torch.nextafter(cp.rates.pgdep, inf) - cp.rates.pgdep).abs(),
                    (torch.nextafter(cm.rates.pgdep, inf) - cm.rates.pgdep).abs(),
                ).max() / (2.0 * eps)
                assert bool((vjp.abs() > bound).item())
                assert bool((fd.abs() > bound).item())
            finally:
                hp.close(); hm.close()
    finally:
        base_handle.close()
