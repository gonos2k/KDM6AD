"""P0-4b.1 — conservative counterfactual sedimentation (ANALYSIS-ONLY experiment).

``conservative_experiment`` variant of the NISLFV-PLM substep: each lower cell
receives the mass ACTUALLY removed from its source cell (the entry-capped
outflow, mass-converted), instead of the legacy rule that re-caps the stored
raw ``falk`` flux by the source's already-depleted POST-update reservoir. The
fall accumulators carry actual-outflow rates, so the chain-end surface
accumulation reports the actual bottom outflow.

This module is deliberately NOT wired into the default runtime, the legacy
oracle path, or the C++/Fortran ports (``legacy_reference`` stays byte-identical
— torch.equal-asserted in tests). Entry: ``kdm6_step_conservative_experiment``.

Conservation: uncapped, the legacy interface is already exactly conservative;
the conservative rule additionally makes the capped regime conservative:
    mass out of cell k−1  =  ρ_{k−1}Δz_{k−1}·dq_out_{k−1}
    mass into  cell k     =  ρ_kΔz_k·dq_in_k  =  the same quantity
so W_post − W_pre + P_actual = O(ε64) per column, no positivity clamp needed
(q − dq_out ≥ 0 by the entry cap; inflow is nonnegative).
"""
from __future__ import annotations

import torch

from .sedimentation import (
    SubstepAdvectionState, SubstepAdvectionOutputs,
    IceSubstepState, IceSubstepOutputs,
    SubstepAdvectionParams, _SubstepCapture,
)


def _mstep_gate(mstep, mstep_col, n_current, dend):
    if mstep_col is not None:
        mstep_col_safe = torch.clamp(mstep_col.to(dend.dtype), min=1.0)
        gate = (mstep_col_safe >= float(n_current)).to(dend.dtype)
    else:
        mstep_col_safe = float(mstep)
        gate = 1.0
    return mstep_col_safe, gate


def conservative_substep_advection_torch(
    state: SubstepAdvectionState,
    fall_qr_in, fall_nr_in, fall_qs_in, fall_qg_in, fall_brs_in,
    work1_qr, workn_qr, work1_qs, work1_qg,
    delz, dend, *,
    mstep: int = 1, mstep_col=None, n_current: int = 1,
    dtcld: float, params: SubstepAdvectionParams,
    ledger=None,
) -> SubstepAdvectionOutputs:
    """Conservative counterfactual of ``substep_advection_torch`` (same signature)."""
    K = state.qr.shape[-1]
    dend_safe = torch.clamp(dend, min=params.qcrmin)
    delz_safe = torch.clamp(delz, min=params.qcrmin)
    mstep_col_safe, gate = _mstep_gate(mstep, mstep_col, n_current, dend)

    cols = {s: [getattr(state, s)[:, k] for k in range(K)] for s in ("qr", "nr", "qs", "qg", "brs")}
    fall = {"qr": [fall_qr_in[:, k] for k in range(K)], "nr": [fall_nr_in[:, k] for k in range(K)],
            "qs": [fall_qs_in[:, k] for k in range(K)], "qg": [fall_qg_in[:, k] for k in range(K)],
            "brs": [fall_brs_in[:, k] for k in range(K)]}
    w1 = {"qr": work1_qr, "qs": work1_qs, "qg": work1_qg, "brs": work1_qg}

    _cap = _SubstepCapture(("qr", "qs", "qg")) if ledger is not None else None
    # previous cell's ACTUAL outflow (mixing ratio) per species — the conserved transfer
    prev_out = {}

    for k in range(K):
        for s in ("qr", "qs", "qg", "brs"):
            falk = dend[:, k] * cols[s][k] * w1[s][:, k] / mstep_col_safe * gate
            dq_out = torch.minimum(falk * dtcld / dend_safe[:, k], cols[s][k])
            # actual-outflow RATE into the fall accumulator (chain-end surface
            # accumulation then reports the actual bottom outflow)
            fall[s][k] = fall[s][k] + dq_out * dend_safe[:, k] / dtcld
            if k == 0:
                dq_in = torch.zeros_like(dq_out)
            else:
                # mass-conserving transfer of the source cell's actual outflow
                dq_in = prev_out[s] * (dend_safe[:, k - 1] * delz[:, k - 1]) \
                    / (dend_safe[:, k] * delz_safe[:, k])
            if _cap is not None and s != "brs":
                if k == 0:
                    _cap.top(s, cols[s][k], dq_out)
                else:
                    _cap.interior(s, cols[s][k], dq_out, dq_in,
                                  falk * dtcld / dend_safe[:, k], dq_in, dq_in)
            cols[s][k] = cols[s][k] - dq_out + dq_in
            prev_out[s] = dq_out
        # numbers (nr): legacy's implied Δz-only measure, actual transfer
        falk_nr = cols["nr"][k] * workn_qr[:, k] / mstep_col_safe * gate
        dn_out = torch.minimum(falk_nr * dtcld, cols["nr"][k])
        fall["nr"][k] = fall["nr"][k] + dn_out / dtcld
        dn_in = torch.zeros_like(dn_out) if k == 0 else \
            prev_out["nr"] * delz[:, k - 1] / delz_safe[:, k]
        cols["nr"][k] = cols["nr"][k] - dn_out + dn_in
        prev_out["nr"] = dn_out

    stacked = {s: torch.stack(cols[s], dim=-1) for s in cols}
    if _cap is not None:
        _cap.commit(
            ledger,
            weight=(dend * delz).detach(),
            delz_bottom=delz[:, -1],
            dtcld=dtcld,
            # actual-outflow rate at bottom → diag = actual bottom outflow mass
            falk_bottom={s: (prev_out[s] * dend_safe[:, -1] / dtcld) for s in ("qr", "qs", "qg")},
            entry_state={s: getattr(state, s) for s in ("qr", "qs", "qg")},
            post_state={s: stacked[s] for s in ("qr", "qs", "qg")},
        )
    return SubstepAdvectionOutputs(
        state=SubstepAdvectionState(qr=stacked["qr"], nr=stacked["nr"], qs=stacked["qs"],
                                    qg=stacked["qg"], brs=stacked["brs"]),
        fall_qr=torch.stack(fall["qr"], dim=-1), fall_nr=torch.stack(fall["nr"], dim=-1),
        fall_qs=torch.stack(fall["qs"], dim=-1), fall_qg=torch.stack(fall["qg"], dim=-1),
        fall_brs=torch.stack(fall["brs"], dim=-1),
    )


def conservative_ice_substep_advection_torch(
    state: IceSubstepState, fall_qi_in, fall_ni_in,
    work1_qi, workn_qi, delz, dend, *,
    mstep: int = 1, mstep_col=None, n_current: int = 1,
    dtcld: float, params: SubstepAdvectionParams,
    ledger=None,
) -> IceSubstepOutputs:
    """Conservative counterfactual of ``ice_substep_advection_torch``."""
    K = state.qi.shape[-1]
    dend_safe = torch.clamp(dend, min=params.qcrmin)
    delz_safe = torch.clamp(delz, min=params.qcrmin)
    mstep_col_safe, gate = _mstep_gate(mstep, mstep_col, n_current, dend)

    qi_cols = [state.qi[:, k] for k in range(K)]
    ni_cols = [state.ni[:, k] for k in range(K)]
    fall_qi = [fall_qi_in[:, k] for k in range(K)]
    fall_ni = [fall_ni_in[:, k] for k in range(K)]
    _cap = _SubstepCapture(("qi",)) if ledger is not None else None
    prev_qi = prev_ni = None

    for k in range(K):
        falk_qi = dend[:, k] * qi_cols[k] * work1_qi[:, k] / mstep_col_safe * gate
        falk_ni = ni_cols[k] * workn_qi[:, k] / mstep_col_safe * gate
        dqi_out = torch.minimum(falk_qi * dtcld / dend_safe[:, k], qi_cols[k])
        dni_out = torch.minimum(falk_ni * dtcld, ni_cols[k])
        fall_qi[k] = fall_qi[k] + dqi_out * dend_safe[:, k] / dtcld
        fall_ni[k] = fall_ni[k] + dni_out / dtcld
        dqi_in = torch.zeros_like(dqi_out) if k == 0 else \
            prev_qi * (dend_safe[:, k - 1] * delz[:, k - 1]) / (dend_safe[:, k] * delz_safe[:, k])
        dni_in = torch.zeros_like(dni_out) if k == 0 else \
            prev_ni * delz[:, k - 1] / delz_safe[:, k]
        if _cap is not None:
            if k == 0:
                _cap.top("qi", qi_cols[k], dqi_out)
            else:
                _cap.interior("qi", qi_cols[k], dqi_out, dqi_in,
                              falk_qi * dtcld / dend_safe[:, k], dqi_in, dqi_in)
        qi_cols[k] = qi_cols[k] - dqi_out + dqi_in
        ni_cols[k] = ni_cols[k] - dni_out + dni_in
        prev_qi, prev_ni = dqi_out, dni_out

    qi_stacked = torch.stack(qi_cols, dim=-1)
    if _cap is not None:
        _cap.commit(
            ledger, weight=(dend * delz).detach(), delz_bottom=delz[:, -1], dtcld=dtcld,
            falk_bottom={"qi": prev_qi * dend_safe[:, -1] / dtcld},
            entry_state={"qi": state.qi}, post_state={"qi": qi_stacked},
        )
    return IceSubstepOutputs(
        state=IceSubstepState(qi=qi_stacked, ni=torch.stack(ni_cols, dim=-1)),
        fall_qi=torch.stack(fall_qi, dim=-1), fall_ni=torch.stack(fall_ni, dim=-1),
    )


CONSERVATIVE_SED_FNS = (conservative_substep_advection_torch,
                        conservative_ice_substep_advection_torch)


def kdm6_step_conservative_experiment(
    state, forcing, params=None, dt: float = 60.0, *,
    xland=None, ncmin_land: float = 0.0, ncmin_sea: float = 0.0, controls=None,
):
    """Run one step with the CONSERVATIVE sedimentation experiment (explicit
    opt-in; the default kdm6_step path is untouched). Returns
    ``(State, ColumnWaterBudget, SedimentationAttribution)`` — under this
    variant the budget must close as W_out − W_in + P_actual = O(ε64)."""
    from .water_budget import SedimentationLedger, _run_with_budget

    sed = SedimentationLedger()
    out, budget = _run_with_budget(state, forcing, params, dt, xland=xland,
                                   ncmin_land=ncmin_land, ncmin_sea=ncmin_sea,
                                   controls=controls, sed_ledger=sed,
                                   sed_substep_fns=CONSERVATIVE_SED_FNS)
    return out, budget, sed.finalize(like=state.qr if dt <= 0.0 else None)
