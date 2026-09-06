"""Check the captured pre-satadj local thermal identity."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch

from kdm6 import constants as c
from kdm6 import melt_freeze as mf
from kdm6.process_attribution import cold_fixture
from kdm6.runtime import kdm6_step
from kdm6.sensitivity_diagnostics import SensitivityTrace, _directional_values


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
        # Directional check: qv is perturbed positively, so both endpoints stay
        # in the admissible state domain.  Compare the same scalar terms at the
        # same first coordinator step, independently by central FD.
        sensible_ad_term, latent_ad_term = local_terms(ad_trace)
        direction = type(state)(*(0.1 * state.qv if name == "qv" else torch.zeros_like(value)
                                  for name, value in zip(state._fields, state)))
        ad_sensible = float(_directional_values(sensible_ad_term, leaves, direction).detach().reshape(-1)[0])
        ad_latent = float(_directional_values(latent_ad_term, leaves, direction).detach().reshape(-1)[0])
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
                fd_sensible = float(((sp - sm) / (2.0 * epsilon)).detach().reshape(-1)[0])
                fd_latent = float(((lp - lm) / (2.0 * epsilon)).detach().reshape(-1)[0])
                same_topology = tp.signature() == tm.signature() == ad_trace.signature() and tp.subcycles == tm.subcycles == ad_trace.subcycles
                fd_rows.append({
                    "epsilon": epsilon, "sensible_fd_j_kg": fd_sensible,
                    "latent_and_amount_fd_j_kg": fd_latent,
                    "sensible_relative_error": _relative_error(fd_sensible, ad_sensible),
                    "latent_and_amount_relative_error": _relative_error(fd_latent, ad_latent),
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
            "qv_direction": {
                "relative_size": 0.1, "sensible_ad_j_kg": ad_sensible,
                "latent_and_amount_ad_j_kg": ad_latent, "fd": fd_rows,
            },
            "ad_operands_requires_grad": {
                name: bool(value.requires_grad)
                for name, value in ad_trace.by_name("state_update")[0].operands.items()
            },
            "operands": {name: {"shape": list(value.shape), "max_abs": float(value.detach().abs().max())}
                         for name, value in record.operands.items()},
            "scope": "local state_update before satadj/cleanup/DSD; fixed forcing; not full column enthalpy",
            "missing_full_budget": ["satadj pcond latent ledger", "sedimentation enthalpy outflow", "external forcing energy convention"],
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
