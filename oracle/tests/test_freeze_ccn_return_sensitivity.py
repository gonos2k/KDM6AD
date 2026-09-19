"""Locate the selected cold-fixture freeze derivative at CCN return.

This is a same-recorded-branch diagnostic, not a physical number-unit closure.
The final large reservoir addition has coarser spacing than its incoming nc.
"""
import inspect

import torch

from kdm6 import coordinator as co
from kdm6 import process_attribution as pa


def test_freeze_ccn_return_boundary_and_epsilon_sweep(monkeypatch):
    original = co.apply_satadj_step_torch
    signature = inspect.signature(original)
    captured = []

    def observe(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        result = original(*args, **kwargs)
        if bound.arguments['nccn'] is not None:
            before = bound.arguments['state']
            after, nccn = result
            captured.append((before.nc, bound.arguments['nccn'], after.nc, nccn))
        return result

    monkeypatch.setattr(co, 'apply_satadj_step_torch', observe)
    state, forcing = pa.cold_fixture()

    def run(alpha, graph=False):
        captured.clear()
        out, trace, handle = pa._run(
            state, forcing, 'freeze', alpha, dt=20.0, graph=graph)
        try:
            assert len(captured) == 1
            nc_in, nccn_in, nc_out, nccn_out = captured[0]
            satadj, = trace.by_name('satadj')
            # No activation, complete cloud evaporation; no endpoint clamp.
            assert not bool(satadj.branch[1].any())
            assert bool(satadj.branch[2].all())
            assert torch.equal(nc_out, torch.zeros_like(nc_out))
            assert torch.equal(nccn_out, nccn_in + nc_in)
            assert torch.equal(out.nccn, nccn_out)
            values = torch.stack((nc_in.sum(), nccn_in.sum(), nccn_out.sum(),
                                  nc_out.sum()))
            gradients = None
            if graph:
                gradients = [pa._metric_grad(v, alpha) for v in values]
            return values, trace, gradients
        finally:
            handle.close()

    alpha = torch.tensor(0.0, dtype=torch.float64, requires_grad=True)
    primal, baseline_trace, derivatives = run(alpha, True)
    assert derivatives[1] == 0.0
    assert derivatives[0] == derivatives[2] != 0.0
    # Complete evaporation erases the final NC response but transfers its
    # nonzero sensitivity to CCN; zero NC is not process independence.
    assert derivatives[3] == 0.0
    zero, _, _ = run(0.0)
    assert torch.equal(primal, zero)
    with torch.autograd.forward_ad.dual_level():
        dual = torch.autograd.forward_ad.make_dual(
            torch.tensor(0.0, dtype=torch.float64),
            torch.tensor(1.0, dtype=torch.float64))
        dual_values, _, _ = run(dual)
        forward_primal, tangent = torch.autograd.forward_ad.unpack_dual(dual_values)
        assert torch.equal(forward_primal, primal.detach())
        torch.testing.assert_close(
            tangent, torch.tensor(derivatives, dtype=torch.float64),
            rtol=1.e-10, atol=0.0)

    # Fixed epsilons expose the distinction between upstream response and
    # rounding of the final addition. Do not relax the attribution threshold.
    errors = {}
    for epsilon in (1.e-6, 1.e-5, 1.e-4, 1.e-3, 1.e-2, 1.e-1):
        plus, plus_trace, _ = run(epsilon)
        minus, minus_trace, _ = run(-epsilon)
        for trace in (plus_trace, minus_trace):
            assert trace.subcycles == baseline_trace.subcycles
            assert len(trace.records) == len(baseline_trace.records)
            for actual, expected in zip(trace.records, baseline_trace.records):
                assert (actual.name, actual.step) == (expected.name, expected.step)
                if expected.branch is not None:
                    assert torch.equal(actual.branch, expected.branch)
        fd = (plus - minus) / (2 * epsilon)
        assert torch.isfinite(fd).all()
        # The difference introduced at the addition is bounded by endpoint
        # output spacing; this is not a bound on the entire upstream algorithm.
        spacing = torch.maximum(
            torch.nextafter(plus[2], torch.tensor(float('inf'))) - plus[2],
            torch.nextafter(minus[2], torch.tensor(float('inf'))) - minus[2])
        assert abs(fd[2] - fd[0]) <= spacing / (2 * epsilon)
        errors[epsilon] = abs(float(fd[2]) - derivatives[2]) / abs(derivatives[2])
    assert errors[1.e-4] > 1.e-4  # retain the original unresolved observation
    assert errors[1.e-3] < 1.e-4
    assert errors[1.e-2] < 1.e-4
