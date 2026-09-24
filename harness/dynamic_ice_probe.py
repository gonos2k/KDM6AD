#!/usr/bin/env python3
"""Synthetic dynamic-ice probe: real slope recomputation to normalized consumer.

This exercises only the existing KDM6 slope and opt-in conservative ice kernel.
It does not run the full main-physics chain or claim a native-column result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import platform
from pathlib import Path

import torch

from kdm6 import constants as c
from kdm6.sed_conservative import conservative_ice_substep_advection_torch
from kdm6.sedimentation import IceSubstepState, default_substep_advection_params
from kdm6.slope import default_slope_params, slope_kdm6_torch
from ice_consumption_contract import (
    VelocitySample,
    audit_events,
    check_geometry,
    consume,
    generation_for,
    normalize,
    schedule,
    select_msteps,
)


DT = 20.0
OUTDIR = Path("graphify-out/dynamic-ice-contract")


def make_fixture(K: int) -> dict:
    """Two synthetic columns: thick layers select 1; thin layers select >1."""
    if K not in (1, 2, 4):
        raise ValueError("synthetic probe supports K=1, 2, or 4")
    dtype = torch.float64
    shape = (2, K)
    qi_profile = [1.0e-5, 2.0e-5, 4.0e-6, 3.0e-5][:K]
    ni_profile = [1.0e4, 2.0e4, 3.0e3, 4.0e4][:K]
    qi = torch.tensor([qi_profile, qi_profile], dtype=dtype)
    ni = torch.tensor([ni_profile, ni_profile], dtype=dtype)
    # Deliberately nonuniform synthetic geometry. K=1 is the one-layer control.
    dz = torch.tensor(
        ([100.0, 110.0, 120.0, 130.0][:K], [6.0, 7.0, 8.0, 9.0][:K]),
        dtype=dtype,
    )
    rho = torch.full(shape, 0.9, dtype=dtype)
    t = torch.full(shape, 260.0, dtype=dtype)
    zero = torch.zeros(shape, dtype=dtype)
    slope_params = default_slope_params()
    bvtg = torch.full(shape, 0.5316, dtype=dtype)
    fixture = {
        "kind": "synthetic_geometry_operator_probe",
        "K": K,
        "dt": DT,
        "qi": qi,
        "ni": ni,
        "dz": dz,
        "rho": rho,
        "t": t,
        "denfac": torch.ones(shape, dtype=dtype),
        "zero": zero,
        "bvtg": bvtg,
        "rslopegbmax": torch.full(shape, slope_params.rslopegmax, dtype=dtype) ** bvtg,
        "pidn0g": torch.full(shape, 2.5e5, dtype=dtype),
        "pvtg": torch.full(shape, 95.0, dtype=dtype),
        "slope_params": slope_params,
        "ice_params": default_substep_advection_params(),
    }
    check_geometry(dz)  # value-only preflight; never inside the AD map
    return fixture


def _slope(qi: torch.Tensor, ni: torch.Tensor, f: dict, generation: tuple):
    zero = f["zero"]
    out = slope_kdm6_torch(
        qr=zero,
        qs=zero,
        qg=zero,
        qi=qi,
        nr=zero,
        ni=ni,
        den=f["rho"],
        denfac=f["denfac"],
        t=f["t"],
        pidn0g=f["pidn0g"],
        pvtg=f["pvtg"],
        bvtg=f["bvtg"],
        rslopegbmax=f["rslopegbmax"],
        params=f["slope_params"],
    )
    return VelocitySample(generation, out.vt_i, out.vtn_i), out


def _branch_signature(qi: torch.Tensor, slope_out) -> torch.Tensor:
    """Observed ice inactive/size-limiter branches, not a copied slope equation."""
    low = torch.as_tensor(1.0 / c.LAMDAIMAX, dtype=qi.dtype, device=qi.device)
    high = torch.as_tensor(1.0 / c.LAMDAIMIN, dtype=qi.dtype, device=qi.device)
    return torch.stack(
        (qi <= c.EPS, slope_out.rslope_i == low, slope_out.rslope_i == high), dim=-1
    )


def _run_cycle(qi, ni, f, counts, cycle, previous, trace):
    fall_qi = torch.zeros_like(qi)
    fall_ni = torch.zeros_like(ni)
    events = []
    mstep_col = torch.tensor(counts, dtype=torch.int64, device=qi.device)
    for n in range(1, max(counts) + 1):
        generation = generation_for(cycle, n)
        raw, slope_out = _slope(qi, ni, f, generation)
        rate = normalize(raw, f["dz"])
        work_qi, work_ni = consume(rate, expected_generation=generation)
        active_events = []
        if trace:
            branch = _branch_signature(qi, slope_out)
            for column, count in enumerate(counts):
                if n <= count:
                    if previous is None:
                        dv_qi = torch.zeros_like(rate.mass[column])
                        dv_ni = torch.zeros_like(rate.number[column])
                    else:
                        dv_qi = raw.mass[column] - previous[0][column]
                        dv_ni = raw.number[column] - previous[1][column]
                    event = {
                        "cycle": cycle,
                        "n": n,
                        "column": column,
                        "selected_mstep": count,
                        "consumed_mstep": count,
                        "producer_generation": raw.generation,
                        "expected_generation": generation,
                        "mass_velocity": raw.mass[column],
                        "number_velocity": raw.number[column],
                        "mass_rate": work_qi[column],
                        "number_rate": work_ni[column],
                        "delta_v_mass": dv_qi,
                        "delta_v_number": dv_ni,
                        "branch_signature": branch[column],
                    }
                    active_events.append(event)
                    events.append(event)
            before_state = tuple(x.clone() for x in (qi, ni, fall_qi, fall_ni))
        out = conservative_ice_substep_advection_torch(
            IceSubstepState(qi=qi, ni=ni),
            fall_qi,
            fall_ni,
            work_qi,
            work_ni,
            f["dz"],
            f["rho"],
            mstep=max(counts),
            mstep_col=mstep_col,
            n_current=n,
            dtcld=f["dt"],
            params=f["ice_params"],
        )
        qi, ni = out.state.qi, out.state.ni
        fall_qi, fall_ni = out.fall_qi, out.fall_ni
        if trace:
            after_state = (qi, ni, fall_qi, fall_ni)
            for event in active_events:
                event["before_state"] = before_state
                event["after_state"] = after_state
        active = (mstep_col >= n).unsqueeze(-1)
        if previous is None:
            previous = (raw.mass, raw.number)
        else:
            previous = (
                torch.where(active, raw.mass, previous[0]),
                torch.where(active, raw.number, previous[1]),
            )
    return qi, ni, fall_qi, fall_ni, events, previous


def make_plan(qi, ni, fixture: dict, cycles: int = 2) -> tuple[tuple[int, ...], ...]:
    """Select a value-only mstep plan by running the same slope/ice composition."""
    if cycles < 1:
        raise ValueError("at least one outer cycle is required")
    if qi.requires_grad or ni.requires_grad:
        raise ValueError("select the discrete plan before entering AD")
    check_geometry(fixture["dz"])
    plan = []
    q, n = qi, ni
    with torch.no_grad():
        for cycle in range(1, cycles + 1):
            raw, _ = _slope(q, n, fixture, (cycle, "selection", 0))
            rates = normalize(raw, fixture["dz"])
            selected = select_msteps(rates, fixture["dt"])
            counts = tuple(int(value) for value in selected.tolist())
            plan.append(counts)
            q, n, _, _, _, _ = _run_cycle(q, n, fixture, counts, cycle, None, False)
    return tuple(plan)


def run_with_plan(qi, ni, fixture: dict, plan, trace: bool = False):
    """Run slope → normalize → conservative-ice cycles under a frozen plan."""
    if not plan or any(len(row) != qi.shape[0] for row in plan):
        raise ValueError("plan must have one nonempty row per cycle and column")
    expected = schedule(plan)
    q, n, fqi, fni = qi, ni, torch.zeros_like(qi), torch.zeros_like(ni)
    events, previous = [], None
    for cycle, counts in enumerate(plan, 1):
        q, n, cycle_qi, cycle_ni, cycle_events, previous = _run_cycle(
            q, n, fixture, counts, cycle, previous, trace
        )
        fqi, fni = fqi + cycle_qi, fni + cycle_ni
        events.extend(cycle_events)
    if trace:
        audit_events(events, expected)
    else:
        events = []
    return (q, n, fqi, fni), events


def _max_consumed_cfl(events, plan, dt=DT):
    return max(
        max(float(event["mass_rate"].max()), float(event["number_rate"].max()))
        * dt
        / plan[event["cycle"] - 1][event["column"]]
        for event in events
    )


def _check_gated_columns(events, plan):
    """Per-consumer snapshots show columns past their mstep are exact no-ops."""
    for event in events:
        before, after = event["before_state"], event["after_state"]
        for column, count in enumerate(plan[event["cycle"] - 1]):
            if event["n"] > count:
                for x, y in zip(before, after):
                    x_bits = x[column].contiguous().view(torch.uint8)
                    y_bits = y[column].contiguous().view(torch.uint8)
                    if not torch.equal(x_bits, y_bits):
                        raise AssertionError(
                            "finished column state/fall changed under the mstep gate"
                        )


def _ad_map(qi, ni, fixture, plan):
    out, events = run_with_plan(qi, ni, fixture, plan, trace=True)
    rates = tuple(
        torch.stack([event[key] for event in events])
        for key in ("mass_rate", "number_rate", "delta_v_mass", "delta_v_number")
    )
    return (*out, *rates)


def _derivative_probe(fixture, plan):
    qi, ni = fixture["qi"], fixture["ni"]
    k = torch.arange(fixture["K"], dtype=qi.dtype).reshape(1, -1)
    direction = (0.01 * qi * torch.sin(k + 0.3), 0.01 * ni * torch.cos(k + 0.7))

    def fn(q, n):
        return _ad_map(q, n, fixture, plan)

    out, tangent = torch.func.jvp(fn, (qi, ni), direction)
    _, pullback = torch.func.vjp(fn, qi, ni)
    seeds = tuple(torch.ones_like(value) / max(value.numel(), 1) for value in out)
    grad_q, grad_n = pullback(seeds)
    left = sum((seed * tan).sum() for seed, tan in zip(seeds, tangent))
    right = (grad_q * direction[0]).sum() + (grad_n * direction[1]).sum()
    eps = 1.0e-3
    q_plus, n_plus = qi + eps * direction[0], ni + eps * direction[1]
    q_minus, n_minus = qi - eps * direction[0], ni - eps * direction[1]
    plus_plan = make_plan(q_plus, n_plus, fixture, cycles=len(plan))
    minus_plan = make_plan(q_minus, n_minus, fixture, cycles=len(plan))
    if plus_plan != plan or minus_plan != plan:
        raise AssertionError(
            "finite-difference perturbation crossed the discrete mstep plan"
        )
    with torch.no_grad():
        plus_out, plus_events = run_with_plan(q_plus, n_plus, fixture, plan, trace=True)
        minus_out, minus_events = run_with_plan(
            q_minus, n_minus, fixture, plan, trace=True
        )
        plus = (
            *plus_out,
            *(
                torch.stack([event[key] for event in plus_events])
                for key in (
                    "mass_rate",
                    "number_rate",
                    "delta_v_mass",
                    "delta_v_number",
                )
            ),
        )
        minus = (
            *minus_out,
            *(
                torch.stack([event[key] for event in minus_events])
                for key in (
                    "mass_rate",
                    "number_rate",
                    "delta_v_mass",
                    "delta_v_number",
                )
            ),
        )
    base_events = run_with_plan(qi, ni, fixture, plan, trace=True)[1]
    _check_gated_columns(base_events, plan)
    _check_gated_columns(plus_events, plan)
    _check_gated_columns(minus_events, plan)

    def signature(events):
        return [event["branch_signature"].tolist() for event in events]

    if signature(base_events) != signature(plus_events) or signature(
        base_events
    ) != signature(minus_events):
        raise AssertionError(
            "finite-difference perturbation crossed an ice slope branch"
        )
    if (
        max(
            _max_consumed_cfl(events, plan, fixture["dt"])
            for events in (base_events, plus_events, minus_events)
        )
        >= 1.0
    ):
        raise AssertionError(
            "finite-difference perturbation crossed the outflow cap branch"
        )
    fd_errors = []
    for tangent_value, plus_value, minus_value in zip(tangent, plus, minus):
        fd = (plus_value - minus_value) / (2 * eps)
        scale = max(
            float(torch.linalg.vector_norm(tangent_value)),
            float(torch.linalg.vector_norm(fd)),
            1.0e-30,
        )
        fd_errors.append(float(torch.linalg.vector_norm(tangent_value - fd)) / scale)
    if (
        float(torch.linalg.vector_norm(tangent[-2])) == 0.0
        or float(torch.linalg.vector_norm(tangent[-1])) == 0.0
    ):
        raise AssertionError(
            "state perturbation did not reach recomputed ice velocities"
        )
    dual_scale = max(1.0, abs(float(left)), abs(float(right)))
    return {
        "epsilon": eps,
        "max_fd_relative_error_including_velocity_trace": max(fd_errors),
        "fd_relative_error_by_output": dict(
            zip(
                (
                    "qi",
                    "ni",
                    "fall_qi",
                    "fall_ni",
                    "mass_rate",
                    "number_rate",
                    "delta_v_mass",
                    "delta_v_number",
                ),
                fd_errors,
            )
        ),
        "jvp_vjp_relative_residual": abs(float(left - right)) / dual_scale,
        "mass_rate_tangent_norm": float(torch.linalg.vector_norm(tangent[-4])),
        "number_rate_tangent_norm": float(torch.linalg.vector_norm(tangent[-3])),
        "delta_v_mass_tangent_norm": float(torch.linalg.vector_norm(tangent[-2])),
        "delta_v_number_tangent_norm": float(torch.linalg.vector_norm(tangent[-1])),
        "plus_minus_plan_stable": True,
        "plus_minus_branch_signatures_stable": True,
    }


def probe_case(K: int) -> dict:
    fixture = make_fixture(K)
    plan = make_plan(fixture["qi"], fixture["ni"], fixture)
    if plan[0][0] != 1 or plan[0][1] <= 1:
        raise AssertionError(
            f"expected geometry to select heterogeneous msteps, got {plan[0]}"
        )
    with torch.no_grad():
        out, events = run_with_plan(
            fixture["qi"], fixture["ni"], fixture, plan, trace=True
        )
    _check_gated_columns(events, plan)
    max_cfl = _max_consumed_cfl(events, plan, fixture["dt"])
    max_delta_mass = max(float(event["delta_v_mass"].abs().max()) for event in events)
    max_delta_number = max(
        float(event["delta_v_number"].abs().max()) for event in events
    )
    if max_cfl >= 1.0:
        raise AssertionError("consumed substep reaches the limiter/cap branch")
    derivative = _derivative_probe(fixture, plan)
    branches = [event["branch_signature"].tolist() for event in events]
    records = []
    for e in events:
        col = e["column"]
        record = {
            k: v for k, v in e.items() if k not in ("before_state", "after_state")
        }
        record = {
            k: v.tolist() if isinstance(v, torch.Tensor) else v
            for k, v in record.items()
        }
        for tag in ("before", "after"):
            record[tag] = {
                name: value[col].tolist()
                for name, value in zip(
                    ("qi", "ni", "fall_qi", "fall_ni"), e[tag + "_state"]
                )
            }
        records.append(record)
    mass_before = (fixture["qi"] * fixture["rho"] * fixture["dz"]).sum(dim=1)
    mass_after = (out[0] * fixture["rho"] * fixture["dz"]).sum(dim=1)
    number_before = (fixture["ni"] * fixture["dz"]).sum(dim=1)
    number_after = (out[1] * fixture["dz"]).sum(dim=1)
    mass_surface = out[2][:, -1] * fixture["dt"] * fixture["dz"][:, -1]
    number_surface = out[3][:, -1] * fixture["dt"] * fixture["dz"][:, -1]
    return {
        "K": K,
        "synthetic_geometry_only": True,
        "dt_seconds": DT,
        "dz_m": fixture["dz"].tolist(),
        "initial_qi": fixture["qi"].tolist(),
        "initial_ni": fixture["ni"].tolist(),
        "rho": fixture["rho"].tolist(),
        "consumer_records": records,
        "inactive_columns_bitwise_unchanged": True,
        "conditional_mass_residual": (mass_after + mass_surface - mass_before).tolist(),
        "conditional_number_residual": (
            number_after + number_surface - number_before
        ).tolist(),
        "mass_surface": mass_surface.tolist(),
        "number_surface": number_surface.tolist(),
        "cumulative_fall_qi": out[2].tolist(),
        "cumulative_fall_ni": out[3].tolist(),
        "plan_mstep_ice_by_cycle_column": [list(row) for row in plan],
        "scheduled_consumer_events": len(events),
        "max_consumed_cfl_per_substep": max_cfl,
        "max_delta_v_mass_m_s": max_delta_mass,
        "max_delta_v_number_m_s": max_delta_number,
        "branch_signatures": branches,
        "final_qi": out[0].tolist(),
        "final_ni": out[1].tolist(),
        "derivatives": derivative,
    }


def selection_drift_witness():
    """Prescribed speed-change counterexample, not a measured host main phase."""
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
    mass, _ = consume(later, generation_for(1, 1))
    return dict(
        scope="prescribed synthetic velocity change; no native failure claim",
        initially_selected_mstep=selected.tolist(),
        consumed_mstep=selected.tolist(),
        consumed_C=(20.0 * mass / selected[:, None]).tolist(),
        independently_reselected_mstep_not_applied=select_msteps(later, 20.0).tolist(),
        selected_budget_sufficient=bool((20.0 * mass / selected[:, None] <= 1).all()),
    )


def run_probe() -> dict:
    return {
        "schema": "dynamic-ice-probe-v1",
        "scope": "synthetic slope_kdm6_torch plus conservative_ice_substep_advection_torch; no main phase/native data",
        "torch_version": torch.__version__,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "cases": [probe_case(K) for K in (1, 2, 4)],
        "selection_drift_witness": selection_drift_witness(),
        "physical_number_basis_resolved": False,
        "operational_fix_applied": False,
        "accepted_observation_cost": False,
    }


def _source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTDIR / "dynamic_ice_probe.json")
    args = parser.parse_args()
    data = run_probe()
    data["source_sha256"] = {
        name: _source_hash(Path(__file__).resolve().parents[1] / rel)
        for name, rel in {
            "slope": "oracle/kdm6/slope.py",
            "ice_kernel": "oracle/kdm6/sed_conservative.py",
            "contract": "harness/ice_consumption_contract.py",
            "runner": "harness/dynamic_ice_probe.py",
        }.items()
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=2) + "\n")
    compact = [
        {
            key: case[key]
            for key in (
                "K",
                "plan_mstep_ice_by_cycle_column",
                "scheduled_consumer_events",
                "max_consumed_cfl_per_substep",
                "max_delta_v_mass_m_s",
                "max_delta_v_number_m_s",
                "derivatives",
            )
        }
        for case in data["cases"]
    ]
    print(json.dumps({"out": str(args.out), "cases": compact}, separators=(",", ":")))


if __name__ == "__main__":
    main()
