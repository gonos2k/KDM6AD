"""Check the captured pre-satadj local thermal identity."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch

from kdm6 import constants as c
from kdm6 import melt_freeze as mf
from kdm6.process_attribution import cold_fixture, warm_fixture
from kdm6.runtime import kdm6_step
from kdm6.sensitivity_diagnostics import SensitivityTrace, _cell_fd_comparison, _directional_values
from scripts.diagnose_cold_profile_path import _derivative_check, _fd_ulp_bound


def local_terms(trace: SensitivityTrace, xls: float = 2.85e6) -> tuple[torch.Tensor, torch.Tensor]:
    """Return applied sensible and reconstructed latent work, both J/kg."""
    su = trace.by_name("state_update")[0]
    op = su.operands
    cpm, xl, supcol = op["cpm"], op["xl"], op["supcol"]
    cold = (supcol >= 0).to(cpm.dtype)
    dtcld = su.dtcld
    wr = trace.by_name("warm_limited")[0].rates
    cr = trace.by_name("cold_limited")[0].rates
    mf5 = trace.by_name("d5_limited")[0].rates
    dep = cr.psdep + cr.pgdep + cr.pidep + cr.pinud
    frz = (cr.piacr + cr.paacw_adj + cr.pmulcs + cr.pmulcg + cr.pmulrs
           + cr.pmulrg + cr.piacw + cr.paacw_adj + cr.pgacr_adj + cr.psacr_adj)
    work_cold = -xls * dep - xl * wr.prevp - (xls - xl) * frz
    work_warm = -xl * (wr.prevp + cr.psevp + cr.pgevp) - (xls - xl) * (mf5.pseml + mf5.pgeml)
    xlwork2 = torch.where(cold > 0, work_cold, work_warm)
    cpm_safe = torch.clamp(cpm, min=c.QCRMIN)
    xlf = xls - xl
    dT_amount = (dtcld * mf.DEFAULT_XLF / cpm_safe * (mf5.psmlt + mf5.pgmlt)
                 - mf.DEFAULT_XLF / cpm_safe * mf5.pimlt_qi
                 + xlf / cpm_safe * (mf5.pinuc + mf5.pfrzdtc + mf5.pfrzdtr))
    sensible = cpm * (su.state_out.t - su.state_in.t)
    latent_and_amount = -xlwork2 * dtcld + cpm * dT_amount
    return sensible, latent_and_amount


def local_residual(trace: SensitivityTrace, xls: float = 2.85e6) -> torch.Tensor:
    """Return J/kg residual of the state_update temperature equation."""
    sensible, latent_and_amount = local_terms(trace, xls=xls)
    return sensible - latent_and_amount


def satadj_pcond_work(trace: SensitivityTrace) -> torch.Tensor:
    """Return pcond-only latent work at post-state saturation adjustment [J/kg]."""
    rec = trace.by_name("satadj")[0]
    return rec.operands["pcond"] * rec.operands["xl"] * rec.dtcld


def satadj_applied_work(trace: SensitivityTrace) -> torch.Tensor:
    """Return actual cpm·ΔT across the applied satadj boundary [J/kg]."""
    rec = trace.by_name("satadj")[0]
    return rec.operands["cpm"] * (rec.state_out.t - rec.state_in.t)


def satadj_formula_work(trace: SensitivityTrace) -> torch.Tensor:
    """Return xl·(pcact+pcond)·dt for the same applied boundary [J/kg]."""
    rec = trace.by_name("satadj")[0]
    op = rec.operands
    return (op["pcact"] + op["pcond"]) * op["xl"] * rec.dtcld


def resolved_warm_qv_probe() -> dict[str, Any]:
    """Use the warm fixture's larger satadj signal as an independent check."""
    state, forcing = warm_fixture()
    leaves = type(state)(*(x.detach().clone().requires_grad_(True) for x in state))
    base_trace = SensitivityTrace()
    _, base_handle = kdm6_step(leaves, forcing, dt=20.0, diagnostic_trace=base_trace)
    try:
        base_work = satadj_formula_work(base_trace)
        base_actual = satadj_applied_work(base_trace)
        direction = type(state)(*(0.1 * state.qv if name == "qv" else torch.zeros_like(value)
                                  for name, value in zip(state._fields, state)))
        ad = _directional_values(base_work, leaves, direction)
        ad_actual = _directional_values(base_actual, leaves, direction)
        rows = []
        for epsilon in (1.0e-4, 1.0e-3, 1.0e-2):
            plus = state._replace(qv=state.qv + epsilon * direction.qv)
            minus = state._replace(qv=state.qv - epsilon * direction.qv)
            tp, tm = SensitivityTrace(), SensitivityTrace()
            hp = hm = None
            try:
                _, hp = kdm6_step(plus, forcing, dt=20.0, diagnostic_trace=tp)
                _, hm = kdm6_step(minus, forcing, dt=20.0, diagnostic_trace=tm)
                yp, ym = satadj_formula_work(tp), satadj_formula_work(tm)
                yap, yam = satadj_applied_work(tp), satadj_applied_work(tm)
                fd = (yp - ym) / (2.0 * epsilon)
                fd_actual = (yap - yam) / (2.0 * epsilon)
                ad_value, fd_value = float(ad.reshape(-1)[0]), float(fd.reshape(-1)[0])
                ad_actual_value, fd_actual_value = float(ad_actual.reshape(-1)[0]), float(fd_actual.reshape(-1)[0])
                rows.append({
                    "epsilon": epsilon, "ad_j_kg": ad_value, "fd_j_kg": fd_value,
                    "relative_error": _relative_error(fd_value, ad_value),
                    "actual_ad_j_kg": ad_actual_value, "actual_fd_j_kg": fd_actual_value,
                    "actual_relative_error": _relative_error(fd_actual_value, ad_actual_value),
                    "endpoint_resolution_scale": _fd_ulp_bound(yp, ym, epsilon),
                    "same_tapped_topology": (tp.signature() == tm.signature() == base_trace.signature()
                                              and tp.subcycles == tm.subcycles == base_trace.subcycles),
                    "identity_endpoint_max_abs_j_kg": max(
                        float((yap - yp).detach().abs().max()),
                        float((yam - ym).detach().abs().max())),
                    "directional_evidence": _cell_fd_comparison(ad, fd),
                })
            finally:
                if hp is not None:
                    hp.close()
                if hm is not None:
                    hm.close()
        return {
            "fixture": "warm_fixture", "direction": "qv_relative_0.1", "fd": rows,
            "status": ("verified" if all(r["same_tapped_topology"]
                        and r["ad_j_kg"] != 0.0 and r["fd_j_kg"] != 0.0
                        and r["actual_ad_j_kg"] != 0.0 and r["actual_fd_j_kg"] != 0.0
                        and r["directional_evidence"]["finite"]
                        and r["relative_error"] < 1.0e-8
                        and r["actual_relative_error"] < 1.0e-8
                        and r["identity_endpoint_max_abs_j_kg"] < 1.0e-8 for r in rows)
                        else "unresolved_numeric"),
        }
    finally:
        base_handle.close()


def _relative_error(a: float, b: float) -> float:
    scale = max(abs(a), abs(b))
    return 0.0 if scale == 0.0 else abs(a - b) / scale


def run_probe() -> dict[str, Any]:
    state, forcing = cold_fixture()
    # One graph run supplies both the identity residual and the qv directional
    # derivatives; forcing remains fixed across this local first-subcycle check.
    leaves = type(state)(*(x.detach().clone().requires_grad_(True) for x in state))
    ad_trace = SensitivityTrace()
    _, ad_handle = kdm6_step(leaves, forcing, dt=20.0, diagnostic_trace=ad_trace)
    try:
        residual = local_residual(ad_trace)
        record = ad_trace.by_name("state_update")[0]
        satadj_identity = satadj_applied_work(ad_trace) - satadj_formula_work(ad_trace)
        # Directional check: qv is perturbed positively, so both endpoints stay
        # in the admissible state domain.  Compare the same scalar terms at the
        # same first coordinator step, independently by central FD.
        sensible_ad_term, latent_ad_term = local_terms(ad_trace)
        satadj_ad_term = satadj_applied_work(ad_trace)
        satadj_formula_ad_term = satadj_formula_work(ad_trace)
        satadj_pcond_ad_term = satadj_pcond_work(ad_trace)
        direction = type(state)(*(0.1 * state.qv if name == "qv" else torch.zeros_like(value)
                                  for name, value in zip(state._fields, state)))
        ad_sensible = float(_directional_values(sensible_ad_term, leaves, direction).detach().reshape(-1)[0])
        ad_latent = float(_directional_values(latent_ad_term, leaves, direction).detach().reshape(-1)[0])
        ad_satadj = float(_directional_values(satadj_ad_term, leaves, direction).detach().reshape(-1)[0])
        ad_satadj_formula = float(_directional_values(satadj_formula_ad_term, leaves, direction).detach().reshape(-1)[0])
        ad_satadj_pcond = float(_directional_values(satadj_pcond_ad_term, leaves, direction).detach().reshape(-1)[0])
        fd_rows = []
        for epsilon in (0.01, 0.03, 0.1):
            plus = state._replace(qv=state.qv + epsilon * direction.qv)
            minus = state._replace(qv=state.qv - epsilon * direction.qv)
            tp, hp = SensitivityTrace(), None
            tm, hm = SensitivityTrace(), None
            try:
                _, hp = kdm6_step(plus, forcing, dt=20.0, diagnostic_trace=tp)
                _, hm = kdm6_step(minus, forcing, dt=20.0, diagnostic_trace=tm)
                sp, lp = local_terms(tp)
                sm, lm = local_terms(tm)
                sap, sam = satadj_applied_work(tp), satadj_applied_work(tm)
                sfp, sfm = satadj_formula_work(tp), satadj_formula_work(tm)
                spp, spm = satadj_pcond_work(tp), satadj_pcond_work(tm)
                satadj_identity_endpoint = max(
                    float((sap - sfp).detach().abs().max()),
                    float((sam - sfm).detach().abs().max()))
                fd_sensible = float(((sp - sm) / (2.0 * epsilon)).detach().reshape(-1)[0])
                fd_latent = float(((lp - lm) / (2.0 * epsilon)).detach().reshape(-1)[0])
                fd_satadj = float(((sap - sam) / (2.0 * epsilon)).detach().reshape(-1)[0])
                fd_satadj_formula = float(((sfp - sfm) / (2.0 * epsilon)).detach().reshape(-1)[0])
                fd_satadj_pcond = float(((spp - spm) / (2.0 * epsilon)).detach().reshape(-1)[0])
                satadj_cmp = _cell_fd_comparison(
                    _directional_values(satadj_ad_term, leaves, direction),
                    (sap - sam) / (2.0 * epsilon))
                satadj_bound = _fd_ulp_bound(sap, sam, epsilon)
                satadj_pcond_bound = _fd_ulp_bound(spp, spm, epsilon)
                satadj_pcond_signal = max(abs(ad_satadj_pcond), abs(fd_satadj_pcond))
                satadj_pcond_check = _derivative_check(
                    ad_satadj_pcond, fd_satadj_pcond, satadj_pcond_bound)
                satadj_pcond_status = (
                    "verified" if _relative_error(fd_satadj_pcond, ad_satadj_pcond) < 1.0e-8
                    else "insufficient_resolution" if satadj_pcond_check["status"] == "unresolved_output_resolution"
                    else "unresolved_numeric")
                same_topology = tp.signature() == tm.signature() == ad_trace.signature() and tp.subcycles == tm.subcycles == ad_trace.subcycles
                fd_rows.append({
                    "epsilon": epsilon, "sensible_fd_j_kg": fd_sensible,
                    "latent_and_amount_fd_j_kg": fd_latent,
                    "satadj_latent_fd_j_kg": fd_satadj,
                    "satadj_formula_fd_j_kg": fd_satadj_formula,
                    "satadj_pcond_fd_j_kg": fd_satadj_pcond,
                    "sensible_relative_error": _relative_error(fd_sensible, ad_sensible),
                    "latent_and_amount_relative_error": _relative_error(fd_latent, ad_latent),
                    "satadj_latent_relative_error": _relative_error(fd_satadj, ad_satadj),
                    "satadj_formula_relative_error": _relative_error(fd_satadj_formula, ad_satadj_formula),
                    "satadj_pcond_relative_error": _relative_error(fd_satadj_pcond, ad_satadj_pcond),
                    "satadj_endpoint_resolution_scale": satadj_bound,
                    "satadj_identity_relative_error": _relative_error(fd_satadj, fd_satadj_formula),
                    "satadj_identity_endpoint_max_abs_j_kg": satadj_identity_endpoint,
                    "satadj_pcond_endpoint_resolution_scale": satadj_pcond_bound,
                    "satadj_pcond_status": satadj_pcond_status,
                    "satadj_directional_evidence": satadj_cmp,
                    "same_tapped_topology": same_topology,
                })
            finally:
                if hp is not None:
                    hp.close()
                if hm is not None:
                    hm.close()
        return {
            "status": ("verified_local_state_update_identity"
                        if float(residual.detach().abs().max()) < 1.0e-8 and all(
                            row["same_tapped_topology"]
                            and row["sensible_relative_error"] < 1.0e-8
                            and row["latent_and_amount_relative_error"] < 1.0e-8
                            for row in fd_rows)
                        else "unresolved_local_identity"),
            "residual_j_kg": float(residual.detach().reshape(-1)[0]),
            "residual_max_abs_j_kg": float(residual.detach().abs().max()),
            "satadj_identity_max_abs_j_kg": float(satadj_identity.detach().abs().max()),
            "qv_direction": {
                "relative_size": 0.1, "sensible_ad_j_kg": ad_sensible,
                "latent_and_amount_ad_j_kg": ad_latent,
                "satadj_latent_ad_j_kg": ad_satadj,
                "satadj_formula_ad_j_kg": ad_satadj_formula,
                "satadj_pcond_ad_j_kg": ad_satadj_pcond, "fd": fd_rows,
                "satadj_pcond_status": ("verified" if all(
                    row["satadj_pcond_status"] == "verified" for row in fd_rows)
                    else "insufficient_resolution" if any(
                        row["satadj_pcond_status"] == "insufficient_resolution" for row in fd_rows)
                    else "unresolved_numeric"),
            },
            "ad_operands_requires_grad": {
                name: bool(value.requires_grad)
                for name, value in ad_trace.by_name("state_update")[0].operands.items()
            },
            "operands": {name: {"shape": list(value.shape), "max_abs": float(value.detach().abs().max())}
                         for name, value in record.operands.items()},
            "scope": "local state_update before satadj/cleanup/DSD; fixed forcing; not full column enthalpy",
            "missing_full_budget": ["satadj pcond ledger across all subcycles/full column",
                                    "sedimentation enthalpy outflow", "external forcing energy convention"],
            "resolved_direction": resolved_warm_qv_probe(),
        }
    finally:
        ad_handle.close()


def main(out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run_probe(), indent=2) + "\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    main(args.out)
