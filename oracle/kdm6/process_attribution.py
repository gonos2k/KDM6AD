"""Cap-aware named-process attribution helpers for the fp64 oracle.

This module deliberately works at the existing ProcessControls boundary.  A
process is perturbed with one dimensionless alpha, its already paired rates
are passed through the coordinator's existing caps, and the resulting output
state is compared with an independently evaluated +/- alpha finite difference.
It does not perturb raw rate tensors independently and does not claim a closed
number or enthalpy budget where the project has not declared the units.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import torch

from .process_controls import ProcessControls
from .runtime import kdm6_step, make_parameters
from .sensitivity_diagnostics import SensitivityTrace
from .state import Forcing, State


PROCESS_CONTROL_FIELDS = {
    "autoconv": "alpha_autoconv",
    "accretion": "alpha_accretion",
    "deposition": "alpha_deposition",
    "riming": "alpha_riming",
    "freeze": "alpha_freeze",
    "melt": "alpha_melt",
}

PROCESS_STAGE = {
    "autoconv": "warm_limited",
    "accretion": "warm_limited",
    "deposition": "cold_limited",
    "riming": "cold_limited",
    "freeze": "d2_d4_freeze",
    "melt": "d5_limited",
}

PROCESS_RATE_FIELDS = {
    "autoconv": ("praut", "nraut"),
    "accretion": ("pracw", "nracw"),
    "deposition": ("pidep", "psdep", "pgdep"),
    "riming": ("psacw", "nsacw", "pgacw", "ngacw", "paacw_adj",
                "naacw", "piacw", "niacw"),
    "freeze": ("pinuc", "ninuc", "pfrzdtc", "nfrzdtc"),
    "melt": ("pseml", "nseml", "pgeml", "ngeml"),
}

# Number fields are present for these groups.  Deposition is intentionally
# mass-only in the current ProcessControls contract.
PAIRED_PROCESS = {"autoconv", "accretion", "riming", "freeze", "melt"}

PROCESS_STATE_FIELDS = {
    "autoconv": ("qc", "qr", "nc", "nr"),
    "accretion": ("qc", "qr", "nc", "nr"),
    "deposition": ("qv", "qs", "qg", "bg", "th", "qi"),
    "riming": ("qv", "qs", "qg", "bg", "th", "qc", "qi", "nc", "ni"),
    "freeze": ("th", "nccn", "nr", "qc", "qi", "nc", "ni"),
    "melt": ("qs", "qg", "qr", "qc", "nr", "bg", "th"),
}


@dataclass(frozen=True)
class ProcessAttribution:
    process: str
    stage: str
    alpha: float
    epsilon: float
    regime: str
    baseline_rates: dict[str, float]
    controlled_rates: dict[str, float]
    rate_fd: dict[str, float]
    rate_ad: dict[str, float]
    state_effect: dict[str, float]
    state_fd: dict[str, float]
    state_ad: dict[str, float]
    water_effect: float
    water_fd: float
    water_ad: float
    temperature_effect: float
    temperature_fd: float
    temperature_ad: float
    rate_max_relative_error: float
    selected_state_max_relative_error: float
    state_fd_ulp_bound: dict[str, float]
    output_resolution_fields: tuple[str, ...]
    checked_state_fields: tuple[str, ...]
    unchecked_state_fields: tuple[str, ...]
    state_field_status: dict[str, str]
    alpha0_state_primal_equal: bool
    alpha0_rate_primal_equal: bool
    alpha0_primal_equal: bool
    alpha0_state_primal_delta: dict[str, float]
    alpha0_rate_primal_delta: dict[str, float]
    numerical_domain: str
    active: bool
    finite_outputs: bool
    nonzero_state_effect: bool
    tapped_topology_fixed: bool
    paired_mass_number: bool
    status: str
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _controls(process: str, alpha: torch.Tensor) -> ProcessControls:
    try:
        field = PROCESS_CONTROL_FIELDS[process]
    except KeyError as exc:
        raise ValueError(f"unknown controlled process: {process}") from exc
    return ProcessControls(**{field: alpha})


def _run(state: State, forcing: Forcing, process: str | None,
         alpha: float | torch.Tensor,
         *, dt: float, graph: bool) -> tuple[State, SensitivityTrace, Any]:
    dtype = state.qc.dtype
    if isinstance(alpha, torch.Tensor):
        alpha_tensor = alpha.to(dtype=dtype)
        if graph and not alpha_tensor.requires_grad:
            alpha_tensor = alpha_tensor.detach().clone().requires_grad_(True)
    else:
        alpha_tensor = torch.tensor(alpha, dtype=dtype, requires_grad=graph)
    controls = None if process is None else _controls(process, alpha_tensor)
    trace = SensitivityTrace()
    out, handle = kdm6_step(
        state, forcing, make_parameters(), dt, value_only=not graph,
        controls=controls, diagnostic_trace=trace,
    )
    return out, trace, handle


def _water(state: State, forcing: Forcing) -> torch.Tensor:
    return (forcing.rho * forcing.delz *
            (state.qv + state.qc + state.qr + state.qi + state.qs + state.qg)).sum()


def _temperature(state: State, forcing: Forcing) -> torch.Tensor:
    # State.th is potential temperature; convert to actual temperature using
    # the forcing Exner factor before calling this a thermal/latent effect.
    return (state.th * forcing.pii).sum()


def _metric_grad(metric: torch.Tensor, alpha: torch.Tensor) -> float:
    if metric.numel() != 1:
        raise ValueError("process attribution requires singleton (B,K) fixtures")
    if not metric.requires_grad:
        return 0.0
    grad = torch.autograd.grad(metric, alpha, retain_graph=True, allow_unused=True)[0]
    return 0.0 if grad is None else float(grad.detach().item())


def _stage_rates(trace: SensitivityTrace, process: str) -> dict[str, torch.Tensor]:
    stage = PROCESS_STAGE[process]
    records = trace.by_name(stage)
    if not records:
        raise ValueError(f"required attribution stage {stage!r} is missing")
    rates = records[-1].rates
    missing = [name for name in PROCESS_RATE_FIELDS[process] if not hasattr(rates, name)]
    if missing:
        raise ValueError(f"required {process} rate fields missing at {stage}: {missing}")
    return {name: getattr(rates, name) for name in PROCESS_RATE_FIELDS[process]}


def _rate_values(rates: dict[str, torch.Tensor]) -> dict[str, float]:
    return {name: float(value.detach().abs().max().item())
            for name, value in sorted(rates.items())}


def _state_abs_delta(a: State, b: State) -> dict[str, float]:
    return {name: float((getattr(a, name) - getattr(b, name)).detach().abs().max().item())
            for name in State._fields}


def _rates_abs_delta(
    a: dict[str, torch.Tensor], b: dict[str, torch.Tensor]
) -> dict[str, float]:
    return {name: float((a[name] - b[name]).detach().abs().max().item())
            for name in a}


def _state_sum_ad(out: State, alpha: torch.Tensor) -> dict[str, float]:
    return {name: _metric_grad(getattr(out, name).sum(), alpha)
            for name in State._fields}


def _fd_ulp_bound(plus: torch.Tensor, minus: torch.Tensor, epsilon: float) -> float:
    """Final-output spacing scale for (plus-minus)/(2 epsilon)."""
    inf = torch.full_like(plus, float("inf"))
    plus_ulp = (torch.nextafter(plus, inf) - plus).abs()
    minus_ulp = (torch.nextafter(minus, inf) - minus).abs()
    return float(torch.maximum(plus_ulp, minus_ulp).max().item() / (2.0 * epsilon))


def attribute_process(
    state: State,
    forcing: Forcing,
    process: str,
    *,
    regime: str = "unspecified",
    alpha: float = 0.2,
    epsilon: float = 1.0e-4,
    dt: float = 20.0,
) -> ProcessAttribution:
    """Measure one admissible process intervention and its independent FD.

    The baseline is controls=None.  The intervention scales the whole named
    ProcessControls group, then uses the existing conservation and freeze
    donor caps.  State effects are final-state differences relative to the
    baseline; state_ad/state_fd are derivatives with respect to the process
    alpha at alpha=0.  ``paired_mass_number`` describes the declared control
    contract, not a proof of physical number-unit closure.
    """
    if process not in PROCESS_CONTROL_FIELDS:
        raise ValueError(f"unknown controlled process: {process}")
    if state.qc.numel() != 1:
        raise ValueError(
            "process attribution currently accepts singleton (B,K) fixtures; "
            "per-cell attribution must be added before multi-cell aggregation")
    if not (epsilon > 0.0 and torch.isfinite(torch.tensor(epsilon))):
        raise ValueError("epsilon must be finite and positive")

    baseline, base_trace, base_handle = _run(
        state, forcing, None, 0.0, dt=dt, graph=False)
    base_handle.close()
    controlled, controlled_trace, controlled_handle = _run(
        state, forcing, process, alpha, dt=dt, graph=False)
    controlled_handle.close()
    plus, plus_trace, plus_handle = _run(
        state, forcing, process, epsilon, dt=dt, graph=False)
    plus_handle.close()
    minus, minus_trace, minus_handle = _run(
        state, forcing, process, -epsilon, dt=dt, graph=False)
    minus_handle.close()
    # Keep a same-control alpha=0 value-only primal for an exact comparison
    # against the graph evaluation below; controls=None is a separate baseline.
    value_alpha0, value_alpha0_trace, value_alpha0_handle = _run(
        state, forcing, process, 0.0, dt=dt, graph=False)
    value_alpha0_handle.close()

    # A separate graph evaluation supplies reverse-AD alpha derivatives.  This is a derivative
    # of the admissible control, not of an independently altered rate field.
    graph_alpha = torch.tensor(0.0, dtype=state.qc.dtype, requires_grad=True)
    graph_out, graph_trace, graph_handle = _run(
        state, forcing, process, graph_alpha, dt=dt, graph=True)
    # The same alpha leaf is retained by _run; scalar metrics use reverse AD.

    base_rates = _stage_rates(base_trace, process)
    controlled_rates = _stage_rates(controlled_trace, process)
    plus_rates = _stage_rates(plus_trace, process)
    minus_rates = _stage_rates(minus_trace, process)
    value_alpha0_rates = _stage_rates(value_alpha0_trace, process)
    rate_fd = {name: float(((plus_rates[name] - minus_rates[name]).sum() /
                            (2.0 * epsilon)).item())
               for name in PROCESS_RATE_FIELDS[process]
               if name in plus_rates and name in minus_rates}
    # At alpha=0, each controlled rate is R exp(alpha) before any shared cap;
    # after a cap the coordinator graph is the source of truth.  A dedicated
    # autograd evaluation with the actual alpha leaf gives the selected rate VJP.
    rate_alpha = graph_alpha
    ad_out, ad_trace, ad_handle = graph_out, graph_trace, graph_handle
    try:
        ad_rates = _stage_rates(ad_trace, process)
        rate_ad = {name: _metric_grad(ad_rates[name], rate_alpha)
                   for name in PROCESS_RATE_FIELDS[process] if name in ad_rates}
        water_ad = _metric_grad(_water(ad_out, forcing), rate_alpha)
        temperature_ad = _metric_grad(_temperature(ad_out, forcing), rate_alpha)
        state_ad = _state_sum_ad(ad_out, rate_alpha)
    finally:
        # The graph must remain alive until every selected rate/state metric
        # has been differentiated; do not close the handle at the trace tap.
        ad_handle.close()

    base_water = float(_water(baseline, forcing).item())
    controlled_water = float(_water(controlled, forcing).item())
    plus_water = float(_water(plus, forcing).item())
    minus_water = float(_water(minus, forcing).item())
    water_fd = (plus_water - minus_water) / (2.0 * epsilon)
    base_temp = float(_temperature(baseline, forcing).item())
    controlled_temp = float(_temperature(controlled, forcing).item())
    plus_temp = float(_temperature(plus, forcing).item())
    minus_temp = float(_temperature(minus, forcing).item())
    temperature_fd = (plus_temp - minus_temp) / (2.0 * epsilon)
    state_fd = {name: float(((getattr(plus, name) - getattr(minus, name)).sum() /
                             (2.0 * epsilon)).item())
                for name in State._fields}
    state_fd_ulp_bound = {
        name: _fd_ulp_bound(getattr(plus, name), getattr(minus, name), epsilon)
        for name in State._fields
    }
    alpha0_state_primal_delta = _state_abs_delta(value_alpha0, graph_out)
    alpha0_rate_primal_delta = _rates_abs_delta(value_alpha0_rates, ad_rates)
    alpha0_state_primal_equal = all(
        torch.equal(getattr(value_alpha0, name), getattr(graph_out, name))
        for name in State._fields
    )
    alpha0_rate_primal_equal = all(
        torch.equal(value_alpha0_rates[name], ad_rates[name])
        for name in value_alpha0_rates
    )
    alpha0_primal_equal = alpha0_state_primal_equal and alpha0_rate_primal_equal
    checked_state_fields = tuple(PROCESS_STATE_FIELDS[process])
    unchecked_state_fields = tuple(
        name for name in State._fields if name not in checked_state_fields
    )
    output_resolution_fields = tuple(
        name for name in checked_state_fields
        if 0.0 < max(abs(state_fd[name]), abs(state_ad[name]))
        <= state_fd_ulp_bound[name]
    )
    state_effect = _state_abs_delta(controlled, baseline)
    baseline_rate_values = _rate_values(base_rates)
    finite_outputs = all(math.isfinite(value) for value in baseline_rate_values.values())
    finite_outputs = finite_outputs and all(
        bool(torch.isfinite(value).all())
        for rates in (base_rates, controlled_rates, plus_rates, minus_rates,
                      value_alpha0_rates, ad_rates)
        for value in rates.values()
    )
    finite_outputs = finite_outputs and all(
        bool(torch.isfinite(getattr(output, name)).all())
        for output in (baseline, controlled, plus, minus, value_alpha0, graph_out)
        for name in State._fields
    )
    finite_outputs = finite_outputs and all(
        math.isfinite(value)
        for mapping in (rate_fd, rate_ad, state_fd, state_ad)
        for value in mapping.values()
    )
    active = any(value > 0.0 for value in baseline_rate_values.values())
    nonzero_effect = any(value > 0.0 for value in state_effect.values())

    def relative_error(fd: dict[str, float], ad: dict[str, float], names) -> float:
        errors = []
        for name in names:
            f, a = fd.get(name, 0.0), ad.get(name, 0.0)
            scale = max(abs(f), abs(a))
            errors.append(0.0 if scale == 0.0 else abs(f - a) / scale)
        return max(errors) if errors else 0.0

    rate_error = relative_error(rate_fd, rate_ad, PROCESS_RATE_FIELDS[process])
    state_error = relative_error(state_fd, state_ad, checked_state_fields)

    def same_topology(*traces: SensitivityTrace) -> bool:
        if not all(t.subcycles == traces[0].subcycles for t in traces[1:]):
            return False
        keys = [(r.step, r.name) for r in traces[0].records]
        if any([(r.step, r.name) for r in t.records] != keys for t in traces[1:]):
            return False
        for i in range(len(keys)):
            branches = [t.records[i].branch for t in traces]
            if any(b is None for b in branches):
                if not all(b is None for b in branches):
                    return False
            elif not all(torch.equal(branches[0].detach().to(torch.bool), b.detach().to(torch.bool))
                         for b in branches[1:]):
                return False
        return True

    tapped_topology_fixed = same_topology(
        base_trace, plus_trace, minus_trace, value_alpha0_trace, graph_trace)
    # Keep field-level evidence separate from the aggregate status.  An exact
    # zero here is a response of this selected fixture/gate; it does not prove
    # structural independence.  For nonzero fields, nonfinite products and a
    # changed recorded topology take precedence over numerical agreement, so a
    # matched FD cannot be called resolved across a branch switch.
    state_field_status = {}
    for name in checked_state_fields:
        fd, ad = state_fd[name], state_ad[name]
        if not finite_outputs:
            state_field_status[name] = "nonfinite_unresolved"
        elif not alpha0_primal_equal:
            state_field_status[name] = "alpha0_primal_mismatch"
        elif fd == 0.0 and ad == 0.0:
            state_field_status[name] = "zero_response"
        elif not tapped_topology_fixed:
            state_field_status[name] = "topology_unresolved"
        elif name in output_resolution_fields:
            state_field_status[name] = "output_resolution_unresolved"
        else:
            scale = max(abs(fd), abs(ad))
            state_field_status[name] = (
                "resolved_nonzero" if abs(fd - ad) / scale <= 1.0e-4
                else "derivative_mismatch_unresolved")
    derivative_ok = rate_error <= 1.0e-6 and state_error <= 1.0e-4
    if not finite_outputs:
        status = "nonfinite_unresolved"
    elif not alpha0_primal_equal:
        status = "alpha0_primal_mismatch"
    elif active and nonzero_effect and output_resolution_fields:
        status = "unresolved_output_resolution"
    elif active and nonzero_effect and tapped_topology_fixed and derivative_ok:
        status = "verified_selected_direction"
    else:
        status = (
        "zero_inactive_or_unresolved" if not active else "partial_topology_or_zero_effect")
    reason = None if status == "verified_selected_direction" else (
        "nonfinite process rate, state, or derivative product" if not finite_outputs else
        "value-only and graph alpha=0 primals differ for state or applied rate" if not alpha0_primal_equal else
        "rate group inactive in this fixture" if not active else
        "FD signal is at or below the per-field output-ULP bound" if output_resolution_fields else
        "active intervention has unresolved derivative mismatch or topology; cause not established")

    return ProcessAttribution(
        process=process, stage=PROCESS_STAGE[process], alpha=float(alpha),
        epsilon=float(epsilon), regime=regime,
        baseline_rates=_rate_values(base_rates),
        controlled_rates=_rate_values(controlled_rates), rate_fd=rate_fd,
        rate_ad=rate_ad, state_effect=state_effect, state_fd=state_fd,
        state_ad=state_ad,
        water_effect=controlled_water - base_water, water_fd=water_fd,
        water_ad=water_ad, temperature_effect=controlled_temp - base_temp,
        temperature_fd=temperature_fd, temperature_ad=temperature_ad,
        rate_max_relative_error=rate_error,
        selected_state_max_relative_error=state_error,
        state_fd_ulp_bound=state_fd_ulp_bound,
        output_resolution_fields=output_resolution_fields,
        checked_state_fields=checked_state_fields,
        unchecked_state_fields=unchecked_state_fields,
        state_field_status=state_field_status,
        alpha0_state_primal_equal=alpha0_state_primal_equal,
        alpha0_rate_primal_equal=alpha0_rate_primal_equal,
        alpha0_primal_equal=alpha0_primal_equal,
        alpha0_state_primal_delta=alpha0_state_primal_delta,
        alpha0_rate_primal_delta=alpha0_rate_primal_delta,
        numerical_domain=("singleton BxK; alpha central FD at fixed exact tapped "
                          "masks/subcycles; per-field selected-state checks"),
        active=active, finite_outputs=finite_outputs,
        nonzero_state_effect=nonzero_effect,
        tapped_topology_fixed=tapped_topology_fixed,
        paired_mass_number=process in PAIRED_PROCESS, status=status, reason=reason,
    )


def warm_fixture() -> tuple[State, Forcing]:
    """Warm rain fixture with active autoconversion and accretion."""
    z = lambda x: torch.tensor([[x]], dtype=torch.float64)
    state = State(
        th=z(296.8), qv=z(1.4e-2), qc=z(1.5e-3), qr=z(1.0e-4),
        qi=z(0.0), qs=z(0.0), qg=z(0.0), nccn=z(1.0e9), nc=z(1.0e8),
        ni=z(0.0), nr=z(1.0e4), bg=z(0.0),
    )
    forcing = Forcing(rho=z(1.089), pii=z(0.9704), p=z(9.0e4), delz=z(500.0))
    return state, forcing


def cold_fixture() -> tuple[State, Forcing]:
    """Mixed-phase cold fixture with nonzero deposition and riming."""
    z = lambda x: torch.tensor([[x]], dtype=torch.float64)
    state = State(
        th=z(265.0), qv=z(2.0e-3), qc=z(1.0e-4), qr=z(1.0e-4),
        qi=z(1.0e-4), qs=z(1.0e-4), qg=z(1.0e-4), nccn=z(1.0e9),
        nc=z(1.0e8), ni=z(1.0e7), nr=z(1.0e5), bg=z(2.0e-7),  # qg/bg = 500
    )
    forcing = Forcing(rho=z(1.0), pii=z(1.0), p=z(8.0e4), delz=z(500.0))
    return state, forcing


def melt_fixture() -> tuple[State, Forcing]:
    """Warm mixed-phase fixture with enhanced D5 melting active."""
    z = lambda x: torch.tensor([[x]], dtype=torch.float64)
    state = State(
        th=z(285.0), qv=z(1.0e-2), qc=z(1.0e-3), qr=z(1.0e-4),
        qi=z(1.0e-4), qs=z(1.0e-3), qg=z(1.0e-3), nccn=z(1.0e9),
        nc=z(1.0e8), ni=z(1.0e7), nr=z(1.0e5), bg=z(2.0e-6),  # qg/bg = 500
    )
    forcing = Forcing(rho=z(1.0), pii=z(1.0), p=z(9.0e4), delz=z(500.0))
    return state, forcing


def coverage_matrix(*, alpha: float = 0.2, epsilon: float = 1.0e-4,
                    dt: float = 20.0) -> dict[str, dict[str, ProcessAttribution]]:
    fixtures = {
        "warm": warm_fixture(), "cold": cold_fixture(), "melt": melt_fixture(),
    }
    return {
        regime: {
            process: attribute_process(state, forcing, process, regime=regime,
                                       alpha=alpha, epsilon=epsilon, dt=dt)
            for process in PROCESS_CONTROL_FIELDS
        }
        for regime, (state, forcing) in fixtures.items()
    }
