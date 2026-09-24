"""Small experiment contracts; no production scheduler or default is changed."""

from dataclasses import dataclass
import math

import torch


@dataclass(frozen=True)
class VelocitySample:
    generation: tuple
    mass: torch.Tensor  # same length unit/s as dz; SI probes use m/s
    number: torch.Tensor  # same length unit/s as dz; SI probes use m/s


@dataclass(frozen=True)
class RateSample:
    generation: tuple
    mass: torch.Tensor  # 1/s
    number: torch.Tensor  # 1/s


def check_geometry(dz):
    """Value-only preflight, outside the differentiated calculation."""
    if dz.ndim != 2 or not bool(torch.isfinite(dz).all() and (dz > 0).all()):
        raise ValueError("positive finite [column, layer] thickness required")


def normalize(sample, dz):
    """Differentiable division on preflighted geometry; rates cannot be re-normalized."""
    if not isinstance(sample, VelocitySample):
        raise TypeError("normalization requires raw velocity, not a rate packet")
    if sample.mass.shape != dz.shape or sample.number.shape != dz.shape:
        raise ValueError("velocity/geometry shape mismatch")
    return RateSample(sample.generation, sample.mass / dz, sample.number / dz)


def consume(sample, expected_generation):
    if not isinstance(sample, RateSample):
        raise TypeError("consumer requires normalized rates")
    if sample.generation != expected_generation:
        raise ValueError("stale velocity generation")
    return sample.mass, sample.number


def select_msteps(rate, dt):
    """Value-only oracle selection policy (runtime.py); not adaptive reselection."""
    if not isinstance(rate, RateSample) or not math.isfinite(dt) or dt <= 0:
        raise ValueError("positive dt and normalized selection packet required")
    maximum = torch.maximum(rate.mass, rate.number)
    if not bool(
        torch.isfinite(rate.mass).all()
        and torch.isfinite(rate.number).all()
        and (rate.mass >= 0).all()
        and (rate.number >= 0).all()
    ):
        raise ValueError("finite nonnegative rates required")
    return torch.clamp(torch.floor(maximum.amax(dim=1) * dt + 1), 1, 100).to(
        torch.int64
    )


def schedule(msteps):
    """Expected consumers from an external per-cycle/per-column plan, never logs."""
    if not msteps or not msteps[0] or any(len(c) != len(msteps[0]) for c in msteps):
        raise ValueError("nonempty rectangular schedule required")
    if any(type(m) is not int or m < 1 or m > 100 for c in msteps for m in c):
        raise ValueError("invalid scheduled substep count")
    return frozenset(
        (cycle, n, column)
        for cycle, counts in enumerate(msteps, 1)
        for column, m in enumerate(counts)
        for n in range(1, m + 1)
    )


def generation_for(cycle, n):
    return (cycle, "ice_velocity", n)


def audit_events(events, expected):
    """Caller retains independent expected schedule; record-side declarations are unused."""
    if not expected:
        raise ValueError("independent nonempty schedule required")
    keys = [(e["cycle"], e["n"], e["column"]) for e in events]
    if len(set(keys)) != len(keys) or set(keys) != set(expected):
        raise ValueError("missing, duplicate or unexpected consumer event")
    planned_counts = {}
    for cycle, n, column in expected:
        planned_counts[cycle, column] = max(planned_counts.get((cycle, column), 0), n)
    for e in events:
        planned = planned_counts[e["cycle"], e["column"]]
        if e["selected_mstep"] != planned or e["consumed_mstep"] != planned:
            raise ValueError("selected/consumed substep count mismatch")
        trusted_generation = generation_for(e["cycle"], e["n"])
        if (
            tuple(e["producer_generation"]) != trusted_generation
            or tuple(e["expected_generation"]) != trusted_generation
        ):
            raise ValueError("consumer uses stale generation")
    return len(keys)
