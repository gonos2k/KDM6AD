"""Bounded cold-column process-to-RTTOV-profile evidence.

This is an evidence probe, rather than a new sensitivity framework.  It uses
the existing cold fixture, KDM ``SensitivityTrace``, and the existing analytic
model-to-RTTOV profile map.  It deliberately does not claim a live RTTOV BT or
cost derivative: no RTTOV K invocation is made here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch

from kdm6.process_attribution import (
    PROCESS_RATE_FIELDS, PROCESS_STAGE, _run as process_run,
    _stage_rates, cold_fixture,
)
from kdm6.runtime import kdm6_step
from kdm6.sensitivity_diagnostics import SensitivityTrace, _directional_values
from kdm6.obs.model_profile_builder import RttovProfileConfig, model_to_rttov_tensors


SOURCES = ("nc", "ni", "nr", "bg")
PROFILE_FIELDS = ("T", "Q", "HYDRO", "DEFF")
RELATIVE_ERROR_GATE = 0.01
EPSILONS = (1.0e-2, 3.0e-2, 1.0e-1)


def _profile(state, forcing, rho_d):
    # The all-sky staging path is intentionally single-column.  KDM remains
    # rank-2; only the profile boundary is squeezed to its documented column API.
    ss = type(state)(*(x[0] for x in state))
    ff = type(forcing)(*(x[0] for x in forcing))
    cfg = RttovProfileConfig(
        gas_units=2,
        qv_convention="mixing_ratio_kgkg_dry",
        cloud=True,
        # rho_d is a background/configuration quantity.  It is held fixed for
        # baseline, AD, and every FD endpoint so the comparison has one map.
        rho_d=rho_d,
    )
    p = model_to_rttov_tensors(ss, ff, cfg, xland=torch.tensor(0.0, dtype=ss.th.dtype))
    return {
        "T": p.t_lay,
        "Q": p.q_lay,
        "HYDRO": torch.cat((p.clw, p.ciw)),
        "DEFF": torch.cat((p.deff_liq, p.deff_ice)),
    }


def _topology(trace: SensitivityTrace) -> dict[str, Any]:
    return {"signature": trace.signature(), "subcycles": trace.subcycles}


def _same_topology(a: SensitivityTrace, b: SensitivityTrace, c: SensitivityTrace) -> bool:
    return _topology(a) == _topology(b) == _topology(c)


def _run(state, forcing, *, trace: SensitivityTrace | None = None):
    return kdm6_step(state, forcing, dt=20.0, diagnostic_trace=trace)


def _relative_error(a: float, b: float, ulp_bound: float) -> float:
    denominator = max(abs(a), abs(b), ulp_bound)
    return 0.0 if denominator == 0.0 else abs(a - b) / denominator


def _fd_ulp_bound(plus: torch.Tensor, minus: torch.Tensor, epsilon: float,
                  cell: int = 0) -> float:
    """Conservative central-FD scale from both endpoint spacings/directions."""
    p, m = plus.reshape(-1), minus.reshape(-1)
    inf = torch.full_like(p, float("inf"))
    neg_inf = torch.full_like(p, float("-inf"))
    p_ulp = torch.maximum((torch.nextafter(p, inf) - p).abs(),
                          (p - torch.nextafter(p, neg_inf)).abs())
    m_ulp = torch.maximum((torch.nextafter(m, inf) - m).abs(),
                          (m - torch.nextafter(m, neg_inf)).abs())
    return float((torch.maximum(p_ulp, m_ulp)[cell] / (2.0 * epsilon)).item())


def _derivative_check(ad: float, fd: float, bound: float) -> dict[str, Any]:
    above = abs(fd) > bound
    rel = _relative_error(ad, fd, bound)
    return {
        "ad": ad, "fd": fd, "relative_error": rel,
        "output_ulp_fd_bound": bound, "fd_above_output_ulp": above,
        "status": ("verified" if ad != 0.0 and fd != 0.0 and above and rel < RELATIVE_ERROR_GATE
                   else "zero" if ad == 0.0 and fd == 0.0
                   else "unresolved_output_resolution" if not above else "ad_fd_mismatch"),
    }


def _moment_pair_admissible(state) -> bool:
    """Declared graupel moment contract: 100 <= qg/bg <= 900."""
    ratio = state.qg / state.bg
    return bool(torch.isfinite(ratio).all() and (ratio >= 100.0).all()
                and (ratio <= 900.0).all())


def _alpha_cells(output: torch.Tensor, alpha: torch.Tensor) -> torch.Tensor:
    """Per-cell scalar-alpha JVP, retaining the vector output cells."""
    values = []
    flat = output.reshape(-1)
    for i in range(flat.numel()):
        grad = torch.autograd.grad(flat[i], alpha, retain_graph=True, allow_unused=True)[0]
        values.append(torch.zeros_like(alpha) if grad is None else grad)
    return torch.stack(values).reshape(output.shape)


def run_process_probe(baseline, forcing, rho_d) -> list[dict[str, Any]]:
    """Link supported alpha controls to post-cap rates and profile cells.

    This is a total admissible intervention of the named control group.  It is
    not a claim that one rate owns the resulting state change uniquely.
    """
    rows = []
    for process in ("deposition", "riming"):
        alpha = torch.tensor(0.0, dtype=baseline.th.dtype, requires_grad=True)
        trace = SensitivityTrace()
        ad_out, ad_trace, ad_handle = process_run(
            baseline, forcing, process, alpha, dt=20.0, graph=True)
        ad_profile = _profile(ad_out, forcing, rho_d)
        ad_cells = {field: _alpha_cells(ad_profile[field], alpha).detach()
                    for field in PROFILE_FIELDS}
        ad_rates = _stage_rates(ad_trace, process)
        rate_ad = {name: float(torch.autograd.grad(value.reshape(-1)[0], alpha,
                                                     retain_graph=True)[0].item())
                   for name, value in ad_rates.items()}
        epsilon_results = {}
        try:
            for epsilon in EPSILONS:
                plus_trace, minus_trace = SensitivityTrace(), SensitivityTrace()
                with torch.no_grad():
                    plus_out, plus_trace, plus_handle = process_run(
                        baseline, forcing, process, epsilon, dt=20.0, graph=False)
                    try:
                        plus_profile = _profile(plus_out, forcing, rho_d)
                    finally:
                        plus_handle.close()
                    minus_out, minus_trace, minus_handle = process_run(
                        baseline, forcing, process, -epsilon, dt=20.0, graph=False)
                    try:
                        minus_profile = _profile(minus_out, forcing, rho_d)
                    finally:
                        minus_handle.close()
                plus_rates = _stage_rates(plus_trace, process)
                minus_rates = _stage_rates(minus_trace, process)
                rate_fd = {name: float(((plus_rates[name] - minus_rates[name]).reshape(-1)[0] /
                                        (2.0 * epsilon)).item())
                           for name in PROCESS_RATE_FIELDS[process]}
                rate_checks = {}
                for name in PROCESS_RATE_FIELDS[process]:
                    av, fv = rate_ad[name], rate_fd[name]
                    bound = _fd_ulp_bound(plus_rates[name], minus_rates[name], epsilon)
                    rate_checks[name] = _derivative_check(av, fv, bound)
                fields = {}
                for field in PROFILE_FIELDS:
                    fd_cells = (plus_profile[field] - minus_profile[field]) / (2.0 * epsilon)
                    ad_flat, fd_flat = ad_cells[field].reshape(-1), fd_cells.reshape(-1)
                    cell = int(torch.argmax(torch.maximum(ad_flat.abs(), fd_flat.abs())).item())
                    bound = _fd_ulp_bound(plus_profile[field].detach(),
                                          minus_profile[field].detach(), epsilon, cell)
                    av, fv = float(ad_flat[cell].item()), float(fd_flat[cell].item())
                    fields[field] = {
                        "cell": cell, **_derivative_check(av, fv, bound),
                        "ad_nonzero": av != 0.0, "fd_nonzero": fv != 0.0,
                    }
                epsilon_results[str(epsilon)] = {
                    "epsilon": epsilon,
                    "same_tapped_topology": _same_topology(ad_trace, plus_trace, minus_trace),
                    "rate_fd": rate_fd, "rate_checks": rate_checks, "profile": fields,
                }
        finally:
            ad_handle.close()
        selected = epsilon_results[str(EPSILONS[-1])]
        verified_fields = [field for field in PROFILE_FIELDS if all(
            epsilon_results[str(eps)]["profile"][field]["status"] == "verified" for eps in EPSILONS)]
        rate_names = [name for name, value in rate_ad.items() if value != 0.0]
        verified_rates = [name for name in PROCESS_RATE_FIELDS[process] if all(
            epsilon_results[str(eps)]["rate_checks"][name]["status"] in ("verified", "zero")
            for eps in EPSILONS)]
        unresolved_rates = [name for name in PROCESS_RATE_FIELDS[process] if name not in verified_rates]
        rows.append({
            "process": process, "stage": PROCESS_STAGE[process],
            "alpha_reference": 0.0, "epsilons": list(EPSILONS),
            "postcap_baseline_rates": {name: float(value.detach().reshape(-1)[0].item())
                                        for name, value in ad_rates.items()},
            "postcap_rate_alpha_jvp": rate_ad,
            "nonzero_postcap_rate_derivatives": rate_names,
            "verified_postcap_rate_derivatives": verified_rates,
            "unresolved_postcap_rate_derivatives": unresolved_rates,
            "same_tapped_topology": all(v["same_tapped_topology"] for v in epsilon_results.values()),
            "profile": selected["profile"], "epsilon_results": epsilon_results,
            "verified_fields": verified_fields,
            "status": "verified_selected_intervention" if rate_names and not unresolved_rates and verified_fields else "partial_rate_or_profile_unresolved",
            "interpretation": "total named-control intervention through existing caps; not unique single-rate causal attribution",
        })
    return rows


def run_probe() -> dict[str, Any]:
    baseline, forcing = cold_fixture()
    # Use an interior, off-knot density for smooth central-FD validation.  The
    # density-500 table knot is covered separately by test_progb's one-sided test.
    baseline = baseline._replace(bg=baseline.qg / 450.0)
    rho_d = (forcing.rho / (1.0 + baseline.qv))[0].detach()
    rows: list[dict[str, Any]] = []
    for source in SOURCES:
        reference = getattr(baseline, source)
        # Positive relative directions preserve the admissible positive moment
        # pair.  The ±epsilon endpoints are therefore not independent raw-rate
        # interventions and do not violate shared donor caps.
        direction = 0.05 * reference
        ad_state = type(baseline)(*(
            x.detach().clone().requires_grad_(True)
            for name, x in zip(baseline._fields, baseline)
        ))
        ad_trace = SensitivityTrace()
        ad_out, ad_handle = _run(ad_state, forcing, trace=ad_trace)
        ad_profile = _profile(ad_out, forcing, rho_d)
        direction_state = type(baseline)(*(
            direction if name == source else torch.zeros_like(x)
            for name, x in zip(baseline._fields, baseline)
        ))
        # Existing double-VJP helper retains each profile cell, so AD and FD
        # select and compare the same cell instead of comparing a scalar sum to
        # a max cell (which is invalid for HYDRO/DEFF vectors).
        ad_cells = {
            field: _directional_values(ad_profile[field], ad_state, direction_state).detach()
            for field in PROFILE_FIELDS
        }
        epsilon_results: dict[str, Any] = {}
        try:
            for epsilon in EPSILONS:
                plus_state = baseline._replace(**{source: reference + epsilon * direction})
                minus_state = baseline._replace(**{source: reference - epsilon * direction})
                plus_trace, minus_trace = SensitivityTrace(), SensitivityTrace()
                with torch.no_grad():
                    plus_out, plus_handle = _run(plus_state, forcing, trace=plus_trace)
                    try:
                        plus_profile = _profile(plus_out, forcing, rho_d)
                    finally:
                        plus_handle.close()
                    minus_out, minus_handle = _run(minus_state, forcing, trace=minus_trace)
                    try:
                        minus_profile = _profile(minus_out, forcing, rho_d)
                    finally:
                        minus_handle.close()

                fields: dict[str, Any] = {}
                for field in PROFILE_FIELDS:
                    fd_cells = (plus_profile[field] - minus_profile[field]) / (2.0 * epsilon)
                    ad_flat, fd_flat = ad_cells[field].reshape(-1), fd_cells.reshape(-1)
                    cell = int(torch.argmax(torch.maximum(ad_flat.abs(), fd_flat.abs())).item())
                    ulp_bound = _fd_ulp_bound(plus_profile[field].detach(),
                                              minus_profile[field].detach(), epsilon, cell)
                    ad_value, fd_value = float(ad_flat[cell].item()), float(fd_flat[cell].item())
                    fields[field] = {
                        "cell": cell, **_derivative_check(ad_value, fd_value, ulp_bound),
                        "ad_nonzero": ad_value != 0.0,
                        "fd_nonzero": fd_value != 0.0,
                    }
                epsilon_results[str(epsilon)] = {
                    "epsilon": epsilon, "same_tapped_topology": _same_topology(ad_trace, plus_trace, minus_trace),
                    "profile": fields,
                }
        finally:
            # Keep the AD graph handle alive through every double-VJP above.
            ad_handle.close()

        selected = epsilon_results[str(EPSILONS[-1])]
        verified_fields = [
            field for field in PROFILE_FIELDS
            if all(epsilon_results[str(eps)]["profile"][field]["status"] == "verified" for eps in EPSILONS)
        ]

        rows.append({
            "source": source,
            "reference": float(reference.reshape(-1)[0].item()),
            "direction": float(direction.reshape(-1)[0].item()),
            "epsilons": list(EPSILONS),
            "positive_endpoints": bool(torch.all(minus_state._asdict()[source] > 0).item()),
            "moment_pair_admissible": all(
                _moment_pair_admissible(baseline._replace(**{source: reference + sign * eps * direction}))
                for eps in EPSILONS for sign in (-1.0, 1.0)
            ) and _moment_pair_admissible(baseline),
            "same_tapped_topology": _same_topology(ad_trace, plus_trace, minus_trace),
            "stage_names": [r["name"] for r in ad_trace.signature()],
            "profile": selected["profile"], "epsilon_results": epsilon_results,
            "verified_fields": verified_fields,
            "status": ("verified_selected_direction" if verified_fields and
                        all(_moment_pair_admissible(baseline._replace(**{source: reference + sign * eps * direction}))
                            for eps in EPSILONS for sign in (-1.0, 1.0))
                        else "ad_fd_mismatch_selected_direction" if any(
                            v["ad_nonzero"] or v["fd_nonzero"] for v in selected["profile"].values())
                        else "zero_or_unresolved_selected_direction"),
        })
    return {
        "contract": {
            "regime": "cold_fixture_single_column",
            "dt_seconds": 20.0,
            "source_intervention": "positive relative initial number/volume state direction",
            "moment_pair_contract": "100 <= qg/bg <= 900; diagnostic baseline sets bg=qg/450 (off-knot)",
            "topology": "exact SensitivityTrace stage signature plus subcycle records",
            "profile_map": "analytic model_to_rttov_tensors; frozen rho_d",
            "rttov_bt_or_cost": "unverified_no_live_rttov_invocation",
            "interpretation": "state/profile Jacobian along an admissible direction; named-process causal attribution remains separate",
            "completion": "partial_named_process_to_profile_and_BT_open",
            "relative_error_gate": RELATIVE_ERROR_GATE,
        },
        "rows": rows,
        "named_process_rows": run_process_probe(baseline, forcing, rho_d),
    }


def write_artifacts(out_dir: Path) -> dict[str, Any]:
    result = run_probe()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cold_profile_path.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [
        "# A4 cold number/volume to RTTOV profile path",
        "",
        "Scope: one existing cold fixture column, positive admissible initial-state directions, and exact `SensitivityTrace` tapped topology. The profile map is analytic/frozen-`rho_d`; no live RTTOV BT or cost derivative is claimed.",
        "",
        "| source | tapped topology | T AD/FD | Q AD/FD | HYDRO AD/FD | DEFF AD/FD | status |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in result["rows"]:
        p = row["profile"]
        def pair(k): return f"{p[k]['ad']:.6g}/{p[k]['fd']:.6g}"
        lines.append(f"| `{row['source']}` | {row['same_tapped_topology']} | {pair('T')} | {pair('Q')} | {pair('HYDRO')} | {pair('DEFF')} | `{row['status']}` |")
    lines += [
        "",
        "Acceptance: a selected direction is verified only when both AD and independent central FD are nonzero, FD exceeds the output-ULP bound, relative error is below 1%, endpoints remain positive, and all tapped trace records/subcycles match. Zero and unresolved paths, including zero `DEFF` response, are recorded as coverage results, not forced sensitivities.",
        "",
        "The rows below are state/profile Jacobians. The completion status is partial: it does not establish named-process -> later-state -> profile/BT causality, a full Jacobian, or a live RTTOV BT/cost derivative.",
        "Named-control probes below are total interventions through the existing post-cap path; they do not assign the resulting effect uniquely to one raw rate.",
        "",
        "## Supported named controls",
        "",
        "| process | post-cap stage | nonzero post-cap rate alpha-JVPs | unresolved post-cap rates | verified profile fields | status |",
        "|---|---|---|---|---|---|",
    ]
    for row in result["named_process_rows"]:
        lines.append(f"| `{row['process']}` | `{row['stage']}` | {', '.join('`'+n+'`' for n in row['nonzero_postcap_rate_derivatives']) or 'none'} | {', '.join('`'+n+'`' for n in row['unresolved_postcap_rate_derivatives']) or 'none'} | {', '.join('`'+n+'`' for n in row['verified_fields']) or 'none'} | `{row['status']}` |")
    (out_dir / "cold_profile_path.md").write_text("\n".join(lines) + "\n")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(write_artifacts(args.out), indent=2))
