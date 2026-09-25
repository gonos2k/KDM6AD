#!/usr/bin/env python3
"""Bounded final-RK shadow candidate for a donor-wide face correction backoff.

This prototype reuses the captured G2 face and RK operands. It does not edit
host source, reconstruct high-order stencils, or claim a physical number budget.
Only the donor's already-limited high-minus-low correction faces are backed off;
the low-order faces stay fixed. A shared face is written once and copied into
both adjacent cell divergences before replaying the observed f32/FMA store.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from fractions import Fraction

from replay_native_number import f32
from replay_negative_number_trace import rk_value
from replay_number_face_flux import divergence_stores


@dataclass(frozen=True)
class Cell:
    """One scalar cell's captured faces, metrics, and final-RK operands."""

    high: tuple[float, float, float, float, float, float]
    low: tuple[float, float, float, float, float, float]
    initial_tendency: float
    rdzw: float
    msftx: float
    rdx: float
    rdy: float
    rk: dict[str, float | int]


@dataclass(frozen=True)
class SharedFace:
    donor: int
    donor_slot: int
    receiver: int
    receiver_slot: int


@dataclass(frozen=True)
class BackoffResult:
    accepted: bool
    reason: str
    factor: float | None
    before: tuple[float, ...]
    after: tuple[float, ...]
    high_faces: tuple[tuple[float, ...], ...] | None


# xL, xR, yS, yN, zB, zT. The z orientation follows module_advect_em.F:
# increasing k points down in mass coordinates, so the signs reverse there.
_OUTGOING = (lambda q: q < 0, lambda q: q > 0,
             lambda q: q < 0, lambda q: q > 0,
             lambda q: q < 0, lambda q: q > 0)


def _bits(value: float) -> int:
    return struct.unpack("I", struct.pack("f", value))[0]


def _from_bits(value: int) -> float:
    return struct.unpack("f", struct.pack("I", value))[0]


def _stored(cell: Cell, high: tuple[float, ...]) -> float:
    zxy = divergence_stores(
        cell.initial_tendency,
        high,
        cell.low,
        cell.rdzw,
        cell.msftx,
        cell.rdx,
        cell.rdy,
    )
    operands = dict(cell.rk)
    operands["advect_tend"] = zxy[-1]
    return rk_value(operands)


def _face_numerator_contribution(cell: Cell, slot: int, delta: float) -> Fraction:
    """Exact pre-rounding RK-numerator change from one stored face delta."""
    horizontal_metric = Fraction(cell.msftx) * Fraction(cell.rdx if slot < 2 else cell.rdy)
    vertical_metric = Fraction(cell.rdzw)
    # Signs follow -div(F): left/south and bottom face terms enter positively;
    # right/north and top face terms enter negatively in their coordinate form.
    sign = (1, -1, 1, -1, -1, 1)[slot]
    metric = vertical_metric if slot >= 4 else horizontal_metric
    return (
        sign
        * Fraction(cell.rk["dt"])
        * Fraction(cell.rk["msfty"])
        * metric
        * Fraction(delta)
    )


def _validate_topology(cells: tuple[Cell, ...], shared: tuple[SharedFace, ...]) -> None:
    if not 2 <= len(cells) <= 7:
        raise ValueError("prototype accepts two to seven cells")
    seen: set[tuple[int, int]] = set()
    opposite = {0: 1, 1: 0, 2: 3, 3: 2, 4: 5, 5: 4}
    for face in shared:
        if not (0 <= face.donor < len(cells) and 0 <= face.receiver < len(cells)):
            raise ValueError("shared face references a missing cell")
        if face.donor == face.receiver or not (0 <= face.donor_slot < 6 and 0 <= face.receiver_slot < 6):
            raise ValueError("invalid shared face")
        if opposite[face.donor_slot] != face.receiver_slot:
            raise ValueError("shared face must map to the opposite cell side")
        for cell_slot in ((face.donor, face.donor_slot), (face.receiver, face.receiver_slot)):
            if cell_slot in seen:
                raise ValueError("a cell face may have only one owner")
            seen.add(cell_slot)
        if cells[face.donor].high[face.donor_slot] != cells[face.receiver].high[face.receiver_slot]:
            raise ValueError("shared high correction must start from one stored value")
        if cells[face.donor].low[face.donor_slot] != cells[face.receiver].low[face.receiver_slot]:
            raise ValueError("shared low-order face must start from one stored value")
        if (_face_numerator_contribution(cells[face.donor], face.donor_slot, 1.0)
                + _face_numerator_contribution(cells[face.receiver], face.receiver_slot, 1.0)
                != 0):
            raise ValueError("shared face has incompatible metric-weighted RK exchange")


def backoff_donor(
    cells: tuple[Cell, ...],
    shared: tuple[SharedFace, ...],
    donor: int,
) -> BackoffResult:
    """Find the least donor-wide correction reduction that passes final RK.

    The factor is searched over binary32 values in [0, 1]. A candidate is
    accepted only when the source-ordered, fused final-RK result is nonnegative
    for the donor and every cell connected by a modified shared face. If the
    donor cannot pass at zero correction, or a receiver loses admissibility,
    the candidate fails closed. This is a small-neighborhood research prototype,
    not a grid solver or a production guarantee. Every changed outgoing face
    must have a registered receiver; an unpaired face cannot be treated as a
    conservative internal exchange.
    """
    _validate_topology(cells, shared)
    if not 0 <= donor < len(cells):
        raise ValueError("donor index is outside the cell set")

    owner = cells[donor]
    before = tuple(_stored(cell, cell.high) for cell in cells)
    if before[donor] >= 0:
        return BackoffResult(True, "already_nonnegative", 1.0, before, before, None)

    pairs_by_slot = {
        face.donor_slot: face for face in shared if face.donor == donor
    }
    outgoing = tuple(
        slot for slot, sign in enumerate(_OUTGOING) if sign(owner.high[slot])
    )
    if not outgoing:
        return BackoffResult(False, "no_outgoing_correction", None, before, before, None)
    if any(slot not in pairs_by_slot for slot in outgoing):
        return BackoffResult(False, "unpaired_outgoing_face", None, before, before, None)

    def evaluate(factor: float) -> tuple[tuple[float, ...], tuple[tuple[float, ...], ...]]:
        high = [list(cell.high) for cell in cells]
        for slot in outgoing:
            high[donor][slot] = f32(owner.high[slot] * factor)
            face = pairs_by_slot.get(slot)
            if face is not None:
                high[face.receiver][face.receiver_slot] = high[donor][slot]
        frozen = tuple(tuple(row) for row in high)
        return tuple(_stored(cell, frozen[i]) for i, cell in enumerate(cells)), frozen

    zero_state, _ = evaluate(0.0)
    if zero_state[donor] < 0:
        return BackoffResult(False, "low_order_or_source_budget_negative", None, before, zero_state, None)

    # Binary search ordered nonnegative binary32 values. The donor's accepted
    # store is monotone over this bounded limiter family for the captured cases;
    # the final candidate is checked against every connected receiver below.
    lo, hi = _bits(0.0), _bits(1.0)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        value = _from_bits(mid)
        states, _ = evaluate(value)
        if states[donor] >= 0:
            lo = mid
        else:
            hi = mid

    factor = _from_bits(lo)
    after, high = evaluate(factor)
    if factor <= 0:
        return BackoffResult(False, "no_positive_factor", None, before, after, None)
    if after[donor] < 0:
        return BackoffResult(False, "source_ordered_donor_still_negative", factor, before, after, None)
    connected = {donor}
    for face in shared:
        if face.donor == donor:
            connected.add(face.receiver)
    if any(after[index] < 0 for index in connected):
        return BackoffResult(False, "connected_receiver_budget_negative", factor, before, after, None)
    if _bits(factor) + 1 < _bits(1.0):
        next_state, _ = evaluate(_from_bits(_bits(factor) + 1))
        if next_state[donor] >= 0:
            return BackoffResult(False, "factor_search_not_maximal", factor, before, after, None)
    return BackoffResult(True, "backed_off", factor, before, after, high)
