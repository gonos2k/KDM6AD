"""Audit an ordered chain of isolated, *applied* phase transfers.

The caller fixes the stage/owner plan from the executed source path, not from
received records. Within one stage, X1's shared-reservoir check applies to all
transfers. The next stage must consume the exact preceding stored state. This
does not generate process rates or certify a full thermodynamic state law.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from collections.abc import Mapping

import numpy as np

from phase_transfer_contract import PhaseBudget, PhaseTransfer, check_phase_budget


MASS_ATOL = 1e-14
HEAT_ATOL_J_PER_KG = 1e-8


def _contains_bool(value: object) -> bool:
    """Inspect raw lists before NumPy turns mixed bool/number input into floats."""
    if isinstance(value, (bool, np.bool_)):
        return True
    if isinstance(value, np.ndarray):
        return value.dtype.kind == "b" or (value.dtype.kind == "O"
                                           and any(_contains_bool(x) for x in value.flat))
    if isinstance(value, (list, tuple)):
        return any(_contains_bool(x) for x in value)
    return False


@dataclass(frozen=True)
class PhaseState:
    reservoirs: Mapping[str, np.ndarray]
    temperature: np.ndarray


@dataclass(frozen=True)
class PlannedStage:
    stage_id: str
    owner: str
    transfer_paths: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class AppliedStage:
    stage_id: str
    owner: str
    before: PhaseState
    after: PhaseState
    heat_capacity_j_per_kg_k: np.ndarray
    transfers: tuple[PhaseTransfer, ...]


@dataclass(frozen=True)
class SequenceBudget:
    stage_budgets: tuple[tuple[str, PhaseBudget], ...]
    stage_ids: tuple[str, ...]


def _numeric_array(value: object, label: str) -> np.ndarray:
    if np.ma.isMaskedArray(value):
        raise ValueError(f"{label} cannot be a masked array")
    if _contains_bool(value):
        raise ValueError(f"{label} cannot contain boolean masks")
    array = np.asarray(value)
    if array.dtype.kind not in "fiu" or array.size == 0:
        raise ValueError(f"{label} must be a nonempty real numeric array")
    if not np.isfinite(array).all():
        raise ValueError(f"{label} must be finite")
    return array


def _same_state(expected: PhaseState, actual: PhaseState, label: str) -> None:
    if not isinstance(expected, PhaseState) or not isinstance(actual, PhaseState):
        raise ValueError(f"{label} needs declared phase states")
    if not expected.reservoirs or set(expected.reservoirs) != set(actual.reservoirs):
        raise ValueError(f"{label} reservoir set differs")
    for name in expected.reservoirs:
        a = _numeric_array(expected.reservoirs[name], f"{label} expected {name}")
        b = _numeric_array(actual.reservoirs[name], f"{label} actual {name}")
        if a.shape != b.shape or not np.array_equal(a, b):
            raise ValueError(f"{label} changed reservoir {name} between stages")
    a = _numeric_array(expected.temperature, f"{label} expected temperature")
    b = _numeric_array(actual.temperature, f"{label} actual temperature")
    if a.shape != b.shape or not np.array_equal(a, b):
        raise ValueError(f"{label} changed temperature between stages")


def check_phase_sequence(
    plan: tuple[PlannedStage, ...],
    stages: tuple[AppliedStage, ...],
    initial: PhaseState,
    final: PhaseState,
) -> SequenceBudget:
    """Check every intermediate state and the independent stage schedule.

    Exact equality at stage handoffs compares the published numerical state,
    rather than applying a second tolerance that could hide a missing update.
    This bounded f64 pilot fixes X1's default mass/heat tolerances *inside*
    each stage. A different precision or mass basis needs a separately
    declared verification contract rather than a caller-relaxed threshold.
    """
    if (not isinstance(plan, tuple) or not plan
            or not isinstance(stages, tuple) or len(stages) != len(plan)):
        raise ValueError("stage records must exactly match a nonempty independent plan")
    if any(not isinstance(p, PlannedStage)
           or not isinstance(p.stage_id, str) or not p.stage_id
           or not isinstance(p.owner, str) or not p.owner for p in plan):
        raise ValueError("plan needs named stages and owners")
    if len({p.stage_id for p in plan}) != len(plan):
        raise ValueError("planned stage IDs must be unique")
    for planned in plan:
        paths = planned.transfer_paths
        if (not isinstance(paths, tuple) or not paths
                or any(not isinstance(path, tuple) or len(path) != 3
                       or any(not isinstance(part, str) or not part for part in path)
                       or path[1] == path[2] for path in paths)
                or len({path[0] for path in paths}) != len(paths)):
            raise ValueError("plan needs unique named source/destination transfer paths")

    preceding = initial
    results: list[tuple[str, PhaseBudget]] = []
    for expected, stage in zip(plan, stages):
        if (not isinstance(stage, AppliedStage) or stage.stage_id != expected.stage_id
                or stage.owner != expected.owner):
            raise ValueError("stage order or owning process differs from plan")
        _same_state(preceding, stage.before, f"{stage.stage_id} handoff")
        if (not isinstance(stage.transfers, tuple) or not stage.transfers
                or any(not isinstance(t, PhaseTransfer) for t in stage.transfers)):
            raise ValueError(f"{stage.stage_id} needs applied phase transfers")
        names = [t.name for t in stage.transfers]
        if len(set(names)) != len(names):
            raise ValueError(f"{stage.stage_id} transfer names must be unique")
        actual_paths = {(t.name, t.source, t.destination) for t in stage.transfers}
        if actual_paths != set(expected.transfer_paths):
            raise ValueError(f"{stage.stage_id} transfer set differs from independent plan")
        _numeric_array(stage.heat_capacity_j_per_kg_k, f"{stage.stage_id} heat capacity")
        for transfer in stage.transfers:
            _numeric_array(transfer.requested, f"{stage.stage_id}/{transfer.name} request")
            _numeric_array(transfer.applied, f"{stage.stage_id}/{transfer.name} applied")
            if (isinstance(transfer.heat_j_per_kg, bool)
                    or not isinstance(transfer.heat_j_per_kg, Real)):
                raise ValueError(f"{stage.stage_id}/{transfer.name} needs real latent heat")
        budget = check_phase_budget(
            stage.before.reservoirs, stage.after.reservoirs,
            stage.before.temperature, stage.after.temperature,
            stage.heat_capacity_j_per_kg_k, stage.transfers,
            mass_atol=MASS_ATOL, heat_atol_j_per_kg=HEAT_ATOL_J_PER_KG,
        )
        results.append((stage.stage_id, budget))
        preceding = stage.after
    _same_state(preceding, final, "final handoff")
    return SequenceBudget(tuple(results), tuple(p.stage_id for p in plan))
