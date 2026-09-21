#!/usr/bin/env python3
"""Fixed-coefficient time accuracy, not a native forecast-error estimate."""

import json
import math

from replay_native_ice_transfer import EVIDENCE, validate, tensors, call_kernel


def inventory_reference(rate, initial, dt):
    """Two independent exponential actions in inventory coordinates, incl. sink.

    Uniformization uses a positive stochastic transition and a geometric bound
    on the remaining Poisson tail. Its bounded domain covers this fixed case.
    """
    import torch

    assert rate.dtype == initial.dtype == torch.float64
    assert rate.ndim == initial.ndim == 1 and rate.shape == initial.shape
    assert bool(torch.isfinite(rate).all() and torch.isfinite(initial).all())
    assert bool((rate >= 0).all() and (initial >= 0).all()) and dt > 0
    total = initial.sum()
    assert float(total) > 0
    k = len(rate)
    a = torch.zeros((k + 1, k + 1), dtype=rate.dtype)
    for i in range(k):
        a[i, i] = -rate[i]
        a[i + 1, i] = rate[i]
    y0 = torch.cat((initial / total, initial.new_zeros(1)))
    matrix = torch.matrix_exp(dt * a) @ y0
    lam = float(rate.max())
    mu = dt * lam
    assert mu <= 64, "positive-series domain exceeded"
    if lam == 0:
        return dict(matrix=matrix * total, series=y0 * total, tail=0.0, terms=1)
    transition = torch.eye(k + 1, dtype=rate.dtype) + a / lam
    assert bool((transition >= 0).all())
    weight = math.exp(-mu)
    term = y0
    series = weight * term
    for j in range(10000):
        next_weight = weight * mu / (j + 1)
        ratio = mu / (j + 2)
        tail = next_weight / (1 - ratio) if ratio < 1 else math.inf
        if tail <= 1e-17:
            break
        term = transition @ term
        weight = next_weight
        series = series + weight * term
    else:
        raise AssertionError("positive series did not converge")
    return dict(matrix=matrix * total, series=series * total, tail=tail, terms=j + 1)


def layer_derivatives(x, c):
    """True forward AD and reverse AD for a nonuniform state-only direction."""
    import torch

    k = torch.arange(x["qi"].shape[-1], dtype=torch.float64).reshape(1, -1)
    q, n = x["qi"], x["ni"]
    direction = (0.01 * q * torch.sin(k + 0.3), 0.01 * n * torch.cos(k + 0.7))

    def f(qi, ni):
        o = call_kernel(x, c, True, qi, ni)
        return o.state.qi, o.state.ni, o.fall_qi, o.fall_ni

    output, jvp = torch.func.jvp(f, (q, n), direction)
    _, pullback = torch.func.vjp(f, q, n)
    seeds = tuple(
        torch.sin(k + 1.1 + i) / o.abs().max().clamp_min(1e-300)
        for i, o in enumerate(output)
    )
    vjp = pullback(seeds)
    left = math.fsum(float((a * b).sum()) for a, b in zip(seeds, jvp))
    right = math.fsum(float((a * b).sum()) for a, b in zip(direction, vjp))
    h = 1e-4
    plus = f(q + h * direction[0], n + h * direction[1])
    minus = f(q - h * direction[0], n - h * direction[1])
    fields = {}
    for name, j, p, m in zip(("qi", "ni", "fall_qi", "fall_ni"), jvp, plus, minus):
        fd = (p - m) / (2 * h)
        den = max(float(j.abs().max()), float(fd.abs().max()))
        fields[name] = dict(
            jvp=j.tolist()[0],
            fd=fd.tolist()[0],
            max_norm_relative=float((j - fd).abs().max()) / den,
        )
    return dict(
        scope="fixed_work_and_metrics_nonuniform_state_direction",
        method="torch.func.jvp / torch.func.vjp",
        h=h,
        fields=fields,
        dual_left=left,
        dual_right=right,
        dual_residual=left - right,
    )


def run(data):
    import torch

    validate(data)
    torch.set_num_threads(1)
    c = data["cases"][1]
    x = tensors(c, torch.float64)
    dt = c["dt"]
    weights = {"ni": x["dz"], "qi": x["rho"] * x["dz"]}
    rates = {"ni": x["workn"], "qi": x["work1"]}
    refs = {}
    reference = {}
    for field in ("qi", "ni"):
        ref = inventory_reference(rates[field][0], (x[field] * weights[field])[0], dt)
        refs[field] = ref["matrix"]
        total = float((x[field] * weights[field]).sum())
        error = float((ref["matrix"] - ref["series"]).abs().sum()) / total
        assert error < 1e-13
        reference[field] = dict(
            inventory=ref["matrix"].tolist(),
            positive_series=ref["series"].tolist(),
            normalized_difference=error,
            poisson_tail_bound=ref["tail"],
            terms=ref["terms"],
            initial_total=total,
        )
    curves = []
    for m in (1, 2, 4, 8, 16, 32, 64, 128):
        current = dict(x)
        for n in range(1, m + 1):
            o = call_kernel(current, dict(c, mstep=m, substep=n), True)
            current = dict(
                current,
                qi=o.state.qi,
                ni=o.state.ni,
                fall_qi=o.fall_qi,
                fall_ni=o.fall_ni,
            )
        values = {}
        for field in ("qi", "ni"):
            inv = (current[field] * weights[field])[0]
            surface = (
                (current["fall_" + field][0, -1] - x["fall_" + field][0, -1])
                * dt
                * x["dz"][0, -1]
            )
            y = torch.cat((inv, surface.reshape(1)))
            total = reference[field]["initial_total"]
            values[field] = dict(
                inventory=y.tolist(),
                normalized_l1=float((y - refs[field]).abs().sum()) / total,
                relative_closure=(float(y.sum()) - total) / total,
                nonnegative=bool((y >= 0).all()),
            )
        curves.append(dict(substeps=m, substep_seconds=dt / m, fields=values))
    return dict(
        schema="ice-fixed-time-v1",
        scope="formal_fixed_executed_coefficient_reference_not_physical_time_truth",
        source_case=2,
        final_seconds=dt,
        work_recomputed=False,
        physical_number_basis_resolved=False,
        operational_fix_applied=False,
        accepted_observation_cost=False,
        torch_version=torch.__version__,
        coefficient_contract="Captured first ice handoff is raw velocity; treating it as a rate defines only a formal numerical reference",
        executed_dt_work_factors=[
            dict(
                native_k=r["native_k"],
                mass=dt * r["work1"],
                number=dt * r["workn"],
                divided_by_dz_mass=dt * r["work1"] / r["dz"],
                divided_by_dz_number=dt * r["workn"] / r["dz"],
            )
            for r in c["rows"]
        ],
        references=reference,
        curves=curves,
        layer_derivatives=layer_derivatives(x, c),
    )


if __name__ == "__main__":
    print(json.dumps(run(json.loads(EVIDENCE.read_text())), indent=2))
