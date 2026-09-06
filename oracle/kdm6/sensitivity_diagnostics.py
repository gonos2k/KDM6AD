"""Opt-in, branch-local KDM process sensitivity diagnostics.

This module is deliberately a diagnostic layer around the existing fp64 oracle.
It does not alter a rate, add a process control, or enter the C++/Fortran ABI.
With no :class:`SensitivityTrace` passed to ``kdm6_step`` there are no trace
records and the legacy call path is unchanged.

The trace follows the owned boundaries in ``kdm62d_one_step_torch``:

``D1 -> D2-D4 -> warm/cold/D5 rates -> conservation-limited rates ->
state_update -> satadj -> cleanup -> DSD limiter``.

Warm ``prevp`` is explicitly named as the value consumed by cold nucleation and
deposition.  A rate-generation record is not called an applied transfer until
the post-conservation record is inspected.  Boolean records contain counts and
are intentionally not presented as complete masks; integer ``mstep`` changes
and branch crossings remain outside this first diagnostic version.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Iterable, Mapping, Sequence

import torch

from .state import State, Forcing, state_dot
from .runtime import kdm6_step, make_parameters
from .water_budget import column_water_kg_m2


def _tensor_items(bundle: Any) -> Iterable[tuple[str, torch.Tensor]]:
    """Yield tensor fields from a NamedTuple-like process output bundle."""
    if bundle is None:
        return
    names = getattr(bundle, "_fields", ())
    for name in names:
        value = getattr(bundle, name)
        if isinstance(value, torch.Tensor):
            yield name, value


@dataclass
class StageRecord:
    """One stage boundary, retaining graph tensors only when diagnostics are on."""

    name: str
    step: int
    dtcld: float
    state_in: Any
    state_out: Any
    rates: Any = None
    branch: torch.Tensor | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def branch_summary(self) -> dict[str, Any] | None:
        if self.branch is None:
            return None
        b = self.branch.detach().to(torch.bool)
        return {
            "active_count": int(b.sum().item()),
            "total_count": int(b.numel()),
            "shape": list(b.shape),
            "mask_sha256": hashlib.sha256(b.cpu().contiguous().numpy().tobytes()).hexdigest(),
            "meaning": "count only; this is not a complete branch mask certificate",
        }

    def rate_summary(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for name, tensor in _tensor_items(self.rates):
            x = tensor.detach()
            finite = torch.isfinite(x)
            numeric = x.to(torch.float64) if not (x.is_floating_point() or x.is_complex()) else x
            out[name] = {
                "shape": list(x.shape),
                "finite": bool(finite.all().item()),
                "active_count": int((x != 0).sum().item()),
                "max_abs": float(numeric.abs().max().item()) if x.numel() else 0.0,
            }
        return out

    def applied_delta_summary(self) -> dict[str, dict[str, Any]]:
        if self.state_in is None or self.state_out is None:
            return {}
        out: dict[str, dict[str, Any]] = {}
        names = getattr(self.state_in, "_fields", ())
        for name in names:
            x = (getattr(self.state_out, name) - getattr(self.state_in, name)).detach()
            out[name] = {
                "max_abs": float(x.abs().max().item()) if x.numel() else 0.0,
                "sum": float(x.sum().item()),
            }
        return out

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "step": self.step,
            "dtcld": self.dtcld,
            "branch": self.branch_summary(),
            "rates": self.rate_summary(),
            "applied_delta": self.applied_delta_summary(),
            "metadata": dict(self.metadata),
        }


class SensitivityTrace:
    """Mutable opt-in collector used by the coordinator stage taps."""

    def __init__(self) -> None:
        self.records: list[StageRecord] = []
        self.subcycles: list[dict[str, Any]] = []

    def record_subcycle(self, step: int, *, mstep_main: int, mstep_ice: int,
                        main_by_column: torch.Tensor, ice_by_column: torch.Tensor) -> None:
        # Value-only topology metadata; these integer gates are not AD inputs.
        self.subcycles.append({"step": int(step), "mstep_main": int(mstep_main),
                               "mstep_ice": int(mstep_ice),
                               "main_by_column": main_by_column.detach().cpu().tolist(),
                               "ice_by_column": ice_by_column.detach().cpu().tolist()})

    def record_stage(
        self, name: str, step: int, dtcld: float, state_in: Any, state_out: Any,
        rates: Any = None, *, branch: torch.Tensor | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> StageRecord:
        record = StageRecord(
            name=name, step=int(step), dtcld=float(dtcld), state_in=state_in,
            state_out=state_out, rates=rates, branch=branch,
            metadata=dict(metadata or {}),
        )
        self.records.append(record)
        return record

    def by_name(self, name: str) -> list[StageRecord]:
        return [r for r in self.records if r.name == name]

    def signature(self) -> list[dict[str, Any]]:
        """Return stage/count metadata; equal counts do not imply equal masks."""
        return [
            {"step": r.step, "name": r.name, "branch": r.branch_summary()}
            for r in self.records
        ]

    def as_dict(self) -> dict[str, Any]:
        return {"records": [r.as_dict() for r in self.records], "signature": self.signature(),
                "subcycles": list(self.subcycles)}


def _clone_requires_grad(state: State) -> State:
    return State(*(x.detach().clone().requires_grad_(True) for x in state))


def _add_direction(state: State, direction: State, scale: float) -> State:
    for name, a, b in zip(State._fields, state, direction):
        if a.shape != b.shape:
            raise ValueError(f"direction.{name} shape {tuple(b.shape)} != state shape {tuple(a.shape)}")
    return State(*(a + scale * b for a, b in zip(state, direction)))


def _directional(output: torch.Tensor, leaves: State, direction: State) -> float:
    if not output.requires_grad:
        return 0.0
    grads = torch.autograd.grad(
        output.sum(), tuple(leaves), retain_graph=True, allow_unused=True,
        materialize_grads=True,
    )
    return float(state_dot(State(*grads), direction).detach().item())


def _coord_water(state: Any, forcing: Forcing) -> torch.Tensor:
    """Fixed rho*dz water measure for a CoordinatorState stage boundary."""
    if hasattr(state, "th"):
        return column_water_kg_m2(state, forcing)
    rho_dz = forcing.rho * forcing.delz
    qt = state.qv + state.qc + state.qr + state.qi + state.qs + state.qg
    return (rho_dz * qt).sum(dim=-1)


def _field_fd(plus: State, minus: State, epsilon: float) -> dict[str, float]:
    return {
        name: float(((getattr(plus, name) - getattr(minus, name)) / (2.0 * epsilon)).abs().max().item())
        for name in State._fields
    }


@dataclass
class SensitivityReport:
    """Serializable result of one local state-direction diagnostic."""

    dt: float
    epsilon: float
    stages: dict[str, Any]
    final_jvp_max_abs: dict[str, float]
    final_fd_max_abs: dict[str, float]
    final_fd_abs_error: dict[str, float]
    stage_fd: dict[str, Any]
    applied_fd: dict[str, Any]
    causal_links: dict[str, Any]
    branch_comparison: dict[str, Any]
    subcycles: list[dict[str, Any]]
    duality: dict[str, float] | None
    water: dict[str, Any]
    zero_reasons: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "dt": self.dt, "epsilon": self.epsilon,
            "stages": self.stages,
            "final_jvp_max_abs": self.final_jvp_max_abs,
            "final_fd_max_abs": self.final_fd_max_abs,
            "final_fd_abs_error": self.final_fd_abs_error,
            "stage_fd": self.stage_fd,
            "applied_fd": self.applied_fd,
            "causal_links": self.causal_links,
            "branch_comparison": self.branch_comparison,
            "subcycles": self.subcycles,
            "duality": self.duality, "water": self.water,
            "zero_reasons": self.zero_reasons,
        }


def diagnose_step(
    state: State,
    forcing: Forcing,
    direction: State,
    *,
    dt: float = 60.0,
    epsilon: float | None = None,
    covector: State | None = None,
    params=None,
    xland=None,
    ncmin_land: float = 0.0,
    ncmin_sea: float = 0.0,
    controls=None,
) -> SensitivityReport:
    """Trace one step and compare its tangent with an independent central FD.

    The derivative is local to the selected fixed active topology.  A zero is
    labelled conservatively: the trace can establish a disabled/count-zero
    branch, while a zero without that evidence remains a fixture zero with an
    unresolved cause.
    """
    if epsilon is None:
        epsilon = 1.0e-5
    if not (torch.isfinite(torch.tensor(epsilon)) and epsilon > 0.0):
        raise ValueError("epsilon must be finite and > 0")
    params = params if params is not None else make_parameters()
    leaves = _clone_requires_grad(state)
    trace = SensitivityTrace()
    out, handle = kdm6_step(
        leaves, forcing, params, dt, value_only=False, xland=xland,
        ncmin_land=ncmin_land, ncmin_sea=ncmin_sea, controls=controls,
        diagnostic_trace=trace,
    )
    tangent = handle.jvp(direction)
    duality = None
    if covector is not None:
        adjoint = handle.vjp(covector, retain_graph=True)
        lhs = float(state_dot(tangent, covector).detach().item())
        rhs = float(state_dot(direction, adjoint).detach().item())
        duality = {"jvp_dot_covector": lhs, "direction_dot_vjp": rhs, "abs_error": abs(lhs - rhs)}

    # Stage rates remain graph-connected until this function has completed.
    stage_data: dict[str, Any] = {}
    for record in trace.records:
        rates = {}
        for name, value in _tensor_items(record.rates):
            rates[name] = {
                "value": record.rate_summary().get(name, {}),
                "directional": _directional(value, leaves, direction),
            }
        applied_directional = {}
        if record.state_in is not None and record.state_out is not None:
            for field_name in getattr(record.state_in, "_fields", ()):
                delta = getattr(record.state_out, field_name) - getattr(record.state_in, field_name)
                applied_directional[field_name] = _directional(delta, leaves, direction)
        stage_data[f"{record.step}:{record.name}"] = {
            "record": record.as_dict(), "rates": rates,
            "applied_directional": applied_directional,
        }
    with torch.no_grad():
        plus_trace, minus_trace = SensitivityTrace(), SensitivityTrace()
        plus, hp = kdm6_step(_add_direction(state, direction, epsilon), forcing, params,
                             dt, value_only=True, xland=xland,
                             ncmin_land=ncmin_land, ncmin_sea=ncmin_sea, controls=controls,
                             diagnostic_trace=plus_trace)
        minus, hm = kdm6_step(_add_direction(state, direction, -epsilon), forcing, params,
                              dt, value_only=True, xland=xland,
                              ncmin_land=ncmin_land, ncmin_sea=ncmin_sea, controls=controls,
                              diagnostic_trace=minus_trace)
        hp.close(); hm.close()
    stage_fd: dict[str, Any] = {}
    applied_fd: dict[str, Any] = {}
    branch_comparison: dict[str, Any] = {
        "subcycles": {"base": trace.subcycles, "plus": plus_trace.subcycles,
                      "minus": minus_trace.subcycles,
                      "equal": trace.subcycles == plus_trace.subcycles == minus_trace.subcycles},
    }
    causal_links: dict[str, Any] = {}
    plus_by_key = {(r.step, r.name): r for r in plus_trace.records}
    minus_by_key = {(r.step, r.name): r for r in minus_trace.records}
    base_keys = {(r.step, r.name) for r in trace.records}
    for key in sorted(base_keys | plus_by_key.keys() | minus_by_key.keys()):
        if not (key in base_keys and key in plus_by_key and key in minus_by_key):
            branch_comparison[f"{key[0]}:{key[1]}"] = {
                "comparable": False, "reason": "stage missing in a perturbation member",
                "present": {"base": key in base_keys, "plus": key in plus_by_key,
                            "minus": key in minus_by_key},
            }
    for record in trace.records:
        key = (record.step, record.name)
        rp, rm = plus_by_key.get(key), minus_by_key.get(key)
        if rp is None or rm is None:
            continue
        b0, bp, bm = record.branch_summary(), rp.branch_summary(), rm.branch_summary()
        if b0 is not None and bp is not None and bm is not None:
            changed = (record.branch != rp.branch) | (record.branch != rm.branch)
            first = torch.nonzero(changed, as_tuple=False)
            branch_comparison[f"{record.step}:{record.name}"] = {
                "base_active_count": b0["active_count"],
                "plus_active_count": bp["active_count"],
                "minus_active_count": bm["active_count"],
                "counts_unchanged": (b0["active_count"] == bp["active_count"] == bm["active_count"]),
                "masks_equal": bool(torch.equal(record.branch.detach().to(torch.bool), rp.branch.detach().to(torch.bool))
                                    and torch.equal(record.branch.detach().to(torch.bool), rm.branch.detach().to(torch.bool))),
                "first_changed_cell": first[0].detach().cpu().tolist() if first.numel() else None,
                "meaning": "exact tapped phase masks; untapped internal branches remain unverified",
            }
        one = {}
        for name, value in _tensor_items(record.rates):
            vp = dict(_tensor_items(rp.rates)).get(name)
            vm = dict(_tensor_items(rm.rates)).get(name)
            if vp is None or vm is None:
                continue
            if not (vp.is_floating_point() or vp.is_complex()):
                # Boolean gate outputs are compared through branch counts and
                # are not differentiable rates.
                continue
            fd = float(((vp - vm).sum() / (2.0 * epsilon)).item())
            ad = stage_data[f"{record.step}:{record.name}"]["rates"].get(name, {}).get("directional", 0.0)
            one[name] = {"fd_sum": fd, "ad_sum": ad, "abs_error": abs(fd - ad)}
        if one:
            stage_fd[f"{record.step}:{record.name}"] = one
        applied_one = {}
        for field_name in getattr(record.state_in, "_fields", ()):
            dplus = getattr(rp.state_out, field_name) - getattr(rp.state_in, field_name)
            dminus = getattr(rm.state_out, field_name) - getattr(rm.state_in, field_name)
            fd = float(((dplus - dminus).sum() / (2.0 * epsilon)).item())
            ad = stage_data[f"{record.step}:{record.name}"]["applied_directional"].get(field_name, 0.0)
            applied_one[field_name] = {"fd_sum": fd, "ad_sum": ad, "abs_error": abs(fd - ad)}
        if applied_one:
            applied_fd[f"{record.step}:{record.name}"] = applied_one
    warm_records = trace.by_name("warm")
    cold_records = trace.by_name("cold")
    update_records = trace.by_name("state_update")
    if warm_records:
        upstream = getattr(warm_records[0].rates, "prevp", None)
        if upstream is not None:
            for consumer_name, consumer, fields in (
                ("cold", cold_records[0].rates if cold_records else None, ("pinud", "pidep")),
                ("state_update", update_records[0].state_out if update_records else None, ("qv", "qr", "t")),
            ):
                if consumer is None:
                    continue
                for field_name in fields:
                    value = getattr(consumer, field_name)
                    grad = torch.autograd.grad(value.sum(), upstream, retain_graph=True,
                                               allow_unused=True)[0] if value.requires_grad else None
                    causal_links[f"warm.prevp->{consumer_name}.{field_name}"] = {
                        "structurally_connected": grad is not None,
                        "max_abs_derivative": 0.0 if grad is None else float(grad.detach().abs().max().item()),
                        "zero_reason": ("fixture/branch yielded zero; cause not established"
                                         if grad is not None and not bool((grad != 0).any().item()) else None),
                    }
    fd = {name: float((((getattr(plus, name) - getattr(minus, name)) / (2.0 * epsilon)).abs().max().item()))
          for name in State._fields}
    jv = {name: float(getattr(tangent, name).detach().abs().max().item()) for name in State._fields}
    err = {name: float((getattr(tangent, name).detach() -
                        (getattr(plus, name) - getattr(minus, name)) / (2.0 * epsilon)).abs().max().item())
           for name in State._fields}
    # Fixed-measure water residual and its tangent.  Sedimentation is included
    # in the full step, so this is reported as measured, not forced to zero.
    win = column_water_kg_m2(leaves, forcing)
    wout = column_water_kg_m2(out, forcing)
    water_tangent = _directional(wout - win, leaves, direction)
    # Compare the same signed scalar as ``water_tangent`` (the sum over
    # columns); do not let opposite column residuals silently change the
    # meaning of the finite-difference check.
    initial_plus = column_water_kg_m2(_add_direction(state, direction, epsilon), forcing)
    initial_minus = column_water_kg_m2(_add_direction(state, direction, -epsilon), forcing)
    water_res_plus = column_water_kg_m2(plus, forcing) - initial_plus
    water_res_minus = column_water_kg_m2(minus, forcing) - initial_minus
    water_fd = float(((water_res_plus - water_res_minus).sum() /
                      (2.0 * epsilon)).item())
    freeze_record = next((r for r in trace.records if r.name == "d2_d4_freeze"), None)
    freeze_water = None
    if freeze_record is not None:
        freeze_value = _coord_water(freeze_record.state_out, forcing) - _coord_water(freeze_record.state_in, forcing)
        freeze_directional = _directional(freeze_value, leaves, direction)
        freeze_water = {"max_abs_value": float(freeze_value.detach().abs().max().item()),
                        "directional": freeze_directional,
                        "measure": "rho * delz * (qv+qc+qr+qi+qs+qg)",
                        "interpretation": "actual D2-D4 stage boundary; clamp/roundoff retained"}
    zero_reasons = {}
    for name, value in jv.items():
        if value != 0.0 or fd[name] != 0.0:
            continue
        zero_reasons[name] = "zero in this fixture/seed; cause not established"
    handle.close()
    return SensitivityReport(
        dt=float(dt), epsilon=float(epsilon), stages=stage_data,
        final_jvp_max_abs=jv, final_fd_max_abs=fd, final_fd_abs_error=err,
        stage_fd=stage_fd, applied_fd=applied_fd,
        branch_comparison=branch_comparison, causal_links=causal_links,
        subcycles=list(trace.subcycles), duality=duality,
        water={"residual_directional": water_tangent, "fd_directional_signed": water_fd,
               "fd_directional_abs": abs(water_fd),
               "ad_fd_abs_error": abs(water_tangent - water_fd),
               "measure": "rho * delz * (qv+qc+qr+qi+qs+qg)",
               "interpretation": "measured full-step residual; no conservation claim",
               "d2_d4_freeze": freeze_water},
        zero_reasons=zero_reasons,
    )


def compare_dt_refinement(
    state: State,
    forcing: Forcing,
    direction: State,
    *,
    dt: float,
    params=None,
    xland=None,
    ncmin_land: float = 0.0,
    ncmin_sea: float = 0.0,
    controls=None,
) -> dict[str, Any]:
    """Compare one ``dt`` step with two sequential ``dt/2`` steps.

    Forcing is held fixed and aligned to both substeps.  The report includes
    state and tangent changes plus subcycle branch/count signatures; integer
    mstep differences and threshold crossings are open diagnostics in V1.
    """
    params = params if params is not None else make_parameters()

    def run_graph(step_dt: float, two: bool):
        x = _clone_requires_grad(state)
        all_tangents = None
        signatures = []
        subcycles = []
        for _ in range(2 if two else 1):
            trace = SensitivityTrace()
            x, h = kdm6_step(x, forcing, params, step_dt, value_only=True, xland=xland,
                             ncmin_land=ncmin_land, ncmin_sea=ncmin_sea,
                             controls=controls, diagnostic_trace=trace)
            signatures.extend(trace.signature())
            subcycles.extend(trace.subcycles)
            h.close()
        return State(*(getattr(x, n).detach() for n in State._fields)), all_tangents, signatures, subcycles

    with torch.no_grad():
        coarse, _, coarse_sig, coarse_sub = run_graph(dt, False)
        fine, _, fine_sig, fine_sub = run_graph(dt / 2.0, True)
    # Tangents are recomputed independently at each final state to avoid
    # conflating sequential direction transport with a reused seed.
    def tangent(step_dt: float, two: bool):
        x = _clone_requires_grad(state)
        v = direction
        sig = []
        for _ in range(2 if two else 1):
            tr = SensitivityTrace()
            y, h = kdm6_step(x, forcing, params, step_dt, xland=xland,
                             ncmin_land=ncmin_land, ncmin_sea=ncmin_sea,
                             controls=controls, diagnostic_trace=tr)
            v = h.jvp(v)
            x, sig = y, sig + tr.signature()
            h.close()
        return v, sig
    coarse_tan, _ = tangent(dt, False)
    fine_tan, _ = tangent(dt / 2.0, True)
    return {
        "interval": float(dt), "forcing_alignment": "same forcing for both dt/2 substeps",
        "state_max_abs_difference": {
            n: float((getattr(coarse, n) - getattr(fine, n)).abs().max().item())
            for n in State._fields
        },
        "tangent_max_abs_difference": {
            n: float((getattr(coarse_tan, n) - getattr(fine_tan, n)).abs().max().item())
            for n in State._fields
        },
        "coarse_signature": coarse_sig,
        "refined_signature": fine_sig,
        "coarse_subcycles": coarse_sub,
        "refined_subcycles": fine_sub,
        "open": ["integer mstep changes and threshold/limiter crossings are not certified by this comparison"],
    }
