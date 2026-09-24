"""Stage-aware validity audit; no host update or blanket clipping policy.

An independent plan declares expected stage roles and quantity domains.
Finite solver-internal states may temporarily leave accepted physical bounds,
but a physical consumer input and accepted output must satisfy them. Diagnostic
values may be undefined and are never read by this audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from numbers import Real


class StageRole(str, Enum):
    SOLVER_INTERNAL = "solver_internal"
    PHYSICAL_CONSUMER_INPUT = "physical_consumer_input"
    ACCEPTED_STATE = "accepted_state"
    DIAGNOSTIC_ONLY = "diagnostic_only"


@dataclass(frozen=True)
class QuantityDomain:
    quantity_id: str
    unit: str
    lower: float | None
    upper: float | None


@dataclass(frozen=True)
class StageSpec:
    stage_id: str
    role: StageRole
    quantity_ids: tuple[str, ...]
    consumes_from: tuple[str, ...]


@dataclass(frozen=True)
class StagePlan:
    plan_id: str
    domains: tuple[QuantityDomain, ...]
    stages: tuple[StageSpec, ...]


@dataclass(frozen=True)
class StageRecord:
    stage_id: str
    role: StageRole
    values: dict[str, object]
    consumed_from: tuple[str, ...]


@dataclass(frozen=True)
class StageAudit:
    checked_ids: tuple[str, ...]
    internal_outside_accepted_domain: tuple[tuple[str, str], ...]


def _domain_map(plan: StagePlan) -> dict[str, QuantityDomain]:
    if not isinstance(plan.plan_id, str) or not plan.plan_id or not plan.domains or not plan.stages:
        raise ValueError("declare a nonempty independent stage plan")
    domains: dict[str, QuantityDomain] = {}
    for domain in plan.domains:
        if (not isinstance(domain.quantity_id, str) or not domain.quantity_id
                or not isinstance(domain.unit, str) or not domain.unit
                or domain.quantity_id in domains):
            raise ValueError("quantity IDs/units must be nonempty and unique")
        for value in (domain.lower, domain.upper):
            if (value is not None and (isinstance(value, bool)
                                      or not isinstance(value, Real)
                                      or not math.isfinite(value))):
                raise ValueError("accepted-domain bounds must be finite real")
        if (domain.lower is not None and domain.upper is not None
                and domain.lower > domain.upper):
            raise ValueError("accepted-domain bounds are reversed")
        domains[domain.quantity_id] = domain
    return domains


def validate_stages(plan: StagePlan, records: tuple[StageRecord, ...]) -> StageAudit:
    """Audit the declared event sequence without changing any recorded value."""
    domains = _domain_map(plan)
    if not isinstance(records, tuple) or len(records) != len(plan.stages):
        raise ValueError("missing or unexpected stage event")
    seen: dict[str, StageRole] = {}
    outside = []
    for spec, record in zip(plan.stages, records):
        if (not isinstance(spec.role, StageRole) or not isinstance(record.role, StageRole)
                or not isinstance(spec.stage_id, str) or not spec.stage_id
                or spec.stage_id in seen
                or record.stage_id != spec.stage_id or record.role is not spec.role
                or not isinstance(spec.quantity_ids, tuple)
                or not spec.quantity_ids or len(set(spec.quantity_ids)) != len(spec.quantity_ids)
                or set(spec.quantity_ids) - set(domains)
                or not isinstance(spec.consumes_from, tuple)
                or not isinstance(record.consumed_from, tuple)
                or record.consumed_from != spec.consumes_from
                or any(src not in seen for src in spec.consumes_from)):
            raise ValueError("stage ID, role, domain or predecessor differs from plan")
        if (spec.role is not StageRole.DIAGNOSTIC_ONLY
                and any(seen[src] is StageRole.DIAGNOSTIC_ONLY
                        for src in spec.consumes_from)):
            raise ValueError("diagnostic-only output cannot feed physical execution")
        if not isinstance(record.values, dict) or set(record.values) != set(spec.quantity_ids):
            raise ValueError("stage quantity set differs from independent plan")
        if spec.role is not StageRole.DIAGNOSTIC_ONLY:
            for name in spec.quantity_ids:
                value = record.values[name]
                if (isinstance(value, bool) or not isinstance(value, Real)
                        or not math.isfinite(value)):
                    raise ValueError(f"{spec.stage_id}.{name}: finite real value required")
                domain = domains[name]
                out_of_bounds = ((domain.lower is not None and value < domain.lower)
                                 or (domain.upper is not None and value > domain.upper))
                if out_of_bounds:
                    if spec.role is StageRole.SOLVER_INTERNAL:
                        outside.append((spec.stage_id, name))
                    else:
                        raise ValueError(
                            f"{spec.stage_id}.{name}: physical consumer/accepted state inadmissible"
                        )
        seen[spec.stage_id] = spec.role
    return StageAudit(tuple(seen), tuple(outside))
