"""Opt-in applied NI sedimentation ledger in the kernel's raw number coordinate.

The ice substep uses NI without a density conversion. Its native-coordinate
column measure is NI*dz; a dry-mass-specific interpretation instead requires
an explicitly supplied dry density and remains conditional on the host/kernel
unit contract. Neither measure is called physically conserved by this ledger.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch


@dataclass(frozen=True)
class IceNumberSubstepRecord:
    before: torch.Tensor                   # (B,K), native NI value at substep entry
    after: torch.Tensor                    # (B,K), actual post-substep NI
    candidate_out: torch.Tensor            # (B,K), uncapped local fall subtraction
    applied_out: torch.Tensor              # (B,K), amount used in the state update
    candidate_in: torch.Tensor             # (B,K), stored-falk incoming candidate
    applied_in: torch.Tensor               # (B,K), post-above-reservoir-capped arrival
    projection: torch.Tensor               # (B,K), clamp-to-zero addition
    fall_before: torch.Tensor              # (B,K), raw fall accumulator at entry
    fall_after: torch.Tensor               # (B,K), raw fall accumulator at exit
    delz: torch.Tensor                     # (B,K), layer thickness
    dend: torch.Tensor                     # (B,K), supplied mass density; NI path does not use it
    gate: torch.Tensor                     # (B,), actual substep activity gate
    mstep_divisor: torch.Tensor            # (B,), actual divisor
    outflow_cap: torch.Tensor              # (B,K), candidate reduced to entry reservoir
    inflow_cap: torch.Tensor               # (B,K), candidate reduced to above post-state
    projection_active: torch.Tensor        # (B,K), clamp-to-zero changed the state
    dtcld: float
    n_current: int


@dataclass(frozen=True)
class IceNumberSubstepBalance:
    column_loss: torch.Tensor              # (B,), weighted before-after
    bottom_applied_out: torch.Tensor       # (B,), weighted actual bottom departure
    interface_difference: torch.Tensor     # (B,K-1), above out minus below in
    projection: torch.Tensor               # (B,), weighted clamp addition
    attributed_loss: torch.Tensor          # (B,), bottom + interfaces - projection
    closure_residual: torch.Tensor         # (B,), state loss minus attributed loss
    bottom_raw_fall_candidate: torch.Tensor  # (B,), bottom candidate_out*dz, NOT surface output
    bottom_accumulator_delta: torch.Tensor   # (B,), rounded fall_after-fall_before*dz*dt
    weight_coordinate: str


class IceNumberAppliedLedger:
    """Collect detached, unmodified operands from direct ice substep calls."""

    def __init__(self):
        self.records: list[IceNumberSubstepRecord] = []

    def record(self, *, before, after, candidate_out, applied_out,
               candidate_in, applied_in, projection, fall_before, fall_after,
               delz, dend, gate, mstep_divisor, dtcld, n_current):
        shape = before.shape
        if len(shape) != 2 or min(shape) < 1:
            raise ValueError("NI record needs a nonempty (B,K) column")
        fields = (after, candidate_out, applied_out, candidate_in, applied_in,
                  projection, fall_before, fall_after, delz, dend)
        if any(x.shape != shape or x.dtype != before.dtype or x.device != before.device
               for x in fields):
            raise ValueError("NI record fields must match the entry column")
        if gate.shape != (shape[0],) or mstep_divisor.shape != (shape[0],):
            raise ValueError("NI gate/divisor must have one value per column")
        with torch.no_grad():
            copied = [x.detach().clone() for x in (before, *fields, gate, mstep_divisor)]
            (before_copy, after_copy, candidate_out_copy, applied_out_copy,
             candidate_in_copy, applied_in_copy, projection_copy,
             fall_before_copy, fall_after_copy, delz_copy, dend_copy,
             gate_copy, divisor_copy) = copied
        self.records.append(IceNumberSubstepRecord(
            before=before_copy, after=after_copy,
            candidate_out=candidate_out_copy, applied_out=applied_out_copy,
            candidate_in=candidate_in_copy, applied_in=applied_in_copy,
            projection=projection_copy,
            fall_before=fall_before_copy, fall_after=fall_after_copy,
            delz=delz_copy, dend=dend_copy, gate=gate_copy,
            mstep_divisor=divisor_copy,
            outflow_cap=candidate_out_copy > applied_out_copy,
            inflow_cap=candidate_in_copy > applied_in_copy,
            projection_active=projection_copy > 0,
            dtcld=float(dtcld), n_current=int(n_current)))


def summarize_ice_number_substep(record: IceNumberSubstepRecord, *,
                                 dry_density: torch.Tensor | None = None) -> IceNumberSubstepBalance:
    """Summarize one record in dz or explicitly selected rho_d*dz coordinates.

    A small residual checks the decomposition. A nonzero interface difference
    is reported, not silently treated as conserved transfer. The optional
    dry-density measure is a conditional host interpretation, not the supplied
    KDM ``dend`` (which can be moist density).
    """
    if not isinstance(record, IceNumberSubstepRecord):
        raise TypeError("expected an IceNumberSubstepRecord")
    if dry_density is not None:
        if (dry_density.shape != record.before.shape or
                dry_density.dtype != record.before.dtype or
                dry_density.device != record.before.device or
                not bool(torch.isfinite(dry_density).all()) or
                not bool((dry_density > 0).all())):
            raise ValueError("explicit dry density must be finite, positive and column-shaped")
    with torch.no_grad():
        weight = record.delz if dry_density is None else dry_density.detach() * record.delz
        weight = weight.detach()
        loss = (weight * (record.before - record.after)).sum(dim=-1)
        bottom = weight[:, -1] * record.applied_out[:, -1]
        interface = (weight[:, :-1] * record.applied_out[:, :-1] -
                     weight[:, 1:] * record.applied_in[:, 1:])
        projection = (weight * record.projection).sum(dim=-1)
        attributed = bottom + interface.sum(dim=-1) - projection
        raw_bottom = record.candidate_out[:, -1] * record.delz[:, -1]
        accumulator_delta = ((record.fall_after[:, -1] - record.fall_before[:, -1]) *
                             record.delz[:, -1] * record.dtcld)
        return IceNumberSubstepBalance(
            column_loss=loss, bottom_applied_out=bottom,
            interface_difference=interface, projection=projection,
            attributed_loss=attributed, closure_residual=loss - attributed,
            bottom_raw_fall_candidate=raw_bottom,
            bottom_accumulator_delta=accumulator_delta,
            weight_coordinate="dz" if dry_density is None else "rho_d*dz",
        )
