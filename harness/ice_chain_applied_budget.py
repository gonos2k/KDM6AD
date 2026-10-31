"""Analysis-only paired QI/NI capture at the actual ice-chain injection point.

Pass an ``IceChainAppliedCapture`` as ``ice_substep_fn`` to
``sedimentation_chain_torch``. It calls the legacy ice substep exactly once per
invocation, forwarding any incoming mass ledger and adding a fresh per-call
QI mass ledger plus the separate NI applied-amount ledger. No speed or state
is recomputed by this wrapper.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch

from oracle.kdm6.ice_number_budget import IceNumberAppliedLedger, IceNumberSubstepRecord
from oracle.kdm6.sedimentation import ice_substep_advection_torch
from oracle.kdm6.water_budget import SedimentationAttribution, SedimentationLedger


class _MassLedgerFanout:
    def __init__(self, local: SedimentationLedger, upstream):
        self.local = local
        self.upstream = upstream

    def record(self, *args, **kwargs):
        self.local.record(*args, **kwargs)
        if self.upstream is not None:
            self.upstream.record(*args, **kwargs)


@dataclass(frozen=True)
class IceChainSubstepWitness:
    n_current: int
    qi_before: torch.Tensor
    qi_after: torch.Tensor
    work1_qi: torch.Tensor          # exact mass-speed operand passed to the substep
    workn_qi: torch.Tensor          # exact number-speed operand passed to the substep
    qi_applied_out_mass: torch.Tensor  # (B,K), dend*dz weighted actual QI departure
    qi_applied_in_mass: torch.Tensor   # (B,K), dend*dz weighted actual QI arrival
    qi_projection_mass: torch.Tensor   # (B,K), dend*dz weighted QI zero-floor addition
    mass: SedimentationAttribution  # this call's QI mass ledger; dend*dz basis
    number: IceNumberSubstepRecord  # this call's NI raw-coordinate operands


class IceChainAppliedCapture:
    """Single-use chain observer; create a fresh instance for each evaluation."""

    def __init__(self):
        self.number_ledger = IceNumberAppliedLedger()
        self.records: list[IceChainSubstepWitness] = []

    def __call__(self, state, fall_qi_in, fall_ni_in, work1_qi, workn_qi,
                 delz, dend, *, mstep, mstep_col, n_current, dtcld, params,
                 ledger=None):
        with torch.no_grad():
            qi_before = state.qi.detach().clone()
            mass_speed = work1_qi.detach().clone()
            number_speed = workn_qi.detach().clone()
        local_mass = SedimentationLedger()
        before_count = len(self.number_ledger.records)
        result = ice_substep_advection_torch(
            state, fall_qi_in, fall_ni_in, work1_qi, workn_qi, delz, dend,
            mstep=mstep, mstep_col=mstep_col, n_current=n_current,
            dtcld=dtcld, params=params,
            ledger=_MassLedgerFanout(local_mass, ledger),
            number_ledger=self.number_ledger,
        )
        if len(self.number_ledger.records) != before_count + 1:
            raise ValueError("ice substep did not produce exactly one NI record")
        if set(local_mass._acc) != {"qi"}:
            raise ValueError("ice substep did not produce exactly one QI mass species")
        with torch.no_grad():
            qi_after = result.state.qi.detach().clone()
            qi_terms = local_mass._acc["qi"]
            qi_out = qi_terms["out"].detach().clone()
            qi_in = qi_terms["in"].detach().clone()
            qi_projection = qi_terms["proj"].detach().clone()
        self.records.append(IceChainSubstepWitness(
            n_current=int(n_current), qi_before=qi_before, qi_after=qi_after,
            work1_qi=mass_speed, workn_qi=number_speed,
            qi_applied_out_mass=qi_out, qi_applied_in_mass=qi_in,
            qi_projection_mass=qi_projection,
            mass=local_mass.finalize(like=state.qi),
            number=self.number_ledger.records[-1],
        ))
        return result
