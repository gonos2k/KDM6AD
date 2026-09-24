#!/usr/bin/env python3
"""Conditional dry-mass/volume probe for warm cloud-rain accretion.

This is a diagnostic adapter around the existing ``accretion_torch`` producer,
not a proposed host conversion or a statement that the historical number field
has a known physical basis. It recomputes DSD slopes from the supplied moments
in each representation and checks the result against an independently written
volume-form collection equation.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from sys import float_info
from pathlib import Path
from typing import Any

import torch

ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "oracle"
if str(ORACLE) not in sys.path:
    sys.path.insert(0, str(ORACLE))

from kdm6 import constants as c  # noqa: E402
from kdm6 import fconst as fc  # noqa: E402
from kdm6.cloud_dsd import (  # noqa: E402
    default_cloud_dsd_params,
    diag_avedia_cloud_torch,
    diag_avedia_rain_torch,
    diag_cloud_slope_torch,
    diag_lencon_torch,
    diag_sigma_cloud_torch,
    diag_species_slope_torch,
)
from kdm6.warm import accretion_torch, default_warm_accretion_params  # noqa: E402

EVIDENCE = ROOT / "harness/evidence/number_boundary_2026-09-20.json"
DIRECTIONS = {"small": 0.85, "large": 1.25}
RTOL = 64.0 * float_info.epsilon


def _t(value: float | torch.Tensor) -> torch.Tensor:
    if isinstance(value, torch.Tensor):
        return value
    return torch.tensor([[value]], dtype=torch.float64)


def _float(value: torch.Tensor) -> float:
    return float(value.detach().cpu().reshape(-1)[0])


def _assert_finite_tree(value: Any, path: str = "result") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _assert_finite_tree(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_finite_tree(child, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise AssertionError(f"nonfinite value at {path}")


def _fresh_dsd(
    qc: torch.Tensor,
    nc_volume: torch.Tensor,
    qr: torch.Tensor,
    nr_volume: torch.Tensor,
    den: torch.Tensor,
    cloud: Any,
) -> dict[str, torch.Tensor]:
    """Rebuild cloud and rain slopes/diameters from this arm's current moments."""
    sc = diag_cloud_slope_torch(qc, nc_volume, den, params=cloud)
    sr = diag_species_slope_torch(
        qr, nr_volume, den, fc.PIDNR, c.DMR, c.LAMDARMAX, c.LAMDARMIN
    )
    avedia_c = diag_avedia_cloud_torch(sc, params=cloud)
    avedia_r = diag_avedia_rain_torch(sr, params=cloud)
    sigma_c = diag_sigma_cloud_torch(sc, params=cloud)
    return {
        "rslopec": sc,
        "rslopec3": sc * sc * sc,
        "rslope_r": sr,
        "rslope3_r": sr * sr * sr,
        "avedia_c": avedia_c,
        "avedia_r": avedia_r,
        "sigma_c": sigma_c,
    }


def _independent_volume_formula(
    C: torch.Tensor,
    Nc: torch.Tensor,
    R: torch.Tensor,
    Nr: torch.Tensor,
    avedia_r: torch.Tensor,
    gate_limit: torch.Tensor,
    rslopec: torch.Tensor,
    rslope_r: torch.Tensor,
    *,
    params: Any,
    cloud: Any,
    dt: float,
) -> tuple[torch.Tensor, torch.Tensor, dict[str, torch.Tensor]]:
    """Direct volume-rate equation from Fortran's two accretion regimes.

    C/R are kg m-3 and Nc/Nr are m-3. This deliberately does not call
    ``accretion_torch`` or consume a rate recorded by the historical trace.
    """
    # Slopes are recomputed from each arm's C,N by the actual DSD producer.
    # Reuse those fresh DSD outputs here so this check isolates the independent
    # collection equation while retaining the source's mixed-precision slope.
    sc3, sr3 = rslopec * rslopec * rslopec, rslope_r * rslope_r * rslope_r
    g41 = params.g4pmr / params.g1pmr
    g71 = params.g7pmr / params.g1pmr

    mass_big = (
        params.cmc * params.ncrk1 * Nc * Nr * sc3
        * (sc3 * params.g6pmc + sr3 * params.g3pmc * g41)
    )
    number_big = (
        params.ncrk1 * Nc * Nr
        * (sc3 * params.g3pmc + sr3 * g41)
    )
    mass_small = (
        params.cmc * params.ncrk2 * Nc * Nr * sc3
        * (sc3 * sc3 * params.g9pmc + sr3 * sr3 * params.g3pmc * g71)
    )
    number_small = (
        params.ncrk2 * Nc * Nr
        * (sc3 * sc3 * params.g6pmc + sr3 * sr3) * g71
    )
    big = avedia_r >= params.di100
    raw_mass = torch.where(big, mass_big, mass_small)
    raw_number = torch.where(big, number_big, number_small)
    mass_capped = torch.minimum(raw_mass, C / dt)
    number_capped = torch.minimum(raw_number, Nc / dt)
    active = R >= gate_limit
    result = (
        torch.where(active, mass_capped, torch.zeros_like(C)),
        torch.where(active, number_capped, torch.zeros_like(Nc)),
        {
            "mass_raw": raw_mass,
            "number_raw": raw_number,
            "mass_cap": C / dt,
            "number_cap": Nc / dt,
            "active": active,
            "big_drop": big,
            "lambda_c": 1.0 / rslopec,
            "lambda_r": 1.0 / rslope_r,
        },
    )
    return result


def _compare(x: torch.Tensor, y: torch.Tensor, rtol: float = RTOL) -> float:
    scale = max(abs(_float(x)), abs(_float(y)), 1.0e-300)
    error = abs(_float(x) - _float(y)) / scale
    if error > rtol:
        raise AssertionError(f"relative mismatch {error:.3e} > {rtol:.3e}")
    return error


def run_case(
    *,
    mode: str,
    capped: bool,
    gate_active: bool = True,
    density: float = 0.88,
    dt: float = 20.0,
) -> dict[str, Any]:
    """Compare dry and volume encodings after fresh DSD and rate recalculation."""
    if mode not in DIRECTIONS:
        raise ValueError("mode must be 'small' or 'large'")
    if not math.isfinite(density) or not math.isfinite(dt) or density <= 0 or dt <= 0:
        raise ValueError("density and dt must be positive")

    cloud = default_cloud_dsd_params()
    params = default_warm_accretion_params()
    # A declared physical state, then its dry-mass and volume coordinates.
    qc_d, qr_d, nc_d = 2.0e-4, 5.0e-5, 1.2e9
    rho = _t(density)
    C, Nc = rho * qc_d, rho * nc_d

    # Choose rain number from the desired fresh mean-volume diameter; both
    # cases stay inside the source rain-slope clamp.
    rain_diameter = DIRECTIONS[mode] * params.di100
    g_ratio = (params.g4pmr / params.g1pmr) ** (1.0 / 3.0)
    Nr = (rho * qr_d) * (g_ratio**3) / (fc.PIDNR * rain_diameter**3)
    R = rho * qr_d

    # Derive the cloud-to-rain transition from the actual DSD formula. The gate
    # test then uses a converted threshold in each representation.
    dsd_volume = _fresh_dsd(C, Nc, R, Nr, _t(1.0), cloud)
    source_lenconcr_volume = diag_lencon_torch(
        C, _t(1.0), dsd_volume["avedia_c"], dsd_volume["sigma_c"],
        qcrmin=c.QCRMIN,
    )[1]
    # Isolate the incoming rain-active threshold with a matched concentration
    # threshold on either side of R. The source-derived lenconcr above remains
    # recorded context; this synthetic threshold avoids conflating gate basis
    # with whether the historical state happens to exceed its threshold.
    gate_limit = R * (0.5 if gate_active else 2.0)

    dt_case = dt
    # Increase only synthetic dt, leaving all collection coefficients intact,
    # until both source inventory caps are active. This is a cap branch test,
    # not an atmospheric timestep claim.
    if capped:
        probe_raw = _independent_volume_formula(
            C, Nc, R, Nr, dsd_volume["avedia_r"], _t(0.0),
            dsd_volume["rslopec"], dsd_volume["rslope_r"],
            params=params, cloud=cloud, dt=1.0,
        )[2]
        dt_case = max(
            dt,
            2.0 * _float(C / probe_raw["mass_raw"]),
            2.0 * _float(Nc / probe_raw["number_raw"]),
        )

    # Arm A: q and n_d in per-dry-mass coordinates. Convert number to the
    # kernel's conditional volume-number input, recompute DSD, call production.
    qc_mix, qr_mix = C / rho, R / rho
    Nc_from_dry, Nr_from_dry = rho * (Nc / rho), rho * (Nr / rho)
    dsd_dry = _fresh_dsd(qc_mix, Nc_from_dry, qr_mix, Nr_from_dry, rho, cloud)
    production_dry = accretion_torch(
        qc_mix, Nc_from_dry, qr_mix, Nr_from_dry, rho,
        dsd_dry["avedia_r"], dsd_dry["rslopec3"], dsd_dry["rslope3_r"],
        gate_limit / rho, params=params, dtcld=dt_case,
    )

    # Arm B: same physical moments as volume quantities. den=1 is the formal
    # adapter because C is already a concentration, not a second atmosphere.
    dsd_vol = _fresh_dsd(C, Nc, R, Nr, _t(1.0), cloud)
    production_volume = accretion_torch(
        C, Nc, R, Nr, _t(1.0), dsd_vol["avedia_r"], dsd_vol["rslopec3"],
        dsd_vol["rslope3_r"], gate_limit, params=params, dtcld=dt_case,
    )

    # Independent direct volume equation; use the actual freshly recalculated
    # rain diameter only to select the source's discrete regime.
    formula_mass, formula_number, formula_meta = _independent_volume_formula(
        C, Nc, R, Nr, dsd_vol["avedia_r"], gate_limit,
        dsd_vol["rslopec"], dsd_vol["rslope_r"],
        params=params, cloud=cloud, dt=dt_case,
    )
    dry_mass_volume = rho * production_dry[0]
    dry_number_volume = production_dry[1]
    err_mass_rep = _compare(dry_mass_volume, production_volume[0])
    err_num_rep = _compare(dry_number_volume, production_volume[1])
    err_mass_formula = _compare(production_volume[0], formula_mass)
    err_num_formula = _compare(production_volume[1], formula_number)

    # Exercise the production cloud gate's representation-domain limit. Its
    # EPS is on qc's declared mass-mixing coordinate, so volume qc=C is not
    # allowed to inherit that same numeric floor near zero.
    rho_floor = _t(0.25)
    qfloor = _t(1.5 * c.EPS)
    nc_floor_probe = _t(10.0 * c.NCMIN / 0.25)
    nc_volume_floor_probe = rho_floor * nc_floor_probe
    floor_cloud_dry = diag_cloud_slope_torch(
        qfloor, nc_volume_floor_probe, rho_floor,
        params=cloud,
    )
    floor_cloud_volume = diag_cloud_slope_torch(
        rho_floor * qfloor, nc_volume_floor_probe, _t(1.0),
        params=cloud,
    )
    cloud_gate_dry = bool(_float((qfloor <= c.EPS).to(torch.float64)))
    cloud_gate_volume = bool(
        _float(((rho_floor * qfloor) <= c.EPS).to(torch.float64))
    )

    result = {
        "case": f"{mode}_{'cap' if capped else 'free'}_{'active' if gate_active else 'gate_off'}",
        "synthetic": True,
        "conditional_number_basis": "n_d in # kg_d^-1; kernel N=rho_d*n_d in # m^-3",
        "physical_density_kg_m3": density,
        "density_role": "fixed physical rho_d; den=1 is a formal volume-coordinate adapter only",
        "mode_expected": mode,
        "mode_actual": "large" if _float(dsd_vol["avedia_r"]) >= params.di100 else "small",
        "fresh_avedia_r_m": _float(dsd_vol["avedia_r"]),
        "source_derived_lenconcr_volume": _float(source_lenconcr_volume),
        "synthetic_gate_limit_volume": _float(gate_limit),
        "gate_limit_scope": "synthetic threshold for conversion/gate branch check; source threshold reported separately",
        "di100_m": params.di100,
        "rain_active": bool(_float(formula_meta["active"].to(torch.float64))),
        "dt_seconds": dt_case,
        "cap_stress_multiplier": 1.0,
        "mass_cap_active": _float(formula_meta["mass_raw"]) >= _float(formula_meta["mass_cap"]),
        "number_cap_active": _float(formula_meta["number_raw"]) >= _float(formula_meta["number_cap"]),
        "dry_to_volume_mass_rate": _float(dry_mass_volume),
        "volume_production_mass_rate": _float(production_volume[0]),
        "independent_volume_mass_rate": _float(formula_mass),
        "volume_number_rate": _float(production_volume[1]),
        "number_rate_converted_back_to_dry": _float(production_volume[1] / rho),
        "independent_volume_number_rate": _float(formula_number),
        "relative_errors": {
            "representation_mass": err_mass_rep,
            "representation_number": err_num_rep,
            "volume_formula_mass": err_mass_formula,
            "volume_formula_number": err_num_formula,
        },
        "near_epsilon_gate_counterexample": {
            "rho_dry": _float(rho_floor),
            "qc_dry": _float(qfloor),
            "C_volume": _float(rho_floor * qfloor),
            "N_volume": _float(nc_volume_floor_probe),
            "eps": c.EPS,
            "dry_active": not cloud_gate_dry,
            "volume_active_if_same_numeric_floor": not cloud_gate_volume,
            "dry_rslopec": _float(floor_cloud_dry),
            "volume_rslopec": _float(floor_cloud_volume),
            "metamorphic_claim_excludes_this_boundary": True,
        },
    }
    _assert_finite_tree(result)
    return result


def derivative_check(mode: str = "large", density: float = 0.88) -> dict[str, float]:
    """JVP/central-FD check of recalculated physical rates along density."""
    if mode not in DIRECTIONS:
        raise ValueError("mode must be 'small' or 'large'")
    if not math.isfinite(density) or density <= 0:
        raise ValueError("density must be finite and positive")
    cloud = default_cloud_dsd_params()
    params = default_warm_accretion_params()
    qc_d, qr_d, nc_d = 2.0e-4, 5.0e-5, 1.2e9
    rain_diameter = DIRECTIONS[mode] * params.di100
    ratio = params.g4pmr / params.g1pmr
    nr_d = qr_d * ratio / (fc.PIDNR * rain_diameter**3)
    dt = 20.0

    def both(r: torch.Tensor) -> torch.Tensor:
        C, Nc = r * qc_d, r * nc_d
        R, Nr = r * qr_d, r * nr_d
        dsd_dry = _fresh_dsd(_t(qc_d), Nc, _t(qr_d), Nr, r, cloud)
        dsd_vol = _fresh_dsd(C, Nc, R, Nr, _t(1.0), cloud)
        lencon = diag_lencon_torch(
            C, _t(1.0), dsd_vol["avedia_c"], dsd_vol["sigma_c"],
            qcrmin=c.QCRMIN,
        )[1] * 0.5
        prod_dry = accretion_torch(
            _t(qc_d), Nc, _t(qr_d), Nr, r, dsd_dry["avedia_r"],
            dsd_dry["rslopec3"], dsd_dry["rslope3_r"], lencon / r,
            params=params, dtcld=dt,
        )
        prod_vol = accretion_torch(
            C, Nc, R, Nr, _t(1.0), dsd_vol["avedia_r"], dsd_vol["rslopec3"],
            dsd_vol["rslope3_r"], lencon, params=params, dtcld=dt,
        )
        direct = _independent_volume_formula(
            C, Nc, R, Nr, dsd_vol["avedia_r"], lencon,
            dsd_vol["rslopec"], dsd_vol["rslope_r"],
            params=params, cloud=cloud, dt=dt,
        )[:2]
        return torch.stack((
            (r * prod_dry[0]).reshape(()), prod_dry[1].reshape(()),
            prod_vol[0].reshape(()), prod_vol[1].reshape(()),
            direct[0].reshape(()), direct[1].reshape(()),
        ))

    r0 = torch.tensor(density, dtype=torch.float64)
    direction = torch.tensor(0.13 * density, dtype=torch.float64)
    values, jvp = torch.func.jvp(both, (r0,), (direction,))
    step = 1.0e-5 * density
    fd = (both(_t(density + step)) - both(_t(density - step))) / (2.0 * step) * direction
    errors = []
    for a, b in zip(jvp, fd):
        scale = max(abs(_float(a)), abs(_float(b)), 1.0e-300)
        errors.append(abs(_float(a) - _float(b)) / scale)
        if errors[-1] > 2.0e-6:
            raise AssertionError(f"JVP/FD mismatch {errors[-1]:.3e}")
    pairs = ((0, 2), (0, 4), (1, 3), (1, 5))
    if any(_compare(values[a], values[b]) > RTOL for a, b in pairs) \
            or any(_compare(jvp[a], jvp[b]) > RTOL for a, b in pairs):
        raise AssertionError("production and independent volume derivatives disagree in value")
    cotangent = torch.tensor([0.25, -0.5, 0.75, 1.25, -0.8, 0.6], dtype=torch.float64)
    _vjp_value, pullback = torch.func.vjp(both, r0)
    vjp = pullback(cotangent)[0]
    jvp_pairing = torch.sum(cotangent * jvp)
    vjp_pairing = vjp * direction
    if _compare(jvp_pairing, vjp_pairing) > RTOL:
        raise AssertionError("JVP/VJP pairing mismatch")
    return {
        "density_direction": _float(direction),
        "mass_rate_jvp": _float(jvp[0]),
        "mass_rate_fd": _float(fd[0]),
        "number_rate_jvp": _float(jvp[1]),
        "number_rate_fd": _float(fd[1]),
        "max_production_vs_direct_jvp_relative_error": max(
            *[
                abs(_float(jvp[a] - jvp[b]))
                / max(abs(_float(jvp[a])), abs(_float(jvp[b])), 1.0e-300)
                for a, b in pairs
            ],
        ),
        "jvp_vjp_pairing_relative_error": abs(_float(jvp_pairing - vjp_pairing))
        / max(abs(_float(jvp_pairing)), abs(_float(vjp_pairing)), 1.0e-300),
        "max_relative_jvp_fd_error": max(errors),
    }


def historical_rows() -> list[dict[str, Any]]:
    """Recalculate three retained rows under two explicit number hypotheses."""
    data = json.loads(EVIDENCE.read_text())
    cloud = default_cloud_dsd_params()
    params = default_warm_accretion_params()
    out: list[dict[str, Any]] = []
    for row in data["rows"]:
        op = row["operands"]
        rho_d = row["rho_d_frozen"]
        for interpretation, rho, number_scale in (
            ("legacy_raw_N_per_m3", op["den"], 1.0),
            ("conditional_dry_n_to_N", rho_d, rho_d),
        ):
            qc, qr = _t(op["qc"]), _t(op["qr"])
            Nc, Nr = _t(number_scale * op["nc"]), _t(number_scale * op["nr"])
            density = _t(rho)
            dsd = _fresh_dsd(qc, Nc, qr, Nr, density, cloud)
            # The retained producer threshold is in the same mass-mixing
            # coordinate as qr. Preserve it for the legacy arm; under the dry
            # interpretation convert that same threshold to volume with the
            # original source density, then into the conditional dry adapter.
            source_threshold_mix = _t(op["lenconcr"])
            physical_threshold = _t(op["den"]) * source_threshold_mix
            limit_mix = (
                source_threshold_mix
                if interpretation == "legacy_raw_N_per_m3"
                else physical_threshold / density
            )
            prod = accretion_torch(
                qc, Nc, qr, Nr, density, dsd["avedia_r"], dsd["rslopec3"],
                dsd["rslope3_r"], limit_mix, params=params, dtcld=20.0,
            )
            C, R = density * qc, density * qr
            direct_mass, direct_number, _meta = _independent_volume_formula(
                C, Nc, R, Nr, dsd["avedia_r"], physical_threshold,
                dsd["rslopec"], dsd["rslope_r"],
                params=params, cloud=cloud, dt=20.0,
            )
            mass_volume = density * prod[0]
            number_volume = prod[1]
            out.append({
                "native_layer": row["native_layer"],
                "interpretation": interpretation,
                "rho_used_kg_m3": rho,
                "captured_source_threshold_mixing_coordinate": op["lenconcr"],
                "volume_threshold_after_conditional_conversion": _float(physical_threshold),
                "conditional": True,
                "physical_number_basis_resolved": False,
                "fresh_avedia_r_m": _float(dsd["avedia_r"]),
                "mode": "large" if _float(dsd["avedia_r"]) >= params.di100 else "small",
                "rain_active": _float(_meta["active"].to(torch.float64)) == 1.0,
                "volume_mass_rate": _float(mass_volume),
                "direct_volume_mass_rate": _float(direct_mass),
                "volume_number_rate": _float(number_volume),
                "direct_volume_number_rate": _float(direct_number),
                "captured_legacy_pracw_context_only": row["producer_outputs"]["pracw"],
                "captured_legacy_nracw_context_only": row["producer_outputs"]["nracw"],
                "relative_error": {
                    "mass": _compare(mass_volume, direct_mass),
                    "number": _compare(number_volume, direct_number),
                },
            })
    return out


def run_probe() -> dict[str, Any]:
    cases = [
        run_case(mode=mode, capped=capped, gate_active=active)
        for mode in ("small", "large")
        for capped in (False, True)
        for active in (False, True)
    ]
    assert all(x["mode_actual"] == x["mode_expected"] for x in cases)
    assert all(x["rain_active"] == x["case"].endswith("_active") for x in cases)
    assert all(x["mass_cap_active"] == x["number_cap_active"] for x in cases)
    assert all(x["mass_cap_active"] == ("_cap_" in x["case"]) for x in cases)
    derivatives = {m: derivative_check(m) for m in ("small", "large")}
    history = historical_rows()
    result = {
        "schema": "moment-representation-probe-v1",
        "scope": "conditional warm-accretion recomputation; synthetic + retained-row diagnostics",
        "producer": "oracle.kdm6.warm.accretion_torch (Fortran pracw/nracw equations)",
        "independent_equation": "direct C,N volume-form two-mode collection equation",
        "source_evidence_sha256": hashlib.sha256(EVIDENCE.read_bytes()).hexdigest(),
        "synthetic_cases": cases,
        "density_jvp_fd": derivatives,
        "historical_conditional_rows": history,
        "limits": {
            "physical_number_basis_resolved": False,
            "production_or_abi_changed": False,
            "native_model_or_rttov_run": False,
            "forecast_or_observation_acceptance": False,
            "den_one_means_a_new_atmosphere": False,
            "large_coefficient_cap_cases_are_physical": False,
            "near_eps_q_gate_invariant": False,
            "historical_rates_replayed_as_native": False,
        },
    }
    _assert_finite_tree(result)
    return result


if __name__ == "__main__":
    print(json.dumps(run_probe(), indent=2, sort_keys=True))
